# Accessibility

The host exposes the accessibility tree WebCore builds for a page, so that an app rendering the page
offscreen can present it to screen readers through the platform's own API: UI Automation on Windows,
NSAccessibility on macOS, AT-SPI on Linux. The app owns the platform objects; the ABI gives it the tree to
mirror, the events that say when to read it again, and the actions an assistive technology performs.
`rv_abi_has("accessibility")` reports the group.

## Windows UI Automation bridge

On Windows, `rv_abi_has("accessibility-uia")` reports the native UI Automation bridge. Attach it to an
initialized window on the same thread as the host:

```c
rv_host_attach_uia(host, hwnd);
/* Keep pumping the window messages and cycling/updating the WebCore host. */
rv_host_detach_uia(host);
/* Destroy the host and window after detaching. */
```

`rv_host_attach_uia` returns `RV_OK` on success. It owns the host's accessibility callback while attached;
do not replace that callback with `rv_host_set_accessibility`. Each host and HWND has at most one bridge.
Detach is idempotent and `rv_host_destroy` also detaches. Non-Windows builds return `RV_ERR_UNSUPPORTED`.

The bridge subclasses the HWND and answers `WM_GETOBJECT` with native COM fragment providers. It exposes
the WebCore tree, names, roles, states and screen geometry, with Invoke, Value, Toggle, RangeValue,
ExpandCollapse, SelectionItem and ScrollItem actions where the corresponding ABI capability applies.
Document and text-field providers expose UTF-16 text ranges, selection, character/word/line/paragraph
movement, text search and geometry. `RangeFromChild` uses `rv_ax_text_child_range`, so the offsets come
from WebCore's DOM text scopes rather than a guess based on matching strings or rectangles.

UIA may call on arbitrary threads. The bridge dispatches ABI work to the HWND owner thread and releases
all native node references there before host destruction. Providers retained by clients after removal or
teardown return `UIA_E_ELEMENTNOTAVAILABLE`. COM disconnection is deferred when teardown happens inside a
synchronous window message, where Windows forbids it. The COM implementation is native and adds no
managed COM dependency to a NativeAOT application.

Detached nodes are evicted on reads and event delivery; periodic sweeps also bound retained detached nodes
when a flavor has no accessibility events. Native handles are released on the host thread, while COM
retirement is deferred if a synchronous message is in progress. Text-range geometry excludes caret-only
degenerate ranges and clips text rectangles to the viewport and CSS overflow-clipping ancestors.

The bridge does not add information absent from the ABI: text attributes, table metadata and relations
remain unavailable. Selection removal and additive text selection are not supported. A text range can
scroll its whole enclosing object into view; scrolling a subrange returns `UIA_E_NOTSUPPORTED` rather
than claiming the object-level action moved that subrange. Visible ranges are computed from laid-out
lines clipped against the viewport and overflow-clipping ancestors; partially visible lines remain whole.

`tests/uia` verifies the exported attachment API and uses an independent OS UI Automation client process
to query and act on a real WebCore host. Its README describes the staged-runtime/build inputs and the
four teardown modes. An SDL presenter attaches using its native Windows handle; the bridge has no SDL
dependency.

## What WebCore provides on each port

WebCore builds its accessibility tree on every port: `AXObjectCache`, `AccessibilityObject` and its
subclasses, and the ARIA name and role computations are in `Sources.txt`, compiled whatever the port or
flavor. No CMake option or `ENABLE` flag removes them, and none of the patches stub them. What differs per
port is the platform layer that turns the tree into the platform API:

