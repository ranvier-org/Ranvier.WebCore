#include "config.h"
#include "RanvierWebCoreAbi.h"
#include <wtf/RunLoop.h>
#include <wtf/Seconds.h>
#include <wtf/text/ASCIILiteral.h>
#include <atomic>

using namespace WTF;
using namespace WTF::StringLiterals;

namespace {
std::atomic<unsigned long long> totalCallbacks { 0 };
std::atomic<int> liveTimers { 0 };
struct TimerProbe {
    Ref<RunLoop> owner;
    RunLoop::Timer timer;
    int callbacks { 0 };
    int offOwnerCallbacks { 0 };
    double secondsInsideCallback { -1 };
    int nestedPumpStatus { -999 };
    std::atomic<bool> cancelOnFirst { false };
    std::atomic<bool> rearmOnFirst { false };
    std::atomic<bool> nestedOnFirst { false };
    std::atomic<bool> destroyOnFirst { false };

    TimerProbe()
        : owner(RunLoop::currentSingleton())
        , timer(owner.copyRef(), "mac211-test-timer"_s, [this] {
            ++callbacks;
            ++totalCallbacks;
            secondsInsideCallback = timer.secondsUntilFire().seconds();
            if (!owner->isCurrent())
                ++offOwnerCallbacks;
            if (callbacks == 1 && destroyOnFirst) {
                delete this;
                return;
            }
            if (callbacks == 1 && nestedOnFirst)
                nestedPumpStatus = rv_run_loop_cycle(0);
            if (callbacks == 1 && cancelOnFirst)
                timer.stop();
            else if (callbacks == 1 && rearmOnFirst)
                timer.startOneShot(Seconds::fromMilliseconds(5));
        })
    {
        ++liveTimers;
    }
    ~TimerProbe() { --liveTimers; }
};
}

#define PROBE_EXPORT extern "C" __attribute__((visibility("default")))

PROBE_EXPORT unsigned long long rv_test_wtf_timer_total_callbacks()
{
    return totalCallbacks.load();
}

PROBE_EXPORT void* rv_test_wtf_timer_create()
{
    if (!RunLoop::isMain())
        return nullptr;
    return new TimerProbe;
}

// Owner destruction or cancellation must not race an arm request.
PROBE_EXPORT int rv_test_wtf_timer_arm(void* handle, double milliseconds, int repeat, int action)
{
    if (!handle || milliseconds < 0 || (repeat && milliseconds == 0) || action < 0 || action > 4)
        return -1;
    auto& probe = *static_cast<TimerProbe*>(handle);
    probe.cancelOnFirst = action == 1;
    probe.rearmOnFirst = action == 2;
    probe.nestedOnFirst = action == 3;
    probe.destroyOnFirst = action == 4;
    auto delay = Seconds::fromMilliseconds(milliseconds);
    if (repeat)
        probe.timer.startRepeating(delay);
    else
        probe.timer.startOneShot(delay);
    return 0;
}

PROBE_EXPORT int rv_test_wtf_timer_state(void* handle, int* callbacks, int* active, int* offOwnerCallbacks)
{
    if (!handle || !callbacks || !active || !offOwnerCallbacks)
        return -1;
    auto& probe = *static_cast<TimerProbe*>(handle);
    if (!probe.owner->isCurrent())
        return -2;
    *callbacks = probe.callbacks;
    *active = probe.timer.isActive();
    *offOwnerCallbacks = probe.offOwnerCallbacks;
    return 0;
}

PROBE_EXPORT int rv_test_wtf_timer_cancel(void* handle)
{
    if (!handle)
        return -1;
    auto& probe = *static_cast<TimerProbe*>(handle);
    if (!probe.owner->isCurrent())
        return -2;
    probe.timer.stop();
    return 0;
}

PROBE_EXPORT int rv_test_wtf_timer_destroy(void* handle)
{
    if (!handle)
        return -1;
    auto* probe = static_cast<TimerProbe*>(handle);
    if (!probe->owner->isCurrent())
        return -2;
    delete probe;
    return 0;
}

PROBE_EXPORT int rv_test_wtf_due_dispatch()
{
    if (!RunLoop::isMain())
        return -2;
    int status = rv_run_loop_cycle(0);
    return status < 0 ? status : 0;
}

PROBE_EXPORT int rv_test_wtf_timer_live() { return liveTimers.load(); }

PROBE_EXPORT int rv_test_wtf_timer_seconds(void* handle, double* inside, double* outside)
{
    if (!handle || !inside || !outside)
        return -1;
    auto& probe = *static_cast<TimerProbe*>(handle);
    if (!probe.owner->isCurrent())
        return -2;
    *inside = probe.secondsInsideCallback;
    *outside = probe.timer.secondsUntilFire().seconds();
    return 0;
}

PROBE_EXPORT int rv_test_wtf_timer_nested_status(void* handle)
{
    if (!handle)
        return -1;
    auto& probe = *static_cast<TimerProbe*>(handle);
    if (!probe.owner->isCurrent())
        return -2;
    return probe.nestedPumpStatus;
}
