/*
 * Ranvier native WebCore C ABI, version 13.
 *
 * The boundary consists of C scalars, UTF-8 strings, opaque handles and a caller-owned RGBA8 buffer,
 * and is identical on every WebCore port that compiles RanvierWebCoreAbi.cpp.
 *
 * Threading: calls are valid only on the thread that first called rv_host_create (WebCore's main
 * thread). A call on another thread returns RV_ERR_WRONG_THREAD (or NULL) and leaves the DOM unchanged.
 *
 * Lifetime: each returned RvNode is a strong reference, released with rv_node_release before
 * rv_host_destroy. Each RvListener holds a strong reference to its target node and is removed with
 * rv_listener_remove before rv_host_destroy. An RvWatch is a weak reference to a node, valid after the node
 * is destroyed and after rv_host_destroy, and is freed with rv_watch_release.
 *
 * Events: listener callbacks run synchronously on the host thread, inside the dispatching call.
 * A callback may call any function of this ABI, including a nested dispatch. An RvEvent pointer is
 * valid only for the duration of the callback that receives it, unless retained with rv_event_retain.
 *
 * Identity: an RvNode or RvEvent pointer is the address of its WebCore object, so two handles to the
 * same object compare equal. Each call that returns a handle adds one reference.
 *
 * Strings out: a getter copies UTF-8 into a caller-owned buffer and writes the byte count, without a
 * terminator, to *length, or -1 for a null string. When capacity is below the byte count it returns
 * RV_ERR_BUFFER_TOO_SMALL with *length set and the buffer untouched.
 */
#pragma once

#include <stdint.h>

#if defined(_WIN32)
#define RV_EXPORT __declspec(dllexport)
#else
#define RV_EXPORT __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

typedef struct RvHost RvHost;
typedef struct RvNode RvNode;
typedef struct RvListener RvListener;
typedef struct RvEvent RvEvent;
typedef struct RvWatch RvWatch;

/* Returns 0 on success. Any other value marks the listener as failed: the dispatch continues with the
 * remaining listeners, and the dispatching call returns RV_ERR_LISTENER_FAILED. */
typedef int32_t (*RvEventCallback)(void* context, RvEvent* event);

enum {
    RV_OK = 0,
    RV_ERR_NULL_ARGUMENT = -1,
    RV_ERR_WRONG_THREAD = -2,
    RV_ERR_DOM_EXCEPTION = -3,
    RV_ERR_NOT_ELEMENT = -4,
    RV_ERR_PAINT_FAILED = -5,
    RV_ERR_BUFFER_TOO_SMALL = -6,
    RV_ERR_LISTENER_FAILED = -7,
    RV_ERR_NOT_INPUT = -8,
    RV_ERR_UNSUPPORTED = -9,
};

/* String properties of rv_node_get_string and rv_node_set_string. */
enum {
    RV_STRING_NODE_NAME = 0,
    RV_STRING_TEXT_CONTENT = 1,
    RV_STRING_LOCAL_NAME = 2,
    RV_STRING_NAMESPACE_URI = 3,
    RV_STRING_INNER_HTML = 4,
    RV_STRING_DATA = 5,
    RV_STRING_VALUE = 6,
    /* Read-only; NULL when the element has no namespace prefix. */
    RV_STRING_PREFIX = 7,
    /* Document.title on a document; HTMLElement.title on an element. */
    RV_STRING_TITLE = 8,
};

/* Parts of rv_element_attribute_at. */
enum {
    RV_ATTRIBUTE_NAME = 0,
    RV_ATTRIBUTE_VALUE = 1,
};

/* Relations of rv_node_relative. */
enum {
    RV_RELATION_PARENT = 0,
    RV_RELATION_FIRST_CHILD = 1,
    RV_RELATION_LAST_CHILD = 2,
    RV_RELATION_NEXT_SIBLING = 3,
    RV_RELATION_PREVIOUS_SIBLING = 4,
    RV_RELATION_OWNER_DOCUMENT = 5,
};