| Port | Platform layer in WebCore | How it reaches assistive technology | Relevance to the host |
|---|---|---|---|
| Windows (`PORT=Win`) | `accessibility/win`: 4 files. MSAA event posting with `NotifyWinEvent`, and an abstract `AccessibilityObjectWrapper` (an `IUnknown`) with no implementation in WebCore | WebKitLegacy implemented the MSAA objects; it is gone from WebKit. Events need the page's `HWND` (`ChromeClient::platformPageClient`), which an offscreen host has none of | The app writes the UI Automation provider; the ABI is the only path. |
| macOS (`PORT=Mac`) | `accessibility/mac` and `cocoa`: `WebAccessibilityObjectWrapperMac`, an `NSAccessibility` element per object, posting notifications itself. The isolated tree (`ENABLE_ACCESSIBILITY_ISOLATED_TREE`) answers queries off the main thread | Through the wrappers, which an `NSView` returns as its accessibility children (`AXCoreObject::platformElement()` is exported) | The app mirrors the ABI's tree, as on Windows (see Decisions); the wrappers stay unused. |
| Linux (`PORT=WPE`) | `accessibility/atspi`: a complete AT-SPI implementation over D-Bus (`USE_ATSPI` is always on for WPE; `USE_ATK`, which `config/wpe.cmake` turns off, only adds the ATK bridge) | `AccessibilityAtspi::connect(busAddress)` registers the page on the accessibility bus; WPE's UI process normally does this | The app mirrors the ABI's tree, as on Windows (see Decisions); WebCore's AT-SPI objects stay unconnected. |

So the tree is present, built and correct on every port; an offscreen host lacks only a way to read it and
to hear its changes. The ABI adds both, on every port alike.

## Turning it on

```c
int32_t rv_host_set_accessibility(RvHost*, int32_t enabled, RvAxCallback callback, void* context);
```

WebCore keeps one accessibility mode per process (`AXObjectCache::gAccessibilityMode`). The first host to
turn accessibility on moves it from off to main-thread mode, and the last host to turn it off moves it back.
While it is on, WebCore builds a cache for each document that asks for one, which includes every page of
the process that posts a change; the host asks for its own document's cache when it turns accessibility on
and after each `rv_host_load_html`. A host starts with accessibility off, and costs nothing until then.

## The tree

`rv_host_ax_root` returns the root, a node of role `RV_ROLE_DOCUMENT` whose bounds are the viewport. Its
descendants are the objects WebCore exposes: an element hidden with `display: none`, `visibility: hidden`,
`aria-hidden` or `inert`, a presentational element, and most purely structural boxes have no node, and
their children belong to the nearest exposed ancestor. A run of text is a node of role `RV_ROLE_TEXT`.

| Read | Function |
|---|---|
| Role | `rv_ax_role`: an `RV_ROLE_*` value; `rv_ax_string(RV_AX_ROLE_NAME)` gives the ARIA role WebCore computed, for an app that maps more finely |
| Name, description, value | `rv_ax_string(RV_AX_NAME, RV_AX_DESCRIPTION, RV_AX_VALUE)` |
| Other strings | `RV_AX_ROLE_DESCRIPTION`, `RV_AX_PLACEHOLDER`, `RV_AX_KEY_SHORTCUTS`, `RV_AX_URL`, `RV_AX_LIVE`, `RV_AX_TEXT` |
| States | `rv_ax_states`: `RV_AX_*` bits |
| Numbers | `rv_ax_number`: a range's value, minimum and maximum; a heading's or tree item's level |
| Bounds | `rv_ax_rect`, in CSS pixels of the viewport, as `rv_element_rect` |
| Structure | `rv_ax_parent`, `rv_ax_children` |
| Identity | Handles compare equal for the same object; `rv_ax_id` is WebCore's `AXID`, unique in the process and never reused |
| The DOM | `rv_ax_dom_node` and `rv_node_ax` cross between the trees |
| Hit test, focus | `rv_host_ax_hit_test(x, y)`, `rv_host_ax_focus` |

The name and description follow WebCore's text alternative computation, taken the way WebCore's AT-SPI
port takes it: the name is the first alternative that is not help text (`aria-labelledby`, `aria-label`, a
`<label>`, `alt`, the contents, `title`), and the description is `aria-describedby` or
`aria-description`, or a `title` that did not give the name.

