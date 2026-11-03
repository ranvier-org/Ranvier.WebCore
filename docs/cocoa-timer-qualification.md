# Cocoa timer delivery

Patch 0069 dispatches already-due registered WTF timers after the host's bounded,
nonblocking CF-source passes. It snapshots at most the earliest 64 deadlines,
retains each CF identity, and revalidates registration and due time before calling
outside the registry lock. The existing WebCore shared-timer fallback remains.
The bound applies to this explicit snapshot; CF may deliver other timer callbacks
during the same public pump.

The private Mac26 experiment and its consumer-only replay passed seven modes on
source `0c4fa528608b0d0f8f214406e4821152b0e7248a`. They syntax-compiled the complete
patched CF source, then used selected-method overrides with immutable producer803
libraries. Those results establish prototype behavior, not a rebuilt Host/JSC.

For the coherent producer gate, preserve the producer's exact dylib SHA256 map as
`runtime-hashes.json`, populate its normal generated headers, and run:

```sh
python -I tests/abi/build_cocoa_timer_contract.py \
  --build "$RANVIER_WORK/build-slim" --webkit-source "$RANVIER_WORK/src" \
  --runtime "$NATIVE_DIR" --runtime-hashes runtime-hashes.json \
  --probe-source tests/abi/cocoa_timer_contract.cpp --output timer-helper
python -I tests/abi/cocoa_timer_contract.py --native-directory "$NATIVE_DIR" \
  --helper timer-helper/libRanvierCocoaTimerContract.dylib --output timer-contract.json
```

This helper creates genuine WTF timers and calls only the public host pump for
outer and nested dispatch. It does not override engine methods. The fixture runs
each mode in a separate process and preserves child reports and logs. Acceptance
requires zero already-due misses, future deadlines, repeat/cancel/rearm,
self-destruction, nested pumping, 72-timer fairness, wrong-owner rejection and
cross-thread arming with callbacks on the owner. Retain all input and runtime
hashes before and after. Actual coherent Mac runtime qualification remains open
until this gate and the native catalogue pass on the rebuilt source.
