# D16 dialog, popover and command invokers plan

## Core and view state

- **Core primitives used:** none inside the native exports. A view that opens or closes a dialog or popover from
  state calls the generated members from an effect (`createEffectOnWithComparer` skips unchanged targets). A view
  that follows `beforetoggle`, `toggle`, `cancel`, `close` or `command` adds the listener under an `Owner` and
  removes it with `onCleanup`; it writes `ToggleEvent.newState` or `CommandEvent.command` into a core signal inside
  `batch`. Invoker attributes (`popovertarget`, `commandfor`, `command`) are ordinary attribute setters.
- **View-owned state:** none. The engine holds the open state, the top layer, the popover stack, focus and the
  close watchers. Event handles are native objects, which the core cannot hold.

**Goal:** construct and read `ToggleEvent` and `CommandEvent`, and prove the dialog, popover, `popovertarget` and
`command`/`commandfor` surface against Chromium on native JIT, NativeAOT and Chromium (Ranvier.WebCore #24).

**Trees:** native `C:/wk/native-dialog`, branch `codex/native-api-dialog-popover`, from G05's `dc0951a`
(Native29/ABI37). Reservation Native30/ABI38, DOM alpha.33, Views 0.1.23, backend alpha.23.

## Pinned source scope

- `HTMLDialogElement` (`show`, `showModal`, `close`, `requestClose`, `open`, `returnValue`, `closedBy`), the
  popover members of `HTMLElement`, `PopoverInvokerElement` and the `command`/`commandForElement` members of
  `HTMLButtonElement` are already generated in ABI37.
- `ToggleEvent` was a contract-only interface; `CommandEvent` was out of scope. Both have type-cast traits and
  `create(type, Init)` factories.
- Settings: `PopoverAttributeEnabled`, `CommandAttributesEnabled` and `CloseWatcherEnabled` are stable and on by
  default. `PopoverHintEnabled` is a preview setting, off by default.

## Measured RED (Native29/ABI37 against Chromium 156.0.8078.4)

Fixture `tests/fixtures/dialog-popover-cases.json`, oracle `tests/fixtures/dialog-popover-oracle.json`
(`tests/abi/dialog_popover_browser.mjs`), native replay `tests/abi/dialog_popover.py`.

- Absent: `rv_dom_toggle_event_create`, `_get_old_state`, `_get_new_state`, `_get_source`,
  `rv_dom_command_event_create`, `_get_command`, `_get_source`.
- `popover="hint"` reflects `"manual"`: `PopoverHintEnabled` is off.
- Dialog methods, popover methods with `source`, `:popover-open`, `:modal`, `:open`, `popovertarget` and command
  activation by `click()` and trusted mouse input, Escape close requests, light dismiss, top-layer hit testing,
  modal autofocus and focus restore all match Chromium.

## Exports (ABI38, additive)

- `gen/dom.json`: `ToggleEvent` and `CommandEvent` join the scope with Document-received `create` factories and
  `ToggleEvent::Init` / `CommandEvent::Init`. Features `dom:ToggleEvent`, `dom:CommandEvent`,
  `dom-constructor:ToggleEvent`, `dom-constructor:CommandEvent`.
- Generator: an event interface gated by `[EnabledBySetting]` checks the setting in its constructor only. Its
  members read without a target, so a constructed `CommandEvent` reads before dispatch.
- Host: `PopoverHintEnabled` follows the measured hint cases (below).

## Teardown

- An open modal dialog with a held `ToggleEvent` at `rv_host_destroy`: the members return a status and no event
  is delivered after destroy.
- An open popover held past document replacement: the replaced document's popover reads inert, and the new
  document's first `showPopover` delivers its own toggle events.

## Qualifications

Recorded with numbers in `docs/dialog-popover-evidence/`.