The functions that read structure or geometry (`rv_host_ax_root`, `_focus`, `_hit_test`, `rv_node_ax`,
`rv_ax_children`, `rv_ax_rect`) bring layout and the tree up to date first, so the app can read it right
after changing the DOM.

### Lifetime

Each `RvAxNode` is a strong reference to the accessibility object, released with `rv_ax_release` before
`rv_host_destroy`. When the DOM node behind an object is removed, or the document is replaced, WebCore
detaches the object: the handle stays valid, and the functions return `RV_ERR_DETACHED` or `NULL`. A
platform bridge drops its platform object then; UI Automation's `UIA_E_ELEMENTNOTAVAILABLE` and AT-SPI's
defunct state are the matching platform answers.

## Events

`RvAxCallback(context, node, event)` runs on the host thread from `rv_run_loop_cycle`, once per node and
event since the previous delivery, in the order WebCore posted them. WebCore posts while it updates the
tree: during the rendering update (`rv_host_update`) after a DOM change, from its own timers during
`rv_run_loop_cycle`, and inside the reads that bring the tree up to date, such as `rv_ax_children`. So the
host queues each notification and delivers the batch on the next run loop cycle, where the callback can
call any function of the ABI. An app that runs `rv_host_update` for each frame the page requests and cycles
the run loop receives every event without doing anything more.

| Event | WebCore notifications | UI Automation | NSAccessibility | AT-SPI |
|---|---|---|---|---|
| `RV_AX_EVENT_FOCUS` | `FocusedUIElementChanged`, focus moving to an active descendant | `UIA_AutomationFocusChangedEventId` | `NSAccessibilityFocusedUIElementChangedNotification` | `focus:` and `object:state-changed:focused` |
| `RV_AX_EVENT_CHILDREN` | `ChildrenChanged` | `UIA_StructureChangedEventId` (`ChildrenInvalidated`) | `NSAccessibilityLayoutChangedNotification` | `object:children-changed` |
| `RV_AX_EVENT_VALUE` | `ValueChanged`, `MenuListValueChanged`, min and max changes | `ValueValue` or `RangeValueValue` property changed | `NSAccessibilityValueChangedNotification` | `object:property-change:accessible-value` |
| `RV_AX_EVENT_STATE` | checked, disabled, expanded, pressed, required, invalid, read-only, busy, focusable, visited, has-popup, multiselectable | the matching property changed (`ToggleToggleState`, `ExpandCollapseExpandCollapseState`, `IsEnabled`, ...) | the matching notification, or `ValueChanged` for checked | `object:state-changed:*` |
| `RV_AX_EVENT_NAME` | `LabelChanged`, `NameChanged`, `TextUnderElementChanged` | `Name` property changed | `NSAccessibilityTitleChangedNotification` | `object:property-change:accessible-name` |
| `RV_AX_EVENT_DESCRIPTION` | `DescribedByChanged`, `ExtendedDescriptionChanged` | `HelpText` or `FullDescription` changed | (read again) | `object:property-change:accessible-description` |
| `RV_AX_EVENT_ROLE` | `RoleChanged` | `ControlType` changed | (read again) | `object:property-change:accessible-role` |
| `RV_AX_EVENT_SELECTION` | `SelectedStateChanged`, `SelectedChildrenChanged`, `SelectedCellsChanged`, `MenuListItemSelected` | `SelectionItem_ElementSelectedEventId` or `Selection_InvalidatedEventId` | `NSAccessibilitySelectedChildrenChangedNotification` | `object:selection-changed` |
| `RV_AX_EVENT_LIVE_REGION` | `LiveRegionChanged`, `LiveRegionAnnouncement` | `UIA_LiveRegionChangedEventId`, or `RaiseNotificationEvent` with `RV_AX_TEXT` | `NSAccessibilityAnnouncementRequestedNotification` with `RV_AX_TEXT` | `object:announcement` or `object:text-changed` |
| `RV_AX_EVENT_LOAD_COMPLETE` | `LoadComplete`, `NewDocumentLoadComplete` | `AsyncContentLoaded` | `AXLoadComplete` | `document:load-complete` |
| `RV_AX_EVENT_LAYOUT` | `LayoutComplete`, `PageScrolled`, `ScrolledToAnchor` | `BoundingRectangle` changed | `NSAccessibilityLayoutChangedNotification` | `object:bounds-changed` |
| `RV_AX_EVENT_MENU_OPENED`, `_CLOSED` | `MenuOpened`, `MenuClosed` | `MenuOpened`, `MenuClosed` | `NSAccessibilityMenuOpened...` | `window:activate` / `deactivate` |

