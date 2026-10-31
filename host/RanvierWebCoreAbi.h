/*
 * Ranvier native WebCore C ABI, version 54.
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
 *
 * Strings in (ABI 51, breaking): every generated rv_dom_* string input carries UTF-8 bytes with an explicit byte
 * count, so a string may hold U+0000. A plain argument is a pointer and a length, -1 for null or absent; a string
 * inside a union or sequence is an RvDomUtf8StringSpan; a dictionary string field is an RvDomUtf8StringInput, present
 * 0 for its default. The hand-written functions of this header take NUL-terminated UTF-8.
 */
#pragma once

#include <stdint.h>

#ifndef RV_EXPORT
#if defined(_WIN32)
#define RV_EXPORT __declspec(dllexport)
#else
#define RV_EXPORT __attribute__((visibility("default")))
#endif
#endif

#ifdef __cplusplus
extern "C" {
#endif

typedef struct RvHost RvHost;
typedef struct RvNode RvNode;
typedef struct RvListener RvListener;
typedef struct RvEvent RvEvent;
typedef struct RvWatch RvWatch;
typedef struct RvNodeFilter RvNodeFilter;
typedef struct RvGpuFrame RvGpuFrame;

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
    /* A generated function's handle argument is an object of another interface (RanvierWebCoreDom.h). */
    RV_ERR_WRONG_INTERFACE = -11,
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
    RV_EVENT_CUSTOM = 8,
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
/* Modes of rv_host_set_accelerated_compositing. */
enum {
    /* Every frame is painted on the CPU; 3D transforms are drawn flat and backdrop filters are ignored. */
    RV_COMPOSITING_OFF = 0,
    /* Every frame is composited. */
    RV_COMPOSITING_ALWAYS = 1,
    /* A frame is composited only while some element needs a layer of its own (a 3D transform, a backdrop
     * filter, will-change, an animated transform or opacity, ...); other frames take the CPU path. */
    RV_COMPOSITING_WHEN_NEEDED = 2,
};

/* Sets the accelerated compositing mode. A host is created in RV_COMPOSITING_WHEN_NEEDED when the library has
 * the GPU code, and in RV_COMPOSITING_OFF otherwise. A composited frame is composited with OpenGL ES (ANGLE on
 * Windows) into an offscreen framebuffer and read back, so 3D transforms and backdrop filters render; it can
 * differ from the CPU frame and between GPUs. Returns RV_ERR_UNSUPPORTED, and leaves the mode unchanged, for
 * an unknown mode, when the library was built without the GPU code, or when RV_COMPOSITING_ALWAYS could not
 * create a GL context. RV_COMPOSITING_WHEN_NEEDED creates the context on the first composited frame; if that
 * fails, the host switches to RV_COMPOSITING_OFF and paints that frame on the CPU. */
RV_EXPORT int32_t rv_host_set_accelerated_compositing(RvHost*, int32_t mode);

enum { RV_GPU_RGBA8_PREMULTIPLIED = 1 };
/* Acquires a Windows D3D11 frame without CPU pixel readback. Call rv_host_update before acquire, as before
 * CPU paint, to advance animations and update compositing layers. consumerDevice is a live ID3D11Device*
 * (for SDL, SDL_PROP_RENDERER_D3D11_DEVICE_POINTER). Requires compositing enabled, scale 1 and a GPU build;
 * otherwise returns RV_ERR_UNSUPPORTED so the caller can paint with rv_host_paint_rgba. An outstanding
 * frame on the same surface also returns RV_ERR_UNSUPPORTED immediately. Other GPU waits are bounded.
 * Writes NULL to *frame on failure. The frame owns its resources independently of host/renderer/window;
 * it remains valid over resize or rv_host_destroy and must be released on the owner thread. */
RV_EXPORT int32_t rv_host_acquire_d3d11_frame(RvHost*, void* consumerDevice, RvGpuFrame** frame);
/* Returns a borrowed ID3D11Texture2D*, physical dimensions and RV_GPU_RGBA8_PREMULTIPLIED. Row 0 is the
 * top of the page; channels are sRGB bytes with premultiplied alpha. SDL imports this pointer with
 * SDL_PROP_TEXTURE_CREATE_D3D11_TEXTURE_POINTER and uses SDL_BLENDMODE_BLEND_PREMULTIPLIED (or NONE for
 * an opaque final image). The texture is consumer-locked until release. Do not update or retain it for
 * GPU use after frame release. SDL may retain its COM reference, but must destroy its wrapper before
 * presenting a different resource. All arguments are required and calls use the host owner thread. */
RV_EXPORT int32_t rv_gpu_frame_info(RvGpuFrame*, void** texture, int32_t* width, int32_t* height, int32_t* format);
/* Before release, flush the SDL draw batch (SDL_FlushRenderer) or SDL_RenderPresent. Release flushes
 * the consumer immediate context, returns the keyed mutex to the producer and frees this frame handle.
 * The SDL wrapper and all frame handles must be disposed before unloading their native DLLs. */
RV_EXPORT int32_t rv_gpu_frame_release(RvGpuFrame*);

/* Bits of the capture parameter of rv_node_add_event_listener. Values 0 and 1 retain their original
 * bubbling/capturing behavior. PASSIVE has an effect only together with PASSIVE_SPECIFIED; omitting
 * PASSIVE_SPECIFIED preserves WebCore's event-specific passive default. */
enum {
    RV_LISTENER_CAPTURE = 1,
    RV_LISTENER_PASSIVE = 2,
    RV_LISTENER_PASSIVE_SPECIFIED = 4,
};

/* Registers a WebCore EventListener on target that calls callback(context, event). capture contains
 * RV_LISTENER_* bits. Explicit passive true ignores preventDefault; explicit false permits it for
 * cancelable events. Returns NULL on a NULL argument or the wrong thread. */
RV_EXPORT RvListener* rv_node_add_event_listener(RvNode* target, const char* type, int32_t capture,
    RvEventCallback callback, void* context);
/* Unregisters the listener and frees the handle. The callback will not run after this returns, also
 * when the listener is removed by another listener of the dispatch in progress. */
RV_EXPORT int32_t rv_listener_remove(RvListener*);

/* Returns RV_DOM_NODE_FILTER_FILTER_ACCEPT, _REJECT or _SKIP (1, 2 or 3) for node, which is borrowed for the call.
 * Any other value marks the filter as failed: the traversal stops as for a throwing NodeFilter, its call returns
 * RV_ERR_DOM_EXCEPTION, and rv_last_exception names ExistingExceptionError. */
typedef int32_t (*RvNodeFilterCallback)(void* context, RvNode* node);
/* Runs once with the filter's context, on the owning thread, when the engine drops its last reference. */
typedef void (*RvNodeFilterRelease)(void* context);

/* Creates a NodeFilter for rv_dom_document_create_tree_walker and rv_dom_document_create_node_iterator that calls
 * callback(context, node). The filter belongs to the document of target. The caller owns the returned reference and
 * drops it with rv_dom_node_filter_release; walkers, iterators and filter getter results hold their own. release, when
 * not NULL, runs after the last of those references is dropped. Returns NULL on a NULL argument or the wrong thread. */
RV_EXPORT RvNodeFilter* rv_node_filter_create(RvNode* target, RvNodeFilterCallback callback, void* context,
    RvNodeFilterRelease release);
/* Writes the context passed to rv_node_filter_create to *context, or NULL for a filter the host did not create. */
RV_EXPORT int32_t rv_node_filter_context(RvNodeFilter* filter, void** context);

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

/* Parts of the engine exception behind the latest RV_ERR_DOM_EXCEPTION, for rv_last_exception.
 * Names include the WebIDL TypeError/RangeError/SyntaxError cases as well as DOMException names, and
 * ExistingExceptionError for a failure reported by a host callback such as an RvNodeFilterCallback. */
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

/* A form submission ("form-submission", v42), from requestSubmit, submit, a submit button or implicit submission.
 * method is "GET" or "POST". url is the request URL; a GET carries the entry list in its query. target is the
 * submitter's formtarget, the form's target or the base target, such as "_blank", or "" without one. content_type is NULL for a GET, and is
 * "application/x-www-form-urlencoded", "text/plain" or "multipart/form-data; boundary=..." for a POST. body points to
 * body_length bytes of the encoded entry list, of which a multipart file part carries its headers and no file bytes.
 * form and the submitter, NULL for none, are borrowed. Every pointer is valid only during the callback. */
typedef struct RvFormSubmission {
    uint32_t size;
    const char* method;
    const char* url;
    const char* target;
    const char* content_type;
    const uint8_t* body;
    int32_t body_length;
    RvNode* form;
    RvNode* submitter;
} RvFormSubmission;
/* Called on the host thread from rv_run_loop_cycle, after the call that submitted has returned and its submit and
 * formdata events have run. The document is never navigated, with or without a handler. */
typedef void (*RvFormSubmissionHandler)(void* context, const RvFormSubmission* submission);
/* Sets the host's form submission handler, or with a NULL handler removes it; a submission without a handler is
 * dropped. */
RV_EXPORT int32_t rv_host_set_form_submission_handler(RvHost*, RvFormSubmissionHandler handler, void* context);
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
 * rv_event_related_target). "compositing" is 1 when rv_host_set_accelerated_compositing can composite: the
 * library was built with the GPU code. "presentation-d3d11" is 1 for the Windows shared-texture frame
 * API; successful acquisition additionally depends on the actual GPU, consumer device and scale. */
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

/* v14: "style", "geometry", "animation", "shadow" and "text-selection" for rv_abi_has. */

/* Operations of rv_element_class on Element.classList. */
enum {
    RV_CLASS_CONTAINS = 0,
    RV_CLASS_ADD = 1,
    RV_CLASS_REMOVE = 2,
    RV_CLASS_TOGGLE = 3,
};

/* Applies the operation to a class token and returns 1 when the element has the class afterwards, else 0. */
RV_EXPORT int32_t rv_element_class(RvNode*, const char* token, int32_t operation);
/* Sets an inline style property, as CSSStyleDeclaration.setProperty with "important" priority when important
 * is 1. An empty value removes the property, and an invalid one leaves it unchanged, as in CSS. */
RV_EXPORT int32_t rv_element_set_style(RvNode*, const char* property, const char* value, int32_t important);
/* Copies an inline style property's value, empty when the element does not set it. */
RV_EXPORT int32_t rv_element_get_style(RvNode*, const char* property, char* buffer, int32_t capacity, int32_t* length);
/* Copies a property of the element's computed style, as getComputedStyle, with style updated first. */
RV_EXPORT int32_t rv_element_computed_style(RvNode*, const char* property, char* buffer, int32_t capacity, int32_t* length);

/* Writes Element.getBoundingClientRect() in CSS pixels of the viewport, with layout updated first. */
RV_EXPORT int32_t rv_element_rect(RvNode*, double* x, double* y, double* width, double* height);
/* The topmost element at x, y CSS pixels of the viewport, as Document.elementFromPoint, or NULL. */
RV_EXPORT RvNode* rv_host_element_at(RvHost*, int32_t x, int32_t y);

/* Alignments of rv_element_scroll_into_view, as ScrollLogicalPosition. */
enum {
    RV_ALIGN_START = 0,
    RV_ALIGN_CENTER = 1,
    RV_ALIGN_END = 2,
    RV_ALIGN_NEAREST = 3,
};

