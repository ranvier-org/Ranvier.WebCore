# Native host tracing

Host tracing is an optional, per-host diagnostic buffer. Check `rv_abi_has("host-tracing")`, then call `rv_host_trace_enable(host, 1)` on the host thread. Tracing is disabled by default. Calling `rv_host_trace_drain` copies and removes the oldest available records into caller-owned storage; a capacity of zero queries and clears the dropped count without removing records. Disable tracing with `rv_host_trace_enable(host, 0)` when finished.

The buffer holds at most 256 records. New records are dropped when it is full, and each drain reports and resets the number dropped since the preceding drain. Enable and disable transitions discard queued records and reset the dropped count. A newly enabled session has its own sequence numbers. All calls follow the host's normal thread and lifetime rules.

Each `RvHostTraceEvent` identifies its phase and `RV_HOST_TRACE_SOURCE_HOST`, a host observation rather than an engine-level attribution. `start_ns` and `duration_ns` use a monotonic clock in nanoseconds with an unspecified epoch. Sequence numbers order records as they are completed and inserted; intervals may overlap, so their start times need not be ordered by sequence.

- `UPDATE_REQUESTED` records a host update request, including an invalidation. It does not identify the reason for invalidation.
- `STYLE_LAYOUT` measures combined preparation explicitly invoked by the host before painting. It does not distinguish engine style from layout or include all work that WebCore may perform internally.
- `PAINT` measures the host's CPU paint or GPU compositing call, not subsequent presentation or readback.
- `RENDERING_UPDATE` measures the host's WebCore page update call. It can include nested engine work.

These events are intended to help correlate host activity, not to emulate the browser Performance API or claim browser timeline parity. Buffering is bounded and does not invoke consumer callbacks. Tracing adds clock and buffer work when enabled; measure its effect on the workload being investigated.
