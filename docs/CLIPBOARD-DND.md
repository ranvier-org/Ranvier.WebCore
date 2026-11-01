# Clipboard and drag and drop

The ABI supports three styles of clipboard and drag and drop. An app picks one per host, and may switch.

| Style | Who moves the data | What the app does | Platforms |
|---|---|---|---|
| **App** | The app, through ABI callbacks | Maps the host's text, HTML and custom types to the OS clipboard or drag session, or keeps them in-process | All |
| **Native** | WebCore's own platform code | Nothing | Windows (OLE) and macOS (NSPasteboard). Linux has no display connection, so there it is the App style |
| **DOM** | The page | Nothing: the page handles `copy`, `cut` and `paste` events, and does its own dragging with pointer events | All |

In every style the page sees the standard DOM events. `copy`, `cut` and `paste` fire with a
`clipboardData`, and `dragstart`, `dragenter`, `dragover`, `drop` and `dragend` fire with a `dataTransfer`.
A page that cancels one of them takes over its default action, as in a browser. The styles differ only in
where the data goes once the page has not cancelled.

## Clipboard

```c
enum { RV_CLIPBOARD_APP = 0, RV_CLIPBOARD_NATIVE = 1, RV_CLIPBOARD_DOM = 2 };
int32_t rv_host_set_clipboard(RvHost*, int32_t style, RvClipboardWrite write, RvClipboardRead read, void* context);
```

- **Commands:** `rv_host_edit(host, RV_EDIT_COPY | CUT | PASTE | PASTE_PLAIN | SELECT_ALL | DELETE | UNDO | REDO)`
  runs a command, as a menu would. Control+C, X and V run the same commands from `rv_host_key`.
- **Copy and cut:**
  1. The host fires `copy` or `cut` with a writable `clipboardData`.
  2. If the page cancelled the event and set data, that data is what was copied. Otherwise it is the
     selection as `text/plain` and `text/html`.
  3. In the App style the host passes each type and value to `write`: the type NUL-terminated, the value as
     UTF-8 bytes and a byte count (ABI 55), so it may hold U+0000. In the Native style WebCore writes
     the platform clipboard. In the DOM style nothing is written.
  4. A cut then deletes the selection, unless the page cancelled the event.
- **Paste:**
  1. In the App style the host calls `read`, which hands over each type the app has, through
     `rv_clipboard_offer(request, type, data, data_length)`.
  2. The host fires `paste` with a read-only `clipboardData` holding those types.
  3. Unless the page cancelled the event, the host inserts `text/html` as a fragment, or else `text/plain`.
  4. In the Native style WebCore reads the platform clipboard. In the DOM style the page receives an empty
     `clipboardData`.
- **Files and images** (`rv_abi_has("clipboard-files")`): during `read` the app offers each file, an image as an
  `image/png` File, with `rv_clipboard_offer_file(request, file)`, a File handle of `rv_dom_file_create`. The paste's
  `clipboardData` lists it in `files`, as an item of kind `file` and as the type `Files`; the page's File is a copy
  with the same name, type and bytes. Files a copy or cut listener adds with `clipboardData.items.add(file)` reach
  the callback of `rv_host_set_clipboard_file_write`, after the string types. `Files` is never a string type.
- **Permission:** `rv_clipboard_deny(request)` during `read` refuses the paste: no `paste` event, nothing inserted,
  and `rv_host_edit` returns `RV_ERR_DOM_EXCEPTION` with `NotAllowedError`.
- **The data's lifetime:** `copy` and `cut` get a read-write `clipboardData`, `paste` a read-only one. Each is
  unreadable once its event is over (empty types, data and files); Files read from it stay valid.

## Drag and drop

```c
enum { RV_DRAG_APP = 0, RV_DRAG_NATIVE = 1, RV_DRAG_DOM = 2 };
int32_t rv_host_set_drag(RvHost*, int32_t style);
```

