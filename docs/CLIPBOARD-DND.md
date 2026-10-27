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
  3. In the App style the host passes each type and value to `write`. In the Native style WebCore writes
     the platform clipboard. In the DOM style nothing is written.
  4. A cut then deletes the selection, unless the page cancelled the event.
- **Paste:**
  1. In the App style the host calls `read`, which hands over each type the app has, through
     `rv_clipboard_offer(request, type, data)`.
  2. The host fires `paste` with a read-only `clipboardData` holding those types.
  3. Unless the page cancelled the event, the host inserts `text/html` as a fragment, or else `text/plain`.
  4. In the Native style WebCore reads the platform clipboard. In the DOM style the page receives an empty
     `clipboardData`.

## Drag and drop

```c
enum { RV_DRAG_APP = 0, RV_DRAG_NATIVE = 1, RV_DRAG_DOM = 2 };
int32_t rv_host_set_drag(RvHost*, int32_t style, RvDragStart start, void* context);
```

- **Dragging into the page** (App and Native):
  1. The app forwards the OS drag events with `rv_host_drag(host, RV_DRAG_ENTER | OVER | LEAVE | DROP, x, y,
     allowedOperations, data)`.
  2. `data` is an `RvDragData` built with `rv_drag_data_create` and `rv_drag_data_add(type, value)`, with
     types such as `text/plain`, `text/html`, `text/uri-list` and `Files` (file paths).
  3. The return value is the operation the page accepts (copy, move or link), which the app shows as the
     cursor. The page's `dragenter`, `dragover` and `drop` listeners decide it.
- **Dragging out of the page:**
  1. When the user drags a draggable element, a link, an image or a selection, the host calls `start` with
     an `RvDrag`: its data types and values, a drag image from `rv_element_snapshot`'s path, the offset of
     the image from the mouse, and the allowed operations.
  2. The app runs an OS drag session, or keeps the drag in-process by feeding the same data back through
     `rv_host_drag`.
  3. The app ends it with `rv_drag_end(drag, operation)`, which fires `dragend`.
- **Native:** the host hands WebCore's platform drag to the OS: OLE `DoDragDrop` on Windows, an
  `NSDraggingSession` on macOS.
- **DOM:** no drag starts. `draggable` has no effect beyond the attribute, and the page drags with pointer
  events.

## Order of work

1. **Clipboard, App and DOM styles.** One code path on every platform.
2. **Drag and drop, App and DOM styles.** A host `DragClient`, and `DragData` built per platform from
   `RvDragData`.
3. **Native styles.** Windows first, where WebCore's code already talks to OLE, then macOS, which needs a
   pasteboard strategy that calls NSPasteboard.