/* Event interfaces of rv_event_interface and rv_host_create_event. */
enum {
    RV_EVENT_EVENT = 0,
    RV_EVENT_UI = 1,
    RV_EVENT_MOUSE = 2,
    RV_EVENT_POINTER = 3,
    RV_EVENT_KEYBOARD = 4,
    RV_EVENT_INPUT = 5,
    RV_EVENT_FOCUS = 6,
    RV_EVENT_OTHER = 7,
};

/* Bits of rv_event_flags. */
enum {
    RV_EVENT_BUBBLES = 1,
    RV_EVENT_CANCELABLE = 2,
    RV_EVENT_PROPAGATION_STOPPED = 4,
    RV_EVENT_DEFAULT_PREVENTED = 8,
    RV_EVENT_TRUSTED = 16,
};

RV_EXPORT int32_t rv_abi_version(void);
RV_EXPORT int64_t rv_process_id(void);

RV_EXPORT RvHost* rv_host_create(int32_t width, int32_t height);
RV_EXPORT void rv_host_destroy(RvHost*);
RV_EXPORT int32_t rv_host_load_html(RvHost*, const char* html);
RV_EXPORT int32_t rv_host_scripts_enabled(RvHost*);
RV_EXPORT int32_t rv_host_vm_entry_disallowed(RvHost*);

RV_EXPORT RvNode* rv_document_body(RvHost*);
/* The document's head element, or NULL when it has none. */
RV_EXPORT RvNode* rv_document_head(RvHost*);
/* The first element in tree order whose ID is elementId, or NULL. */
RV_EXPORT RvNode* rv_document_get_element_by_id(RvHost*, const char* elementId);
RV_EXPORT RvNode* rv_document_create_element(RvHost*, const char* tagName);
RV_EXPORT RvNode* rv_document_create_text(RvHost*, const char* data);

RV_EXPORT int32_t rv_node_append_child(RvNode* parent, RvNode* child);
RV_EXPORT int32_t rv_node_set_text_content(RvNode*, const char* text);
RV_EXPORT int32_t rv_element_set_attribute(RvNode*, const char* name, const char* value);
RV_EXPORT void rv_node_release(RvNode*);

/* Lays out and paints the viewport into rgba (width*height*4 bytes, unpremultiplied RGBA8, sRGB). */
RV_EXPORT int32_t rv_host_paint_rgba(RvHost*, uint8_t* rgba, int32_t length);

/* Registers a WebCore EventListener on target that calls callback(context, event). Returns NULL on a
 * NULL argument or the wrong thread. */
RV_EXPORT RvListener* rv_node_add_event_listener(RvNode* target, const char* type, int32_t capture,
    RvEventCallback callback, void* context);
/* Unregisters the listener and frees the handle. The callback will not run after this returns, also
 * when the listener is removed by another listener of the dispatch in progress. */
RV_EXPORT int32_t rv_listener_remove(RvListener*);

/* Dispatches a new untrusted Event. *defaultPrevented is set to 1 when a listener cancelled it. */
RV_EXPORT int32_t rv_node_dispatch_event(RvNode* target, const char* type, int32_t bubbles, int32_t cancelable,
    int32_t* defaultPrevented);
/* Runs HTMLElement::click(): a simulated click with the element's default action. */
RV_EXPORT int32_t rv_element_click(RvNode*);
/* Returns 1 or 0 for an <input> element's checkedness, or RV_ERR_NOT_INPUT. */
RV_EXPORT int32_t rv_input_checked(RvNode*);

/* 1 capturing, 2 at target, 3 bubbling. */
RV_EXPORT int32_t rv_event_phase(RvEvent*);
RV_EXPORT int32_t rv_event_default_prevented(RvEvent*);
RV_EXPORT void rv_event_prevent_default(RvEvent*);
RV_EXPORT void rv_event_stop_propagation(RvEvent*);

/* v3: the DOM subset of one Ranvier component. */

