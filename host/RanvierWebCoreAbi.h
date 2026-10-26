/*
 * Ranvier native WebCore C ABI, experiment v7.
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

#ifdef __cplusplus
}
#endif