WebCore's platform layers post these through their own code, which an offscreen host cannot use (the
Windows layer needs an `HWND`; the Cocoa layer does not post `ChildrenChanged` at all). Patch
`0011-ax-embedder-notifications` adds `USE_AX_EMBEDDER_NOTIFICATIONS`: with it on, `AXObjectCache` also
hands each notification it delivers to the page's `ChromeClient::postAccessibilityNotification`, the hook
WebCore's PlayStation port uses, on every port and before the platform layer sees it. The option defaults
to OFF, and `config/slim.cmake` turns it on; `RvChromeClient` overrides the hook. The lean flavor keeps every
patch option at its default, so it has the tree and no events, and `rv_abi_has("accessibility-events")`
returns 0 there.

## Actions

| Action | WebCore | UI Automation pattern |
|---|---|---|
| `RV_AX_PRESS` | `press()`: the element's default action, as a click | `Invoke`, and `Toggle` for checkable nodes |
| `RV_AX_FOCUS` | `setFocused(true)` | `SetFocus` |
| `RV_AX_SCROLL_INTO_VIEW` | `scrollToMakeVisible()` | `ScrollItem` |
| `RV_AX_INCREMENT`, `_DECREMENT` | `increment()`, `decrement()` on a range | `RangeValue` small change |
| `RV_AX_EXPAND`, `_COLLAPSE` | `setIsExpanded()`: `<details>`, `<select>` and other native disclosure | `ExpandCollapse` |
| `RV_AX_SELECT` | `setSelected(true)` | `SelectionItem.Select` |
| `rv_ax_set_value` | an `<input>` or `<textarea>` value set with `input` and `change`, else `setValue()` | `Value.SetValue` |
| `rv_ax_set_number` | `setValue(float)`, clamped to the range | `RangeValue.SetValue` |

An ARIA widget's expansion and selection are the page's own state: `RV_AX_EXPAND` on a button with
`aria-expanded` returns 0, and the app presses it instead, as a screen reader does.

## Roles

`RV_ROLE_*` folds WebCore's 130 roles into 71 that map one to one onto the platforms' control types. The
mapping is `roleValue` in `host/RanvierWebCoreAbi.cpp`. A sketch of the bridge's side:

