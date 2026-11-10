static int32_t validateGpuPipelineHost(RvHost* host)
{
    if (!host)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    if (!liveHosts.contains(host))
        return RV_ERR_DETACHED;
    if (host->inFrame || host->documentTransaction != RvHost::DocumentTransaction::Idle)
        return RV_ERR_UNSUPPORTED;
    return RV_OK;
}

int32_t rv_host_configure_gpu_pipeline(RvHost* host, void* consumerDevice)
{
    auto valid = validateGpuPipelineHost(host);
    if (valid != RV_OK)
        return valid;
    if (!consumerDevice)
        return RV_ERR_NULL_ARGUMENT;
#if defined(_WIN32) && RANVIER_COMPOSITING
    auto* device = static_cast<ID3D11Device*>(consumerDevice);
    if (device->GetDeviceRemovedReason() != S_OK)
        return RV_ERR_DEVICE_LOST;
    if (!host->framePipeline)
        host->framePipeline = std::make_shared<RvD3D11Pipeline>();
    auto& pipeline = *host->framePipeline;
    if (pipeline.device.Get() == device)
        return RV_OK;
    if (pipeline.device) {
        pipeline.poll();
        for (int i = 0; i < RvFramePipeline::capacity; ++i) {
            if (pipeline.state.slots[i].phase == RvFramePipeline::Phase::Ready)
                pipeline.discard(i);
        }
        pipeline.poll();
        for (auto& slot : pipeline.state.slots) {
            if (slot.phase != RvFramePipeline::Phase::Free)
                return RV_NOT_READY;
        }
        for (auto& surface : pipeline.surfaces)
            surface.reset();
    }
    pipeline.device = device;
    return RV_OK;
#else
    return RV_ERR_UNSUPPORTED;
#endif
}

int32_t rv_host_submit_gpu_frame(RvHost* host, uint64_t frameId)
{
    auto valid = validateGpuPipelineHost(host);
    if (valid != RV_OK)
        return valid;
#if defined(_WIN32) && RANVIER_COMPOSITING
    auto pipeline = host->framePipeline;
    if (!pipeline || host->compositingMode == RV_COMPOSITING_OFF || !pipeline->state.accepts(frameId))
        return RV_ERR_UNSUPPORTED;
    if (!pipeline->poll())
        return RV_ERR_DEVICE_LOST;
    auto pixelSize = paintSize(*host);
    for (int i = 0; i < RvFramePipeline::capacity; ++i) {
        if (pipeline->state.slots[i].phase == RvFramePipeline::Phase::Ready
            && (pipeline->generations[i] != pipeline->generation
                || !pipeline->surfaces[i]->matches(pipeline->device.Get(), pixelSize.width(), pixelSize.height())))
            pipeline->discard(i);
    }
    if (!pipeline->poll())
        return RV_ERR_DEVICE_LOST;
    int slot = pipeline->freeSlot();
    if (slot < 0)
        return RV_NOT_READY;
    host->documentTransaction = RvHost::DocumentTransaction::Rendering;
    auto result = [&]() -> int32_t {
        SetForScope inFrame(host->inFrame, true);
        RefPtr<LocalFrameView> view;
        {
            RvTraceSpan span(*host, RV_HOST_TRACE_STYLE_LAYOUT);
            host->document().updateLayoutIgnorePendingStylesheets();
            view = host->frame().view();
            if (!view)
                return RV_ERR_PAINT_FAILED;
            view->updateLayoutAndStyleIfNeededRecursive();
        }
        if (host->destroyAfterDocumentTransaction)
            return RV_ERR_DETACHED;
        if (!view->clipLayer())
            return RV_ERR_UNSUPPORTED;
        if (host->compositor && (host->compositor->size != host->size || host->compositor->scale != host->deviceScale))
            host->compositor = nullptr;
        if (!host->compositor)
            host->compositor = RvCompositor::create(host->size, host->deviceScale);
        if (!host->compositor)
            return RV_ERR_UNSUPPORTED;
        // Layout callbacks can resize; allocate for the resulting viewport, not the preflight size.
        auto size = paintSize(*host);
        auto& surface = pipeline->surfaces[slot];
        if (surface && !surface->matches(pipeline->device.Get(), size.width(), size.height()))
            surface.reset();
        if (!surface) {
            surface = RvD3D11Surface::create(pipeline->device.Get(), size.width(), size.height(), [] {
                auto* context = compositingContext();
                return context && context->makeContextCurrent();
            }, true);
        }
        if (!surface)
            return pipeline->device->GetDeviceRemovedReason() == S_OK ? RV_NOT_READY : RV_ERR_DEVICE_LOST;
        auto ready = surface->tryBeginProducer();
        if (ready != RvGpuReadiness::Ready)
            return ready == RvGpuReadiness::NotReady ? RV_NOT_READY : RV_ERR_DEVICE_LOST;
        int32_t painted;
        {
            RvTraceSpan span(*host, RV_HOST_TRACE_PAINT);
            painted = composite(*host, *host->compositor, *view, nullptr, surface->framebuffer(), true);
        }
        if (painted != RV_OK) {
            surface->cancelProducer();
            return painted;
        }
        {
            RvTraceSpan span(*host, RV_HOST_TRACE_GPU_SUBMIT);
            if (!surface->submitProducer()) {
                surface->cancelProducer();
                surface.reset();
                return RV_ERR_DEVICE_LOST;
            }
        }
        int reserved = pipeline->state.reserve(frameId);
        RELEASE_ASSERT(reserved == slot);
        pipeline->generations[slot] = pipeline->generation;
        return RV_OK;
    }();
    if (host->updateWanted && !host->destroyAfterDocumentTransaction)
        host->requestFrame();
    if (finishDocumentTransaction(host) != RV_OK)
        return RV_ERR_DETACHED;
    return result;
#else
    return RV_ERR_UNSUPPORTED;
#endif
}

int32_t rv_host_try_acquire_completed_gpu_frame(RvHost* host, uint64_t* frameId, RvGpuFrame** frame)
{
    if (!frameId || !frame)
        return RV_ERR_NULL_ARGUMENT;
    *frameId = 0;
    *frame = nullptr;
    auto valid = validateGpuPipelineHost(host);
    if (valid != RV_OK)
        return valid;
#if defined(_WIN32) && RANVIER_COMPOSITING
    auto pipeline = host->framePipeline;
    if (!pipeline)
        return RV_ERR_UNSUPPORTED;
    if (!pipeline->poll())
        return RV_ERR_DEVICE_LOST;
    auto size = paintSize(*host);
    for (int i = 0; i < RvFramePipeline::capacity; ++i) {
        if (pipeline->state.slots[i].phase == RvFramePipeline::Phase::Ready
            && (pipeline->generations[i] != pipeline->generation
                || !pipeline->surfaces[i]->matches(pipeline->device.Get(), size.width(), size.height())))
            pipeline->discard(i);
    }
    int newest = pipeline->state.newestReady();
    for (int i = 0; i < RvFramePipeline::capacity; ++i) {
        if (i != newest && pipeline->state.slots[i].phase == RvFramePipeline::Phase::Ready)
            pipeline->discard(i);
    }
    if (newest < 0)
        return RV_NOT_READY;
    pipeline->state.lease(newest);
    *frameId = pipeline->state.slots[newest].id;
    *frame = new RvGpuFrame { pipeline->surfaces[newest], pipeline, newest };
    return RV_OK;
#else
    return RV_ERR_UNSUPPORTED;
#endif
}