/* Scrolls the element's scrollable ancestors and the viewport to show it, aligned on each axis. With smooth
 * set, the scroll animates over the following rendering updates. */
RV_EXPORT int32_t rv_element_scroll_into_view(RvNode*, int32_t block, int32_t inlineAlignment, int32_t smooth);

/* Metrics of rv_element_scroll_metric, as the Element properties of the same names. */
enum {
    RV_SCROLL_LEFT = 0,
    RV_SCROLL_TOP = 1,
    RV_SCROLL_WIDTH = 2,
    RV_SCROLL_HEIGHT = 3,
    RV_CLIENT_WIDTH = 4,
    RV_CLIENT_HEIGHT = 5,
};

/* Writes a scroll metric of the element in CSS pixels, with layout updated first. */
RV_EXPORT int32_t rv_element_scroll_metric(RvNode*, int32_t metric, int32_t* value);
/* Scrolls the element's content to left, top CSS pixels, as Element.scrollTo; with smooth set, animated. */
RV_EXPORT int32_t rv_element_scroll_to(RvNode*, int32_t left, int32_t top, int32_t smooth);

/* Attaches an open shadow root to the element, as Element.attachShadow({ mode: "open" }), and returns it: a
 * node of type 11 that takes children, styles and slots. NULL on failure, with *status
 * RV_ERR_DOM_EXCEPTION and the exception in rv_last_exception. */
RV_EXPORT RvNode* rv_element_attach_shadow(RvNode*, int32_t* status);
/* The element's open shadow root, or NULL. */
RV_EXPORT RvNode* rv_element_shadow_root(RvNode*);

/* Writes the selection of an input or textarea as UTF-16 offsets into its value. */
RV_EXPORT int32_t rv_text_selection(RvNode*, int32_t* start, int32_t* end);
/* Selects start to end of an input or textarea's value, clamped to it. */
RV_EXPORT int32_t rv_text_set_selection(RvNode*, int32_t start, int32_t end);

typedef struct RvAnimation RvAnimation;

/* Writes *count, then a strong handle to each animation of the element, which includes CSS animations and
 * transitions; with subtree set, also its descendants'. Each handle is released with rv_animation_release
 * before rv_host_destroy. When capacity is below *count it returns RV_ERR_BUFFER_TOO_SMALL and writes no
 * handles. */
RV_EXPORT int32_t rv_element_animations(RvNode*, int32_t subtree, RvAnimation** animations, int32_t capacity, int32_t* count);
/* The same for every animation of the host's document. */
RV_EXPORT int32_t rv_host_animations(RvHost*, RvAnimation** animations, int32_t capacity, int32_t* count);
RV_EXPORT void rv_animation_release(RvAnimation*);

/* Actions of rv_animation_control, as the Animation methods of the same names. */
enum {
    RV_ANIMATION_PLAY = 0,
    RV_ANIMATION_PAUSE = 1,
    RV_ANIMATION_REVERSE = 2,
    RV_ANIMATION_FINISH = 3,
    RV_ANIMATION_CANCEL = 4,
};

/* Play states of rv_animation_state, as Animation.playState. */
enum {
    RV_ANIMATION_IDLE = 0,
    RV_ANIMATION_RUNNING = 1,
    RV_ANIMATION_PAUSED = 2,
    RV_ANIMATION_FINISHED = 3,
};

RV_EXPORT int32_t rv_animation_control(RvAnimation*, int32_t action);
RV_EXPORT int32_t rv_animation_state(RvAnimation*);
/* Writes Animation.currentTime in milliseconds and returns 1, or returns 0 when it is unresolved. */
RV_EXPORT int32_t rv_animation_time(RvAnimation*, double* milliseconds);
/* Sets Animation.currentTime in milliseconds. */
RV_EXPORT int32_t rv_animation_seek(RvAnimation*, double milliseconds);
/* Sets the playback rate, as Animation.updatePlaybackRate: 1 is normal speed, negative plays backward. */
RV_EXPORT int32_t rv_animation_set_rate(RvAnimation*, double rate);
/* Copies the CSS animation's name, the CSS transition's property, or the animation's id. */
RV_EXPORT int32_t rv_animation_name(RvAnimation*, char* buffer, int32_t capacity, int32_t* length);
/* A strong handle to the element the animation's effect targets, or NULL. */
RV_EXPORT RvNode* rv_animation_target(RvAnimation*);

/* v15: "observers" and "snapshot" for rv_abi_has. */

/* Adds a reference to the node and returns it, for keeping a node an observer callback passes. */
RV_EXPORT RvNode* rv_node_retain(RvNode*);

typedef struct RvObserver RvObserver;

/* Called on the host thread during rv_host_update, once per observed element whose content box changed size,
 * and once for each element when it is first observed. width and height are CSS pixels. The target is valid
 * for the callback; rv_node_retain keeps it. The callback may call any function of this ABI. */
typedef void (*RvResizeCallback)(void* context, RvNode* target, double width, double height);
/* Called on the host thread during rv_host_update, once per observed element whose intersection with the
 * viewport crossed one of the observer's thresholds, and once for each element when it is first observed.
 * ratio is the visible fraction of the element, from 0 to 1. The target is as for RvResizeCallback. */
typedef void (*RvIntersectionCallback)(void* context, RvNode* target, int32_t intersecting, double ratio);

/* A ResizeObserver, observing elements' content boxes. */
RV_EXPORT RvObserver* rv_host_observe_resize(RvHost*, RvResizeCallback callback, void* context);
/* An IntersectionObserver with the viewport as its root. rootMargin is a CSS margin, such as "0px" or
 * "100px 0px", that grows or shrinks the viewport, or NULL for none; thresholds are the ratios that report,
 * ascending from 0 to 1, or NULL with count 0 for 0 alone. NULL for an invalid margin or threshold. */
RV_EXPORT RvObserver* rv_host_observe_intersection(RvHost*, RvIntersectionCallback callback, void* context, const char* rootMargin,
    const double* thresholds, int32_t thresholdCount);
RV_EXPORT int32_t rv_observer_observe(RvObserver*, RvNode* element);
RV_EXPORT int32_t rv_observer_unobserve(RvObserver*, RvNode* element);
/* Disconnects the observer and frees it, before rv_host_destroy. Its callback will not run after this returns. */
RV_EXPORT void rv_observer_release(RvObserver*);

/* Paints the element and its descendants alone, without what lies behind or over them, at the host's device
 * scale, into unpremultiplied RGBA8, such as for a drag image. Writes the image's size in device pixels to
 * *width and *height; when length is below width * height * 4 it returns RV_ERR_BUFFER_TOO_SMALL with the
 * size written and rgba untouched. */
RV_EXPORT int32_t rv_element_snapshot(RvNode*, uint8_t* rgba, int32_t length, int32_t* width, int32_t* height);

/* v16: "partial-paint" for rv_abi_has. */

/* Paints the area x, y, width, height, in CSS pixels of the viewport and clipped to it, into its place in
 * rgba, an image of rv_host_paint_size as rv_host_paint_rgba writes, and leaves the rest of rgba as it was.
 * After a full paint, painting rv_host_dirty_rect each frame keeps the image current. The dirty rectangle is
 * cleared when the area contains it. At a fractional device scale the area's edges are rounded down to whole
 * device pixels. */
RV_EXPORT int32_t rv_host_paint_rgba_rect(RvHost*, uint8_t* rgba, int32_t length, int32_t x, int32_t y, int32_t width, int32_t height);

/* v17: "popups" and "tooltip" for rv_abi_has. */

typedef struct RvPopup RvPopup;

/* Actions of RvPopupCallback. */
enum {
    /* A <select> opens its menu: the app shows the items at the select's box, x, y, width, height in CSS
     * pixels of the viewport, with item selected highlighted, then calls rv_popup_choose. */
    RV_POPUP_SHOW = 0,
    /* The page closes the menu, such as when the select is removed: the app hides it, and the popup is
     * invalid once the callback returns. */
    RV_POPUP_HIDE = 1,
};

/* Kinds of rv_popup_item. */
enum {
    RV_POPUP_ITEM_OPTION = 0,
    RV_POPUP_ITEM_SEPARATOR = 1,
    /* An <optgroup> label. */
    RV_POPUP_ITEM_GROUP = 2,
};

/* Called on the host thread for a <select>'s menu. */
typedef void (*RvPopupCallback)(void* context, RvPopup* popup, int32_t action, int32_t x, int32_t y, int32_t width, int32_t height,
    int32_t selected);

/* Sets the host's popup handler, which shows <select> menus as the app's own native menus, or with a NULL
 * handler removes it. Without a handler a select opens no menu, and the page draws its own, such as on
 * mousedown. */
RV_EXPORT int32_t rv_host_set_popup_handler(RvHost*, RvPopupCallback callback, void* context);
RV_EXPORT int32_t rv_popup_item_count(RvPopup*);
/* Writes the item's kind and whether it is enabled, and copies its text as WebCore's own menus show it: the
 * options of an <optgroup> are indented by four spaces, and a group label is not enabled. */
RV_EXPORT int32_t rv_popup_item(RvPopup*, int32_t index, int32_t* kind, int32_t* enabled, char* buffer, int32_t capacity, int32_t* length);
/* Ends the menu with the item at index chosen, which selects it and fires input and change, or with -1 for
 * none. The popup is invalid after the call. */
RV_EXPORT int32_t rv_popup_choose(RvPopup*, int32_t index);

/* Copies the tooltip for the mouse's position, the title attribute of the element under it, as last set by
 * rv_host_mouse: empty when there is none. The app shows it after its own hover delay. */
RV_EXPORT int32_t rv_host_tooltip(RvHost*, char* buffer, int32_t capacity, int32_t* length);

/* v18: "clipboard" for rv_abi_has. docs/CLIPBOARD-DND.md describes the styles. */

/* Clipboard styles of rv_host_set_clipboard. */
enum {
    /* The app moves the data, through the write and read callbacks. */
    RV_CLIPBOARD_APP = 0,
    /* WebCore's own platform clipboard code: Windows and macOS. */
    RV_CLIPBOARD_NATIVE = 1,
    /* Only the page sees the data, through copy, cut and paste events. A host starts in this style. */
    RV_CLIPBOARD_DOM = 2,
};

/* Editing commands of rv_host_edit. */
enum {
    RV_EDIT_COPY = 0,
    RV_EDIT_CUT = 1,
    RV_EDIT_PASTE = 2,
    /* Pastes text/plain only. */
    RV_EDIT_PASTE_PLAIN = 3,
    RV_EDIT_SELECT_ALL = 4,
    RV_EDIT_DELETE = 5,
};

typedef struct RvClipboardRequest RvClipboardRequest;

/* App style: called once per copied type, such as "text/plain" and "text/html", in order. first is 1 for the
 * first type of a copy or cut, when the app replaces what its clipboard held. */
typedef void (*RvClipboardWrite)(void* context, const char* type, const char* data, int32_t first);
/* App style: called at a paste; the app offers each type it holds with rv_clipboard_offer before it returns. */
typedef void (*RvClipboardRead)(void* context, RvClipboardRequest* request);

/* Sets the host's clipboard style. The callbacks are for RV_CLIPBOARD_APP and NULL otherwise.
 * RV_CLIPBOARD_NATIVE returns RV_ERR_UNSUPPORTED where WebCore has no platform clipboard (Linux). */
