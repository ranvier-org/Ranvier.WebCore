# Windows UI Automation implementation plan

> For agentic workers: execute inline with the executing-plans skill, in this isolated worktree.

**Goal:** expose the ABI accessibility tree through the actual Windows UI Automation service, including actions, text ranges and safe teardown.

**Architecture:** native COM fragment providers owned by a window attachment. Subclass the HWND for discovery; dispatch all ABI access to its owner thread. No runtime managed COM dependency.

**Tech Stack:** C++20, Windows SDK UIAutomationCore, existing C accessibility ABI.

**Spec:** docs/ACCESSIBILITY.md.

## Constraints

- No ABI version bump; integration owns the batch version.
- Do not modify DOM generation, packaging or CI.
- Every native node reference is released on the host thread before destruction.
- Keep text offsets in UTF-16 and map geometry between CSS viewport and physical screen pixels.

## Review focus

- Remote callers surviving node removal and window destruction receive element unavailable.
- Reentrant event delivery must not deadlock host message processing.
- Password values stay masked and unsupported patterns are not advertised.
- Geometry includes window position and display scale.
- Text endpoint operations clamp and normalize ranges safely.

## Tasks

- [x] Add a native OS client/server acceptance executable and runner. First fail by asserting attachment exports exist against the current staged library.
- [x] Implement attachment, HWND discovery, fragment navigation, properties, Invoke/Value/Toggle and live identity. Run real OS tree/action checks.
- [x] Add range/value/selection/expand/scroll patterns and Text/TextRange implementation. Verify text reading, endpoint movement, selection, geometry and unsupported attributes through UIA.
- [x] Verify events, detached nodes and outstanding client references across teardown. Run against the real staged WebCore library.
- [x] Integrate Windows CMake source/link dependencies and owner-thread destruction hook. Compile checks and native OS acceptance passed; integration review follows the local commit.

## Execution record

- RED: preview.4 staged DLL lacks `rv_host_attach_uia`.
- GREEN: separate native client discovered the real HWND tree, invoked the button and observed its Name event.
- RED/GREEN: surrogate-pair endpoint movement, clipped textarea lines, out-of-range RangeValue, synchronous detach, unsolicited dispatch messages and default localized control roles.
- `RangeFromChild` first failed with E_INVALIDARG; added the exact native text-scope helper, rebuilt a private host DLL from the existing read-only WebCore libraries and verified the child text through OS UIA.
- Ruling: range-specific scrolling, selection removal, text attributes and table/relationship metadata remain explicitly unsupported where the ABI has no implementation; do not fabricate success. Cost: those interactions need further ABI work.
- No ABI version bump, package publication, shared-cache changes or CI edits; integration owns them.
- Fresh review added OS RED/GREEN checks for range children, innermost enclosing element, degenerate caret geometry and offscreen geometry. Numeric RangeValue events also pass through an OS subscription.
- Cache lifetime RED: baseline 18 to 275 retained entries after 128 real DOM/UIA cycles. GREEN: baseline 18 to 19 after the same 128 cycles, with detached-node eviction, owner-thread AX release and deferred COM retirement.
- Final integrated DLL acceptance passed explicit/host/window/synchronous teardown and moved-window overflow with scale 1.5. Header/managed declaration check: 178 functions, zero differences. The staged candidate advertises accessibility-uia and exports all three new functions.
- Final `scripts/abi_tests.py` gate passed against the private candidate runtime, including all ABI scenarios and teardown probes. The Release driver built with zero warnings and errors; DOM generation check also passed.