RV_EXPORT RvNode* rv_host_document(RvHost*);
RV_EXPORT RvNode* rv_document_create_comment(RvHost*, const char* data);
RV_EXPORT RvNode* rv_document_create_fragment(RvHost*);
/* Document.importNode in the host's document. */
RV_EXPORT RvNode* rv_document_import_node(RvHost*, RvNode*, int32_t deep);
/* The children of a fragment parsed from markup with context as the HTML fragment parsing context
 * element, through Range.createContextualFragment. */
RV_EXPORT RvNode* rv_node_parse_fragment(RvNode* context, const char* markup);

/* 1 element, 3 text, 8 comment, 9 document, 11 fragment, as Node.nodeType. */
RV_EXPORT int32_t rv_node_type(RvNode*);
/* The related node, or NULL when there is none. */
RV_EXPORT RvNode* rv_node_relative(RvNode*, int32_t relation);
RV_EXPORT int32_t rv_node_get_string(RvNode*, int32_t property, char* buffer, int32_t capacity, int32_t* length);
/* Writes RV_STRING_TEXT_CONTENT, RV_STRING_INNER_HTML, RV_STRING_DATA, RV_STRING_VALUE or RV_STRING_TITLE.
 * RV_STRING_VALUE reads and writes the value of <input>, <textarea>, <select> and <option>. */
RV_EXPORT int32_t rv_node_set_string(RvNode*, int32_t property, const char* value);
/* Inserts child before reference, or appends it when reference is NULL. */
RV_EXPORT int32_t rv_node_insert_before(RvNode* parent, RvNode* child, RvNode* reference);
RV_EXPORT int32_t rv_node_remove_child(RvNode* parent, RvNode* child);
/* Node.replaceChild: replaces oldChild with newChild. */
RV_EXPORT int32_t rv_node_replace_child(RvNode* parent, RvNode* newChild, RvNode* oldChild);
/* ChildNode.remove. */
RV_EXPORT int32_t rv_node_remove(RvNode*);
RV_EXPORT RvNode* rv_node_clone(RvNode*, int32_t deep);
/* 1 when other is an inclusive descendant of node, else 0. */
RV_EXPORT int32_t rv_node_contains(RvNode* node, RvNode* other);
RV_EXPORT int32_t rv_node_is_connected(RvNode*);

RV_EXPORT int32_t rv_element_get_attribute(RvNode*, const char* name, char* buffer, int32_t capacity, int32_t* length);
RV_EXPORT int32_t rv_element_remove_attribute(RvNode*, const char* name);
RV_EXPORT int32_t rv_input_set_checked(RvNode*, int32_t checked);

/* Adds a reference to an event; each retained or created event is released with rv_event_release. */
RV_EXPORT RvEvent* rv_event_retain(RvEvent*);
RV_EXPORT void rv_event_release(RvEvent*);
/* A new untrusted event from Document.createEvent and Event.initEvent. RV_EVENT_INPUT creates a
 * UIEvent, RV_EVENT_POINTER a MouseEvent: the document's createEvent has no other constructors. */
RV_EXPORT RvEvent* rv_host_create_event(RvHost*, int32_t eventInterface, const char* type, int32_t bubbles, int32_t cancelable);
/* Dispatches a created event. *defaultPrevented is set to 1 when a listener cancelled it. */
RV_EXPORT int32_t rv_node_dispatch(RvNode* target, RvEvent*, int32_t* defaultPrevented);
RV_EXPORT int32_t rv_event_interface(RvEvent*);
RV_EXPORT int32_t rv_event_flags(RvEvent*);
RV_EXPORT int32_t rv_event_type(RvEvent*, char* buffer, int32_t capacity, int32_t* length);
RV_EXPORT int32_t rv_event_key(RvEvent*, char* buffer, int32_t capacity, int32_t* length);
/* The target, or with current set the currentTarget, when it is a node; else NULL. */
RV_EXPORT RvNode* rv_event_target(RvEvent*, int32_t current);

/* Parts of the DOMException behind the latest RV_ERR_DOM_EXCEPTION, for rv_last_exception. */
enum {
    RV_EXCEPTION_NAME = 0,
    RV_EXCEPTION_MESSAGE = 1,
};