RV_EXPORT int32_t rv_host_set_clipboard(RvHost*, int32_t style, RvClipboardWrite write, RvClipboardRead read, void* context);
/* Offers one type of the clipboard's content to a paste, during RvClipboardRead. */
RV_EXPORT int32_t rv_clipboard_offer(RvClipboardRequest*, const char* type, const char* data);
/* Runs an editing command on the selection of the host's document, as a menu would; Control+C, X and V in
 * rv_host_key run the same commands. Copy, cut and paste fire their DOM events first, and a page that
 * cancels one supplies or takes the data itself. Returns 1 when the command ran, 0 when it does not apply,
 * such as a copy with nothing selected, or a negative status. */
RV_EXPORT int32_t rv_host_edit(RvHost*, int32_t command);

/* v19: "drop" for rv_abi_has: drags from outside into the page. docs/CLIPBOARD-DND.md describes the styles. */

/* Drag styles of rv_host_set_drag. */
enum {
    /* The app forwards the OS drag with rv_host_drag, and the host fires the DOM drag events. */
    RV_DRAG_APP = 0,
    /* WebCore's own platform drag code. Not yet supported: rv_host_set_drag returns RV_ERR_UNSUPPORTED. */
    RV_DRAG_NATIVE = 1,
    /* No drag reaches the page: rv_host_drag fires nothing. A host starts in this style. */
    RV_DRAG_DOM = 2,
};

/* Bits of the operations of rv_host_drag, as the DataTransfer effects copy, move and link. */
enum {
    RV_DROP_NONE = 0,
    RV_DROP_COPY = 1,
    RV_DROP_MOVE = 2,
    RV_DROP_LINK = 4,
};

/* Actions of rv_host_drag. */
enum {
    /* The drag entered the view or moved over it. */
    RV_DRAG_OVER = 0,
    /* The drag left the view or was cancelled. */
    RV_DRAG_LEAVE = 1,
    /* The drag was released over the view. */
    RV_DRAG_DROP = 2,
};

typedef struct RvDragData RvDragData;

RV_EXPORT int32_t rv_host_set_drag(RvHost*, int32_t style);
/* The data of a drag, of types such as "text/plain", "text/html" and "text/uri-list" (file URLs for files). */
RV_EXPORT RvDragData* rv_drag_data_create(void);
RV_EXPORT int32_t rv_drag_data_add(RvDragData*, const char* type, const char* data);
RV_EXPORT void rv_drag_data_release(RvDragData*);
/* Forwards a drag from outside the page at x, y CSS pixels of the viewport, with the RV_DROP_* operations
 * the source allows. As the element under the point changes the host fires dragleave and dragenter, then
 * dragover, or drop for RV_DRAG_DROP, each with a dataTransfer holding data; drop's data is readable. Returns
 * the RV_DROP_* operation the page accepts, which the app shows as the cursor: the dataTransfer's dropEffect
 * when a listener cancelled dragover, else RV_DROP_COPY for text over editable content, else RV_DROP_NONE.
 * A drop that no listener cancels inserts the text, or the HTML, into editable content at the point. */
RV_EXPORT int32_t rv_host_drag(RvHost*, int32_t action, int32_t x, int32_t y, int32_t allowed, RvDragData* data, int32_t modifiers);

/* v20: "drag-out" for rv_abi_has: drags that start in the page. */

typedef struct RvDrag RvDrag;

/* Called on the host thread when the user drags a draggable element, a link, an image or a selection with
 * the mouse, in the App drag style, after the page's dragstart listeners have set the data. x and y are where
 * the press was, in CSS pixels of the viewport; allowed holds the RV_DROP_* operations the page allows. The
 * app reads the drag's data and image, runs the drag, such as an OS drag session or a drag inside the page
 * fed back through rv_host_drag, and ends it with rv_drag_end. */
typedef void (*RvDragStartCallback)(void* context, RvDrag* drag, int32_t x, int32_t y, int32_t allowed);

/* Sets the host's drag start callback, or with a NULL callback removes it. Without one, or in the DOM style,
 * no drag starts in the page. */
RV_EXPORT int32_t rv_host_set_drag_start(RvHost*, RvDragStartCallback callback, void* context);
RV_EXPORT int32_t rv_drag_item_count(RvDrag*);
/* Copies the type or the value of the drag's item at index. */
RV_EXPORT int32_t rv_drag_item_type(RvDrag*, int32_t index, char* buffer, int32_t capacity, int32_t* length);
RV_EXPORT int32_t rv_drag_item_value(RvDrag*, int32_t index, char* buffer, int32_t capacity, int32_t* length);
/* A copy of the drag's items as drag data, for rv_host_drag; released with rv_drag_data_release. */
RV_EXPORT RvDragData* rv_drag_data(RvDrag*);
/* Paints the dragged element as rv_element_snapshot does, and writes where the press was within the image,
 * in device pixels, to *offsetX and *offsetY. RV_ERR_UNSUPPORTED for a selection drag, which has no element. */
RV_EXPORT int32_t rv_drag_image(RvDrag*, uint8_t* rgba, int32_t length, int32_t* width, int32_t* height, int32_t* offsetX, int32_t* offsetY);
/* Ends the drag at x, y CSS pixels of the viewport with the RV_DROP_* operation the drop target accepted, or
 * RV_DROP_NONE when the drag was cancelled: the page's dragend fires with it. The drag is invalid after the
 * call. */
RV_EXPORT int32_t rv_drag_end(RvDrag*, int32_t x, int32_t y, int32_t operation);

/* "accessibility" for rv_abi_has: the page's accessibility tree, which the app exposes through the platform's
 * accessibility API (UI Automation, NSAccessibility, AT-SPI). docs/ACCESSIBILITY.md describes the model.
 *
 * An RvAxNode is a strong reference to one of WebCore's accessibility objects, released with rv_ax_release
 * before rv_host_destroy; two handles to the same object compare equal. The tree holds the objects a screen
 * reader sees: elements that are hidden, presentational or purely structural have no node of their own, and
 * their children are children of the nearest exposed ancestor. When the DOM node behind an object is
 * removed, the object is detached: its handle stays valid, rv_ax_role returns RV_ERR_DETACHED, and the
 * other functions return RV_ERR_DETACHED or NULL. Geometry is in CSS pixels of the viewport, as
 * rv_element_rect. */

typedef struct RvAxNode RvAxNode;

enum {
    RV_ERR_DETACHED = -10,
};

/* Roles of rv_ax_role: a small, stable set that maps onto each platform's control types. RV_AX_ROLE_NAME
 * gives the ARIA role WebCore computed, for an app that maps more finely. */
enum {
    RV_ROLE_UNKNOWN = 0,
    /* The page itself: the root of the tree. */
    RV_ROLE_DOCUMENT = 1,
    RV_ROLE_APPLICATION = 2,
    /* A container with no semantics of its own, such as a <div> with a name or an inline element. */
    RV_ROLE_GENERIC = 3,
    RV_ROLE_GROUP = 4,
    /* A run of text. */
    RV_ROLE_TEXT = 5,
    RV_ROLE_PARAGRAPH = 6,
    RV_ROLE_HEADING = 7,
    RV_ROLE_LINK = 8,
    RV_ROLE_BUTTON = 9,
    RV_ROLE_TOGGLE_BUTTON = 10,
    RV_ROLE_CHECKBOX = 11,
    RV_ROLE_RADIO = 12,
    RV_ROLE_RADIO_GROUP = 13,
    RV_ROLE_SWITCH = 14,
    /* A single-line text field, including search, number and date fields. */
    RV_ROLE_TEXT_FIELD = 15,
    /* A multi-line text field. */
    RV_ROLE_TEXT_AREA = 16,
    /* A combo box, including a single-selection <select>. */
    RV_ROLE_COMBO_BOX = 17,
    RV_ROLE_LIST_BOX = 18,
    RV_ROLE_OPTION = 19,
    RV_ROLE_MENU = 20,
    RV_ROLE_MENU_BAR = 21,
    RV_ROLE_MENU_ITEM = 22,
    RV_ROLE_MENU_ITEM_CHECKBOX = 23,
    RV_ROLE_MENU_ITEM_RADIO = 24,
    RV_ROLE_SLIDER = 25,
    RV_ROLE_SPIN_BUTTON = 26,
    RV_ROLE_PROGRESS = 27,
    RV_ROLE_METER = 28,
    RV_ROLE_SCROLL_BAR = 29,
    RV_ROLE_IMAGE = 30,
    RV_ROLE_LIST = 31,
    RV_ROLE_LIST_ITEM = 32,
    /* A term and its definition, as in a description list. */
    RV_ROLE_TERM = 33,
    RV_ROLE_DEFINITION = 34,
    RV_ROLE_TABLE = 35,
    RV_ROLE_GRID = 36,
    RV_ROLE_TREE_GRID = 37,
    RV_ROLE_ROW = 38,
    RV_ROLE_CELL = 39,
    RV_ROLE_COLUMN_HEADER = 40,
    RV_ROLE_ROW_HEADER = 41,
    RV_ROLE_TREE = 42,
    RV_ROLE_TREE_ITEM = 43,
    RV_ROLE_TAB_LIST = 44,
    RV_ROLE_TAB = 45,
    RV_ROLE_TAB_PANEL = 46,
    RV_ROLE_DIALOG = 47,
    RV_ROLE_ALERT_DIALOG = 48,
    RV_ROLE_ALERT = 49,
    RV_ROLE_STATUS = 50,
    RV_ROLE_LOG = 51,
    RV_ROLE_MARQUEE = 52,
    RV_ROLE_TIMER = 53,
    RV_ROLE_TOOLTIP = 54,
    RV_ROLE_TOOLBAR = 55,
    RV_ROLE_SEPARATOR = 56,
    /* Landmarks. */
    RV_ROLE_BANNER = 57,
    RV_ROLE_NAVIGATION = 58,
    RV_ROLE_MAIN = 59,
    RV_ROLE_COMPLEMENTARY = 60,
    RV_ROLE_CONTENT_INFO = 61,
    RV_ROLE_REGION = 62,
    RV_ROLE_SEARCH = 63,
    RV_ROLE_FORM = 64,
    RV_ROLE_ARTICLE = 65,
    RV_ROLE_FEED = 66,
    RV_ROLE_FIGURE = 67,
    RV_ROLE_NOTE = 68,
    RV_ROLE_MATH = 69,
    /* A label, legend or caption that names another element. */
    RV_ROLE_LABEL = 70,
};

