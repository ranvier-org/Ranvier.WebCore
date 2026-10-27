# Accessibility

The host exposes the accessibility tree WebCore builds for a page, so that an app rendering the page
offscreen can present it to screen readers through the platform's own API: UI Automation on Windows,
NSAccessibility on macOS, AT-SPI on Linux. The app owns the platform objects; the ABI gives it the tree to
mirror, the events that say when to read it again, and the actions an assistive technology performs.
`rv_abi_has("accessibility")` reports the group.

## What WebCore provides on each port

WebCore builds its accessibility tree on every port: `AXObjectCache`, `AccessibilityObject` and its
subclasses, and the ARIA name and role computations are in `Sources.txt`, compiled whatever the port or
flavor. No CMake option or `ENABLE` flag removes them, and none of the patches stub them. What differs per
port is the platform layer that turns the tree into the platform API:

| Port | Platform layer in WebCore | How it reaches assistive technology | Relevance to the host |
|---|---|---|---|
| Windows (`PORT=Win`) | `accessibility/win`: 4 files. MSAA event posting with `NotifyWinEvent`, and an abstract `AccessibilityObjectWrapper` (an `IUnknown`) with no implementation in WebCore | WebKitLegacy implemented the MSAA objects; it is gone from WebKit. Events need the page's `HWND` (`ChromeClient::platformPageClient`), which an offscreen host has none of | The app writes the UI Automation provider; the ABI is the only path. |
| macOS (`PORT=Mac`) | `accessibility/mac` and `cocoa`: `WebAccessibilityObjectWrapperMac`, an `NSAccessibility` element per object, posting notifications itself. The isolated tree (`ENABLE_ACCESSIBILITY_ISOLATED_TREE`) answers queries off the main thread | Through the wrappers, which an `NSView` returns as its accessibility children (`AXCoreObject::platformElement()` is exported) | Two routes: mirror the ABI's tree, or hand the wrappers to AppKit. See the decisions below. |
| Linux (`PORT=WPE`) | `accessibility/atspi`: a complete AT-SPI implementation over D-Bus (`USE_ATSPI` is always on for WPE; `USE_ATK`, which `config/wpe.cmake` turns off, only adds the ATK bridge) | `AccessibilityAtspi::connect(busAddress)` registers the page on the accessibility bus; WPE's UI process normally does this | Two routes as on macOS: mirror the ABI's tree, or connect WebCore's own AT-SPI objects and plug them into the app's tree. |

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

## Size

Measured on Windows x64, slim flavor, against the same build without these changes (2026-10-27):

| File | Before | After | Change |
|---|---|---|---|
| `WebCore.dll` | 45,457,920 | 45,459,456 | +1,536 bytes: patch 0011's hook and three exports |
| `RanvierWebCoreHost.dll` | 160,256 | 175,104 | +14,848 bytes: the ABI's accessibility functions |
| Package (24 files) | 77,688,017 | 77,704,401 | +16,384 bytes |

The tree itself costs nothing in the package: WebCore compiles it on every port whether or not anything
reads it. At run time a host with accessibility on keeps an accessibility object per exposed node and
updates the tree as the page changes, which costs memory and time in proportion to the page (E); a host
with it off costs nothing.

## Not covered

- **Text ranges.** UI Automation's `TextPattern`, NSAccessibility's text marker APIs and AT-SPI's `Text`
  interface (caret, selection, character and line bounds, text attributes) need WebCore's
  `AXTextMarker` ranges, which the ABI does not expose. A screen reader can read names and values, and a
  text field's whole value, but not navigate inside text by character or line.
- **Tables.** Row and column counts, indexes, spans and headers (`AXTableHelpers`) are not exposed; the
  app sees rows and cells as children.
- **Relations.** `aria-controls`, `aria-owns`, `aria-flowto`, `aria-details` and `aria-errormessage`
  targets, and position in set (`aria-posinset`, `aria-setsize`) are not exposed.
- **Frames.** The host loads one document. An `<iframe>`'s content appears through WebCore's frame objects
  as on any port, but no test covers it.
- **Off the main thread.** UI Automation calls a provider on its own threads; the app marshals each call
  to the host thread, as every call of the ABI requires. WebCore's isolated tree, which answers off the
  main thread on macOS, is not used.