/* Copies a part of the latest DOM exception; a null string before the first. */
RV_EXPORT int32_t rv_last_exception(int32_t part, char* buffer, int32_t capacity, int32_t* length);
/* The first matching element of a document, fragment or element, or NULL. *status is RV_OK or
 * RV_ERR_DOM_EXCEPTION for an invalid selector. */
RV_EXPORT RvNode* rv_node_query_selector(RvNode* scope, const char* selectors, int32_t* status);
/* Writes *count, then a handle to each match in document order. When capacity is below *count it
 * returns RV_ERR_BUFFER_TOO_SMALL and writes no handles. The document keeps the matches of a tag or
 * class selector in its querySelectorAll result cache until a mutation under the scope or a memory
 * release. */
RV_EXPORT int32_t rv_node_query_selector_all(RvNode* scope, const char* selectors, RvNode** nodes, int32_t capacity, int32_t* count);
/* rv_node_query_selector_all with the same matches, order and errors, and without an entry in the
 * document's result cache: each descendant from the first match is tested with Element.matches. A
 * selector containing :scope runs WebCore's querySelectorAll, which caches no such selector. */
RV_EXPORT int32_t rv_node_query_selector_all_uncached(RvNode* scope, const char* selectors, RvNode** nodes, int32_t capacity, int32_t* count);

/* The node's reference count, the caller's handle included, or a negative status. */
RV_EXPORT int32_t rv_node_ref_count(RvNode*);
/* A weak reference to the node, or NULL. */
RV_EXPORT RvWatch* rv_node_watch(RvNode*);
/* 1 while the watched node exists, 0 once WebCore has destroyed it, or a negative status. */
RV_EXPORT int32_t rv_watch_alive(RvWatch*);
/* A strong reference to the watched node while it exists, else NULL. */
RV_EXPORT RvNode* rv_watch_node(RvWatch*);
RV_EXPORT void rv_watch_release(RvWatch*);
/* Releases WebCore's caches as under critical memory pressure, synchronously. Among them are each
 * document's cached querySelectorAll results, which hold their elements. */
RV_EXPORT void rv_release_memory(void);
/* Runs a synchronous full JavaScriptCore garbage collection, then returns free memory to the system. */
RV_EXPORT void rv_collect_garbage(void);
/* Runs a synchronous eden JavaScriptCore garbage collection, which collects objects allocated since the
 * last collection, and keeps free memory. */
RV_EXPORT void rv_collect_garbage_eden(void);
/* 1 when the node has a JavaScript wrapper, 0 when it has none, or a negative status. */
RV_EXPORT int32_t rv_node_has_wrapper(RvNode*);

/* v9 */

/* The number of the element's attributes, or a negative status. */
RV_EXPORT int32_t rv_element_attribute_count(RvNode*);
/* The qualified name (RV_ATTRIBUTE_NAME) or value (RV_ATTRIBUTE_VALUE) of the element's attribute at
 * index, in the element's attribute order. */
RV_EXPORT int32_t rv_element_attribute_at(RvNode*, int32_t index, int32_t part, char* buffer, int32_t capacity, int32_t* length);
/* Runs Element::focus() with default options. */
RV_EXPORT int32_t rv_element_focus(RvNode*);
/* Document.activeElement: the focused element, else the body, else NULL. */
RV_EXPORT RvNode* rv_document_active_element(RvHost*);

/* v10 */

/* Cycles the calling thread's run loop, which fires due timers and dispatches pending messages, until the
 * given milliseconds have elapsed, at least once. Returns the cycles run, or a negative status. */
RV_EXPORT int32_t rv_run_loop_cycle(int32_t milliseconds);

/* v11 */

typedef struct RvResourceLoad RvResourceLoad;

/* Serves a load the document starts for a URL other than a data: URL, such as an image, a stylesheet or a
 * font. WebCore calls it from rv_run_loop_cycle, after the call that started the load has returned, for
 * each load still pending. The host completes the load exactly once, during the
 * callback or later on the host thread, with rv_resource_load_finish or rv_resource_load_fail, also after
 * the document cancelled it. Completing frees the RvResourceLoad. */