/* Bits of rv_ax_states. */
enum {
    RV_AX_FOCUSABLE = 1 << 0,
    RV_AX_FOCUSED = 1 << 1,
    RV_AX_DISABLED = 1 << 2,
    /* The node has a checked state: a checkbox, radio, switch or checkable menu item. */
    RV_AX_CHECKABLE = 1 << 3,
    RV_AX_CHECKED = 1 << 4,
    /* Neither checked nor unchecked: an indeterminate checkbox, or aria-checked="mixed". */
    RV_AX_MIXED = 1 << 5,
    /* A toggle button that is pressed. */
    RV_AX_PRESSED = 1 << 6,
    /* The node expands and collapses, and RV_AX_EXPANDED tells which it is. */
    RV_AX_EXPANDABLE = 1 << 7,
    RV_AX_EXPANDED = 1 << 8,
    RV_AX_SELECTABLE = 1 << 9,
    RV_AX_SELECTED = 1 << 10,
    RV_AX_MULTISELECTABLE = 1 << 11,
    /* rv_ax_set_value, or rv_ax_set_number for a range, changes the node's value. */
    RV_AX_EDITABLE = 1 << 12,
    RV_AX_REQUIRED = 1 << 13,
    RV_AX_INVALID = 1 << 14,
    RV_AX_MULTILINE = 1 << 15,
    /* A password field: the value is not exposed. */
    RV_AX_PROTECTED = 1 << 16,
    RV_AX_VISITED = 1 << 17,
    RV_AX_BUSY = 1 << 18,
    RV_AX_MODAL = 1 << 19,
    RV_AX_HAS_POPUP = 1 << 20,
    /* The node lies outside the viewport, or is scrolled out of view. */
    RV_AX_OFFSCREEN = 1 << 21,
    /* The node is a live region: RV_AX_LIVE is "polite" or "assertive". */
    RV_AX_LIVE_REGION = 1 << 22,
};

/* Strings of rv_ax_string. Each is empty when the node has none. */
enum {
    /* The accessible name, from the ARIA name computation: aria-labelledby, aria-label, a <label>, alt, the
     * contents, title. */
    RV_AX_NAME = 0,
    /* The accessible description: aria-describedby, aria-description, or a title not used for the name. */
    RV_AX_DESCRIPTION = 1,
    /* The value: a text field's text, a combo box's selected option, a range's value as text. Empty for a
     * password field. */
    RV_AX_VALUE = 2,
    /* The ARIA role WebCore computed, such as "button" or "textbox". */
    RV_AX_ROLE_NAME = 3,
    /* aria-roledescription. */
    RV_AX_ROLE_DESCRIPTION = 4,
    RV_AX_PLACEHOLDER = 5,
    /* aria-keyshortcuts. */
    RV_AX_KEY_SHORTCUTS = 6,
    /* A link's URL. */
    RV_AX_URL = 7,
    /* The live region politeness of the node: "polite", "assertive", or empty. */
    RV_AX_LIVE = 8,
    /* The text of the node's descendants, such as what a live region says when it changes. */
    RV_AX_TEXT = 9,
};

/* Numbers of rv_ax_number. */
enum {
    /* A range's value, minimum and maximum: a slider, spin button, progress bar, meter or scroll bar. */
    RV_AX_NUMBER_VALUE = 0,
    RV_AX_NUMBER_MIN = 1,
    RV_AX_NUMBER_MAX = 2,
    /* A heading's level from 1 to 6, or a tree item's level from 1. */
    RV_AX_NUMBER_LEVEL = 3,
};

/* Actions of rv_ax_action. */
enum {
    /* The node's default action, as a click: presses a button, follows a link, toggles a checkbox. */
    RV_AX_PRESS = 0,
    RV_AX_FOCUS = 1,
    /* Scrolls the node's scrollable ancestors and the viewport to show it. */
    RV_AX_SCROLL_INTO_VIEW = 2,
    /* Steps a range's value, as the arrow keys do. */
    RV_AX_INCREMENT = 3,
    RV_AX_DECREMENT = 4,
    RV_AX_EXPAND = 5,
    RV_AX_COLLAPSE = 6,
    /* Selects an option, tab, row or other selectable node. */
    RV_AX_SELECT = 7,
};

/* Events of RvAxCallback. */
enum {
    /* The node gained keyboard focus, or became the active descendant of the focused node. */
    RV_AX_EVENT_FOCUS = 0,
    /* Nodes were added to or removed from the node's children: the app reads them again. */
    RV_AX_EVENT_CHILDREN = 1,
    RV_AX_EVENT_VALUE = 2,
    /* One of the node's rv_ax_states changed. */
    RV_AX_EVENT_STATE = 3,
    RV_AX_EVENT_NAME = 4,
    RV_AX_EVENT_DESCRIPTION = 5,
    RV_AX_EVENT_ROLE = 6,
    /* The node was selected or deselected, or the selection among the node's children changed. */
    RV_AX_EVENT_SELECTION = 7,
    /* The contents of the live region at node changed; the app announces RV_AX_TEXT with the node's RV_AX_LIVE
     * politeness. */
    RV_AX_EVENT_LIVE_REGION = 8,
    /* The document finished loading. */
    RV_AX_EVENT_LOAD_COMPLETE = 9,
    /* Layout or scrolling moved nodes: the app reads bounds again. */
    RV_AX_EVENT_LAYOUT = 10,
    RV_AX_EVENT_MENU_OPENED = 11,
    RV_AX_EVENT_MENU_CLOSED = 12,
    /* "accessibility-text": text was inserted into or deleted from the editable content at node, which is a text
     * field or the editable node where the edit happened; the app reads its text again. */
    RV_AX_EVENT_TEXT = 13,
    /* "accessibility-text": the selection or caret moved within the text of node, or of the text field node. */
    RV_AX_EVENT_TEXT_SELECTION = 14,
};

/* Called on the host thread from rv_run_loop_cycle, once per node and event since the previous call, in the
 * order WebCore posted them, where rv_abi_has("accessibility-events") is 1: a WebCore built with
 * USE_AX_EMBEDDER_NOTIFICATIONS (patch 0011), as the slim flavor is. Elsewhere it is never called. WebCore
 * posts as it updates the tree: in rv_host_update after a DOM change, in its timers, and in the reads below. The node is valid for the callback; rv_ax_retain keeps it. The callback may call
 * any function of this ABI. */
typedef void (*RvAxCallback)(void* context, RvAxNode* node, int32_t event);

/* Turns accessibility on or off for the host, and sets the callback for its events, or with a NULL callback
 * removes it. WebCore keeps one accessibility mode per process: it builds the tree for every page while any
 * host has accessibility on, and stops when the last host turns it off. A host starts with it off, and the
 * functions below that start from the host return NULL. Returns RV_ERR_UNSUPPORTED when WebCore made no
 * accessibility cache for the host's document. */
RV_EXPORT int32_t rv_host_set_accessibility(RvHost*, int32_t enabled, RvAxCallback callback, void* context);

/* Windows UI Automation bridge ("accessibility-uia"). Attach on the host/window owner thread after the
 * HWND is fully initialized. The bridge owns the accessibility callback until detached, so do not replace
 * it with rv_host_set_accessibility while attached. One attachment per host and HWND. The window's message
 * loop must keep pumping while UI Automation clients query it. No managed COM interop is required.
 * Detach on the same thread, before destroying either the host or HWND; it is idempotent. Outstanding UIA
 * references become unavailable. rv_host_destroy also detaches. Non-Windows builds return UNSUPPORTED. */
RV_EXPORT int32_t rv_host_attach_uia(RvHost*, void* hwnd);
RV_EXPORT int32_t rv_host_detach_uia(RvHost*);
/* The root of the host's tree, of role RV_ROLE_DOCUMENT, with layout and the tree updated first; NULL while
 * accessibility is off. */
RV_EXPORT RvAxNode* rv_host_ax_root(RvHost*);
/* The node with keyboard focus, or the root when no element has focus; NULL while accessibility is off. */
RV_EXPORT RvAxNode* rv_host_ax_focus(RvHost*);
/* The deepest node at x, y CSS pixels of the viewport, or NULL. */
RV_EXPORT RvAxNode* rv_host_ax_hit_test(RvHost*, int32_t x, int32_t y);
/* The node of a DOM node, or NULL when the DOM node has none: it is not exposed, or accessibility is off. */
RV_EXPORT RvAxNode* rv_node_ax(RvNode*);
/* The DOM node behind the node, or NULL for a node WebCore made without one, such as a list marker. */
RV_EXPORT RvNode* rv_ax_dom_node(RvAxNode*);
/* Adds a reference to the node and returns it, for keeping a node a callback passes. */
RV_EXPORT RvAxNode* rv_ax_retain(RvAxNode*);
RV_EXPORT void rv_ax_release(RvAxNode*);
/* WebCore's identifier of the node's object: positive, unique in the process and never reused, for a
 * platform's runtime identifiers. A negative status on failure. */
RV_EXPORT int64_t rv_ax_id(RvAxNode*);
/* An RV_ROLE_* value, or a negative status. */
RV_EXPORT int32_t rv_ax_role(RvAxNode*);
/* The RV_AX_* state bits, or a negative status. */
RV_EXPORT int32_t rv_ax_states(RvAxNode*);
RV_EXPORT int32_t rv_ax_string(RvAxNode*, int32_t property, char* buffer, int32_t capacity, int32_t* length);
/* Writes a number of the node, or returns RV_ERR_UNSUPPORTED when the node has none: a range for the values,
 * a heading or tree item for the level. */
RV_EXPORT int32_t rv_ax_number(RvAxNode*, int32_t property, double* value);
/* Writes the node's bounds in CSS pixels of the viewport, with layout updated first. */
RV_EXPORT int32_t rv_ax_rect(RvAxNode*, double* x, double* y, double* width, double* height);
/* The node's parent, or NULL for the root. */
RV_EXPORT RvAxNode* rv_ax_parent(RvAxNode*);
/* Writes *count, then a handle to each child in order. When capacity is below *count it returns
 * RV_ERR_BUFFER_TOO_SMALL and writes no handles, so capacity 0 reads the count. */
RV_EXPORT int32_t rv_ax_children(RvAxNode*, RvAxNode** nodes, int32_t capacity, int32_t* count);

/* v49: "accessibility-relations" for rv_abi_has. Kinds of rv_ax_relations: the node's ARIA relationship targets,
 * from the attribute's ID references or the elements set through the matching Element.aria*Element(s) reflection. */
enum {
    RV_AX_RELATION_ACTIVE_DESCENDANT = 0,
    RV_AX_RELATION_CONTROLS = 1,
    RV_AX_RELATION_DESCRIBED_BY = 2,
    RV_AX_RELATION_DETAILS = 3,
    RV_AX_RELATION_ERROR_MESSAGE = 4,
    RV_AX_RELATION_FLOW_TO = 5,
    RV_AX_RELATION_LABELLED_BY = 6,
    RV_AX_RELATION_OWNS = 7,
};
/* Writes *count, then a new reference to each target of the relation kind, in the order WebCore records them: the
 * reference order of the attribute or the reflected elements, each target once. A target without an accessible
 * object is left out. As rv_ax_children, capacity below *count returns RV_ERR_BUFFER_TOO_SMALL and writes no
 * handles; an unknown kind returns RV_ERR_UNSUPPORTED, and a node whose object is gone RV_ERR_DETACHED. */
RV_EXPORT int32_t rv_ax_relations(RvAxNode*, int32_t kind, RvAxNode** nodes, int32_t capacity, int32_t* count);
/* Performs an action, as an assistive technology asks. Returns 1 when the node performed it, 0 when the action
 * does not apply to the node, or a negative status. */
RV_EXPORT int32_t rv_ax_action(RvAxNode*, int32_t action);
/* Sets the value of an editable text field. An <input> or <textarea> fires input and change, as after a user's
 * edit; other editable content takes the text as WebCore's platform accessibility sets it. Returns 1 when set,
 * 0 when the node's value is not editable, or a negative status. */
RV_EXPORT int32_t rv_ax_set_value(RvAxNode*, const char* value);
/* Sets the value of a range, such as a slider, clamped to its minimum and maximum; a range <input> fires input
 * and change. Returns as rv_ax_set_value. */
