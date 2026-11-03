#if defined(RANVIER_MAC_GPU_SPIKE) && RANVIER_MAC_GPU_SPIKE
struct RvMacSpikeFrame {
    std::unique_ptr<RvMacSpikeSurface> surface;
};

int32_t rv_mac_spike_bind_iosurface(RvHost* host, RvNode* target, void* surface, int32_t flipY)
{
    if (!host || !target)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    if (!liveHosts.contains(host) || host->documentTransaction != RvHost::DocumentTransaction::Idle)
        return RV_ERR_DETACHED;
    if (host->inFrame || (flipY != 0 && flipY != 1))
        return RV_ERR_UNSUPPORTED;
    auto* element = dynamicDowncast<Element>(*node(target));
    if (!element || &element->document() != &host->document() || !element->isConnected())
        return RV_ERR_WRONG_HOST;
    std::unique_ptr<RvNativeMacTextureInput> input;
    if (surface) {
        input = RvNativeMacTextureInput::create(*element, surface, flipY, [] {
            auto* context = compositingContext();
            return context && context->makeContextCurrent();
        });
        if (!input)
            return RV_ERR_UNSUPPORTED;
    }
    host->nativeTextures.removeAllMatching([&](auto& prior) { return prior->element.get() == element; });
    if (input)
        host->nativeTextures.append(WTF::move(input));
    host->requestFrame();
    return RV_OK;
}

const char* rv_mac_spike_identity()
{
    return onOwningThread() ? rvMacSpikeIdentity() : nullptr;
}

int32_t rv_mac_spike_acquire_frame(RvHost* host, RvMacSpikeFrame** frame)
{
    if (!frame)
        return RV_ERR_NULL_ARGUMENT;
    *frame = nullptr;
    if (!host)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    if (!liveHosts.contains(host))
        return RV_ERR_DETACHED;
    if (host->documentTransaction != RvHost::DocumentTransaction::Idle
        || host->inFrame || host->compositingMode == RV_COMPOSITING_OFF)
        return RV_ERR_UNSUPPORTED;
    host->documentTransaction = RvHost::DocumentTransaction::Rendering;
    auto result = [&]() -> int32_t {
        SetForScope inFrame(host->inFrame, true);
        host->frameRequested = false;
        host->document().updateLayoutIgnorePendingStylesheets();
        RefPtr view = host->frame().view();
        if (!view)
            return RV_ERR_PAINT_FAILED;
        view->updateLayoutAndStyleIfNeededRecursive(LayoutOptions::UpdateCompositingLayers);
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
        auto pixelSize = paintSize(*host);
        auto surface = RvMacSpikeSurface::create(pixelSize.width(), pixelSize.height(), [] {
            auto* context = compositingContext();
            return context && context->makeContextCurrent();
        });
        if (!surface)
            return RV_ERR_UNSUPPORTED;
        auto paintResult = composite(*host, *host->compositor, *view, nullptr, surface->framebuffer());
        if (paintResult != RV_OK || !surface->finishProducer())
            return RV_ERR_PAINT_FAILED;
        host->dirty = { };
        ++host->macSpikeGpuFrames;
        *frame = new RvMacSpikeFrame { WTF::move(surface) };
        return RV_OK;
    }();
    if (host->updateWanted && !host->destroyAfterDocumentTransaction)
        host->requestFrame();
    if (host->destroyAfterDocumentTransaction && *frame)
        delete std::exchange(*frame, nullptr);
    if (finishDocumentTransaction(host) != RV_OK)
        return RV_ERR_DETACHED;
    return result;
}

int32_t rv_mac_spike_frame_info(RvMacSpikeFrame* frame, void** surface, int32_t* width, int32_t* height)
{
    if (!frame || !surface || !width || !height)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    *surface = frame->surface->surface();
    *width = frame->surface->width();
    *height = frame->surface->height();
    return RV_OK;
}

int32_t rv_mac_spike_frame_release(RvMacSpikeFrame* frame)
{
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    delete frame;
    return RV_OK;
}

int32_t rv_mac_spike_counters(RvHost* host, uint64_t* gpu, uint64_t* readback, uint64_t* basePaints)
{
    if (!host || !gpu || !readback || !basePaints)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    if (!liveHosts.contains(host))
        return RV_ERR_DETACHED;
    *gpu = host->macSpikeGpuFrames;
    *readback = host->macSpikeReadbackFrames;
    *basePaints = host->compositor ? host->compositor->macSpikeBasePaints : 0;
    return RV_OK;
}
#endif