typedef void (*RvResourceHandler)(void* context, RvResourceLoad* load, const char* url);

/* Sets the host's resource handler, or with a NULL handler removes it. Without a handler each such load
 * fails. */
RV_EXPORT int32_t rv_host_set_resource_handler(RvHost*, RvResourceHandler handler, void* context);
/* Completes the load with a status 200 response of length bytes, which WebCore copies. contentType is a
 * Content-Type value such as "text/css; charset=utf-8". The response allows every origin, so fonts and
 * other CORS-mode loads pass. Inside the handler WebCore receives the response before this returns;
 * otherwise on the next rv_run_loop_cycle. */
RV_EXPORT int32_t rv_resource_load_finish(RvResourceLoad*, const uint8_t* data, int32_t length, const char* contentType);
/* Completes the load with a network error, at the same time as rv_resource_load_finish would. */
RV_EXPORT int32_t rv_resource_load_fail(RvResourceLoad*);

/* v12 */

/* 1 when this library has the named group of functions, else 0, so a caller can test for a group instead of
 * an exact rv_abi_version: "resize" (rv_host_resize, rv_host_set_device_scale, rv_host_paint_size), "input"
 * (rv_host_mouse, rv_host_wheel, rv_host_key, rv_host_set_focused), "frame" (rv_host_set_frame_callback,
 * rv_host_update, rv_host_dirty_rect) and "event-details" (rv_event_number, rv_event_string,
 * rv_event_related_target). */
RV_EXPORT int32_t rv_abi_has(const char* feature);

/* Sets the viewport to width by height CSS pixels, as rv_host_create does. Input coordinates and dirty
 * rectangles are in CSS pixels of the viewport. */
RV_EXPORT int32_t rv_host_resize(RvHost*, int32_t width, int32_t height);
/* Sets the device pixels per CSS pixel, 1 at creation, from 0.25 to 8. rv_host_paint_rgba then paints
 * rv_host_paint_size pixels: the viewport's CSS size times the scale, rounded down. */
RV_EXPORT int32_t rv_host_set_device_scale(RvHost*, float scale);
/* Writes the size in device pixels of the image rv_host_paint_rgba paints. */
RV_EXPORT int32_t rv_host_paint_size(RvHost*, int32_t* width, int32_t* height);

/* Actions of rv_host_mouse. */
enum {
    RV_MOUSE_MOVE = 0,
    RV_MOUSE_DOWN = 1,
    RV_MOUSE_UP = 2,
};

/* Buttons of rv_host_mouse, as MouseEvent.button, and RV_BUTTON_NONE for a move with no button pressed. */
enum {
    RV_BUTTON_NONE = -1,
    RV_BUTTON_LEFT = 0,
    RV_BUTTON_MIDDLE = 1,
    RV_BUTTON_RIGHT = 2,
};

/* Bits of the modifiers of the input functions and of RV_NUMBER_MODIFIERS. */
enum {
    RV_MODIFIER_SHIFT = 1,
    RV_MODIFIER_CONTROL = 2,
    RV_MODIFIER_ALT = 4,
    RV_MODIFIER_META = 8,
};

/* Actions of rv_host_key. */
enum {
    RV_KEY_DOWN = 0,
    RV_KEY_UP = 1,
    RV_KEY_CHAR = 2,
};

/* Native input, handled as the user's: WebCore hit-tests it and dispatches trusted DOM events, then runs each
 * event's default action unless a listener cancelled it, which updates :hover and :active, focus, selection,
 * scrolling and the value of an edited field. x and y are CSS pixels in the viewport. clickCount is 1 for a
 * single press, 2 for a double; a move takes 0. Each returns 1 when the page or WebCore handled the event,
 * 0 when not, or a negative status. */