RV_EXPORT int32_t rv_ax_set_number(RvAxNode*, double value);

/* "accessibility-text" for rv_abi_has: a node's text, for UI Automation's TextPattern, NSAccessibility's text
 * attributes and AT-SPI's Text interface. A node's text is its DOM node's rendered text as the page reads it,
 * with a newline between blocks; a text field's is its value, masked with U+2022 for a password field. Offsets
 * are UTF-16 code units from 0 to rv_ax_text_length. Each function returns RV_ERR_UNSUPPORTED for a node
 * without a DOM node, such as a list marker, and for an offset or range outside the text. Layout is updated
 * first. */

/* Units of rv_ax_text_boundary. */
enum {
    /* One character: a UTF-16 code unit, or a surrogate pair. */
    RV_TEXT_CHARACTER = 0,
    RV_TEXT_WORD = 1,
    /* A line as laid out, which wraps with the width of its box. */
    RV_TEXT_LINE = 2,
    RV_TEXT_SENTENCE = 3,
    RV_TEXT_PARAGRAPH = 4,
};

/* The length of the node's text in UTF-16 code units, or a negative status. */
RV_EXPORT int32_t rv_ax_text_length(RvAxNode*);
/* Copies the text from start to end, UTF-16 offsets, as UTF-8. */
RV_EXPORT int32_t rv_ax_text(RvAxNode*, int32_t start, int32_t end, char* buffer, int32_t capacity, int32_t* length);
/* Writes the start and end of the unit that contains offset: for a word, the word or the space after it as
 * WebCore's word breaking finds them; for a line, sentence or paragraph, the unit with the newline that ends it.
 * At the end of the text, the last unit, or for a character an empty range. A UI Automation text range moves by
 * calling this at its ends; AT-SPI's GetStringAtOffset and NSAccessibility's ranges for a line read it once. */
RV_EXPORT int32_t rv_ax_text_boundary(RvAxNode*, int32_t offset, int32_t unit, int32_t* start, int32_t* end);
/* Writes the part of the page's selection within the node's text and returns 1: a caret as start equal to end,
 * a selection clipped to the text. Returns 0 and writes -1 when the selection lies outside the text. */
RV_EXPORT int32_t rv_ax_text_selection(RvAxNode*, int32_t* start, int32_t* end);
/* The offset of the caret, the selection's moving end, in the node's text, or -1 when it lies outside it. */
RV_EXPORT int32_t rv_ax_text_caret(RvAxNode*);
/* Selects the text from start to end, or places the caret when they are equal, as the page's selection. */
RV_EXPORT int32_t rv_ax_text_set_selection(RvAxNode*, int32_t start, int32_t end);
/* Writes *count, then x, y, width, height for each rectangle the text from start to end covers, in CSS pixels of
 * the viewport: one per line box of each text run, or the caret's rectangle when start equals end. rects holds
 * capacity rectangles, 4 doubles each; when capacity is below *count it returns RV_ERR_BUFFER_TOO_SMALL and
 * writes none. */
RV_EXPORT int32_t rv_ax_text_rects(RvAxNode*, int32_t start, int32_t end, double* rects, int32_t capacity, int32_t* count);
/* The offset in the node's text nearest x, y CSS pixels of the viewport, or -1 when that point's text lies outside
 * the node. */
RV_EXPORT int32_t rv_ax_text_offset_at(RvAxNode*, int32_t x, int32_t y);

/* The descendant's text range in ancestor's UTF-16 text coordinates, for UIA RangeFromChild. Returns
 * UNSUPPORTED when child is outside ancestor's text scope. A text field's inner-editor value does not
 * appear in its ancestor's plain text: its position there can therefore be an empty range. */
RV_EXPORT int32_t rv_ax_text_child_range(RvAxNode* ancestor, RvAxNode* child, int32_t* start, int32_t* end);

/* Replaces the main frame with UTF-8 image/svg+xml, with scripts disabled. Malformed XML loads the engine's parser-error document. */
RV_EXPORT int32_t rv_host_load_svg(RvHost*, const char* svg);

/* Passive capability queries. Categories: ABI=0, renderer setting=1, image format=2,
 * font format=3, platform facility=4. Dimensions: exported=0, implemented=1, enabled=2,
 * permitted=3, available=4. Facts: unknown=-1, no=0, yes=1. Arbitrary unknown names stay unknown.
 * Value kinds: absent=0, boolean=1, number=2, text=3. Boolean numeric values are exactly 0/1.
 * Wrong-kind getters return RV_ERR_UNSUPPORTED with outputs untouched. String length/capacity
 * count exact UTF-8 bytes, without a NUL terminator, following the existing string transport. */
RV_EXPORT int32_t rv_capability_count(int32_t category);
RV_EXPORT int32_t rv_capability_name_at(int32_t category, int32_t index, char* buffer, int32_t capacity, int32_t* length);
RV_EXPORT int32_t rv_host_capability_fact(RvHost*, int32_t category, const char* name, int32_t dimension, int32_t* fact);
RV_EXPORT int32_t rv_host_capability_value_kind(RvHost*, int32_t category, const char* name, int32_t* kind);
RV_EXPORT int32_t rv_host_capability_value_number(RvHost*, int32_t category, const char* name, double* number);
RV_EXPORT int32_t rv_host_capability_value_text(RvHost*, int32_t category, const char* name, char* buffer, int32_t capacity, int32_t* length);

/* Selects a fragment in the current main SVG document only; it does not navigate, update history or promise :target.
 * Empty clears the active view and writes selected=0. A missing/malformed fragment clears the previous view and
 * writes the engine's false result with RV_OK. Argument/thread/document errors preserve *selected and SVG state.
 * The UTF-8 fragment is passed directly to the engine, without adding/removing '#' or URL parsing. */
RV_EXPORT int32_t rv_host_select_svg_view(RvHost*, const char* fragment, int32_t* selected);

/* Image decode readiness ("image-decode"), without JavaScript or a promise. */
enum {
    RV_RESOURCE_SUCCEEDED = 0,
    RV_RESOURCE_LOAD_FAILED = 1,
    RV_RESOURCE_DECODE_FAILED = 2,
    RV_RESOURCE_CANCELLED = 3,
    RV_RESOURCE_INVALIDATED = 4,
};

/* Receives exactly one terminal outcome per operation on the owning thread. width and height are the image's natural
 * size on RV_RESOURCE_SUCCEEDED and 0 otherwise. */
typedef void (*RvResourceCompletion)(void* context, int32_t outcome, int32_t width, int32_t height);

/* Observes an existing <img> or SVG <image> in the host's current document without changing or refetching it, and
 * writes an operation token. The element's ImageLoader settles the operation where it settles HTMLImageElement.decode():
 * SUCCEEDED after the decoder completes for a bitmap, or once loading finishes for an SVG image, which has no separate
 * decode stage; INVALIDATED for a source change or an inactive document; CANCELLED for a cancelled load; LOAD_FAILED
 * for a missing source, a load error or an access-control error; DECODE_FAILED for an invalid bitmap.
 * The completion is never called before rv_image_decode returns; a terminal reached during the call is delivered on
 * a later rv_run_loop_cycle, or by rv_resource_cancel/rv_resource_release, whichever is first. Other engine
 * terminals are delivered from the engine callback that produces them. Returns RV_ERR_UNSUPPORTED for another
 * element type or a target outside the host's document. */
RV_EXPORT int32_t rv_image_decode(RvHost*, RvNode* image, RvResourceCompletion completion, void* context, uint64_t* operation);
/* Font readiness ("font-load"), without JavaScript or a promise: builds a FontFace for family from length bytes,
 * which are copied before the call returns, and writes an operation token. SUCCEEDED follows the face's own loaded
 * state and adds it to the host document's FontFaceSet; DECODE_FAILED reports bytes the engine cannot use as a font,
 * including empty bytes. A succeeded font stays in the document's fonts until rv_resource_release, rv_host_destroy
 * or a new document removes it. width and height are 0. Delivery, cancel and release follow rv_image_decode.
 * Returns RV_ERR_UNSUPPORTED for an empty or non-UTF-8 family. */
RV_EXPORT int32_t rv_font_load(RvHost*, const char* family, const uint8_t* data, int32_t length, RvResourceCompletion completion, void* context, uint64_t* operation);
/* Delivers CANCELLED to an in-flight operation, or a pending terminal already reached, before returning. */
RV_EXPORT int32_t rv_resource_cancel(uint64_t operation);
/* Ends the operation as rv_resource_cancel does, then unregisters it; the completion and its context are not used
 * afterwards. Every operation requires one release; repeated and unknown tokens return RV_OK. rv_host_destroy and
 * a new document deliver INVALIDATED to in-flight operations and release them; a terminal operation stays
 * registered until released and holds no document. */
RV_EXPORT int32_t rv_resource_release(uint64_t operation);

/* Event construction and standalone targets ("event-construction", v32). */
typedef struct RvEventTarget RvEventTarget;

/* Kinds of rv_host_construct_event; each uses the engine's constructor for that interface and its init dictionary. */
enum {
    RV_CONSTRUCT_EVENT = 0,
    RV_CONSTRUCT_CUSTOM = 1,
    RV_CONSTRUCT_UI = 2,
    RV_CONSTRUCT_MOUSE = 3,
    RV_CONSTRUCT_KEYBOARD = 4,
    RV_CONSTRUCT_FOCUS = 5,
};

/* The init dictionary fields of rv_host_construct_event. size is sizeof(RvEventInit). Fields that the kind's init
 * dictionary lacks are ignored: detail for UI, mouse and focus kinds; the coordinates, button, buttons and
 * relatedTarget for mouse; key, code, location, repeat and isComposing for keyboard; relatedTarget for focus;
 * modifiers (RV_MODIFIER_* bits) for mouse and keyboard. customDetailJson is CustomEvent.detail as UTF-8 JSON text,
 * parsed in the host document's realm; NULL is a null detail. key and code may be NULL for empty strings.
 * relatedTarget is borrowed for the call. UIEvent.view stays null, as for an init dictionary without view. */
typedef struct RvEventInit {
    int32_t size;
    int32_t bubbles;
    int32_t cancelable;
    int32_t composed;
    int32_t detail;
    int32_t modifiers;
    double screenX;
    double screenY;
    double clientX;
    double clientY;
    int32_t button;
    int32_t buttons;
    const char* key;
    const char* code;
    int32_t location;
    int32_t repeat;
    int32_t isComposing;
    RvEventTarget* relatedTarget;
    const char* customDetailJson;
} RvEventInit;

/* A new untrusted event from the engine constructor of kind. The caller owns one reference and releases it with
 * rv_event_release, before or after rv_host_destroy. A CustomEvent detail is parsed from JSON without running script
 * (the host keeps script entry disallowed) and stays reachable while the event is alive and its document is the host's
 * current document. Returns NULL for an unknown kind, a size other than sizeof(RvEventInit), a non-UTF-8 string,
 * detail JSON the engine's parser rejects, or a call off the owning thread. The engine exposes MouseEvent clientX and
 * clientY as integers. */
RV_EXPORT RvEvent* rv_host_construct_event(RvHost*, int32_t kind, const char* type, const RvEventInit* init);
/* CustomEvent.detail serialized as JSON in the event's realm, with the exact-byte UTF-8 protocol of rv_event_type:
 * length and capacity exclude the terminator. A null detail writes "null". Returns RV_ERR_UNSUPPORTED, leaving
 * *length unchanged, for an event that is not a CustomEvent, a detail JSON.stringify cannot serialize, or a detail
 * whose document was replaced or destroyed (rv_host_load_html, rv_host_load_svg, rv_host_destroy). */