| `RV_ROLE_*` | UI Automation control type | NSAccessibility role | AT-SPI role |
|---|---|---|---|
| `DOCUMENT` | `Document` | `AXWebArea` | `document-web` |
| `GENERIC`, `GROUP`, landmarks, `ARTICLE`, `FIGURE`, `NOTE`, `FORM` | `Group` (landmarks with `LandmarkType`) | `AXGroup` with a subrole | `section`, `landmark`, `article`, `form` ... |
| `TEXT`, `PARAGRAPH`, `LABEL` | `Text` | `AXStaticText` | `static`, `paragraph`, `label` |
| `HEADING` | `Text` with `HeadingLevel` | `AXHeading` | `heading` |
| `LINK` | `Hyperlink` | `AXLink` | `link` |
| `BUTTON`, `TOGGLE_BUTTON` | `Button` | `AXButton`, `AXCheckBox` subrole toggle | `push-button`, `toggle-button` |
| `CHECKBOX`, `SWITCH` | `CheckBox` | `AXCheckBox` | `check-box`, `switch` |
| `RADIO`, `RADIO_GROUP` | `RadioButton`, `Group` | `AXRadioButton`, `AXRadioGroup` | `radio-button`, `panel` |
| `TEXT_FIELD`, `TEXT_AREA` | `Edit` | `AXTextField`, `AXTextArea` | `entry` |
| `COMBO_BOX`, `LIST_BOX`, `OPTION` | `ComboBox`, `List`, `ListItem` | `AXComboBox` or `AXPopUpButton`, `AXList`, `AXStaticText` | `combo-box`, `list-box`, `list-item` |
| `MENU`, `MENU_BAR`, `MENU_ITEM*` | `Menu`, `MenuBar`, `MenuItem` | `AXMenu`, `AXMenuBar`, `AXMenuItem` | `menu`, `menu-bar`, `menu-item` ... |
| `SLIDER`, `SPIN_BUTTON`, `PROGRESS`, `METER`, `SCROLL_BAR` | `Slider`, `Spinner`, `ProgressBar`, `ProgressBar`, `ScrollBar` | `AXSlider`, `AXIncrementor`, `AXProgressIndicator`, `AXLevelIndicator`, `AXScrollBar` | `slider`, `spin-button`, `progress-bar`, `level-bar`, `scroll-bar` |
| `IMAGE` | `Image` | `AXImage` | `image` |
| `LIST`, `LIST_ITEM`, `TERM`, `DEFINITION` | `List`, `ListItem`, `Text`, `Text` | `AXList`, `AXGroup` ... | `list`, `list-item`, `description-term`, `description-value` |
| `TABLE`, `GRID`, `TREE_GRID`, `ROW`, `CELL`, `*_HEADER` | `Table`, `DataGrid`, `DataGrid`, `DataItem`, `DataItem`, `HeaderItem` | `AXTable`, `AXRow`, `AXCell` | `table`, `table-row`, `table-cell`, `*-header` |
| `TREE`, `TREE_ITEM` | `Tree`, `TreeItem` | `AXOutline`, `AXRow` | `tree`, `tree-item` |
| `TAB_LIST`, `TAB`, `TAB_PANEL` | `Tab`, `TabItem`, `Pane` | `AXTabGroup`, `AXRadioButton`, `AXGroup` | `page-tab-list`, `page-tab`, `scroll-pane` |
| `DIALOG`, `ALERT_DIALOG`, `ALERT`, `STATUS`, `LOG`, `MARQUEE`, `TIMER`, `TOOLTIP` | `Window` (dialogs), `Text`, `StatusBar`, `ToolTip` | `AXGroup` with a subrole | `dialog`, `alert`, `status-bar`, `log`, `marquee`, `timer`, `tool-tip` |
| `TOOLBAR`, `SEPARATOR`, `MATH` | `ToolBar`, `Separator`, `Group` | `AXToolbar`, `AXSplitter`, `AXGroup` | `tool-bar`, `separator`, `math` |

## Text

`rv_abi_has("accessibility-text")` adds a node's text, enough to back UI Automation's `TextPattern` and
`TextRange`, NSAccessibility's text attributes (`AXValue`, `AXSelectedTextRange`, `AXInsertionPointLineNumber`,
`AXStringForRange`, `AXBoundsForRange`, `AXRangeForPosition`) and AT-SPI's `Text` interface, from one model:

- **The text.** A node's text is its DOM node's text as WebCore's `TextIterator` reads it (`plainText`): the
  rendered text, with a newline between blocks. A text field's text is its inner editor's, so its value; a
  password field's is masked with U+2022. The root's text is the whole document's.
- **Offsets** are UTF-16 code units, as in UI Automation, `NSRange` and the DOM. AT-SPI counts characters,
  so the bridge converts there.
