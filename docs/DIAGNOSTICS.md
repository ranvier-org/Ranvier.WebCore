# Diagnostics: page inspection, host errors, host tracing

Three opt-in diagnostic groups, each detected with `rv_abi_has`: `diagnostics` (page inspection), `host-errors` and `host-tracing`. All are disabled by default.

## Page inspection (ABI 50, cascade ABI 54)

The host inspects a page's document natively: no developer-tools frontend, inspector protocol or script evaluation.
`rv_abi_has("diagnostics")` reports the group; `host/RanvierWebCoreAbi.h` holds the contract.

### Availability

| Facility (category 4) | Implemented | Enabled | Available |
| --- | --- | --- | --- |
| `diagnostics` | 1 | the host's opt-in | unknown |
| `inspector-frontend` | 0 | unknown | 0 |
| `cascade-diagnostics` (v54) | 1 | the host's opt-in | unknown |
| `inspector`, `jsc-inspector` | 0 on slim (`USE_INSPECTOR_STUB`, `USE_JSC_INSPECTOR_STUB`) | | |
| `remote-inspector` | 0 on slim (`ENABLE_REMOTE_INSPECTOR=OFF`) | | |

The slim flavor builds WebCore's and JavaScriptCore's inspectors as stubs (patches 0008 and 0009) and packages no
WebInspectorUI resources. The diagnostics glue (`host/RanvierInspectGlue.cpp`) calls no inspector controller,
instrumentation or agent; the candidate builder checks the glue object's undefined symbols for them.

### Opt-in and snapshots

- `rv_host_set_diagnostics(host, 1)` enables the `rv_host_inspect_*` calls. Until then they return
  `RV_ERR_UNSUPPORTED` before reading the node or the document.
- `RvDiagnostic` snapshots copy UTF-8 text and numbers and hold no engine object. They stay readable after the host
  disables diagnostics or is destroyed, read on any thread, and are freed by `rv_diagnostic_release`.
  `rv_diagnostic_live_count` counts unreleased snapshots.

### Reads

- Render tree: the engine's `externalRepresentation` of the main frame (renderers, text runs and RenderLayers), or an
  element's renderer subtree. `RV_RENDER_TREE_*` flags are this ABI's own; addresses and printing mode are excluded.
  The text is engine-specific: probes assert its structure (nesting, a box per visible element, none for
  display:none, positions consistent with the box model), never equality with another engine.
- Matched rules: the style rule collector's matched rules in cascade order (user agent, user, author; each by cascade
  layer, specificity and position), then the inline style. Each entry carries the origin, the selector list, the most
  specific matching selector, its specificity (`:where()` adds (0, 0, 0), `:is()` its most specific argument), the
  selector counts and the engine-serialised declarations.
- Cascade (v54, C25): `rv_host_inspect_cascade` lists the declarations of a longhand or custom property in the
  element's cascade input order (user agent, user, author with presentational hints first and the style attribute
  after the element's rules), with the property's logical counterpart under the element's writing mode. Each entry
  carries origin, specificity, `!important`, layer order and dotted name, the enclosing `@media`, `@supports` and
  `@container` conditions, sheet, rule and declaration indices, the shorthand it expanded from and a `var()` flag.
  `:host()` and `::slotted()` rules from a shadow tree precede the element's tree's rules and `::part()` rules follow
  the style attribute; their sheet, rule and layer fields count in the tree scope defining the rule.
  `RV_CASCADE_WINNER` marks the declaration `Style::PropertyCascade` selects; it is never derived from the computed
  value. With no winner on an inherited property, or a winning `inherit` (or `unset` on an inherited property), entries
  continue with the composed-tree parent at the next `RV_CASCADE_DEPTH`. The query reads the current DOM and rule
  sets, applying only a pending style sheet change, and updates no element style or layout. Declared limits: a winning
  `revert` or `revert-layer` is reported as that keyword; `:visited`, `@starting-style` and animations are absent; the
  value is the declared value, and `var()` resolution is `rv_element_computed_style`'s; a `::slotted()` rule's
  specificity is the engine's, its argument's alone (css-scoping-1 adds the pseudo-element).
- Box model: content, padding, border and margin boxes in `getBoundingClientRect` space. The border box equals
  `rv_element_rect`; untransformed values are LayoutUnit multiples of 1/64 px.

### Browser equivalents

Only the box model has one: `getBoundingClientRect` plus the computed border, padding and margin widths. The Chromium
oracle `tests/fixtures/inspector-diagnostics-oracle.json` records it unscrolled, scrolled and at page scale 2. The
render tree, matched rules, cascade provenance and a developer-tools frontend have no web API; managed browser
providers report them `Unsupported`. The C25 Chromium oracle `tests/fixtures/cascade-diagnostics-oracle.json` records
only computed values, each compared with the shared fixture `tests/fixtures/cascade-diagnostics.json`.

## Host error records

Use `rv_abi_has("host-errors")` to detect the optional host error record API. Records are disabled by default. After `rv_host_error_enable(host, 1)`, a failed native presentation acquisition records the operation, D3D11 or EGL source, and the same status returned by the call. On D3D11, `native_code` is the consumer device's `GetDeviceRemovedReason` HRESULT; zero means no removal reason was reported. EGL records currently use zero for the native code, so a record alone does not assert context loss. Argument, thread and preflight failures are reported by the direct return value.

Each host retains only the latest record. `rv_host_error_take` copies it into caller-owned storage and clears it; `present` says whether a record was available. A later failure can overwrite an unread record. Changing the enabled state clears it, and host destruction releases it with the host. Calls follow the host's owning-thread and lifetime rules. No callbacks are made by this facility.

Existing operation-specific error paths remain authoritative. For example, image decode completion distinguishes decode failure, load failure, cancellation and invalidation, while DOM exceptions use the existing status and `rv_last_exception`. An expected cancellation does not create a presentation error record. Applications can route these results through their existing exception and logging providers.

## Host tracing

Host tracing is an optional, per-host diagnostic buffer. Check `rv_abi_has("host-tracing")`, then call `rv_host_trace_enable(host, 1)` on the host thread. Tracing is disabled by default. Calling `rv_host_trace_drain` copies and removes the oldest available records into caller-owned storage; a capacity of zero queries and clears the dropped count without removing records. Disable tracing with `rv_host_trace_enable(host, 0)` when finished.

The buffer holds at most 256 records. New records are dropped when it is full, and each drain reports and resets the number dropped since the preceding drain. Enable and disable transitions discard queued records and reset the dropped count. A newly enabled session has its own sequence numbers. All calls follow the host's normal thread and lifetime rules.

Each `RvHostTraceEvent` identifies its phase and `RV_HOST_TRACE_SOURCE_HOST`, a host observation rather than an engine-level attribution. `start_ns` and `duration_ns` use a monotonic clock in nanoseconds with an unspecified epoch. Sequence numbers order records as they are completed and inserted; intervals may overlap, so their start times need not be ordered by sequence.

- `UPDATE_REQUESTED` records a host update request, including an invalidation. It does not identify the reason for invalidation.
- `STYLE_LAYOUT` measures combined preparation explicitly invoked by the host before painting. It does not distinguish engine style from layout or include all work that WebCore may perform internally.
- `PAINT` measures the host's CPU paint or GPU compositing call, not subsequent presentation or readback.
- `RENDERING_UPDATE` measures the host's WebCore page update call. It can include nested engine work.

These events are intended to help correlate host activity, not to emulate the browser Performance API or claim browser timeline parity. Buffering is bounded and does not invoke consumer callbacks. Tracing adds clock and buffer work when enabled; measure its effect on the workload being investigated.