RV_EXPORT int32_t rv_custom_event_detail_json(RvEvent*, char* buffer, int32_t capacity, int32_t* length);

/* A new standalone EventTarget (the engine's EventTarget constructor) for the host's current document. The caller owns
 * one reference and releases it with rv_event_target_release, before or after rv_host_destroy. Listeners added with
 * rv_event_target_add_listener hold the target and are removed with rv_listener_remove, which also remains valid
 * after rv_host_destroy. After the document is replaced or destroyed the target has no context; dispatch on it
 * still runs its listeners on the owning thread. */
RV_EXPORT RvEventTarget* rv_host_create_event_target(RvHost*);
RV_EXPORT RvEventTarget* rv_event_target_retain(RvEventTarget*);
RV_EXPORT void rv_event_target_release(RvEventTarget*);
/* A new reference to the node as an EventTarget, for the rv_event_target_* functions. */
RV_EXPORT RvEventTarget* rv_node_as_event_target(RvNode*);
/* A new node reference when the target is a node, else NULL. */
RV_EXPORT RvNode* rv_event_target_as_node(RvEventTarget*);
/* 1 when both handles refer to the same target, else 0. */
RV_EXPORT int32_t rv_event_target_equals(RvEventTarget* left, RvEventTarget* right);
/* rv_node_add_event_listener for any EventTarget; remove the listener with rv_listener_remove. */
RV_EXPORT RvListener* rv_event_target_add_listener(RvEventTarget*, const char* type, int32_t flags, RvEventCallback callback, void* context);
/* rv_node_dispatch for any EventTarget. */
RV_EXPORT int32_t rv_event_target_dispatch(RvEventTarget*, RvEvent*, int32_t* defaultPrevented);
/* The event's target, or with current set its currentTarget, as a new EventTarget reference; NULL when it has none. */
RV_EXPORT RvEventTarget* rv_event_get_target(RvEvent*, int32_t current);
/* The relatedTarget of a mouse or focus event as a new EventTarget reference, or NULL. */
RV_EXPORT RvEventTarget* rv_event_get_related_target(RvEvent*);

/* Window event target and input state ("input-state", v34). */

/* A new reference to the window of the host's current document, as an EventTarget for the rv_event_target_*
 * functions; release it with rv_event_target_release. Each call returns a new reference; rv_event_target_equals is 1
 * for two references to one window. Listeners receive every event type dispatched to the window: window events such
 * as focus, blur and resize, and the capture and bubble phases of events dispatched to the document's nodes, with
 * the window as currentTarget. A host has one window for its lifetime: replacing the document (rv_host_load_html,
 * rv_host_load_svg) keeps the window and its listeners. A reference and its listeners stay valid after rv_host_destroy,
 * and rv_listener_remove on them returns RV_OK. Returns NULL for a NULL host, a document without a window, or a call
 * off the owning thread. */
RV_EXPORT RvEventTarget* rv_host_window_event_target(RvHost* host);
/* Writes Navigator.maxTouchPoints of the current document's window. RV_ERR_UNSUPPORTED when the document has no
 * window. */
RV_EXPORT int32_t rv_host_max_touch_points(RvHost* host, int32_t* value);

/* v35: "viewport" for rv_abi_has. */
typedef struct RvWindowMetrics {
    /* sizeof(RvWindowMetrics), set by the caller. */
    int32_t size;
    /* CSS pixels: the viewport including scrollbars, and the window, which for a host is the viewport. */
    int32_t innerWidth;
    int32_t innerHeight;
    int32_t outerWidth;
    int32_t outerHeight;
    /* The device scale times the page zoom. */
    double devicePixelRatio;
} RvWindowMetrics;

/* Writes the window's Window.innerWidth/innerHeight/outerWidth/outerHeight/devicePixelRatio. Returns
 * RV_ERR_UNSUPPORTED when metrics->size is smaller than RvWindowMetrics. */
RV_EXPORT int32_t rv_host_window_metrics(RvHost*, RvWindowMetrics* metrics);
/* Sets whether the page is visible, as the platform window is shown or minimized, hidden or occluded. A change of
 * document.visibilityState queues a visibilitychange event at the document; a hidden page defers its resize
 * event until it is visible. A host starts visible. */
RV_EXPORT int32_t rv_host_set_visible(RvHost*, int32_t visible);
/* Window.matchMedia(query) as a new EventTarget reference. Its "change" event fires in rv_host_update, after the
 * window's resize and scroll events. The handle remains valid after rv_host_destroy. */
RV_EXPORT RvEventTarget* rv_host_match_media(RvHost*, const char* query);
/* MediaQueryList.matches and MediaQueryList.media; RV_ERR_WRONG_INTERFACE for another target. */
RV_EXPORT int32_t rv_media_query_matches(RvEventTarget*, int32_t* matches);
RV_EXPORT int32_t rv_media_query_media(RvEventTarget*, char* buffer, int32_t capacity, int32_t* length);

/* v39: "dom-binary-values" for rv_abi_has. RvBlob is the generated handle of Blob and File, and RvFileList of
 * FileList (RanvierWebCoreDom.h). The host's blob registry holds the bytes of every Blob and File it creates in
 * memory, so reading them completes during the call. */
typedef struct RvBlob RvBlob;
typedef struct RvFileList RvFileList;

/* Copies the bytes of blob into buffer and writes their count to *length. A capacity below the count copies
 * nothing and returns RV_ERR_BUFFER_TOO_SMALL with the count in *length; buffer may be NULL for capacity 0.
 * Returns RV_ERR_UNSUPPORTED for a blob whose bytes are not held in memory, such as a file-backed one. */
RV_EXPORT int32_t rv_blob_read_bytes(RvBlob* blob, uint8_t* buffer, int64_t capacity, int64_t* length);
/* A new FileList holding count files in order, as a new reference. files may be NULL for count 0.
 * Returns RV_ERR_WRONG_INTERFACE for an item that is a Blob and not a File. */
RV_EXPORT int32_t rv_file_list_create(RvBlob* const* files, int32_t count, RvFileList** result);

/* v52: "blob-urls" for rv_abi_has. URL.createObjectURL and URL.revokeObjectURL are the generated
 * rv_dom_domurl_create_object_url and rv_dom_domurl_revoke_object_url, and FileReader is the generated
 * rv_dom_file_reader_* family over an RvEventTarget. The document's blob: loads, such as an <img> source or a
 * stylesheet, are served by the engine from its blob registry and never reach the host's resource handler. A URL
 * stops loading once revoked, and once its document is replaced or its host destroyed. */
enum {
    RV_BLOB_READ_TEXT = 0,
    RV_BLOB_READ_BYTES = 1,
};
/* Blob.text() (RV_BLOB_READ_TEXT: the bytes decoded as UTF-8 with replacement, a leading BOM removed, delivered as
 * UTF-8) or Blob.arrayBuffer() and Blob.bytes() (RV_BLOB_READ_BYTES), read asynchronously by the engine's blob loader
 * in the host's current document, also for a file-backed blob. The operation follows rv_image_decode's delivery,
 * rv_resource_cancel and rv_resource_release: SUCCEEDED with the result available from rv_blob_read_result, or
 * LOAD_FAILED with the DOMException name from rv_blob_read_error, such as "NotFoundError" for a missing file.
 * width and height are 0. A new document or rv_host_destroy delivers INVALIDATED to a read in flight. */
RV_EXPORT int32_t rv_blob_read(RvHost*, RvBlob* blob, int32_t mode, RvResourceCompletion completion, void* context, uint64_t* operation);
/* Reads the bytes of the blob a blob: URL refers to, as a native read of the URL in the host's current document; it is
 * not fetch(). url is url_length bytes of UTF-8; a fragment is ignored. LOAD_FAILED for a revoked or unknown URL. Delivery
 * follows rv_blob_read; rv_blob_read_type writes the blob's type. Returns RV_ERR_UNSUPPORTED for a URL that does not
 * parse or whose scheme is not blob. */
RV_EXPORT int32_t rv_blob_url_read(RvHost*, const uint8_t* url, int32_t url_length, RvResourceCompletion completion, void* context, uint64_t* operation);
/* Copies a SUCCEEDED read's result into buffer and writes its byte count to *length, until rv_resource_release.
 * Capacity, NULL buffer and RV_ERR_BUFFER_TOO_SMALL follow rv_blob_read_bytes. RV_ERR_UNSUPPORTED for another
 * operation or outcome. */
RV_EXPORT int32_t rv_blob_read_result(uint64_t operation, uint8_t* buffer, int64_t capacity, int64_t* length);
/* The blob's type of a SUCCEEDED read, NUL-terminated UTF-8; capacity counts the NUL. */
RV_EXPORT int32_t rv_blob_read_type(uint64_t operation, char* buffer, int32_t capacity, int32_t* length);
/* The DOMException name of a LOAD_FAILED read, NUL-terminated; RV_ERR_UNSUPPORTED for another outcome. */
RV_EXPORT int32_t rv_blob_read_error(uint64_t operation, char* buffer, int32_t capacity, int32_t* length);
/* A new File backed by the file at path, which the app supplies and trusts: path_length bytes of UTF-8 naming an absolute
 * path, or RV_ERR_UNSUPPORTED for a relative one. The file is not opened: name and type come from the path, and a file
 * missing or deleted when read fails the read with "NotFoundError". rv_blob_read_bytes returns RV_ERR_UNSUPPORTED for
 * it; read it with rv_blob_read, FileReader or an object URL. */
RV_EXPORT int32_t rv_file_create_from_path(RvHost*, const uint8_t* path, int32_t path_length, RvBlob** result);

enum {
    RV_FILE_READER_RESULT_NULL = 0,
    RV_FILE_READER_RESULT_STRING = 1,
    RV_FILE_READER_RESULT_BYTES = 2,
};
/* FileReader.result: writes its kind, and copies a string as UTF-8 or an ArrayBuffer's bytes into buffer with their
 * count in *length (0 for NULL). Capacity follows rv_blob_read_bytes. RV_ERR_WRONG_INTERFACE for another target. */
RV_EXPORT int32_t rv_file_reader_result(RvEventTarget* reader, int32_t* kind, uint8_t* buffer, int64_t capacity, int64_t* length);
/* FileReader.error: the DOMException name, NUL-terminated, or *length = -1 for a null error. */
RV_EXPORT int32_t rv_file_reader_error(RvEventTarget* reader, char* buffer, int32_t capacity, int32_t* length);

/* "text-segmentation" for rv_abi_has: graphemes, words, sentences and line-break opportunities of UTF-16 text,
 * with the engine's ICU. Graphemes and lines use WebKit's caret and line iterators (line-break normal; CSS loose,
 * strict and anywhere are out of scope); words and sentences use ICU's iterators for the locale. Every word,
 * sentence and line boundary is a grapheme boundary: a rule boundary inside a grapheme cluster joins its two segments. */