- **Units.** `rv_ax_text_boundary(offset, unit)` returns the character, word, line, sentence or paragraph
  containing an offset, from WebCore's own `startOfWord`, `startOfLine` (lines as laid out),
  `startOfSentence` and `startOfParagraph`. A `TextRange.Move` or `ExpandToEnclosingUnit` and AT-SPI's
  `GetStringAtOffset` are calls to it; a line, sentence or paragraph includes the newline that ends it.
- **Caret and selection.** `rv_ax_text_selection` clips the page's selection to the node's text,
  `rv_ax_text_caret` gives the selection's moving end, and `rv_ax_text_set_selection` sets either. The page
  has one selection, as a browser has.
- **Geometry.** `rv_ax_text_rects` gives a rectangle per line box of the range (UI Automation's
  `GetBoundingRectangles`), or the caret's rectangle for an empty range; `rv_ax_text_offset_at` is the
  reverse (`RangeFromPoint`, `GetOffsetAtPoint`).
- **Events.** `RV_AX_EVENT_TEXT` (`UIA_Text_TextChangedEventId`, `object:text-changed`,
  `AXValueChanged`) and `RV_AX_EVENT_TEXT_SELECTION` (`UIA_Text_TextSelectionChangedEventId`,
  `object:text-caret-moved`, `AXSelectedTextChanged`). Patch 0011 hands WebCore's text edit and selection
  notifications to the host on every port; WebCore's own platform layers post them through different paths
  (Windows through its queue as `SelectedTextChanged`, Cocoa and AT-SPI directly). WebCore reports a
  selection change in the rendering update after it, so the event follows the app's next `rv_host_update`.
- **Form fields in the root's text.** `TextIterator` does not enter text fields, so the root's text holds
  the page's text runs without the fields' values; each field's own node has its value as text.

The host computes these from WebCore's editing primitives (`TextIterator`, `VisibleUnits`, the frame
selection), which WebCore already exports, rather than from `AXTextMarker`, whose members are not exported
and differ between the Cocoa and other ports. So the text functions add no export to patch 0010.

## Decisions

Settled by the user on 2026-10-27:

- **Version.** Part of `rv_abi_version` 20, with the `rv_abi_has` groups `accessibility`,
  `accessibility-events` and `accessibility-text`.
- **Lifecycle.** WebCore's accessibility mode is per process: on while any host has accessibility on, and
  back off when the last host turns it off.
- **Lean flavor.** Patch 0011 stays off in the lean flavor, which therefore has the tree and no events.
- **One bridge.** macOS and Linux use the same ABI tree as Windows, not WebCore's own NSAccessibility
  wrappers or AT-SPI objects.
- **Text ranges** are in scope (the section above).
- **Roles.** The 71 folded `RV_ROLE_*` values stay; `RV_AX_ROLE_NAME` gives the finer ARIA role.
- **Events** are delivered asynchronously on the next run loop cycle, with no flush call.

## Size

Measured on Windows x64, slim flavor, against the same build without these changes (2026-10-27):

| File | Before | After | Change |
|---|---|---|---|
| `WebCore.dll` | 45,457,920 | 45,460,480 | +2,560 bytes: patch 0011's hooks and three exports |
| `RanvierWebCoreHost.dll` | 160,256 | 189,440 | +29,184 bytes: the ABI's accessibility and text functions |
| Package (24 files) | 77,688,017 | 77,719,761 | +31,744 bytes |

The tree itself costs nothing in the package: WebCore compiles it on every port whether or not anything
reads it. At run time a host with accessibility on keeps an accessibility object per exposed node and
updates the tree as the page changes, which costs memory and time in proportion to the page (E); a host
with it off costs nothing.

## Relations

