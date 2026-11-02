# Mutation observation

`mutation-observation` supplies disconnected native observers. Create one with
`rv_host_create_mutation_observer`, then call `rv_mutation_observer_observe` for each target.
Valid accessible nodes from another document and adopted nodes follow WebCore's observation rules.
Creating an observer does not change the default signal/effect implementation.

Options preserve omitted versus false flags and omitted versus empty attribute filters. WebCore
performs observation defaulting and reports invalid combinations as `TypeError`. The host copies
filter strings during Observe. The callback and context-release function are required; a rejected
factory call leaves context ownership with the caller. Successful creation owns the context until
closure and the final in-flight callback return.

Callbacks run through the ordinary WebCore event loop, pumped with `rv_run_loop_cycle`. The callback
receives its observer identity and a borrowed record batch. Retain that batch inside the callback
to keep it. `TakeRecords` drains immediately into an owned batch, including an empty batch;
Disconnect discards queued records and permits later observation. Observer Release closes and
consumes its token. A provider must clear its stored token before calling Release, because the
context-release callback may reenter disposal. Raw C callers still release their
closed external observer token; automatic close ends the engine/context lifetime, not caller ownership.

Record views, strings, node arrays and node pointers borrow storage from their batch. Strings carry
UTF-16 code units: length -1 is null and 0 is empty. Retain nodes before wrapping them or releasing
the batch. Batches own complete engine records and pending targets independently of their observer.
Node wrappers retain the existing session-disposal rules. A retained record does not keep its
observer callback/context alive.

Host destruction and HTML/SVG document replacement close observers created in the old document,
using a protected state snapshot. An in-flight callback keeps its local lease until return. The
View provider uses its context-release callback to notify the shared `onClosed` hook, which clears
the shared callback, abort registration and provider handle. Callback exceptions must be caught
and reported by the provider; they must not cross the native callback boundary.

While a host is invalidating its document, observer creation and nested HTML/SVG replacement return
`RV_ERR_DETACHED`. Reentering destruction during destruction has no effect. Destruction requested
during replacement is deferred until the transaction can destroy the host safely; the outer load
returns `RV_ERR_DETACHED` after honoring that request. A normal replacement remains usable afterward.

`RanvierMutationGlue.cpp` compiles into WebCore through `WebCore_EMBEDDER_SOURCES`; the host exposes
thin forwards and lifecycle hooks. The DOM generator and vendor WebKit series are unchanged. The
canonical P/Invoke generator preserves six structs, two delegates and nine functions. Observer and
batch tokens use provider ownership rather than generated object-kind IDs.

The lane uses its inherited ABI/package values until coordinator integration assigns a new cohort.
This source addition does not change the frozen preview.3/preview.4 packages or claim production
runtime qualification. The source tests compile C11/C++20 sizes and every field offset for supported
64-bit layouts. The public runtime probe exercises delivery, draining, options, foreign documents,
adoption, reentrancy, host replacement/destruction, context ownership and output-size/thread errors.
It is selected by the catalogue, extracted-package checks and an explicit native workflow step.
The probe isolates teardown modes in separate processes so a crash cannot hide later controls.

```shell
python -I tests/test_mutation_contract.py
python -I tests/test_mutation_routing.py
python -I tests/abi/generate_native.py check
python -I -X utf8 tests/abi/mutation_observation.py --native-directory <native-directory>
```
