#pragma once

#include "RanvierWebCoreAbi.h"
#include <WebCore/PlatformExportMacros.h>

// Contract:
// - ranvier_wake_lock_request runs WakeLock.request's document checks for the document, then decide(context) when
//   they pass, and on a grant adds a new sentinel to the document's wake lock manager. Failures record the
//   exception for rv_last_exception and return RV_ERR_DOM_EXCEPTION.
// - ranvier_wake_lock_release, ranvier_wake_lock_state: rv_wake_lock_release and rv_wake_lock_state after the
//   thread check, with their contracts.
// - ranvier_wake_lock_release_all releases the document's screen locks, each with its "release" event.
// - ranvier_sleep_disabler_install installs the process's SleepDisablerClient; idempotent. The host calls it before
//   any document exists, so every disabler starts and ends under the client.
// - ranvier_sleep_disabler_set_callback forwards later disablers to callback; NULL stops forwarding.
extern "C" {
WEBCORE_EXPORT int32_t ranvier_wake_lock_request(RvNode* document, int32_t type, int32_t (*decide)(void*), void* context, RvEventTarget** sentinel);
WEBCORE_EXPORT int32_t ranvier_wake_lock_release(RvEventTarget*);
WEBCORE_EXPORT int32_t ranvier_wake_lock_state(RvEventTarget*, int32_t* released, int32_t* type);
WEBCORE_EXPORT int32_t ranvier_wake_lock_release_all(RvNode* document);
WEBCORE_EXPORT void ranvier_sleep_disabler_install(void);
WEBCORE_EXPORT void ranvier_sleep_disabler_set_callback(RvSleepDisablerCallback, void* context);
}
