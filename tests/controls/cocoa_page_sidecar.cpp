#include "config.h"
#include "RanvierWebCoreAbi.h"
#include <WebCore/Document.h>
#include <WebCore/DocumentPage.h>
#include <WebCore/Node.h>
#include <WebCore/Page.h>
#include <WebCore/Settings.h>

using namespace WebCore;

namespace {
// Test fixtures call only with a live host between owner-turn operations, before teardown.
template<typename Action> int32_t withPage(RvHost* host, Action&& action)
{
    if (!host)
        return RV_ERR_NULL_ARGUMENT;
    auto* handle = rv_host_document(host);
    if (!handle)
        return RV_ERR_WRONG_THREAD;
    struct Release {
        RvNode* node;
        ~Release() { rv_node_release(node); }
    } release { handle };
    auto& node = *reinterpret_cast<Node*>(handle);
    if (!node.isDocumentNode())
        return RV_ERR_WRONG_INTERFACE;
    auto& document = downcast<Document>(node);
    auto* page = document.page();
    if (!page)
        return RV_ERR_DETACHED;
    return action(*page);
}
}

#define CONTROL_EXPORT extern "C" __attribute__((visibility("default")))

CONTROL_EXPORT int32_t project2_progress_form_control_profile(RvHost* host, int32_t mode, int32_t* current)
{
    if (!current)
        return RV_ERR_NULL_ARGUMENT;
    *current = -1;
    if (mode < -1 || mode > 1)
        return RV_ERR_UNSUPPORTED;
#if PLATFORM(MAC) && ENABLE(FORM_CONTROL_REFRESH)
    return withPage(host, [&](Page& page) -> int32_t {
        auto& settings = page.settings();
        if (mode >= 0) {
            settings.setFormControlRefreshEnabled(mode != 0);
            page.updateStyleAfterChangeInEnvironment();
        }
        *current = settings.formControlRefreshEnabled() ? 1 : 0;
        return RV_OK;
    });
#else
    return RV_ERR_UNSUPPORTED;
#endif
}

CONTROL_EXPORT int32_t project2_progress_system_motion(RvHost* host)
{
#if PLATFORM(MAC)
    return withPage(host, [](Page& page) -> int32_t {
        page.settings().setForcedPrefersReducedMotionAccessibilityValue(ForcedAccessibilityValue::System);
        page.accessibilitySettingsDidChange();
        return RV_OK;
    });
#else
    return RV_ERR_UNSUPPORTED;
#endif
}

CONTROL_EXPORT int32_t project2_progress_system_contrast(RvHost* host)
{
#if PLATFORM(MAC)
    return withPage(host, [](Page& page) -> int32_t {
        page.settings().setForcedPrefersContrastAccessibilityValue(ForcedAccessibilityValue::System);
        page.accessibilitySettingsDidChange();
        return RV_OK;
    });
#else
    return RV_ERR_UNSUPPORTED;
#endif
}
