#include "config.h"
#include "RanvierWakeLockGlue.h"
#include "dom/RanvierDomGlue.h"
#include "ContextDestructionObserverInlines.h"
#include "Document.h"
#include "DocumentPage.h"
#include "EventTarget.h"
#include "EventTargetInlines.h"
#include "EventTargetInterfaces.h"
#include "Exception.h"
#include "Node.h"
#include "PermissionsPolicy.h"
#include "SleepDisablerClient.h"
#include "VisibilityState.h"
#include "WakeLockManager.h"
#include "WakeLockSentinel.h"
#include "WakeLockType.h"
#include <wtf/HashMap.h>
#include <wtf/text/CString.h>
#include <wtf/NeverDestroyed.h>
#include <wtf/TZoneMallocInlines.h>

using namespace WebCore;

namespace {

Document* documentOf(RvNode* handle)
{
    return handle ? dynamicDowncast<Document>(reinterpret_cast<Node*>(handle)) : nullptr;
}

WakeLockSentinel* sentinelOf(RvEventTarget* handle)
{
    auto* target = reinterpret_cast<EventTarget*>(handle);
    if (target->eventTargetInterface() != EventTargetInterfaceType::WakeLockSentinel)
        return nullptr;
    return static_cast<WakeLockSentinel*>(target);
}

int32_t notAllowed(ASCIILiteral message)
{
    return Ranvier::recordException(Exception { ExceptionCode::NotAllowedError, message });
}

struct SleepDisablerForwarding {
    RvSleepDisablerCallback callback { nullptr };
    void* context { nullptr };
    // The display flag and reason of each disabler reported as started; an end is reported only after its start.
    HashMap<uint64_t, std::pair<bool, CString>> reported;
};

SleepDisablerForwarding& forwarding()
{
    static NeverDestroyed<SleepDisablerForwarding> state;
    return state.get();
}

class RanvierSleepDisablerClient final : public SleepDisablerClient {
    WTF_MAKE_TZONE_ALLOCATED_INLINE(RanvierSleepDisablerClient);

    void didCreateSleepDisabler(SleepDisablerIdentifier identifier, const String& reason, bool display, std::optional<PageIdentifier>) final
    {
        auto& state = forwarding();
        if (!state.callback)
            return;
        auto id = identifier.toUInt64();
        auto bytes = reason.utf8();
        state.reported.set(id, std::pair { display, bytes });
        state.callback(state.context, id, display ? 1 : 0, bytes.data(), 1);
    }

    void didDestroySleepDisabler(SleepDisablerIdentifier identifier, std::optional<PageIdentifier>) final
    {
        auto& state = forwarding();
        auto entry = state.reported.takeOptional(identifier.toUInt64());
        if (!entry || !state.callback)
            return;
        state.callback(state.context, identifier.toUInt64(), entry->first ? 1 : 0, entry->second.data(), 0);
    }
};

}

int32_t ranvier_wake_lock_request(RvNode* documentHandle, int32_t type, int32_t (*decide)(void*), void* context, RvEventTarget** sentinel)
{
    RefPtr document = documentOf(documentHandle);
    if (!document || !sentinel)
        return RV_ERR_NULL_ARGUMENT;
    *sentinel = nullptr;
    if (type != RV_WAKE_LOCK_SCREEN)
        return Ranvier::recordException(Exception { ExceptionCode::TypeError, "The provided value is not a valid enum value of type WakeLockType"_s });
    if (!document->isFullyActive() || !document->page())
        return notAllowed("Document is not fully active"_s);
    if (!PermissionsPolicy::isFeatureEnabled(PermissionsPolicy::Feature::ScreenWakeLock, *document, PermissionsPolicy::ShouldReportViolation::No))
        return notAllowed("'screen-wake-lock' is not allowed by Feature-Policy"_s);
    if (document->visibilityState() == VisibilityState::Hidden)
        return notAllowed("Document is hidden"_s);
    if (!decide || decide(context) != 1)
        return notAllowed("Permission was denied"_s);
    // The policy may have changed the document.
    if (!document->isFullyActive() || document->visibilityState() == VisibilityState::Hidden)
        return notAllowed("Document is not fully active"_s);
    Ref lock = WakeLockSentinel::create(*document, WakeLockType::Screen);
    Ref<EventTarget> target = lock.get();
    protect(document->wakeLockManager())->addWakeLock(lock.copyRef(), document->pageID());
    *sentinel = reinterpret_cast<RvEventTarget*>(&target.leakRef());
    return RV_OK;
}

int32_t ranvier_wake_lock_release(RvEventTarget* handle)
{
    if (!handle)
        return RV_ERR_NULL_ARGUMENT;
    RefPtr lock = sentinelOf(handle);
    if (!lock)
        return RV_ERR_WRONG_INTERFACE;
    if (lock->released())
        return RV_OK;
    if (RefPtr document = downcast<Document>(static_cast<ActiveDOMObject&>(*lock).scriptExecutionContext()))
        lock->release(protect(document->wakeLockManager()).get());
    return RV_OK;
}

int32_t ranvier_wake_lock_state(RvEventTarget* handle, int32_t* released, int32_t* type)
{
    if (!handle || !released || !type)
        return RV_ERR_NULL_ARGUMENT;
    RefPtr lock = sentinelOf(handle);
    if (!lock)
        return RV_ERR_WRONG_INTERFACE;
    *released = lock->released() ? 1 : 0;
    *type = RV_WAKE_LOCK_SCREEN;
    return RV_OK;
}

int32_t ranvier_wake_lock_release_all(RvNode* documentHandle)
{
    RefPtr document = documentOf(documentHandle);
    if (!document)
        return RV_ERR_NULL_ARGUMENT;
    protect(document->wakeLockManager())->releaseAllLocks(WakeLockType::Screen);
    return RV_OK;
}

void ranvier_sleep_disabler_install(void)
{
    auto& client = sleepDisablerClient();
    if (!client)
        client = makeUnique<RanvierSleepDisablerClient>();
}

void ranvier_sleep_disabler_set_callback(RvSleepDisablerCallback callback, void* context)
{
    auto& state = forwarding();
    state.callback = callback;
    state.context = context;
    if (!callback)
        state.reported.clear();
}