RV_EXPORT int32_t rv_host_mouse(RvHost*, int32_t action, int32_t x, int32_t y, int32_t button, int32_t clickCount, int32_t modifiers);
/* A wheel event at x, y, which scrolls by deltaX and deltaY CSS pixels, positive right and down. */
RV_EXPORT int32_t rv_host_wheel(RvHost*, int32_t x, int32_t y, float deltaX, float deltaY, int32_t modifiers);
/* key and code are KeyboardEvent.key and KeyboardEvent.code values, such as "a" and "KeyA", or "Enter" for
 * both. A platform sends RV_KEY_DOWN, then RV_KEY_CHAR with text for a key that produces characters, then
 * RV_KEY_UP; text is NULL or empty for the others. RV_KEY_DOWN runs the key's editing command (Backspace,
 * Delete, the arrows, Home, End, Enter, Control+A), and Tab moves focus; RV_KEY_CHAR inserts text into the
 * focused editable element. */
RV_EXPORT int32_t rv_host_key(RvHost*, int32_t action, const char* key, const char* code, const char* text, int32_t modifiers, int32_t repeat);
/* Sets whether the host's window has keyboard focus and is active, as the platform window's focus changes.
 * A host starts unfocused: no caret blinks and :focus-visible does not match until it is focused. */
RV_EXPORT int32_t rv_host_set_focused(RvHost*, int32_t focused);

/* Called on the host thread when the page wants a frame: part of it was invalidated, or WebCore asked for a
 * rendering update, as a running animation or transition does each frame. It is called once until the next
 * rv_host_update or rv_host_paint_rgba, never during them, and must not call this ABI: the app schedules a
 * frame, such as on its next vertical blank, that calls rv_host_update and then rv_host_paint_rgba. */
typedef void (*RvFrameCallback)(void* context);

/* Sets the host's frame callback, or with a NULL callback removes it. */
RV_EXPORT int32_t rv_host_set_frame_callback(RvHost*, RvFrameCallback callback, void* context);
/* Runs WebCore's rendering update for now: animations and transitions advance, resize and intersection
 * observers run, and style and layout update. */
RV_EXPORT int32_t rv_host_update(RvHost*);
/* Writes the bounds of the viewport area invalidated since the last rv_host_paint_rgba, in CSS pixels, and
 * returns 1, or returns 0 and writes zeros when no area was. A scroll of the viewport invalidates all of it. */
RV_EXPORT int32_t rv_host_dirty_rect(RvHost*, int32_t* x, int32_t* y, int32_t* width, int32_t* height);

/* Numbers of rv_event_number. */
enum {
    /* MouseEvent.clientX and clientY, in CSS pixels. */
    RV_NUMBER_CLIENT_X = 0,
    RV_NUMBER_CLIENT_Y = 1,
    /* MouseEvent.button and buttons. */
    RV_NUMBER_BUTTON = 2,
    RV_NUMBER_BUTTONS = 3,
    /* The RV_MODIFIER_* bits of a mouse, wheel or keyboard event. */
    RV_NUMBER_MODIFIERS = 4,
    /* UIEvent.detail: the click count of a mouse event. */
    RV_NUMBER_DETAIL = 5,
    /* WheelEvent.deltaX and deltaY. */
    RV_NUMBER_DELTA_X = 6,
    RV_NUMBER_DELTA_Y = 7,
    /* KeyboardEvent.location and repeat (1 or 0). */
    RV_NUMBER_KEY_LOCATION = 8,
    RV_NUMBER_KEY_REPEAT = 9,
};

/* Strings of rv_event_string. */
enum {
    /* KeyboardEvent.code. */
    RV_EVENT_STRING_CODE = 0,
    /* InputEvent.data and inputType. */
    RV_EVENT_STRING_DATA = 1,
    RV_EVENT_STRING_INPUT_TYPE = 2,
};

/* Writes a number of the event to *value, or returns RV_ERR_UNSUPPORTED when its interface has none. */
RV_EXPORT int32_t rv_event_number(RvEvent*, int32_t number, double* value);
/* Copies a string of the event, or returns RV_ERR_UNSUPPORTED when its interface has none. */
RV_EXPORT int32_t rv_event_string(RvEvent*, int32_t property, char* buffer, int32_t capacity, int32_t* length);
/* The relatedTarget of a mouse or focus event when it is a node, else NULL. */
RV_EXPORT RvNode* rv_event_related_target(RvEvent*);

