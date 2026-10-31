# Pre-existing VM-entry attempts under the host's DisallowVMEntry (found by anim1, not A01 scope)

Runtime: native46-candidate-6 (C:/wk/native-cascade-shadow/artifacts/native46-candidate-6/runtime), which has none of
the A01 code. The probe arms JSC's crash with the exported `JSC::Options::setOption("crashOnDisallowedVMEntry=true")`
(`?setOption@Options@JSC@@SA_NPEBD_N@Z` in JavaScriptCore.dll). Each VM entry that DisallowVMEntry refuses then aborts
the process. Without the option, the refused entry returns `jsUndefined()` (`VM::checkVMEntryPermission`), so nothing
runs and nothing is reported.

## Findings

1. **rv_host_load_html attempts a VM entry on every load**, even for `<p>x</p>`.
   - With the JSC_crashOnDisallowedVMEntry=true environment variable set before the library loads, the first
     rv_host_load_html aborts.
   - When the option is set at runtime after a first load, the second load aborts.
2. **The first document->globalObject() attempts one.** That call creates the window proxy lazily. When the option
   is armed after the page loads:
   - the first generated globalObject constructor aborts (rv_dom_error_event_create, ErrorEvent with
     "globalObject": true);
   - the same call survives if it was made once before arming.
3. These attempts likely leave the JS microtask queue non-empty. Any later JSLock release at depth 0 calls
   `VM::drainMicrotasks` (`JSLock::willReleaseLock`). A non-empty queue opens a VMEntryScope, and the microtask call is
   refused. This is how A01's Element.animate, KeyframeEffect create and setKeyframes come to attempt a VM entry: they
   take the lock to build their keyframes object (qualified in A01, per root decision B).

## Repro (Python, -I)

```
python -I C:/wk/waapi-artifacts/vmentry_create.py <runtime>          # load after env arm: abort at rv_host_load_html
python -I C:/wk/waapi-artifacts/vmentry_setopt.py <runtime> control  # runtime arm, second load: abort
python -I C:/wk/waapi-artifacts/vmentry_global.py <runtime> once     # first ErrorEvent create after arm: abort
python -I C:/wk/waapi-artifacts/vmentry_global.py <runtime> twice    # created before arm: survives
```

Recorded outputs: C:/wk/waapi-artifacts/vmentry-evidence.txt. Open question for root: what each load and the
window-proxy creation try to run (JS microtasks queued by bindings initialization, or an explicit call). Finding the
caller needs a debugger breakpoint on `JSC::VM::checkVMEntryPermission` in the parent runtime.

4. **rv_host_update (the rendering update before rv_host_paint_rgba) also attempts a VM entry** with the crash armed,
   on waapi-candidate-2 in the armed section of tests/abi/web_animations.py, with a paused animation alive. The
   rendering update was therefore left out of the armed scope.