enum {
    RV_SEGMENT_GRAPHEME = 0,
    RV_SEGMENT_WORD = 1,
    RV_SEGMENT_SENTENCE = 2,
    RV_SEGMENT_LINE = 3,
};
/* The segments of a text. Segment i starts at starts[i], in UTF-16 code units, and ends where segment i + 1 starts,
 * the last at the text's length. word_like holds one flag per segment for RV_SEGMENT_WORD, 1 where ICU's rule status
 * is UBRK_WORD_NONE_LIMIT or above (Intl.Segmenter's isWordLike), and is NULL otherwise. locale is ICU's valid
 * locale for the request, NUL-terminated UTF-8. The buffers are owned until rv_text_segments_release. */
typedef struct RvTextSegments {
    int32_t count;
    int32_t* starts;
    int32_t* word_like;
    char* locale;
} RvTextSegments;
/* Segments length UTF-16 code units of text at granularity for locale, a BCP 47 language tag; NULL or "" is the
 * root locale. text may be NULL for length 0, which gives zero segments. A locale that is not a well-formed tag
 * returns RV_ERR_DOM_EXCEPTION with a RangeError. Runs on the owning thread after the first rv_host_create, and
 * keeps working after every host is destroyed. Windows packages segment with their own ICU 77; Linux and macOS
 * packages use the system ICU, so results follow its version (rv_text_segmentation_version). */
RV_EXPORT int32_t rv_text_segment(int32_t granularity, const char* locale, const uint16_t* text, int32_t length, RvTextSegments* result);
/* Frees the buffers of segments and zeroes it; on any thread. */
RV_EXPORT void rv_text_segments_release(RvTextSegments* segments);
/* The ICU and Unicode versions behind rv_text_segment, such as "icu=77.1 unicode=16.0", as rv_node_get_string
 * copies a string. Windows packages carry ICU; Linux and macOS packages use the system's. */
RV_EXPORT int32_t rv_text_segmentation_version(char* buffer, int32_t capacity, int32_t* length);

/* v45: "page-scale" and "obscured-insets" for rv_abi_has, and "visual-viewport" for the generated
 * rv_dom_window_get_visual_viewport and rv_dom_visual_viewport_* functions (RanvierWebCoreDom.h). A VisualViewport
 * handle is an RvEventTarget: its resize and scroll events fire in rv_host_update, after the window's. */

/* Sets the page scale, as a pinch zoom does: 1 at creation. Returns RV_ERR_UNSUPPORTED for a non-finite scale or one
 * at or below 0; any other scale applies unclamped, since the engine has no minimum or maximum. originX and originY
 * are the scroll position, in CSS pixels of the scaled document, that the viewport takes. The visual viewport is then
 * the viewport's CSS size divided by the scale, in LayoutUnits of 1/64 CSS pixel: 320 / 1.5 reads 213.328125. While
 * the page is scaled, window.innerWidth and innerHeight are the visual viewport's size, and the layout viewport stays
 * at the document's origin, so VisualViewport.offsetLeft and offsetTop equal pageLeft and pageTop. */
RV_EXPORT int32_t rv_host_set_page_scale(RvHost*, double scale, int32_t originX, int32_t originY);
/* Writes the page scale. */
RV_EXPORT int32_t rv_host_page_scale(RvHost*, double* scale);
/* Sets the CSS pixel widths of the viewport's edges that host UI covers, such as a toolbar or an on-screen
 * keyboard: 0 at creation. Returns RV_ERR_UNSUPPORTED for a non-finite or negative inset. The insets shrink the
 * visual viewport and window.innerWidth and innerHeight by the covered edges, and fire the window's and then the
 * visual viewport's resize event. Document coordinates stay in place, top inset included, and rv_host_element_at
 * finds nothing in the covered right and bottom areas. */
RV_EXPORT int32_t rv_host_set_obscured_insets(RvHost*, double top, double right, double bottom, double left);

/* "dom-generated" and "dom:<Interface>" for rv_abi_has: the generated functions of RanvierWebCoreDom.h, one per
 * IDL member of the interfaces gen/dom.json lists, from the same library. */

/* v46: "screen" for rv_abi_has: the app's display integration sets the screen a host's document reports through Screen,
 * ScreenOrientation and the device-width, device-height and color media features. Until the first call the screen is
 * the host's size in CSS pixels, all of it available, 24 bits deep, landscape-primary unless taller than wide; it
 * then follows rv_host_resize. orientation is an RV_SCREEN_* value; ScreenOrientation.angle follows from it on the
 * natural landscape orientation (landscape-primary 0, portrait-primary 90, landscape-secondary 180,
 * portrait-secondary 270). A change of orientation fires the engine's change event. Orientation locking is not
 * supported. Set size to sizeof(RvScreenMetrics). Returns RV_ERR_UNSUPPORTED, and changes nothing, for a size
 * below this layout, a width or height of 0 or less, a negative available extent, a color depth outside 1-64 or
 * an unknown orientation. A document kept past rv_host_destroy has no frame, and its Screen reports 0. */
enum {
    RV_SCREEN_PORTRAIT_PRIMARY = 0,
    RV_SCREEN_PORTRAIT_SECONDARY = 1,
    RV_SCREEN_LANDSCAPE_PRIMARY = 2,
    RV_SCREEN_LANDSCAPE_SECONDARY = 3,
};
typedef struct RvScreenMetrics {
    uint32_t size;
    int32_t width;
    int32_t height;
    int32_t avail_left;
    int32_t avail_top;
    int32_t avail_width;
    int32_t avail_height;
    int32_t color_depth;
    int32_t orientation;
} RvScreenMetrics;
RV_EXPORT int32_t rv_host_set_screen(RvHost*, const RvScreenMetrics* metrics);

/* v44: "dom-crypto-random" for rv_abi_has: rv_dom_crypto_get_random_values and rv_dom_crypto_random_uuid
 * (RanvierWebCoreDom.h) call the crypto object of a document's Window. */

/* v50: "diagnostics" for rv_abi_has: native inspection of a host's document without a developer-tools frontend,
 * an inspector protocol or script evaluation. Diagnostics are opt-in per host: until rv_host_set_diagnostics enables
 * them, every rv_host_inspect_* call returns RV_ERR_UNSUPPORTED before reading the document. The platform facility
 * "diagnostics" reports the opt-in as its enabled fact; "inspector-frontend" reports the developer-tools frontend,
 * which no flavor implements.
 *
 * An RvDiagnostic is a snapshot: UTF-8 copies of what the engine reported, holding no engine object. It stays
 * readable after its host disables diagnostics or is destroyed, and is freed only by rv_diagnostic_release. The
 * rv_diagnostic_* functions run on any thread. */
typedef struct RvDiagnostic RvDiagnostic;

/* Enables (1) or disables (0) diagnostics for the host. Live snapshots are unaffected. */
RV_EXPORT int32_t rv_host_set_diagnostics(RvHost*, int32_t enabled);

/* Kinds of rv_diagnostic_kind. */
enum {
    RV_DIAGNOSTIC_RENDER_TREE = 1,
    RV_DIAGNOSTIC_MATCHED_RULES = 2,
    /* v54 */
    RV_DIAGNOSTIC_CASCADE = 3,
};

/* Flags of rv_host_inspect_render_tree. The layer flags apply to a document dump only. */
enum {
    /* Every RenderLayer, including those that paint nothing. */
    RV_RENDER_TREE_ALL_LAYERS = 1 << 0,
    /* Annotates the positive, negative and normal-flow layer lists. */
    RV_RENDER_TREE_LAYER_NESTING = 1 << 1,
    /* Adds each box's layout and visual overflow rectangles. */
    RV_RENDER_TREE_OVERFLOW = 1 << 2,
    /* Adds the extra geometry of SVG renderers. */
    RV_RENDER_TREE_SVG_GEOMETRY = 1 << 3,
    /* Adds each element's id and class attributes. */
    RV_RENDER_TREE_ID_AND_CLASS = 1 << 4,
    /* Adds the renderers' pending-layout bits. */
    RV_RENDER_TREE_LAYOUT_STATE = 1 << 5,
};

/* Writes a new RV_DIAGNOSTIC_RENDER_TREE snapshot to *diagnostic, with style and layout updated first. With target
 * NULL or the host's document, its text is the engine's render tree dump of the main frame: one line per renderer
 * and per text run, nested by two-space indentation, with each RenderLayer as a "layer" line. With an element of
 * the document, it is the element's renderer subtree, one line per renderer in the same format, with no layer or
 * text-run lines. Positions and sizes are in CSS pixels of the renderer's containing coordinate space. Returns
 * RV_ERR_UNSUPPORTED for an unknown flag, a layer flag with an element, an element with no renderer or outside the
 * document, or diagnostics disabled, and leaves *diagnostic unchanged on every error. */
RV_EXPORT int32_t rv_host_inspect_render_tree(RvHost*, RvNode* target, int32_t flags, RvDiagnostic** diagnostic);

/* Writes a new RV_DIAGNOSTIC_MATCHED_RULES snapshot for an element of the host's document, with style updated
 * first: one entry per style rule whose selector list matches the element, in the engine's cascade order (user-agent
 * rules, then user rules, then author rules, each ordered by cascade layer, specificity and position; rules inside
 * a non-matching @media are absent), then one RV_RULE_ORIGIN_INLINE entry for a non-empty style attribute. Returns
 * RV_ERR_NOT_ELEMENT for another node, RV_ERR_UNSUPPORTED for an element outside the document or diagnostics
 * disabled, and leaves *diagnostic unchanged on every error. */
RV_EXPORT int32_t rv_host_inspect_matched_rules(RvHost*, RvNode* element, RvDiagnostic** diagnostic);

/* Origins of RV_RULE_ORIGIN. */
enum {
    RV_RULE_ORIGIN_USER_AGENT = 0,
    RV_RULE_ORIGIN_USER = 1,
    RV_RULE_ORIGIN_AUTHOR = 2,
    RV_RULE_ORIGIN_INLINE = 3,
    /* v54: a presentational attribute, or the direction of dir=auto; rv_host_inspect_cascade only. */
    RV_RULE_ORIGIN_PRESENTATIONAL_HINT = 4,
};

/* Number fields of rv_diagnostic_entry_number. Specificity is the engine's (a, b, c) of the most specific selector
 * in the rule's list that matches the element: :where() contributes (0, 0, 0) and :is() the most specific of its
 * arguments. An inline entry has specificity (0, 0, 0) and no selectors. */
enum {
    RV_RULE_ORIGIN = 0,
    RV_RULE_SPECIFICITY_A = 1,
    RV_RULE_SPECIFICITY_B = 2,
    RV_RULE_SPECIFICITY_C = 3,
    /* Selectors in the rule's selector list. */
    RV_RULE_SELECTOR_COUNT = 4,
    /* Selectors of the list that match the element. */
    RV_RULE_MATCHED_SELECTOR_COUNT = 5,
};

/* String fields of rv_diagnostic_entry_string, as the engine serialises them; an inline entry's selector fields
 * are empty. */
enum {
    /* The rule's selector list. */
    RV_RULE_SELECTOR_TEXT = 0,
    /* The selector the specificity belongs to. */
    RV_RULE_MATCHED_SELECTOR = 1,
    /* The rule's declaration block, without braces. */
    RV_RULE_DECLARATIONS = 2,
};