- **Dragging into the page**, the App style (ABI 19):
  1. The app forwards the OS drag events with `rv_host_drag(host, RV_DRAG_OVER | LEAVE | DROP, x, y,
     allowedOperations, data, modifiers)`.
  2. `data` is an `RvDragData` built with `rv_drag_data_create` and `rv_drag_data_add(type, data, data_length)`, with
     types such as `text/plain`, `text/html` and `text/uri-list`, and `rv_drag_data_add_file(file)` for files
     (`rv_abi_has("data-transfer-files")`). WPE accepts the host's in-memory File payloads; its OS pasteboard
     and disk-path access restrictions remain in place. GTK continues to report this capability unavailable.
     `dragenter`, `dragover` and `dragleave` see a protected `dataTransfer`, whose types are readable and whose
     data and files are not; `drop` sees a read-only one. Each is unreadable once its event is over.
  3. The host fires `dragenter` and `dragleave` as the element under the point changes, then `dragover`,
     or `drop` on release, at that element. It fires them itself, as for the clipboard, so the same code
     runs on every platform.
  4. The return value is the operation the page accepts (copy, move or link), which the app shows as the
     cursor. A cancelled `dragover` accepts its `dropEffect`; with no listener, text over editable
     content is a copy; anything else is refused.
  5. A drop that no listener cancels inserts the text, or the HTML, at the point.
- **Dragging out of the page**, the App style (ABI 20, `rv_abi_has("drag-out")`):
  1. The app sets a callback with `rv_host_set_drag_start`. When the user drags a draggable element, a
     link, an image or a selection, after the page's `dragstart` listeners have set the data, the host calls
     it with an `RvDrag`, where the press was, and the operations the page allows.
  2. The app reads the items with `rv_drag_item_count`, `rv_drag_item_type` and `rv_drag_item_value`, the
     Files the page added with `rv_drag_file_count` and `rv_drag_file`, and the image with `rv_drag_image`: the
     dragged element painted as `rv_element_snapshot` does, with where the press was inside it, or the element
     a `dragstart` listener passed to `setDragImage`, with its offset. A selection drag has no image of its own.
  3. The app runs an OS drag session, or keeps the drag in-process by feeding `rv_drag_data(drag)` back
     through `rv_host_drag`.
  4. The app ends it with `rv_drag_end(drag, x, y, operation)`, which fires `dragend` with the operation
     the target accepted, or none when cancelled.
- **Native:** the host hands WebCore's platform drag to the OS: OLE `DoDragDrop` on Windows, an
  `NSDraggingSession` on macOS.
- **DOM:** no drag starts. `draggable` has no effect beyond the attribute, and the page drags with pointer
  events.

## Order of work

1. **Done:** clipboard in the App, DOM and Native styles (ABI 18). The Native clipboard style calls
   WebCore's own commands.
2. **Done:** drags into the page in the App and DOM styles (ABI 19).
3. **Done:** drags out of the page in the App style, through a host `DragClient` (ABI 20).
4. **Done:** the DataTransfer object model (generated `rv_dom_data_transfer_*`, `DragEvent.dataTransfer`,
   `ClipboardEvent.clipboardData`, `InputEvent.dataTransfer`), file payloads both ways, and `rv_host_replace_range`
   for `insertReplacementText` edits with target ranges (I07, T09, T04; source patch 0041). A range of another
   document returns `RV_ERR_WRONG_HOST`, as anchors of another host do since G14 (batch 3).
5. **Next:** the Native drag style. Windows first, where WebCore's code already talks to OLE, then macOS,
   which needs a pasteboard strategy that calls NSPasteboard.

## Source patch 0041

`DataTransfer::allowsFileAccess` returned false on every port but Cocoa (and GTK/WPE in-memory pastes), so no
`dataTransfer.files`, file item or `Files` type reached a page on Windows or Linux. On the remaining ports the patch
allows file access when the pasteboard holds in-memory file contents, which the host's transfer pasteboard reports for
app File payloads. WebCore's own pasteboards report file paths and stay hidden. `docs/data-transfer-evidence/red`
holds the RED measurement on Native46, and `tests/abi/data_transfer.py` the files read in drops and pastes.
