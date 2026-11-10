#if RANVIER_COMPOSITING && (defined(__linux__) || (defined(RANVIER_MAC_GPU_SPIKE) && RANVIER_MAC_GPU_SPIKE))
static int32_t configurePortablePipeline(RvHost* host, void* consumer)
{
    if (!rv_abi_has("gpu-frame-pipeline-v1"))
        return RV_ERR_UNSUPPORTED;
#if defined(__linux__)
    if (eglGetCurrentDisplay() != configuredEGLDisplay || eglGetCurrentContext() != consumer)
        return RV_ERR_UNSUPPORTED;
#endif
    if (!host->framePipeline)
        host->framePipeline = std::make_shared<RvPlatformPipeline>();
    auto& pipeline = *host->framePipeline;
    if (!pipeline.poll())
        return RV_ERR_DEVICE_LOST;
    if (pipeline.consumer && pipeline.consumer != consumer) {
        for (int i = 0; i < RvFramePipeline::capacity; ++i) {
            if (pipeline.state.slots[i].phase == RvFramePipeline::Phase::Ready)
                pipeline.discard(i);
            if (pipeline.state.slots[i].phase != RvFramePipeline::Phase::Free)
                return RV_NOT_READY;
        }
        for (auto& surface : pipeline.surfaces)
            surface.reset();
    }
    pipeline.consumer = consumer;
    return RV_OK;
}

static void discardObsoletePortableFrames(RvHost* host, RvPlatformPipeline& pipeline)
{
    auto size = paintSize(*host);
    for (int i = 0; i < RvFramePipeline::capacity; ++i) {
        if (pipeline.state.slots[i].phase == RvFramePipeline::Phase::Ready
            && (pipeline.generations[i] != pipeline.generation || !pipeline.surfaces[i]->matches(size.width(), size.height())))
            pipeline.discard(i);
    }
}

static int32_t submitPortableFrame(RvHost* host, uint64_t frameId)
{
    auto pipeline = host->framePipeline;
    if (!pipeline || host->compositingMode == RV_COMPOSITING_OFF || !pipeline->state.accepts(frameId))
        return RV_ERR_UNSUPPORTED;
    // External-image legacy transactions promise completed reads on return. They retain that path.
    if (!host->nativeTextures.isEmpty())
        return RV_ERR_UNSUPPORTED;
#if defined(__linux__)
    if (eglGetCurrentDisplay() != configuredEGLDisplay || eglGetCurrentContext() != pipeline->consumer)
        return RV_ERR_UNSUPPORTED;
    RvEGLContextScope returnContext;
#endif
    if (!pipeline->poll())
        return RV_ERR_DEVICE_LOST;
    discardObsoletePortableFrames(host, *pipeline);
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
            view->updateLayoutAndStyleIfNeededRecursive(LayoutOptions::UpdateCompositingLayers);
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
        auto size = paintSize(*host);
        auto& surface = pipeline->surfaces[slot];
        if (surface && !surface->matches(size.width(), size.height()))
            surface.reset();
        bool exhausted = false;
        if (!surface) {
            surface = RvPlatformSurface::create(size.width(), size.height(), [] {
                auto* context = compositingContext();
                return context && context->makeContextCurrent();
            }, true, &exhausted);
        }
        if (!surface)
            return exhausted ? RV_NOT_READY : RV_ERR_UNSUPPORTED;
        if (!surface->beginProducer())
            return RV_ERR_DEVICE_LOST;
        RELEASE_ASSERT(pipeline->state.reserve(frameId) == slot);
        pipeline->generations[slot] = pipeline->generation;
        int32_t painted;
        {
            RvTraceSpan span(*host, RV_HOST_TRACE_PAINT);
            painted = composite(*host, *host->compositor, *view, nullptr, surface->framebuffer());
        }
        {
            RvTraceSpan span(*host, RV_HOST_TRACE_GPU_SUBMIT);
            if (!surface->submitProducer(pipeline->consumer)) {
                pipeline->failed = true;
                return RV_ERR_DEVICE_LOST;
            }
        }
        if (painted != RV_OK) {
            pipeline->failed = true;
            return painted;
        }
        return RV_OK;
    }();
    if (host->updateWanted && !host->destroyAfterDocumentTransaction)
        host->requestFrame();
    if (finishDocumentTransaction(host) != RV_OK)
        return RV_ERR_DETACHED;
    return result;
}

static int32_t acquirePortableFrame(RvHost* host, uint64_t* frameId, RvGpuFrame** frame)
{
    auto pipeline = host->framePipeline;
    if (!pipeline)
        return RV_ERR_UNSUPPORTED;
#if defined(__linux__)
    if (eglGetCurrentDisplay() != configuredEGLDisplay || eglGetCurrentContext() != pipeline->consumer)
        return RV_ERR_UNSUPPORTED;
    RvEGLContextScope returnContext;
#endif
    if (!pipeline->poll())
        return RV_ERR_DEVICE_LOST;
    discardObsoletePortableFrames(host, *pipeline);
    int newest = pipeline->state.newestReady();
    for (int i = 0; i < RvFramePipeline::capacity; ++i) {
        if (i != newest && pipeline->state.slots[i].phase == RvFramePipeline::Phase::Ready)
            pipeline->discard(i);
    }
    if (newest < 0)
        return RV_NOT_READY;
    pipeline->state.lease(newest);
    *frameId = pipeline->state.slots[newest].id;
    auto* result = new RvGpuFrame;
    result->pipeline = pipeline;
    result->slot = newest;
#if defined(__linux__)
    result->surface = pipeline->surfaces[newest];
#endif
    *frame = result;
    return RV_OK;
}
#endif