`rv_ax_relations` (`accessibility-relations`, ABI49) writes a node's ARIA relationship targets for one of eight kinds:
active descendant, controls, described by, details, error message, flow to, labelled by and owns. The targets come from
the attribute's ID references or from the elements set through `Element.aria*Element(s)` (`RanvierWebCoreDom.h`).
Setting the elements sets the attribute to the empty string, and setting the attribute replaces the elements. The order
is the reference order, and a target appears once. A target with no accessible object is left out: a removed element,
or one in a shadow root that the referring element cannot see. The handles are new references, and a node whose object
is gone returns `RV_ERR_DETACHED`. `ariaActionsElements` reports `RV_ERR_UNSUPPORTED`, because WebKit keeps
`ARIAActionsSupportEnabled` off.

## Not covered

- **Text attributes.** Font, size, weight, colour, language and misspelling over a text range (UI
  Automation's `GetAttributeValue`, AT-SPI's `GetAttributeRun`) are not exposed.
- **Text inside a single object only.** A text range lives in one node's text; a UI Automation range that
  spans the document uses the root's text, which holds every text run but not the fields' values. Embedded objects (an image or a
  button inside a paragraph) are not marked in the text with U+FFFC as AT-SPI's hypertext expects.
- **Tables.** Row and column counts, indexes, spans and headers (`AXTableHelpers`) are not exposed; the
  app sees rows and cells as children.
- **Position in set.** `aria-posinset` and `aria-setsize` are not exposed.
- **Frames.** The host loads one document. An `<iframe>`'s content appears through WebCore's frame objects
  as on any port, but no test covers it.
- **Off the main thread.** UI Automation calls a provider on its own threads; the app marshals each call
  to the host thread, as every call of the ABI requires. WebCore's isolated tree, which answers off the
  main thread on macOS, is not used.

## Platform bridges: help wanted

The ABI above is complete for a first bridge, but no bridge exists yet: nothing turns the tree into UI
Automation, NSAccessibility or AT-SPI objects, so a page rendered through the host is invisible to screen
readers today. Each bridge is self-contained work against this document, and a good place to contribute. The
native path's window layer is SDL3, which gives a bridge the platform window it attaches to
(`SDL_PROP_WINDOW_WIN32_HWND_POINTER`, `SDL_PROP_WINDOW_COCOA_WINDOW_POINTER`, the X11 or Wayland handles).
Where the bridges live (one package per platform, or one with three back ends) is open: propose it in an issue.

| Platform | The bridge | Notes |
|---|---|---|
| Windows | A UI Automation provider: `IRawElementProviderFragmentRoot` for the window, `IRawElementProviderFragment` per `RvAxNode`, returned from `WM_GETOBJECT` with `UiaReturnRawElementProvider`, and the patterns in the Actions and Text sections | SDL3 owns the window procedure, so `WM_GETOBJECT` is caught with `SDL_SetWindowsMessageHook` or a window subclass. From .NET, `[GeneratedComInterface]` keeps the COM interop AOT-compatible. UI Automation calls arrive on its own threads and are marshalled to the host thread |
| macOS | An `NSAccessibilityElement` per node, returned from the content view's `accessibilityChildren`, posting the notifications in the Events table | From .NET through the Objective-C runtime (`objc_msgSend`, `class_addMethod`), which stays AOT-compatible without a binding library |
| Linux | AT-SPI over D-Bus: find the accessibility bus with `org.a11y.Bus.GetAddress`, register the root, and implement `org.a11y.atspi.Accessible`, `Component`, `Action`, `Value` and `Text` | AT-SPI offsets count characters, not UTF-16 code units (see Text). Tmds.DBus is a managed D-Bus client |

Each bridge maps roles with the Roles table, events with the Events table, and actions with the Actions table;
detached nodes answer as the Lifetime section says. Check a bridge with the platform's inspector and a screen
reader: Accessibility Insights and Narrator or NVDA on Windows, Accessibility Inspector and VoiceOver on macOS,
Accerciser and Orca on Linux. `tests/abi/Accessibility.fs` shows the calls in order on a real page.