/* The snapshot's RV_DIAGNOSTIC_* kind, or RV_ERR_NULL_ARGUMENT. */
RV_EXPORT int32_t rv_diagnostic_kind(RvDiagnostic* diagnostic);
/* Copies a render-tree snapshot's text or a cascade snapshot's property name; a matched-rules snapshot's text is empty. */
RV_EXPORT int32_t rv_diagnostic_text(RvDiagnostic* diagnostic, char* buffer, int32_t capacity, int32_t* length);
/* The number of entries: 0 for a render-tree snapshot. */
RV_EXPORT int32_t rv_diagnostic_count(RvDiagnostic* diagnostic);
/* Copies a string field of entry index. Returns RV_ERR_UNSUPPORTED for an index or field out of range for the snapshot's kind. */
RV_EXPORT int32_t rv_diagnostic_entry_string(RvDiagnostic* diagnostic, int32_t index, int32_t field, char* buffer, int32_t capacity, int32_t* length);
/* Writes a number field of entry index. Returns RV_ERR_UNSUPPORTED, leaving *value unchanged, for an index or field
 * out of range for the snapshot's kind. */
RV_EXPORT int32_t rv_diagnostic_entry_number(RvDiagnostic* diagnostic, int32_t index, int32_t field, double* value);
RV_EXPORT void rv_diagnostic_release(RvDiagnostic* diagnostic);
/* The number of snapshots in the process not yet released. */
RV_EXPORT int32_t rv_diagnostic_live_count(void);

/* Rectangles of rv_host_inspect_box_model, each four doubles x, y, width, height. */
enum {
    RV_BOX_CONTENT = 0,
    RV_BOX_PADDING = 4,
    RV_BOX_BORDER = 8,
    RV_BOX_MARGIN = 12,
    RV_BOX_VALUES = 16,
};

/* Writes the element's content, padding, border and margin boxes as RV_BOX_VALUES doubles, with layout updated
 * first. Each is the bounding rectangle of the box after transforms, in the coordinate space of rv_element_rect
 * (Element.getBoundingClientRect): CSS pixels of the viewport after scrolling, with the element's zoom applied. The
 * border box equals rv_element_rect. Without transforms the values are multiples of 1/64 px. Returns
 * RV_ERR_NOT_ELEMENT for another node, RV_ERR_UNSUPPORTED for an element without a CSS box renderer (display: none
 * or contents, an inline box, SVG content) or outside the document, or diagnostics disabled, and leaves values
 * unchanged on every error. */
RV_EXPORT int32_t rv_host_inspect_box_model(RvHost*, RvNode* element, double* values);

/* v53: "coordinate-spaces" for rv_abi_has: points and box quads converted between named coordinate spaces of one
 * host's document, through every CSS transform, perspective included, and the current scroll, page scale and device
 * scale, with layout updated first and without running script. Spaces:
 *   RV_SPACE_NODE   the local space of a node's CSS box: the border box's top-left corner is 0, 0, before the node's
 *                   own transform. The document node's local space is its page space.
 *   RV_SPACE_PAGE   CSS pixels of the document from its top-left corner, independent of scroll and page scale.
 *   RV_SPACE_CLIENT CSS pixels of Element.getBoundingClientRect, Document.elementFromPoint, rv_host_element_at and
 *                   MouseEvent.clientX and clientY.
 *   RV_SPACE_HOST   CSS pixels of the host surface: the space of rv_host_mouse, rv_host_wheel and rv_host_dirty_rect.
 *                   It equals CLIENT at page scale 1. While page-scaled, HOST is CLIENT times the page scale: the
 *                   client point x, y is reached by rv_host_mouse at x * scale, y * scale.
 *   RV_SPACE_DEVICE device pixels of the image rv_host_paint_rgba paints: HOST times the device scale.
 * The app's window position on the screen is the windowing system's: a screen point is a DEVICE point plus the
 * origin the app's windowing system reports for the host's surface. Points are double precision; WebCore maps them
 * in single precision and LayoutUnits of 1/64 CSS pixel. Conversions agree with what the host paints and hit-tests.
 * The slim software path paints without 3D compositing: the perspective property and transform-style: preserve-3d
 * have no effect, and a perspective() function maps as the software paint draws it, so points of such chains lie up
 * to 26.5 CSS pixels from where a 3D-compositing browser such as Chromium places them. */
enum {
    RV_SPACE_NODE = 0,
    RV_SPACE_PAGE = 1,
    RV_SPACE_CLIENT = 2,
    RV_SPACE_HOST = 3,
    RV_SPACE_DEVICE = 4,
};
/* Boxes of rv_node_box_quad, as CSS box edges. */
enum {
    RV_QUAD_BORDER_BOX = 0,
    RV_QUAD_PADDING_BOX = 1,
    RV_QUAD_CONTENT_BOX = 2,
    RV_QUAD_MARGIN_BOX = 3,
};
enum {
    /* The anchors of a conversion belong to different hosts. */
    RV_ERR_WRONG_HOST = -12,
};
/* Converts count points of xy, as x0, y0, x1, y1 and so on, from fromSpace anchored at from to toSpace anchored at to,
 * in place. RV_SPACE_NODE is the anchor node's own space; for the other spaces the anchor is any node of the
 * document, the document node included. A NULL to anchors toSpace at from's document. xy changes only on RV_OK.
 * Returns RV_ERR_NULL_ARGUMENT for a NULL from, or a NULL xy with count above 0; RV_ERR_DETACHED for an anchor
 * outside the document a live host shows: a node removed from its document, one in a document that a later
 * rv_host_load_html or rv_host_load_svg replaced, or one held past rv_host_destroy; RV_ERR_WRONG_HOST for anchors of
 * two hosts; RV_ERR_UNSUPPORTED for an unknown space, a negative count, a non-finite coordinate, an anchor in a
 * subframe document (a host's frame loader creates no subframes), an RV_SPACE_NODE anchor without a CSS box
 * (display: none or contents, inline boxes, text and SVG shapes), or a point mapped into an RV_SPACE_NODE whose
 * transforms are singular there, such as scale(0) or rotateY(90deg). */
RV_EXPORT int32_t rv_node_convert_points(RvNode* from, int32_t fromSpace, RvNode* to, int32_t toSpace, double* xy, int32_t count);
/* Writes the four corners of a node's box in toSpace anchored at to, as x, y pairs in the order of DOMQuad's p1 to
 * p4: top-left, top-right, bottom-right, bottom-left. box is an RV_QUAD_* value; a NULL to is node's document. The
 * statuses are those of rv_node_convert_points with node as the RV_SPACE_NODE anchor, and RV_ERR_UNSUPPORTED for an
 * unknown box. */
RV_EXPORT int32_t rv_node_box_quad(RvNode* node, int32_t box, RvNode* to, int32_t toSpace, double* quad);

/* v54: "cascade-diagnostics" for rv_abi_has and as a platform facility, enabled with "diagnostics".
 *
 * Writes a new RV_DIAGNOSTIC_CASCADE snapshot of a longhand or custom property for an element of the host's document.
 * property is a CSS property name of property_length UTF-8 bytes; the snapshot text is its canonical name.
 *
 * Entries are the declarations of the property in the element's cascade, in the engine's cascade input order: user
 * agent, user, then author declarations, each ordered by cascade layer, specificity and position, with presentational
 * hints first and the style attribute after the element's own rules. Rules of other tree scopes follow the shadow
 * context order: :host() and ::slotted() rules precede the rules of the element's tree, and ::part() rules follow the
 * style attribute; the winner reverses that order for !important. A logical or physical property also lists the
 * declarations of its counterpart under the element's writing mode. RV_CASCADE_WINNER marks the declaration the
 * engine's cascade selects, honouring !important, origin, layer and position; a level with no declaration has no
 * winner. When the level has no winner and the property inherits, or its winner is inherit (or unset on an inherited
 * property), the entries continue with the parent element in the composed tree at RV_CASCADE_DEPTH + 1, until a level
 * whose winner is another value, or a level without a winner whose property does not inherit, or the root. A custom
 * property inherits unless registered with inherits: false.
 *
 * The query reads the current DOM and the current rule sets, applying a pending style sheet change first; it updates
 * no style and no layout. Container conditions are evaluated against the last layout, and a logical pair against the
 * element's last computed writing mode. Declared limits: a winning revert or revert-layer is reported as that keyword;
 * :visited declarations, @starting-style rules and animations are absent; RV_CASCADE_VALUE is the declared value, and
 * var() resolution is reported by rv_element_computed_style.
 *
 * Returns RV_ERR_NULL_ARGUMENT for a NULL property, RV_ERR_NOT_ELEMENT for another node, RV_ERR_UNSUPPORTED for an
 * unknown or shorthand property, a negative property_length, an element outside the document or diagnostics disabled,
 * and leaves *diagnostic unchanged on every error. */
RV_EXPORT int32_t rv_host_inspect_cascade(RvHost*, RvNode* element, const uint8_t* property, int32_t property_length, RvDiagnostic** diagnostic);

/* Number fields of a cascade entry. The origin and specificity fields share the RV_RULE_* indices. */
enum {
    RV_CASCADE_ORIGIN = 0,
    RV_CASCADE_SPECIFICITY_A = 1,
    RV_CASCADE_SPECIFICITY_B = 2,
    RV_CASCADE_SPECIFICITY_C = 3,
    /* 1 for an !important declaration. */
    RV_CASCADE_IMPORTANT = 4,
    /* The layer's position in its origin's layer order from 0; -1 for unlayered declarations, hints and inline style. */
    RV_CASCADE_LAYER_ORDER = 5,
    /* 1 for the winner of its level. */
    RV_CASCADE_WINNER = 6,
    /* 0 for the element, n for its nth ancestor in the composed tree. */
    RV_CASCADE_DEPTH = 7,
    /* The rule's style sheet among the active style sheets of the tree scope defining the rule: the element's, its
     * shadow root's for :host rules, its slot's for ::slotted() rules, or a host's for ::part() rules; -1 when no
     * active sheet holds it. RV_CASCADE_LAYER_ORDER is the order of that tree scope's layers. */
    RV_CASCADE_SHEET_INDEX = 8,
    /* The rule's position among the sheet's style rules in pre-order, an imported sheet's rules in place of its
     * @import; -1 with no sheet. */
    RV_CASCADE_RULE_INDEX = 9,
    /* The declaration's position in its declaration block, a shorthand counting once per longhand. */
    RV_CASCADE_DECLARATION_INDEX = 10,
    /* 1 for a value containing var() or another substitution function. */
    RV_CASCADE_VARIABLE_REFERENCE = 11,
    RV_CASCADE_NUMBER_FIELDS = 12,
};

/* String fields of a cascade entry, as the engine serialises them. The selector fields share the RV_RULE_* indices
 * and are empty for hints and inline style. */
enum {
    RV_CASCADE_SELECTOR_TEXT = 0,
    RV_CASCADE_MATCHED_SELECTOR = 1,
    /* The declared longhand or custom property: the queried property or its logical counterpart. */
    RV_CASCADE_PROPERTY = 2,
    /* The declared value, without !important. */
    RV_CASCADE_VALUE = 3,
    /* The shorthand the declaration was expanded from, or empty. */
    RV_CASCADE_SHORTHAND = 4,
    /* The dotted cascade layer name, an anonymous layer as an empty segment; empty when unlayered. */
    RV_CASCADE_LAYER = 5,
    /* The enclosing @media, @supports and @container conditions, outermost first, one per line as the at-keyword, a
     * space and the condition text. */
    RV_CASCADE_CONDITIONS = 6,
    RV_CASCADE_STRING_FIELDS = 7,
};

#ifdef __cplusplus
}
#endif