/* v13: "cursor", "scroll" and "ime" for rv_abi_has. */

/* Cursors of rv_host_cursor, as the CSS cursor values. */
enum {
    RV_CURSOR_DEFAULT = 0,
    RV_CURSOR_POINTER = 1,
    RV_CURSOR_TEXT = 2,
    RV_CURSOR_VERTICAL_TEXT = 3,
    RV_CURSOR_CROSSHAIR = 4,
    RV_CURSOR_MOVE = 5,
    RV_CURSOR_ALL_SCROLL = 6,
    RV_CURSOR_WAIT = 7,
    RV_CURSOR_PROGRESS = 8,
    RV_CURSOR_HELP = 9,
    RV_CURSOR_CONTEXT_MENU = 10,
    RV_CURSOR_CELL = 11,
    RV_CURSOR_ALIAS = 12,
    RV_CURSOR_COPY = 13,
    RV_CURSOR_NO_DROP = 14,
    RV_CURSOR_NOT_ALLOWED = 15,
    RV_CURSOR_GRAB = 16,
    RV_CURSOR_GRABBING = 17,
    RV_CURSOR_ZOOM_IN = 18,
    RV_CURSOR_ZOOM_OUT = 19,
    RV_CURSOR_NONE = 20,
    RV_CURSOR_COL_RESIZE = 21,
    RV_CURSOR_ROW_RESIZE = 22,
    RV_CURSOR_N_RESIZE = 23,
    RV_CURSOR_E_RESIZE = 24,
    RV_CURSOR_S_RESIZE = 25,
    RV_CURSOR_W_RESIZE = 26,
    RV_CURSOR_NE_RESIZE = 27,
    RV_CURSOR_NW_RESIZE = 28,
    RV_CURSOR_SE_RESIZE = 29,
    RV_CURSOR_SW_RESIZE = 30,
    RV_CURSOR_EW_RESIZE = 31,
    RV_CURSOR_NS_RESIZE = 32,
    RV_CURSOR_NESW_RESIZE = 33,
    RV_CURSOR_NWSE_RESIZE = 34,
    /* An image the page set with cursor: url(); the image is not available. */
    RV_CURSOR_CUSTOM = 35,
};

/* The cursor for the mouse's position, as last set by rv_host_mouse: the app applies it after each mouse call. */
RV_EXPORT int32_t rv_host_cursor(RvHost*);

/* Writes the viewport's scroll position in CSS pixels. */
RV_EXPORT int32_t rv_host_scroll_position(RvHost*, int32_t* x, int32_t* y);
/* Scrolls the viewport to x, y CSS pixels, clamped to the document. The scroll event fires on the next
 * rv_host_update. */
RV_EXPORT int32_t rv_host_scroll_to(RvHost*, int32_t x, int32_t y);

/* Input method composition in the focused editable element, as a platform's input method reports it. The
 * composition is the underlined text being composed; selectionStart and selectionEnd are UTF-16 offsets of
 * the selection within it. Setting it replaces the selection or the previous composition, and empty text
 * removes it. */
RV_EXPORT int32_t rv_host_ime_set_composition(RvHost*, const char* text, int32_t selectionStart, int32_t selectionEnd);
/* Replaces the composition, or the selection when there is none, with text, as typed text. */
RV_EXPORT int32_t rv_host_ime_commit(RvHost*, const char* text);
RV_EXPORT int32_t rv_host_ime_cancel(RvHost*);
/* Writes the bounds of the composition's first line, or of the caret, in CSS pixels of the viewport, where an
 * input method places its candidate window, and returns 1; returns 0 and writes zeros when there is neither. */
RV_EXPORT int32_t rv_host_ime_rect(RvHost*, int32_t* x, int32_t* y, int32_t* width, int32_t* height);

#ifdef __cplusplus
}
#endif
