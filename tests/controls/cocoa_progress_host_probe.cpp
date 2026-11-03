// Compile this test-only Host replacement with its matching source and generated configuration.
#include "RanvierWebCoreAbi.cpp"

extern "C" __attribute__((visibility("default")))
int32_t project2_progress_form_control_profile(RvHost* host, int32_t mode, int32_t* current)
{
    if (current)
        *current = -1;
    if (!host || !current)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    if (!liveHosts.contains(host) || host->documentTransaction != RvHost::DocumentTransaction::Idle
        || host->inFrame || host->editingDepth)
        return RV_ERR_DETACHED;
    if (mode < -1 || mode > 1)
        return RV_ERR_UNSUPPORTED;
#if PLATFORM(MAC) && ENABLE(FORM_CONTROL_REFRESH)
    auto& page = host->page.get();
    auto& settings = page.settings();
    if (mode >= 0) {
        settings.setFormControlRefreshEnabled(mode != 0);
        page.updateStyleAfterChangeInEnvironment();
    }
    *current = settings.formControlRefreshEnabled() ? 1 : 0;
    return RV_OK;
#else
    return RV_ERR_UNSUPPORTED;
#endif
}

extern "C" __attribute__((visibility("default")))
int32_t project2_progress_system_motion(RvHost* host)
{
    if (!host)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    if (!liveHosts.contains(host) || host->documentTransaction != RvHost::DocumentTransaction::Idle
        || host->inFrame || host->editingDepth)
        return RV_ERR_DETACHED;
#if PLATFORM(MAC)
    auto& page = host->page.get();
    page.settings().setForcedPrefersReducedMotionAccessibilityValue(ForcedAccessibilityValue::System);
    page.accessibilitySettingsDidChange();
    return RV_OK;
#else
    return RV_ERR_UNSUPPORTED;
#endif
}
