/// P/Invoke surface of RanvierWebCoreAbi.h. The library name resolves to libRanvierWebCoreHost.so,
/// RanvierWebCoreHost.dll or libRanvierWebCoreHost.dylib by the runtime's platform probing.
module RanvierWebCoreAbi.Native

open System
open System.Runtime.InteropServices

// BEGIN GENERATED from host/RanvierWebCoreAbi.h by tests/abi/generate_native.py; edit the header, then run it.

[<Literal>]
let private Lib = "RanvierWebCoreHost"

/// <summary>The <c>RvEventCallback</c> of the header.</summary>
[<UnmanagedFunctionPointer(CallingConvention.Cdecl)>]
type EventCallback = delegate of context: nativeint * event: nativeint -> int

/// <summary>The <c>RvEventInit</c> of the header; strings are caller-owned NUL-terminated UTF-8 pointers.</summary>
[<Struct; StructLayout(LayoutKind.Sequential)>]
type EventInit =
    val mutable size: int
    val mutable bubbles: int
    val mutable cancelable: int
    val mutable composed: int
    val mutable detail: int
    val mutable modifiers: int
    val mutable screenX: float
    val mutable screenY: float
    val mutable clientX: float
    val mutable clientY: float
    val mutable button: int
    val mutable buttons: int
    val mutable key: nativeint
    val mutable code: nativeint
    val mutable location: int
    val mutable repeat: int
    val mutable isComposing: int
    val mutable relatedTarget: nativeint
    val mutable customDetailJson: nativeint

/// <summary>The <c>RvTextSegments</c> of the header: owned until <c>rv_text_segments_release</c>.</summary>
[<Struct; StructLayout(LayoutKind.Sequential)>]
type TextSegments =
    val mutable count: int
    val mutable starts: nativeint
    val mutable word_like: nativeint
    val mutable locale: nativeint

/// <summary>The <c>RvResourceHandler</c> of the header; <c>url</c> is a NUL-terminated UTF-8 string.</summary>
[<UnmanagedFunctionPointer(CallingConvention.Cdecl)>]
type ResourceHandler = delegate of context: nativeint * load: nativeint * url: nativeint -> unit

/// <summary>The <c>RvFormSubmission</c> of the header; every pointer is valid only during the handler call.</summary>
[<Struct; StructLayout(LayoutKind.Sequential)>]
type FormSubmission =
    val mutable size: uint32
    val mutable method: nativeint
    val mutable url: nativeint
    val mutable target: nativeint
    val mutable contentType: nativeint
    val mutable body: nativeint
    val mutable bodyLength: int
    val mutable form: nativeint
    val mutable submitter: nativeint

/// <summary>The <c>RvFormSubmissionHandler</c> of the header; <c>submission</c> points to a <c>FormSubmission</c>.</summary>
[<UnmanagedFunctionPointer(CallingConvention.Cdecl)>]
type FormSubmissionHandler = delegate of context: nativeint * submission: nativeint -> unit

/// <summary>The <c>RvResourceCompletion</c> of the header: one terminal outcome with an image's natural size.</summary>
[<UnmanagedFunctionPointer(CallingConvention.Cdecl)>]
type ResourceCompletion = delegate of context: nativeint * outcome: int * width: int * height: int -> unit

/// <summary>The <c>RvFrameCallback</c> of the header.</summary>
[<UnmanagedFunctionPointer(CallingConvention.Cdecl)>]
type FrameCallback = delegate of context: nativeint -> unit

/// <summary>The <c>RvResizeCallback</c> of the header.</summary>
[<UnmanagedFunctionPointer(CallingConvention.Cdecl)>]
type ResizeCallback = delegate of context: nativeint * target: nativeint * width: float * height: float -> unit

/// <summary>The <c>RvIntersectionCallback</c> of the header.</summary>
[<UnmanagedFunctionPointer(CallingConvention.Cdecl)>]
type IntersectionCallback =
    delegate of context: nativeint * target: nativeint * intersecting: int * ratio: float -> unit

/// <summary>The <c>RvPopupCallback</c> of the header.</summary>
[<UnmanagedFunctionPointer(CallingConvention.Cdecl)>]
type PopupCallback =
    delegate of
        context: nativeint * popup: nativeint * action: int * x: int * y: int * width: int * height: int * selected: int ->
            unit

/// <summary>The <c>RvClipboardWrite</c> of the header; <c>type</c> and <c>data</c> are NUL-terminated UTF-8.</summary>
[<UnmanagedFunctionPointer(CallingConvention.Cdecl)>]
type ClipboardWrite = delegate of context: nativeint * ``type``: nativeint * data: nativeint * first: int -> unit

/// <summary>The <c>RvClipboardRead</c> of the header.</summary>
[<UnmanagedFunctionPointer(CallingConvention.Cdecl)>]
type ClipboardRead = delegate of context: nativeint * request: nativeint -> unit

/// <summary>The <c>RvDragStartCallback</c> of the header.</summary>
[<UnmanagedFunctionPointer(CallingConvention.Cdecl)>]
type DragStartCallback = delegate of context: nativeint * drag: nativeint * x: int * y: int * allowed: int -> unit

/// <summary>The <c>RvAxCallback</c> of the header.</summary>
[<UnmanagedFunctionPointer(CallingConvention.Cdecl)>]
type AxCallback = delegate of context: nativeint * node: nativeint * event: int -> unit

/// <summary>The <c>RvNodeFilterCallback</c> of the header.</summary>
[<UnmanagedFunctionPointer(CallingConvention.Cdecl)>]
type NodeFilterCallback = delegate of context: nativeint * node: nativeint -> int

/// <summary>The <c>RvNodeFilterRelease</c> of the header.</summary>
[<UnmanagedFunctionPointer(CallingConvention.Cdecl)>]
type NodeFilterRelease = delegate of context: nativeint -> unit

/// <summary>
/// Per-function counts and Stopwatch ticks of the calls made while <c>On</c>, indexed as <c>Names</c>. The ticks of a
/// call span its P/Invoke transition, marshalling and native work.
/// </summary>
module Calls =
    let Names =
        [|
            "rv_abi_version"
            "rv_process_id"
            "rv_host_create"
            "rv_host_destroy"
            "rv_host_load_html"
            "rv_host_scripts_enabled"
            "rv_host_vm_entry_disallowed"
            "rv_document_body"
            "rv_document_head"
            "rv_document_get_element_by_id"
            "rv_document_create_element"
            "rv_document_create_text"
            "rv_node_append_child"
            "rv_node_set_text_content"
            "rv_element_set_attribute"
            "rv_node_release"
            "rv_host_paint_rgba"
            "rv_host_set_accelerated_compositing"
            "rv_host_acquire_d3d11_frame"
            "rv_gpu_frame_info"
            "rv_gpu_frame_release"
            "rv_node_add_event_listener"
            "rv_listener_remove"
            "rv_node_filter_create"
            "rv_node_filter_context"
            "rv_node_dispatch_event"
            "rv_element_click"
            "rv_input_checked"
            "rv_event_phase"
            "rv_event_default_prevented"
            "rv_event_prevent_default"
            "rv_event_stop_propagation"
            "rv_host_document"
            "rv_document_create_comment"
            "rv_document_create_fragment"
            "rv_document_import_node"
            "rv_node_parse_fragment"
            "rv_node_type"
            "rv_node_relative"
            "rv_node_get_string"
            "rv_node_set_string"
            "rv_node_insert_before"
            "rv_node_remove_child"
            "rv_node_replace_child"
            "rv_node_remove"
            "rv_node_clone"
            "rv_node_contains"
            "rv_node_is_connected"
            "rv_element_get_attribute"
            "rv_element_remove_attribute"
            "rv_input_set_checked"
            "rv_event_retain"
            "rv_event_release"
            "rv_host_create_event"
            "rv_node_dispatch"
            "rv_event_interface"
            "rv_event_flags"
            "rv_event_type"
            "rv_event_key"
            "rv_event_target"
            "rv_last_exception"
            "rv_node_query_selector"
            "rv_node_query_selector_all"
            "rv_node_query_selector_all_uncached"
            "rv_node_ref_count"
            "rv_node_watch"
            "rv_watch_alive"
            "rv_watch_node"
            "rv_watch_release"
            "rv_release_memory"
            "rv_collect_garbage"
            "rv_collect_garbage_eden"
            "rv_node_has_wrapper"
            "rv_element_attribute_count"
            "rv_element_attribute_at"
            "rv_element_focus"
            "rv_document_active_element"
            "rv_run_loop_cycle"
            "rv_host_set_resource_handler"
            "rv_host_set_form_submission_handler"
            "rv_resource_load_finish"
            "rv_resource_load_fail"
            "rv_abi_has"
            "rv_host_resize"
            "rv_host_set_device_scale"
            "rv_host_paint_size"
            "rv_host_mouse"
            "rv_host_wheel"
            "rv_host_key"
            "rv_host_set_focused"
            "rv_host_set_frame_callback"
            "rv_host_update"
            "rv_host_dirty_rect"
            "rv_event_number"
            "rv_event_string"
            "rv_event_related_target"
            "rv_host_cursor"
            "rv_host_scroll_position"
            "rv_host_scroll_to"
            "rv_host_ime_set_composition"
            "rv_host_ime_commit"
            "rv_host_ime_cancel"
            "rv_host_ime_rect"
            "rv_element_class"
            "rv_element_set_style"
            "rv_element_get_style"
            "rv_element_computed_style"
            "rv_element_rect"
            "rv_host_element_at"
            "rv_element_scroll_into_view"
            "rv_element_scroll_metric"
            "rv_element_scroll_to"
            "rv_element_attach_shadow"
            "rv_element_shadow_root"
            "rv_text_selection"
            "rv_text_set_selection"
            "rv_element_animations"
            "rv_host_animations"
            "rv_animation_release"
            "rv_animation_control"
            "rv_animation_state"
            "rv_animation_time"
            "rv_animation_seek"
            "rv_animation_set_rate"
            "rv_animation_name"
            "rv_animation_target"
            "rv_node_retain"
            "rv_host_observe_resize"
            "rv_host_observe_intersection"
            "rv_observer_observe"
            "rv_observer_unobserve"
            "rv_observer_release"
            "rv_element_snapshot"
            "rv_host_paint_rgba_rect"
            "rv_host_set_popup_handler"
            "rv_popup_item_count"
            "rv_popup_item"
            "rv_popup_choose"
            "rv_host_tooltip"
            "rv_host_set_clipboard"
            "rv_clipboard_offer"
            "rv_host_edit"
            "rv_host_set_drag"
            "rv_drag_data_create"
            "rv_drag_data_add"
            "rv_drag_data_release"
            "rv_host_drag"
            "rv_host_set_drag_start"
            "rv_drag_item_count"
            "rv_drag_item_type"
            "rv_drag_item_value"
            "rv_drag_data"
            "rv_drag_image"
            "rv_drag_end"
            "rv_host_set_accessibility"
            "rv_host_attach_uia"
            "rv_host_detach_uia"
            "rv_host_ax_root"
            "rv_host_ax_focus"
            "rv_host_ax_hit_test"
            "rv_node_ax"
            "rv_ax_dom_node"
            "rv_ax_retain"
            "rv_ax_release"
            "rv_ax_id"
            "rv_ax_role"
            "rv_ax_states"
            "rv_ax_string"
            "rv_ax_number"
            "rv_ax_rect"
            "rv_ax_parent"
            "rv_ax_children"
            "rv_ax_relations"
            "rv_ax_action"
            "rv_ax_set_value"
            "rv_ax_set_number"
            "rv_ax_text_length"
            "rv_ax_text"
            "rv_ax_text_boundary"
            "rv_ax_text_selection"
            "rv_ax_text_caret"
            "rv_ax_text_set_selection"
            "rv_ax_text_rects"
            "rv_ax_text_offset_at"
            "rv_ax_text_child_range"
            "rv_host_load_svg"
            "rv_capability_count"
            "rv_capability_name_at"
            "rv_host_capability_fact"
            "rv_host_capability_value_kind"
            "rv_host_capability_value_number"
            "rv_host_capability_value_text"
            "rv_host_select_svg_view"
            "rv_image_decode"
            "rv_font_load"
            "rv_resource_cancel"
            "rv_resource_release"
            "rv_host_construct_event"
            "rv_custom_event_detail_json"
            "rv_host_create_event_target"
            "rv_event_target_retain"
            "rv_event_target_release"
            "rv_node_as_event_target"
            "rv_event_target_as_node"
            "rv_event_target_equals"
            "rv_event_target_add_listener"
            "rv_event_target_dispatch"
            "rv_event_get_target"
            "rv_event_get_related_target"
            "rv_host_window_event_target"
            "rv_host_max_touch_points"
            "rv_host_window_metrics"
            "rv_host_set_visible"
            "rv_host_match_media"
            "rv_media_query_matches"
            "rv_media_query_media"
            "rv_blob_read_bytes"
            "rv_file_list_create"
            "rv_blob_read"
            "rv_blob_url_read"
            "rv_blob_read_result"
            "rv_blob_read_type"
            "rv_blob_read_error"
            "rv_file_create_from_path"
            "rv_file_reader_result"
            "rv_file_reader_error"
            "rv_text_segment"
            "rv_text_segments_release"
            "rv_text_segmentation_version"
            "rv_host_set_page_scale"
            "rv_host_page_scale"
            "rv_host_set_obscured_insets"
            "rv_host_set_screen"
            "rv_host_set_diagnostics"
            "rv_host_inspect_render_tree"
            "rv_host_inspect_matched_rules"
            "rv_diagnostic_kind"
            "rv_diagnostic_text"
            "rv_diagnostic_count"
            "rv_diagnostic_entry_string"
            "rv_diagnostic_entry_number"
            "rv_diagnostic_release"
            "rv_diagnostic_live_count"
            "rv_host_inspect_box_model"
            "rv_node_convert_points"
            "rv_node_box_quad"
            "rv_host_inspect_cascade"
        |]

    let Counts: int64 array = Array.zeroCreate Names.Length
    let Ticks: int64 array = Array.zeroCreate Names.Length
    let mutable On = false
    /// <summary>The sum of <c>Ticks</c>.</summary>
    let mutable Elapsed = 0L

/// <summary>The header's functions as P/Invoke declarations.</summary>
module Raw =

    [<DllImport(Lib)>]
    extern int rv_abi_version()

    [<DllImport(Lib)>]
    extern int64 rv_process_id()

    [<DllImport(Lib)>]
    extern nativeint rv_host_create(int width, int height)

    [<DllImport(Lib)>]
    extern void rv_host_destroy(nativeint host)

    [<DllImport(Lib)>]
    extern int rv_host_load_html(nativeint host, [<MarshalAs(UnmanagedType.LPUTF8Str)>] string html)

    [<DllImport(Lib)>]
    extern int rv_host_scripts_enabled(nativeint host)

    [<DllImport(Lib)>]
    extern int rv_host_vm_entry_disallowed(nativeint host)

    [<DllImport(Lib)>]
    extern nativeint rv_document_body(nativeint host)

    [<DllImport(Lib)>]
    extern nativeint rv_document_head(nativeint host)

    [<DllImport(Lib)>]
    extern nativeint rv_document_get_element_by_id(
        nativeint host,
        [<MarshalAs(UnmanagedType.LPUTF8Str)>] string elementId
    )

    [<DllImport(Lib)>]
    extern nativeint rv_document_create_element(nativeint host, [<MarshalAs(UnmanagedType.LPUTF8Str)>] string tagName)

    [<DllImport(Lib)>]
    extern nativeint rv_document_create_text(nativeint host, [<MarshalAs(UnmanagedType.LPUTF8Str)>] string data)

    [<DllImport(Lib)>]
    extern int rv_node_append_child(nativeint parent, nativeint child)

    [<DllImport(Lib)>]
    extern int rv_node_set_text_content(nativeint node, [<MarshalAs(UnmanagedType.LPUTF8Str)>] string text)

    [<DllImport(Lib)>]
    extern int rv_element_set_attribute(
        nativeint node,
        [<MarshalAs(UnmanagedType.LPUTF8Str)>] string name,
        [<MarshalAs(UnmanagedType.LPUTF8Str)>] string value
    )

    [<DllImport(Lib)>]
    extern void rv_node_release(nativeint node)

    [<DllImport(Lib)>]
    extern int rv_host_paint_rgba(nativeint host, [<In; Out>] byte[] rgba, int length)

    [<DllImport(Lib)>]
    extern int rv_host_set_accelerated_compositing(nativeint host, int mode)

    [<DllImport(Lib)>]
    extern int rv_host_acquire_d3d11_frame(nativeint host, nativeint consumerDevice, nativeint& frame)

    [<DllImport(Lib)>]
    extern int rv_gpu_frame_info(nativeint value, nativeint& texture, int& width, int& height, int& format)

    [<DllImport(Lib)>]
    extern int rv_gpu_frame_release(nativeint value)

    [<DllImport(Lib)>]
    extern nativeint rv_node_add_event_listener(
        nativeint target,
        [<MarshalAs(UnmanagedType.LPUTF8Str)>] string ``type``,
        int capture,
        nativeint callback,
        nativeint context
    )

    [<DllImport(Lib)>]
    extern int rv_listener_remove(nativeint listener)

    [<DllImport(Lib)>]
    extern nativeint rv_node_filter_create(nativeint target, nativeint callback, nativeint context, nativeint release)

    [<DllImport(Lib)>]
    extern int rv_node_filter_context(nativeint filter, nativeint& context)

    [<DllImport(Lib)>]
    extern int rv_node_dispatch_event(
        nativeint target,
        [<MarshalAs(UnmanagedType.LPUTF8Str)>] string ``type``,
        int bubbles,
        int cancelable,
        int& defaultPrevented
    )

    [<DllImport(Lib)>]
    extern int rv_element_click(nativeint node)

    [<DllImport(Lib)>]
    extern int rv_input_checked(nativeint node)

    [<DllImport(Lib)>]
    extern int rv_event_phase(nativeint ``event``)

    [<DllImport(Lib)>]
    extern int rv_event_default_prevented(nativeint ``event``)

    [<DllImport(Lib)>]
    extern void rv_event_prevent_default(nativeint ``event``)

    [<DllImport(Lib)>]
    extern void rv_event_stop_propagation(nativeint ``event``)

    [<DllImport(Lib)>]
    extern nativeint rv_host_document(nativeint host)

    [<DllImport(Lib)>]
    extern nativeint rv_document_create_comment(nativeint host, [<MarshalAs(UnmanagedType.LPUTF8Str)>] string data)

    [<DllImport(Lib)>]
    extern nativeint rv_document_create_fragment(nativeint host)

    [<DllImport(Lib)>]
    extern nativeint rv_document_import_node(nativeint host, nativeint node, int deep)

    [<DllImport(Lib)>]
    extern nativeint rv_node_parse_fragment(nativeint context, [<MarshalAs(UnmanagedType.LPUTF8Str)>] string markup)

    [<DllImport(Lib)>]
    extern int rv_node_type(nativeint node)

    [<DllImport(Lib)>]
    extern nativeint rv_node_relative(nativeint node, int relation)

    [<DllImport(Lib)>]
    extern int rv_node_get_string(nativeint node, int property, byte[] buffer, int capacity, int[] length)

    [<DllImport(Lib)>]
    extern int rv_node_set_string(nativeint node, int property, [<MarshalAs(UnmanagedType.LPUTF8Str)>] string value)

    [<DllImport(Lib)>]
    extern int rv_node_insert_before(nativeint parent, nativeint child, nativeint reference)

    [<DllImport(Lib)>]
    extern int rv_node_remove_child(nativeint parent, nativeint child)

    [<DllImport(Lib)>]
    extern int rv_node_replace_child(nativeint parent, nativeint newChild, nativeint oldChild)

    [<DllImport(Lib)>]
    extern int rv_node_remove(nativeint node)

    [<DllImport(Lib)>]
    extern nativeint rv_node_clone(nativeint node, int deep)

    [<DllImport(Lib)>]
    extern int rv_node_contains(nativeint node, nativeint other)

    [<DllImport(Lib)>]
    extern int rv_node_is_connected(nativeint node)

    [<DllImport(Lib)>]
    extern int rv_element_get_attribute(
        nativeint node,
        [<MarshalAs(UnmanagedType.LPUTF8Str)>] string name,
        byte[] buffer,
        int capacity,
        int[] length
    )

    [<DllImport(Lib)>]
    extern int rv_element_remove_attribute(nativeint node, [<MarshalAs(UnmanagedType.LPUTF8Str)>] string name)

    [<DllImport(Lib)>]
    extern int rv_input_set_checked(nativeint node, int ``checked``)

    [<DllImport(Lib)>]
    extern nativeint rv_event_retain(nativeint ``event``)

    [<DllImport(Lib)>]
    extern void rv_event_release(nativeint ``event``)

    [<DllImport(Lib)>]
    extern nativeint rv_host_create_event(
        nativeint host,
        int eventInterface,
        [<MarshalAs(UnmanagedType.LPUTF8Str)>] string ``type``,
        int bubbles,
        int cancelable
    )

    [<DllImport(Lib)>]
    extern int rv_node_dispatch(nativeint target, nativeint ``event``, int& defaultPrevented)

    [<DllImport(Lib)>]
    extern int rv_event_interface(nativeint ``event``)

    [<DllImport(Lib)>]
    extern int rv_event_flags(nativeint ``event``)

    [<DllImport(Lib)>]
    extern int rv_event_type(nativeint ``event``, byte[] buffer, int capacity, int[] length)

    [<DllImport(Lib)>]
    extern int rv_event_key(nativeint ``event``, byte[] buffer, int capacity, int[] length)

    [<DllImport(Lib)>]
    extern nativeint rv_event_target(nativeint ``event``, int current)

    [<DllImport(Lib)>]
    extern int rv_last_exception(int part, byte[] buffer, int capacity, int[] length)

    [<DllImport(Lib)>]
    extern nativeint rv_node_query_selector(
        nativeint scope,
        [<MarshalAs(UnmanagedType.LPUTF8Str)>] string selectors,
        int& status
    )

    [<DllImport(Lib)>]
    extern int rv_node_query_selector_all(
        nativeint scope,
        [<MarshalAs(UnmanagedType.LPUTF8Str)>] string selectors,
        nativeint[] nodes,
        int capacity,
        int& count
    )

    [<DllImport(Lib)>]
    extern int rv_node_query_selector_all_uncached(
        nativeint scope,
        [<MarshalAs(UnmanagedType.LPUTF8Str)>] string selectors,
        nativeint[] nodes,
        int capacity,
        int& count
    )

    [<DllImport(Lib)>]
    extern int rv_node_ref_count(nativeint node)

    [<DllImport(Lib)>]
    extern nativeint rv_node_watch(nativeint node)

    [<DllImport(Lib)>]
    extern int rv_watch_alive(nativeint watch)

    [<DllImport(Lib)>]
    extern nativeint rv_watch_node(nativeint watch)

    [<DllImport(Lib)>]
    extern void rv_watch_release(nativeint watch)

    [<DllImport(Lib)>]
    extern void rv_release_memory()

    [<DllImport(Lib)>]
    extern void rv_collect_garbage()

    [<DllImport(Lib)>]
    extern void rv_collect_garbage_eden()

    [<DllImport(Lib)>]
    extern int rv_node_has_wrapper(nativeint node)

    [<DllImport(Lib)>]
    extern int rv_element_attribute_count(nativeint node)

    [<DllImport(Lib)>]
    extern int rv_element_attribute_at(nativeint node, int index, int part, byte[] buffer, int capacity, int[] length)

    [<DllImport(Lib)>]
    extern int rv_element_focus(nativeint node)

    [<DllImport(Lib)>]
    extern nativeint rv_document_active_element(nativeint host)

    [<DllImport(Lib)>]
    extern int rv_run_loop_cycle(int milliseconds)

    [<DllImport(Lib)>]
    extern int rv_host_set_resource_handler(nativeint host, nativeint handler, nativeint context)

    [<DllImport(Lib)>]
    extern int rv_host_set_form_submission_handler(nativeint host, nativeint handler, nativeint context)

    [<DllImport(Lib)>]
    extern int rv_resource_load_finish(
        nativeint value,
        [<In>] byte[] data,
        int length,
        [<MarshalAs(UnmanagedType.LPUTF8Str)>] string contentType
    )

    [<DllImport(Lib)>]
    extern int rv_resource_load_fail(nativeint value)

    [<DllImport(Lib)>]
    extern int rv_abi_has([<MarshalAs(UnmanagedType.LPUTF8Str)>] string feature)

    [<DllImport(Lib)>]
    extern int rv_host_resize(nativeint host, int width, int height)

    [<DllImport(Lib)>]
    extern int rv_host_set_device_scale(nativeint host, float32 scale)

    [<DllImport(Lib)>]
    extern int rv_host_paint_size(nativeint host, int& width, int& height)

    [<DllImport(Lib)>]
    extern int rv_host_mouse(nativeint host, int action, int x, int y, int button, int clickCount, int modifiers)

    [<DllImport(Lib)>]
    extern int rv_host_wheel(nativeint host, int x, int y, float32 deltaX, float32 deltaY, int modifiers)

    [<DllImport(Lib)>]
    extern int rv_host_key(
        nativeint host,
        int action,
        [<MarshalAs(UnmanagedType.LPUTF8Str)>] string key,
        [<MarshalAs(UnmanagedType.LPUTF8Str)>] string code,
        [<MarshalAs(UnmanagedType.LPUTF8Str)>] string text,
        int modifiers,
        int repeat
    )

    [<DllImport(Lib)>]
    extern int rv_host_set_focused(nativeint host, int focused)

    [<DllImport(Lib)>]
    extern int rv_host_set_frame_callback(nativeint host, nativeint callback, nativeint context)

    [<DllImport(Lib)>]
    extern int rv_host_update(nativeint host)

    [<DllImport(Lib)>]
    extern int rv_host_dirty_rect(nativeint host, int& x, int& y, int& width, int& height)

    [<DllImport(Lib)>]
    extern int rv_event_number(nativeint ``event``, int number, double& value)

    [<DllImport(Lib)>]
    extern int rv_event_string(nativeint ``event``, int property, byte[] buffer, int capacity, int[] length)

    [<DllImport(Lib)>]
    extern nativeint rv_event_related_target(nativeint ``event``)

    [<DllImport(Lib)>]
    extern int rv_host_cursor(nativeint host)

    [<DllImport(Lib)>]
    extern int rv_host_scroll_position(nativeint host, int& x, int& y)

    [<DllImport(Lib)>]
    extern int rv_host_scroll_to(nativeint host, int x, int y)

    [<DllImport(Lib)>]
    extern int rv_host_ime_set_composition(
        nativeint host,
        [<MarshalAs(UnmanagedType.LPUTF8Str)>] string text,
        int selectionStart,
        int selectionEnd
    )

    [<DllImport(Lib)>]
    extern int rv_host_ime_commit(nativeint host, [<MarshalAs(UnmanagedType.LPUTF8Str)>] string text)

    [<DllImport(Lib)>]
    extern int rv_host_ime_cancel(nativeint host)

    [<DllImport(Lib)>]
    extern int rv_host_ime_rect(nativeint host, int& x, int& y, int& width, int& height)

    [<DllImport(Lib)>]
    extern int rv_element_class(nativeint node, [<MarshalAs(UnmanagedType.LPUTF8Str)>] string token, int operation)

    [<DllImport(Lib)>]
    extern int rv_element_set_style(
        nativeint node,
        [<MarshalAs(UnmanagedType.LPUTF8Str)>] string property,
        [<MarshalAs(UnmanagedType.LPUTF8Str)>] string value,
        int important
    )

    [<DllImport(Lib)>]
    extern int rv_element_get_style(
        nativeint node,
        [<MarshalAs(UnmanagedType.LPUTF8Str)>] string property,
        byte[] buffer,
        int capacity,
        int[] length
    )

    [<DllImport(Lib)>]
    extern int rv_element_computed_style(
        nativeint node,
        [<MarshalAs(UnmanagedType.LPUTF8Str)>] string property,
        byte[] buffer,
        int capacity,
        int[] length
    )

    [<DllImport(Lib)>]
    extern int rv_element_rect(nativeint node, double& x, double& y, double& width, double& height)

    [<DllImport(Lib)>]
    extern nativeint rv_host_element_at(nativeint host, int x, int y)

    [<DllImport(Lib)>]
    extern int rv_element_scroll_into_view(nativeint node, int block, int inlineAlignment, int smooth)

    [<DllImport(Lib)>]
    extern int rv_element_scroll_metric(nativeint node, int metric, int& value)

    [<DllImport(Lib)>]
    extern int rv_element_scroll_to(nativeint node, int left, int top, int smooth)

    [<DllImport(Lib)>]
    extern nativeint rv_element_attach_shadow(nativeint node, int& status)

    [<DllImport(Lib)>]
    extern nativeint rv_element_shadow_root(nativeint node)

    [<DllImport(Lib)>]
    extern int rv_text_selection(nativeint node, int& start, int& ``end``)

    [<DllImport(Lib)>]
    extern int rv_text_set_selection(nativeint node, int start, int ``end``)

    [<DllImport(Lib)>]
    extern int rv_element_animations(nativeint node, int subtree, nativeint[] animations, int capacity, int& count)

    [<DllImport(Lib)>]
    extern int rv_host_animations(nativeint host, nativeint[] animations, int capacity, int& count)

    [<DllImport(Lib)>]
    extern void rv_animation_release(nativeint animation)

    [<DllImport(Lib)>]
    extern int rv_animation_control(nativeint animation, int action)

    [<DllImport(Lib)>]
    extern int rv_animation_state(nativeint animation)

    [<DllImport(Lib)>]
    extern int rv_animation_time(nativeint animation, double& milliseconds)

    [<DllImport(Lib)>]
    extern int rv_animation_seek(nativeint animation, float milliseconds)

    [<DllImport(Lib)>]
    extern int rv_animation_set_rate(nativeint animation, float rate)

    [<DllImport(Lib)>]
    extern int rv_animation_name(nativeint animation, byte[] buffer, int capacity, int[] length)

    [<DllImport(Lib)>]
    extern nativeint rv_animation_target(nativeint animation)

    [<DllImport(Lib)>]
    extern nativeint rv_node_retain(nativeint node)

    [<DllImport(Lib)>]
    extern nativeint rv_host_observe_resize(nativeint host, nativeint callback, nativeint context)

    [<DllImport(Lib)>]
    extern nativeint rv_host_observe_intersection(
        nativeint host,
        nativeint callback,
        nativeint context,
        [<MarshalAs(UnmanagedType.LPUTF8Str)>] string rootMargin,
        [<In>] float[] thresholds,
        int thresholdCount
    )

    [<DllImport(Lib)>]
    extern int rv_observer_observe(nativeint value, nativeint element)

    [<DllImport(Lib)>]
    extern int rv_observer_unobserve(nativeint value, nativeint element)

    [<DllImport(Lib)>]
    extern void rv_observer_release(nativeint value)

    [<DllImport(Lib)>]
    extern int rv_element_snapshot(nativeint node, [<In; Out>] byte[] rgba, int length, int& width, int& height)

    [<DllImport(Lib)>]
    extern int rv_host_paint_rgba_rect(
        nativeint host,
        [<In; Out>] byte[] rgba,
        int length,
        int x,
        int y,
        int width,
        int height
    )

    [<DllImport(Lib)>]
    extern int rv_host_set_popup_handler(nativeint host, nativeint callback, nativeint context)

    [<DllImport(Lib)>]
    extern int rv_popup_item_count(nativeint value)

    [<DllImport(Lib)>]
    extern int rv_popup_item(
        nativeint value,
        int index,
        int& kind,
        int& enabled,
        byte[] buffer,
        int capacity,
        int[] length
    )

    [<DllImport(Lib)>]
    extern int rv_popup_choose(nativeint value, int index)

    [<DllImport(Lib)>]
    extern int rv_host_tooltip(nativeint host, byte[] buffer, int capacity, int[] length)

    [<DllImport(Lib)>]
    extern int rv_host_set_clipboard(nativeint host, int style, nativeint write, nativeint read, nativeint context)

    [<DllImport(Lib)>]
    extern int rv_clipboard_offer(
        nativeint value,
        [<MarshalAs(UnmanagedType.LPUTF8Str)>] string ``type``,
        [<MarshalAs(UnmanagedType.LPUTF8Str)>] string data
    )

    [<DllImport(Lib)>]
    extern int rv_host_edit(nativeint host, int command)

    [<DllImport(Lib)>]
    extern int rv_host_set_drag(nativeint host, int style)

    [<DllImport(Lib)>]
    extern nativeint rv_drag_data_create()

    [<DllImport(Lib)>]
    extern int rv_drag_data_add(
        nativeint value,
        [<MarshalAs(UnmanagedType.LPUTF8Str)>] string ``type``,
        [<MarshalAs(UnmanagedType.LPUTF8Str)>] string data
    )

    [<DllImport(Lib)>]
    extern void rv_drag_data_release(nativeint value)

    [<DllImport(Lib)>]
    extern int rv_host_drag(nativeint host, int action, int x, int y, int allowed, nativeint data, int modifiers)

    [<DllImport(Lib)>]
    extern int rv_host_set_drag_start(nativeint host, nativeint callback, nativeint context)

    [<DllImport(Lib)>]
    extern int rv_drag_item_count(nativeint value)

    [<DllImport(Lib)>]
    extern int rv_drag_item_type(nativeint value, int index, byte[] buffer, int capacity, int[] length)

    [<DllImport(Lib)>]
    extern int rv_drag_item_value(nativeint value, int index, byte[] buffer, int capacity, int[] length)

    [<DllImport(Lib)>]
    extern nativeint rv_drag_data(nativeint value)

    [<DllImport(Lib)>]
    extern int rv_drag_image(
        nativeint value,
        [<In; Out>] byte[] rgba,
        int length,
        int& width,
        int& height,
        int& offsetX,
        int& offsetY
    )

    [<DllImport(Lib)>]
    extern int rv_drag_end(nativeint value, int x, int y, int operation)

    [<DllImport(Lib)>]
    extern int rv_host_set_accessibility(nativeint host, int enabled, nativeint callback, nativeint context)

    [<DllImport(Lib)>]
    extern int rv_host_attach_uia(nativeint host, nativeint hwnd)

    [<DllImport(Lib)>]
    extern int rv_host_detach_uia(nativeint host)

    [<DllImport(Lib)>]
    extern nativeint rv_host_ax_root(nativeint host)

    [<DllImport(Lib)>]
    extern nativeint rv_host_ax_focus(nativeint host)

    [<DllImport(Lib)>]
    extern nativeint rv_host_ax_hit_test(nativeint host, int x, int y)

    [<DllImport(Lib)>]
    extern nativeint rv_node_ax(nativeint node)

    [<DllImport(Lib)>]
    extern nativeint rv_ax_dom_node(nativeint ax)

    [<DllImport(Lib)>]
    extern nativeint rv_ax_retain(nativeint ax)

    [<DllImport(Lib)>]
    extern void rv_ax_release(nativeint ax)

    [<DllImport(Lib)>]
    extern int64 rv_ax_id(nativeint ax)

    [<DllImport(Lib)>]
    extern int rv_ax_role(nativeint ax)

    [<DllImport(Lib)>]
    extern int rv_ax_states(nativeint ax)

    [<DllImport(Lib)>]
    extern int rv_ax_string(nativeint ax, int property, byte[] buffer, int capacity, int[] length)

    [<DllImport(Lib)>]
    extern int rv_ax_number(nativeint ax, int property, double& value)

    [<DllImport(Lib)>]
    extern int rv_ax_rect(nativeint ax, double& x, double& y, double& width, double& height)

    [<DllImport(Lib)>]
    extern nativeint rv_ax_parent(nativeint ax)

    [<DllImport(Lib)>]
    extern int rv_ax_children(nativeint ax, nativeint[] nodes, int capacity, int& count)

    [<DllImport(Lib)>]
    extern int rv_ax_relations(nativeint ax, int kind, nativeint[] nodes, int capacity, int& count)

    [<DllImport(Lib)>]
    extern int rv_ax_action(nativeint ax, int action)

    [<DllImport(Lib)>]
    extern int rv_ax_set_value(nativeint ax, [<MarshalAs(UnmanagedType.LPUTF8Str)>] string value)

    [<DllImport(Lib)>]
    extern int rv_ax_set_number(nativeint ax, float value)

    [<DllImport(Lib)>]
    extern int rv_ax_text_length(nativeint ax)

    [<DllImport(Lib)>]
    extern int rv_ax_text(nativeint ax, int start, int ``end``, byte[] buffer, int capacity, int[] length)

    [<DllImport(Lib)>]
    extern int rv_ax_text_boundary(nativeint ax, int offset, int unit, int& start, int& ``end``)

    [<DllImport(Lib)>]
    extern int rv_ax_text_selection(nativeint ax, int& start, int& ``end``)

    [<DllImport(Lib)>]
    extern int rv_ax_text_caret(nativeint ax)

    [<DllImport(Lib)>]
    extern int rv_ax_text_set_selection(nativeint ax, int start, int ``end``)

    [<DllImport(Lib)>]
    extern int rv_ax_text_rects(
        nativeint ax,
        int start,
        int ``end``,
        [<In; Out>] float[] rects,
        int capacity,
        int& count
    )

    [<DllImport(Lib)>]
    extern int rv_ax_text_offset_at(nativeint ax, int x, int y)

    [<DllImport(Lib)>]
    extern int rv_ax_text_child_range(nativeint ancestor, nativeint child, int& start, int& ``end``)

    [<DllImport(Lib)>]
    extern int rv_host_load_svg(nativeint host, [<MarshalAs(UnmanagedType.LPUTF8Str)>] string svg)

    [<DllImport(Lib)>]
    extern int rv_capability_count(int category)

    [<DllImport(Lib)>]
    extern int rv_capability_name_at(int category, int index, byte[] buffer, int capacity, int[] length)

    [<DllImport(Lib)>]
    extern int rv_host_capability_fact(
        nativeint host,
        int category,
        [<MarshalAs(UnmanagedType.LPUTF8Str)>] string name,
        int dimension,
        int& fact
    )

    [<DllImport(Lib)>]
    extern int rv_host_capability_value_kind(
        nativeint host,
        int category,
        [<MarshalAs(UnmanagedType.LPUTF8Str)>] string name,
        int& kind
    )

    [<DllImport(Lib)>]
    extern int rv_host_capability_value_number(
        nativeint host,
        int category,
        [<MarshalAs(UnmanagedType.LPUTF8Str)>] string name,
        double& number
    )

    [<DllImport(Lib)>]
    extern int rv_host_capability_value_text(
        nativeint host,
        int category,
        [<MarshalAs(UnmanagedType.LPUTF8Str)>] string name,
        byte[] buffer,
        int capacity,
        int[] length
    )

    [<DllImport(Lib)>]
    extern int rv_host_select_svg_view(
        nativeint host,
        [<MarshalAs(UnmanagedType.LPUTF8Str)>] string fragment,
        int& selected
    )

    [<DllImport(Lib)>]
    extern int rv_image_decode(
        nativeint host,
        nativeint image,
        nativeint completion,
        nativeint context,
        uint64& operation
    )

    [<DllImport(Lib)>]
    extern int rv_font_load(
        nativeint host,
        [<MarshalAs(UnmanagedType.LPUTF8Str)>] string family,
        [<In>] byte[] data,
        int length,
        nativeint completion,
        nativeint context,
        uint64& operation
    )

    [<DllImport(Lib)>]
    extern int rv_resource_cancel(uint64 operation)

    [<DllImport(Lib)>]
    extern int rv_resource_release(uint64 operation)

    [<DllImport(Lib)>]
    extern nativeint rv_host_construct_event(
        nativeint host,
        int kind,
        [<MarshalAs(UnmanagedType.LPUTF8Str)>] string ``type``,
        EventInit& init
    )

    [<DllImport(Lib)>]
    extern int rv_custom_event_detail_json(nativeint ``event``, byte[] buffer, int capacity, int[] length)

    [<DllImport(Lib)>]
    extern nativeint rv_host_create_event_target(nativeint host)

    [<DllImport(Lib)>]
    extern nativeint rv_event_target_retain(nativeint target)

    [<DllImport(Lib)>]
    extern void rv_event_target_release(nativeint target)

    [<DllImport(Lib)>]
    extern nativeint rv_node_as_event_target(nativeint node)

    [<DllImport(Lib)>]
    extern nativeint rv_event_target_as_node(nativeint target)

    [<DllImport(Lib)>]
    extern int rv_event_target_equals(nativeint left, nativeint right)

    [<DllImport(Lib)>]
    extern nativeint rv_event_target_add_listener(
        nativeint target,
        [<MarshalAs(UnmanagedType.LPUTF8Str)>] string ``type``,
        int flags,
        nativeint callback,
        nativeint context
    )

    [<DllImport(Lib)>]
    extern int rv_event_target_dispatch(nativeint target, nativeint ``event``, int& defaultPrevented)

    [<DllImport(Lib)>]
    extern nativeint rv_event_get_target(nativeint ``event``, int current)

    [<DllImport(Lib)>]
    extern nativeint rv_event_get_related_target(nativeint ``event``)

    [<DllImport(Lib)>]
    extern nativeint rv_host_window_event_target(nativeint host)

    [<DllImport(Lib)>]
    extern int rv_host_max_touch_points(nativeint host, int& value)

    [<DllImport(Lib)>]
    extern int rv_host_window_metrics(nativeint host, nativeint metrics)

    [<DllImport(Lib)>]
    extern int rv_host_set_visible(nativeint host, int visible)

    [<DllImport(Lib)>]
    extern nativeint rv_host_match_media(nativeint host, [<MarshalAs(UnmanagedType.LPUTF8Str)>] string query)

    [<DllImport(Lib)>]
    extern int rv_media_query_matches(nativeint target, int& matches)

    [<DllImport(Lib)>]
    extern int rv_media_query_media(nativeint target, byte[] buffer, int capacity, int[] length)

    [<DllImport(Lib)>]
    extern int rv_blob_read_bytes(nativeint blob, [<In; Out>] byte[] buffer, int64 capacity, int64& length)

    [<DllImport(Lib)>]
    extern int rv_file_list_create([<In>] nativeint[] files, int count, nativeint[] result)

    [<DllImport(Lib)>]
    extern int rv_blob_read(
        nativeint host,
        nativeint blob,
        int mode,
        nativeint completion,
        nativeint context,
        uint64& operation
    )

    [<DllImport(Lib)>]
    extern int rv_blob_url_read(
        nativeint host,
        [<In>] byte[] url,
        int url_length,
        nativeint completion,
        nativeint context,
        uint64& operation
    )

    [<DllImport(Lib)>]
    extern int rv_blob_read_result(uint64 operation, [<In; Out>] byte[] buffer, int64 capacity, int64& length)

    [<DllImport(Lib)>]
    extern int rv_blob_read_type(uint64 operation, byte[] buffer, int capacity, int[] length)

    [<DllImport(Lib)>]
    extern int rv_blob_read_error(uint64 operation, byte[] buffer, int capacity, int[] length)

    [<DllImport(Lib)>]
    extern int rv_file_create_from_path(nativeint host, [<In>] byte[] path, int path_length, nativeint[] result)

    [<DllImport(Lib)>]
    extern int rv_file_reader_result(
        nativeint reader,
        int& kind,
        [<In; Out>] byte[] buffer,
        int64 capacity,
        int64& length
    )

    [<DllImport(Lib)>]
    extern int rv_file_reader_error(nativeint reader, byte[] buffer, int capacity, int[] length)

    [<DllImport(Lib)>]
    extern int rv_text_segment(
        int granularity,
        [<MarshalAs(UnmanagedType.LPUTF8Str)>] string locale,
        [<In>] uint16[] text,
        int length,
        TextSegments& result
    )

    [<DllImport(Lib)>]
    extern void rv_text_segments_release(TextSegments& segments)

    [<DllImport(Lib)>]
    extern int rv_text_segmentation_version(byte[] buffer, int capacity, int[] length)

    [<DllImport(Lib)>]
    extern int rv_host_set_page_scale(nativeint host, float scale, int originX, int originY)

    [<DllImport(Lib)>]
    extern int rv_host_page_scale(nativeint host, double& scale)

    [<DllImport(Lib)>]
    extern int rv_host_set_obscured_insets(nativeint host, float top, float right, float bottom, float left)

    [<DllImport(Lib)>]
    extern int rv_host_set_screen(nativeint host, nativeint metrics)

    [<DllImport(Lib)>]
    extern int rv_host_set_diagnostics(nativeint host, int enabled)

    [<DllImport(Lib)>]
    extern int rv_host_inspect_render_tree(nativeint host, nativeint target, int flags, nativeint[] diagnostic)

    [<DllImport(Lib)>]
    extern int rv_host_inspect_matched_rules(nativeint host, nativeint element, nativeint[] diagnostic)

    [<DllImport(Lib)>]
    extern int rv_diagnostic_kind(nativeint diagnostic)

    [<DllImport(Lib)>]
    extern int rv_diagnostic_text(nativeint diagnostic, byte[] buffer, int capacity, int[] length)

    [<DllImport(Lib)>]
    extern int rv_diagnostic_count(nativeint diagnostic)

    [<DllImport(Lib)>]
    extern int rv_diagnostic_entry_string(
        nativeint diagnostic,
        int index,
        int field,
        byte[] buffer,
        int capacity,
        int[] length
    )

    [<DllImport(Lib)>]
    extern int rv_diagnostic_entry_number(nativeint diagnostic, int index, int field, double& value)

    [<DllImport(Lib)>]
    extern void rv_diagnostic_release(nativeint diagnostic)

    [<DllImport(Lib)>]
    extern int rv_diagnostic_live_count()

    [<DllImport(Lib)>]
    extern int rv_host_inspect_box_model(nativeint host, nativeint element, double& values)

    [<DllImport(Lib)>]
    extern int rv_node_convert_points(
        nativeint from,
        int fromSpace,
        nativeint ``to``,
        int toSpace,
        double& xy,
        int count
    )

    [<DllImport(Lib)>]
    extern int rv_node_box_quad(nativeint node, int box, nativeint ``to``, int toSpace, double& quad)
    [<DllImport(Lib)>]
    extern int rv_host_inspect_cascade(nativeint host, nativeint element, [<In>] byte[] property, int property_length, nativeint[] diagnostic)

let rv_abi_version () : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_abi_version ()
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[0] <- Calls.Counts[0] + 1L
        Calls.Ticks[0] <- Calls.Ticks[0] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_abi_version ()

let rv_process_id () : int64 =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_process_id ()
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[1] <- Calls.Counts[1] + 1L
        Calls.Ticks[1] <- Calls.Ticks[1] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_process_id ()

let rv_host_create (width: int, height: int) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_create (width, height)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[2] <- Calls.Counts[2] + 1L
        Calls.Ticks[2] <- Calls.Ticks[2] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_create (width, height)

let rv_host_destroy (host: nativeint) : unit =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_destroy (host)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[3] <- Calls.Counts[3] + 1L
        Calls.Ticks[3] <- Calls.Ticks[3] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_destroy (host)

let rv_host_load_html (host: nativeint, html: string) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_load_html (host, html)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[4] <- Calls.Counts[4] + 1L
        Calls.Ticks[4] <- Calls.Ticks[4] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_load_html (host, html)

let rv_host_scripts_enabled (host: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_scripts_enabled (host)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[5] <- Calls.Counts[5] + 1L
        Calls.Ticks[5] <- Calls.Ticks[5] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_scripts_enabled (host)

let rv_host_vm_entry_disallowed (host: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_vm_entry_disallowed (host)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[6] <- Calls.Counts[6] + 1L
        Calls.Ticks[6] <- Calls.Ticks[6] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_vm_entry_disallowed (host)

let rv_document_body (host: nativeint) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_document_body (host)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[7] <- Calls.Counts[7] + 1L
        Calls.Ticks[7] <- Calls.Ticks[7] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_document_body (host)

let rv_document_head (host: nativeint) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_document_head (host)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[8] <- Calls.Counts[8] + 1L
        Calls.Ticks[8] <- Calls.Ticks[8] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_document_head (host)

let rv_document_get_element_by_id (host: nativeint, elementId: string) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_document_get_element_by_id (host, elementId)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[9] <- Calls.Counts[9] + 1L
        Calls.Ticks[9] <- Calls.Ticks[9] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_document_get_element_by_id (host, elementId)

let rv_document_create_element (host: nativeint, tagName: string) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_document_create_element (host, tagName)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[10] <- Calls.Counts[10] + 1L
        Calls.Ticks[10] <- Calls.Ticks[10] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_document_create_element (host, tagName)

let rv_document_create_text (host: nativeint, data: string) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_document_create_text (host, data)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[11] <- Calls.Counts[11] + 1L
        Calls.Ticks[11] <- Calls.Ticks[11] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_document_create_text (host, data)

let rv_node_append_child (parent: nativeint, child: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_node_append_child (parent, child)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[12] <- Calls.Counts[12] + 1L
        Calls.Ticks[12] <- Calls.Ticks[12] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_node_append_child (parent, child)

let rv_node_set_text_content (node: nativeint, text: string) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_node_set_text_content (node, text)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[13] <- Calls.Counts[13] + 1L
        Calls.Ticks[13] <- Calls.Ticks[13] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_node_set_text_content (node, text)

let rv_element_set_attribute (node: nativeint, name: string, value: string) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_element_set_attribute (node, name, value)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[14] <- Calls.Counts[14] + 1L
        Calls.Ticks[14] <- Calls.Ticks[14] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_element_set_attribute (node, name, value)

let rv_node_release (node: nativeint) : unit =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_node_release (node)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[15] <- Calls.Counts[15] + 1L
        Calls.Ticks[15] <- Calls.Ticks[15] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_node_release (node)

let rv_host_paint_rgba (host: nativeint, rgba: byte[], length: int) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_paint_rgba (host, rgba, length)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[16] <- Calls.Counts[16] + 1L
        Calls.Ticks[16] <- Calls.Ticks[16] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_paint_rgba (host, rgba, length)

let rv_host_set_accelerated_compositing (host: nativeint, mode: int) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_set_accelerated_compositing (host, mode)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[17] <- Calls.Counts[17] + 1L
        Calls.Ticks[17] <- Calls.Ticks[17] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_set_accelerated_compositing (host, mode)

let rv_host_acquire_d3d11_frame (host: nativeint, consumerDevice: nativeint, frame: byref<nativeint>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_acquire_d3d11_frame (host, consumerDevice, &frame)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[18] <- Calls.Counts[18] + 1L
        Calls.Ticks[18] <- Calls.Ticks[18] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_acquire_d3d11_frame (host, consumerDevice, &frame)

let rv_gpu_frame_info
    (value: nativeint, texture: byref<nativeint>, width: byref<int>, height: byref<int>, format: byref<int>)
    : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_gpu_frame_info (value, &texture, &width, &height, &format)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[19] <- Calls.Counts[19] + 1L
        Calls.Ticks[19] <- Calls.Ticks[19] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_gpu_frame_info (value, &texture, &width, &height, &format)

let rv_gpu_frame_release (value: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_gpu_frame_release (value)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[20] <- Calls.Counts[20] + 1L
        Calls.Ticks[20] <- Calls.Ticks[20] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_gpu_frame_release (value)

let rv_node_add_event_listener
    (target: nativeint, ``type``: string, capture: int, callback: nativeint, context: nativeint)
    : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()

        let result =
            Raw.rv_node_add_event_listener (target, ``type``, capture, callback, context)

        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[21] <- Calls.Counts[21] + 1L
        Calls.Ticks[21] <- Calls.Ticks[21] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_node_add_event_listener (target, ``type``, capture, callback, context)

let rv_listener_remove (listener: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_listener_remove (listener)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[22] <- Calls.Counts[22] + 1L
        Calls.Ticks[22] <- Calls.Ticks[22] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_listener_remove (listener)

let rv_node_filter_create (target: nativeint, callback: nativeint, context: nativeint, release: nativeint) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_node_filter_create (target, callback, context, release)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[23] <- Calls.Counts[23] + 1L
        Calls.Ticks[23] <- Calls.Ticks[23] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_node_filter_create (target, callback, context, release)

let rv_node_filter_context (filter: nativeint, context: byref<nativeint>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_node_filter_context (filter, &context)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[24] <- Calls.Counts[24] + 1L
        Calls.Ticks[24] <- Calls.Ticks[24] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_node_filter_context (filter, &context)

let rv_node_dispatch_event
    (target: nativeint, ``type``: string, bubbles: int, cancelable: int, defaultPrevented: byref<int>)
    : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()

        let result =
            Raw.rv_node_dispatch_event (target, ``type``, bubbles, cancelable, &defaultPrevented)

        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[25] <- Calls.Counts[25] + 1L
        Calls.Ticks[25] <- Calls.Ticks[25] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_node_dispatch_event (target, ``type``, bubbles, cancelable, &defaultPrevented)

let rv_element_click (node: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_element_click (node)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[26] <- Calls.Counts[26] + 1L
        Calls.Ticks[26] <- Calls.Ticks[26] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_element_click (node)

let rv_input_checked (node: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_input_checked (node)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[27] <- Calls.Counts[27] + 1L
        Calls.Ticks[27] <- Calls.Ticks[27] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_input_checked (node)

let rv_event_phase (``event``: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_event_phase (``event``)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[28] <- Calls.Counts[28] + 1L
        Calls.Ticks[28] <- Calls.Ticks[28] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_event_phase (``event``)

let rv_event_default_prevented (``event``: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_event_default_prevented (``event``)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[29] <- Calls.Counts[29] + 1L
        Calls.Ticks[29] <- Calls.Ticks[29] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_event_default_prevented (``event``)

let rv_event_prevent_default (``event``: nativeint) : unit =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_event_prevent_default (``event``)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[30] <- Calls.Counts[30] + 1L
        Calls.Ticks[30] <- Calls.Ticks[30] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_event_prevent_default (``event``)

let rv_event_stop_propagation (``event``: nativeint) : unit =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_event_stop_propagation (``event``)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[31] <- Calls.Counts[31] + 1L
        Calls.Ticks[31] <- Calls.Ticks[31] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_event_stop_propagation (``event``)

let rv_host_document (host: nativeint) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_document (host)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[32] <- Calls.Counts[32] + 1L
        Calls.Ticks[32] <- Calls.Ticks[32] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_document (host)

let rv_document_create_comment (host: nativeint, data: string) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_document_create_comment (host, data)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[33] <- Calls.Counts[33] + 1L
        Calls.Ticks[33] <- Calls.Ticks[33] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_document_create_comment (host, data)

let rv_document_create_fragment (host: nativeint) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_document_create_fragment (host)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[34] <- Calls.Counts[34] + 1L
        Calls.Ticks[34] <- Calls.Ticks[34] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_document_create_fragment (host)

let rv_document_import_node (host: nativeint, node: nativeint, deep: int) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_document_import_node (host, node, deep)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[35] <- Calls.Counts[35] + 1L
        Calls.Ticks[35] <- Calls.Ticks[35] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_document_import_node (host, node, deep)

let rv_node_parse_fragment (context: nativeint, markup: string) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_node_parse_fragment (context, markup)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[36] <- Calls.Counts[36] + 1L
        Calls.Ticks[36] <- Calls.Ticks[36] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_node_parse_fragment (context, markup)

let rv_node_type (node: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_node_type (node)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[37] <- Calls.Counts[37] + 1L
        Calls.Ticks[37] <- Calls.Ticks[37] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_node_type (node)

let rv_node_relative (node: nativeint, relation: int) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_node_relative (node, relation)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[38] <- Calls.Counts[38] + 1L
        Calls.Ticks[38] <- Calls.Ticks[38] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_node_relative (node, relation)

let rv_node_get_string (node: nativeint, property: int, buffer: byte[], capacity: int, length: int[]) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_node_get_string (node, property, buffer, capacity, length)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[39] <- Calls.Counts[39] + 1L
        Calls.Ticks[39] <- Calls.Ticks[39] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_node_get_string (node, property, buffer, capacity, length)

let rv_node_set_string (node: nativeint, property: int, value: string) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_node_set_string (node, property, value)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[40] <- Calls.Counts[40] + 1L
        Calls.Ticks[40] <- Calls.Ticks[40] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_node_set_string (node, property, value)

let rv_node_insert_before (parent: nativeint, child: nativeint, reference: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_node_insert_before (parent, child, reference)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[41] <- Calls.Counts[41] + 1L
        Calls.Ticks[41] <- Calls.Ticks[41] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_node_insert_before (parent, child, reference)

let rv_node_remove_child (parent: nativeint, child: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_node_remove_child (parent, child)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[42] <- Calls.Counts[42] + 1L
        Calls.Ticks[42] <- Calls.Ticks[42] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_node_remove_child (parent, child)

let rv_node_replace_child (parent: nativeint, newChild: nativeint, oldChild: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_node_replace_child (parent, newChild, oldChild)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[43] <- Calls.Counts[43] + 1L
        Calls.Ticks[43] <- Calls.Ticks[43] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_node_replace_child (parent, newChild, oldChild)

let rv_node_remove (node: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_node_remove (node)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[44] <- Calls.Counts[44] + 1L
        Calls.Ticks[44] <- Calls.Ticks[44] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_node_remove (node)

let rv_node_clone (node: nativeint, deep: int) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_node_clone (node, deep)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[45] <- Calls.Counts[45] + 1L
        Calls.Ticks[45] <- Calls.Ticks[45] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_node_clone (node, deep)

let rv_node_contains (node: nativeint, other: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_node_contains (node, other)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[46] <- Calls.Counts[46] + 1L
        Calls.Ticks[46] <- Calls.Ticks[46] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_node_contains (node, other)

let rv_node_is_connected (node: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_node_is_connected (node)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[47] <- Calls.Counts[47] + 1L
        Calls.Ticks[47] <- Calls.Ticks[47] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_node_is_connected (node)

let rv_element_get_attribute (node: nativeint, name: string, buffer: byte[], capacity: int, length: int[]) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_element_get_attribute (node, name, buffer, capacity, length)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[48] <- Calls.Counts[48] + 1L
        Calls.Ticks[48] <- Calls.Ticks[48] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_element_get_attribute (node, name, buffer, capacity, length)

let rv_element_remove_attribute (node: nativeint, name: string) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_element_remove_attribute (node, name)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[49] <- Calls.Counts[49] + 1L
        Calls.Ticks[49] <- Calls.Ticks[49] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_element_remove_attribute (node, name)

let rv_input_set_checked (node: nativeint, ``checked``: int) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_input_set_checked (node, ``checked``)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[50] <- Calls.Counts[50] + 1L
        Calls.Ticks[50] <- Calls.Ticks[50] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_input_set_checked (node, ``checked``)

let rv_event_retain (``event``: nativeint) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_event_retain (``event``)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[51] <- Calls.Counts[51] + 1L
        Calls.Ticks[51] <- Calls.Ticks[51] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_event_retain (``event``)

let rv_event_release (``event``: nativeint) : unit =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_event_release (``event``)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[52] <- Calls.Counts[52] + 1L
        Calls.Ticks[52] <- Calls.Ticks[52] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_event_release (``event``)

let rv_host_create_event
    (host: nativeint, eventInterface: int, ``type``: string, bubbles: int, cancelable: int)
    : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()

        let result =
            Raw.rv_host_create_event (host, eventInterface, ``type``, bubbles, cancelable)

        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[53] <- Calls.Counts[53] + 1L
        Calls.Ticks[53] <- Calls.Ticks[53] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_create_event (host, eventInterface, ``type``, bubbles, cancelable)

let rv_node_dispatch (target: nativeint, ``event``: nativeint, defaultPrevented: byref<int>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_node_dispatch (target, ``event``, &defaultPrevented)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[54] <- Calls.Counts[54] + 1L
        Calls.Ticks[54] <- Calls.Ticks[54] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_node_dispatch (target, ``event``, &defaultPrevented)

let rv_event_interface (``event``: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_event_interface (``event``)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[55] <- Calls.Counts[55] + 1L
        Calls.Ticks[55] <- Calls.Ticks[55] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_event_interface (``event``)

let rv_event_flags (``event``: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_event_flags (``event``)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[56] <- Calls.Counts[56] + 1L
        Calls.Ticks[56] <- Calls.Ticks[56] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_event_flags (``event``)

let rv_event_type (``event``: nativeint, buffer: byte[], capacity: int, length: int[]) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_event_type (``event``, buffer, capacity, length)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[57] <- Calls.Counts[57] + 1L
        Calls.Ticks[57] <- Calls.Ticks[57] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_event_type (``event``, buffer, capacity, length)

let rv_event_key (``event``: nativeint, buffer: byte[], capacity: int, length: int[]) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_event_key (``event``, buffer, capacity, length)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[58] <- Calls.Counts[58] + 1L
        Calls.Ticks[58] <- Calls.Ticks[58] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_event_key (``event``, buffer, capacity, length)

let rv_event_target (``event``: nativeint, current: int) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_event_target (``event``, current)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[59] <- Calls.Counts[59] + 1L
        Calls.Ticks[59] <- Calls.Ticks[59] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_event_target (``event``, current)

let rv_last_exception (part: int, buffer: byte[], capacity: int, length: int[]) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_last_exception (part, buffer, capacity, length)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[60] <- Calls.Counts[60] + 1L
        Calls.Ticks[60] <- Calls.Ticks[60] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_last_exception (part, buffer, capacity, length)

let rv_node_query_selector (scope: nativeint, selectors: string, status: byref<int>) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_node_query_selector (scope, selectors, &status)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[61] <- Calls.Counts[61] + 1L
        Calls.Ticks[61] <- Calls.Ticks[61] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_node_query_selector (scope, selectors, &status)

let rv_node_query_selector_all
    (scope: nativeint, selectors: string, nodes: nativeint[], capacity: int, count: byref<int>)
    : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()

        let result =
            Raw.rv_node_query_selector_all (scope, selectors, nodes, capacity, &count)

        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[62] <- Calls.Counts[62] + 1L
        Calls.Ticks[62] <- Calls.Ticks[62] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_node_query_selector_all (scope, selectors, nodes, capacity, &count)

let rv_node_query_selector_all_uncached
    (scope: nativeint, selectors: string, nodes: nativeint[], capacity: int, count: byref<int>)
    : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()

        let result =
            Raw.rv_node_query_selector_all_uncached (scope, selectors, nodes, capacity, &count)

        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[63] <- Calls.Counts[63] + 1L
        Calls.Ticks[63] <- Calls.Ticks[63] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_node_query_selector_all_uncached (scope, selectors, nodes, capacity, &count)

let rv_node_ref_count (node: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_node_ref_count (node)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[64] <- Calls.Counts[64] + 1L
        Calls.Ticks[64] <- Calls.Ticks[64] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_node_ref_count (node)

let rv_node_watch (node: nativeint) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_node_watch (node)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[65] <- Calls.Counts[65] + 1L
        Calls.Ticks[65] <- Calls.Ticks[65] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_node_watch (node)

let rv_watch_alive (watch: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_watch_alive (watch)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[66] <- Calls.Counts[66] + 1L
        Calls.Ticks[66] <- Calls.Ticks[66] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_watch_alive (watch)

let rv_watch_node (watch: nativeint) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_watch_node (watch)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[67] <- Calls.Counts[67] + 1L
        Calls.Ticks[67] <- Calls.Ticks[67] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_watch_node (watch)

let rv_watch_release (watch: nativeint) : unit =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_watch_release (watch)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[68] <- Calls.Counts[68] + 1L
        Calls.Ticks[68] <- Calls.Ticks[68] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_watch_release (watch)

let rv_release_memory () : unit =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_release_memory ()
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[69] <- Calls.Counts[69] + 1L
        Calls.Ticks[69] <- Calls.Ticks[69] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_release_memory ()

let rv_collect_garbage () : unit =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_collect_garbage ()
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[70] <- Calls.Counts[70] + 1L
        Calls.Ticks[70] <- Calls.Ticks[70] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_collect_garbage ()

let rv_collect_garbage_eden () : unit =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_collect_garbage_eden ()
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[71] <- Calls.Counts[71] + 1L
        Calls.Ticks[71] <- Calls.Ticks[71] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_collect_garbage_eden ()

let rv_node_has_wrapper (node: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_node_has_wrapper (node)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[72] <- Calls.Counts[72] + 1L
        Calls.Ticks[72] <- Calls.Ticks[72] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_node_has_wrapper (node)

let rv_element_attribute_count (node: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_element_attribute_count (node)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[73] <- Calls.Counts[73] + 1L
        Calls.Ticks[73] <- Calls.Ticks[73] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_element_attribute_count (node)

let rv_element_attribute_at
    (node: nativeint, index: int, part: int, buffer: byte[], capacity: int, length: int[])
    : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()

        let result =
            Raw.rv_element_attribute_at (node, index, part, buffer, capacity, length)

        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[74] <- Calls.Counts[74] + 1L
        Calls.Ticks[74] <- Calls.Ticks[74] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_element_attribute_at (node, index, part, buffer, capacity, length)

let rv_element_focus (node: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_element_focus (node)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[75] <- Calls.Counts[75] + 1L
        Calls.Ticks[75] <- Calls.Ticks[75] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_element_focus (node)

let rv_document_active_element (host: nativeint) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_document_active_element (host)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[76] <- Calls.Counts[76] + 1L
        Calls.Ticks[76] <- Calls.Ticks[76] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_document_active_element (host)

let rv_run_loop_cycle (milliseconds: int) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_run_loop_cycle (milliseconds)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[77] <- Calls.Counts[77] + 1L
        Calls.Ticks[77] <- Calls.Ticks[77] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_run_loop_cycle (milliseconds)

let rv_host_set_resource_handler (host: nativeint, handler: nativeint, context: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_set_resource_handler (host, handler, context)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[78] <- Calls.Counts[78] + 1L
        Calls.Ticks[78] <- Calls.Ticks[78] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_set_resource_handler (host, handler, context)

let rv_host_set_form_submission_handler (host: nativeint, handler: nativeint, context: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_set_form_submission_handler (host, handler, context)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[79] <- Calls.Counts[79] + 1L
        Calls.Ticks[79] <- Calls.Ticks[79] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_set_form_submission_handler (host, handler, context)

let rv_resource_load_finish (value: nativeint, data: byte[], length: int, contentType: string) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_resource_load_finish (value, data, length, contentType)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[80] <- Calls.Counts[80] + 1L
        Calls.Ticks[80] <- Calls.Ticks[80] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_resource_load_finish (value, data, length, contentType)

let rv_resource_load_fail (value: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_resource_load_fail (value)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[81] <- Calls.Counts[81] + 1L
        Calls.Ticks[81] <- Calls.Ticks[81] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_resource_load_fail (value)

let rv_abi_has (feature: string) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_abi_has (feature)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[82] <- Calls.Counts[82] + 1L
        Calls.Ticks[82] <- Calls.Ticks[82] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_abi_has (feature)

let rv_host_resize (host: nativeint, width: int, height: int) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_resize (host, width, height)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[83] <- Calls.Counts[83] + 1L
        Calls.Ticks[83] <- Calls.Ticks[83] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_resize (host, width, height)

let rv_host_set_device_scale (host: nativeint, scale: float32) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_set_device_scale (host, scale)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[84] <- Calls.Counts[84] + 1L
        Calls.Ticks[84] <- Calls.Ticks[84] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_set_device_scale (host, scale)

let rv_host_paint_size (host: nativeint, width: byref<int>, height: byref<int>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_paint_size (host, &width, &height)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[85] <- Calls.Counts[85] + 1L
        Calls.Ticks[85] <- Calls.Ticks[85] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_paint_size (host, &width, &height)

let rv_host_mouse (host: nativeint, action: int, x: int, y: int, button: int, clickCount: int, modifiers: int) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_mouse (host, action, x, y, button, clickCount, modifiers)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[86] <- Calls.Counts[86] + 1L
        Calls.Ticks[86] <- Calls.Ticks[86] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_mouse (host, action, x, y, button, clickCount, modifiers)

let rv_host_wheel (host: nativeint, x: int, y: int, deltaX: float32, deltaY: float32, modifiers: int) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_wheel (host, x, y, deltaX, deltaY, modifiers)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[87] <- Calls.Counts[87] + 1L
        Calls.Ticks[87] <- Calls.Ticks[87] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_wheel (host, x, y, deltaX, deltaY, modifiers)

let rv_host_key
    (host: nativeint, action: int, key: string, code: string, text: string, modifiers: int, repeat: int)
    : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_key (host, action, key, code, text, modifiers, repeat)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[88] <- Calls.Counts[88] + 1L
        Calls.Ticks[88] <- Calls.Ticks[88] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_key (host, action, key, code, text, modifiers, repeat)

let rv_host_set_focused (host: nativeint, focused: int) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_set_focused (host, focused)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[89] <- Calls.Counts[89] + 1L
        Calls.Ticks[89] <- Calls.Ticks[89] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_set_focused (host, focused)

let rv_host_set_frame_callback (host: nativeint, callback: nativeint, context: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_set_frame_callback (host, callback, context)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[90] <- Calls.Counts[90] + 1L
        Calls.Ticks[90] <- Calls.Ticks[90] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_set_frame_callback (host, callback, context)

let rv_host_update (host: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_update (host)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[91] <- Calls.Counts[91] + 1L
        Calls.Ticks[91] <- Calls.Ticks[91] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_update (host)

let rv_host_dirty_rect (host: nativeint, x: byref<int>, y: byref<int>, width: byref<int>, height: byref<int>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_dirty_rect (host, &x, &y, &width, &height)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[92] <- Calls.Counts[92] + 1L
        Calls.Ticks[92] <- Calls.Ticks[92] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_dirty_rect (host, &x, &y, &width, &height)

let rv_event_number (``event``: nativeint, number: int, value: byref<double>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_event_number (``event``, number, &value)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[93] <- Calls.Counts[93] + 1L
        Calls.Ticks[93] <- Calls.Ticks[93] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_event_number (``event``, number, &value)

let rv_event_string (``event``: nativeint, property: int, buffer: byte[], capacity: int, length: int[]) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_event_string (``event``, property, buffer, capacity, length)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[94] <- Calls.Counts[94] + 1L
        Calls.Ticks[94] <- Calls.Ticks[94] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_event_string (``event``, property, buffer, capacity, length)

let rv_event_related_target (``event``: nativeint) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_event_related_target (``event``)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[95] <- Calls.Counts[95] + 1L
        Calls.Ticks[95] <- Calls.Ticks[95] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_event_related_target (``event``)

let rv_host_cursor (host: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_cursor (host)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[96] <- Calls.Counts[96] + 1L
        Calls.Ticks[96] <- Calls.Ticks[96] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_cursor (host)

let rv_host_scroll_position (host: nativeint, x: byref<int>, y: byref<int>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_scroll_position (host, &x, &y)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[97] <- Calls.Counts[97] + 1L
        Calls.Ticks[97] <- Calls.Ticks[97] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_scroll_position (host, &x, &y)

let rv_host_scroll_to (host: nativeint, x: int, y: int) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_scroll_to (host, x, y)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[98] <- Calls.Counts[98] + 1L
        Calls.Ticks[98] <- Calls.Ticks[98] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_scroll_to (host, x, y)

let rv_host_ime_set_composition (host: nativeint, text: string, selectionStart: int, selectionEnd: int) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()

        let result =
            Raw.rv_host_ime_set_composition (host, text, selectionStart, selectionEnd)

        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[99] <- Calls.Counts[99] + 1L
        Calls.Ticks[99] <- Calls.Ticks[99] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_ime_set_composition (host, text, selectionStart, selectionEnd)

let rv_host_ime_commit (host: nativeint, text: string) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_ime_commit (host, text)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[100] <- Calls.Counts[100] + 1L
        Calls.Ticks[100] <- Calls.Ticks[100] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_ime_commit (host, text)

let rv_host_ime_cancel (host: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_ime_cancel (host)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[101] <- Calls.Counts[101] + 1L
        Calls.Ticks[101] <- Calls.Ticks[101] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_ime_cancel (host)

let rv_host_ime_rect (host: nativeint, x: byref<int>, y: byref<int>, width: byref<int>, height: byref<int>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_ime_rect (host, &x, &y, &width, &height)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[102] <- Calls.Counts[102] + 1L
        Calls.Ticks[102] <- Calls.Ticks[102] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_ime_rect (host, &x, &y, &width, &height)

let rv_element_class (node: nativeint, token: string, operation: int) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_element_class (node, token, operation)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[103] <- Calls.Counts[103] + 1L
        Calls.Ticks[103] <- Calls.Ticks[103] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_element_class (node, token, operation)

let rv_element_set_style (node: nativeint, property: string, value: string, important: int) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_element_set_style (node, property, value, important)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[104] <- Calls.Counts[104] + 1L
        Calls.Ticks[104] <- Calls.Ticks[104] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_element_set_style (node, property, value, important)

let rv_element_get_style (node: nativeint, property: string, buffer: byte[], capacity: int, length: int[]) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_element_get_style (node, property, buffer, capacity, length)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[105] <- Calls.Counts[105] + 1L
        Calls.Ticks[105] <- Calls.Ticks[105] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_element_get_style (node, property, buffer, capacity, length)

let rv_element_computed_style (node: nativeint, property: string, buffer: byte[], capacity: int, length: int[]) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()

        let result =
            Raw.rv_element_computed_style (node, property, buffer, capacity, length)

        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[106] <- Calls.Counts[106] + 1L
        Calls.Ticks[106] <- Calls.Ticks[106] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_element_computed_style (node, property, buffer, capacity, length)

let rv_element_rect
    (node: nativeint, x: byref<double>, y: byref<double>, width: byref<double>, height: byref<double>)
    : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_element_rect (node, &x, &y, &width, &height)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[107] <- Calls.Counts[107] + 1L
        Calls.Ticks[107] <- Calls.Ticks[107] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_element_rect (node, &x, &y, &width, &height)

let rv_host_element_at (host: nativeint, x: int, y: int) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_element_at (host, x, y)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[108] <- Calls.Counts[108] + 1L
        Calls.Ticks[108] <- Calls.Ticks[108] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_element_at (host, x, y)

let rv_element_scroll_into_view (node: nativeint, block: int, inlineAlignment: int, smooth: int) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_element_scroll_into_view (node, block, inlineAlignment, smooth)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[109] <- Calls.Counts[109] + 1L
        Calls.Ticks[109] <- Calls.Ticks[109] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_element_scroll_into_view (node, block, inlineAlignment, smooth)

let rv_element_scroll_metric (node: nativeint, metric: int, value: byref<int>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_element_scroll_metric (node, metric, &value)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[110] <- Calls.Counts[110] + 1L
        Calls.Ticks[110] <- Calls.Ticks[110] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_element_scroll_metric (node, metric, &value)

let rv_element_scroll_to (node: nativeint, left: int, top: int, smooth: int) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_element_scroll_to (node, left, top, smooth)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[111] <- Calls.Counts[111] + 1L
        Calls.Ticks[111] <- Calls.Ticks[111] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_element_scroll_to (node, left, top, smooth)

let rv_element_attach_shadow (node: nativeint, status: byref<int>) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_element_attach_shadow (node, &status)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[112] <- Calls.Counts[112] + 1L
        Calls.Ticks[112] <- Calls.Ticks[112] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_element_attach_shadow (node, &status)

let rv_element_shadow_root (node: nativeint) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_element_shadow_root (node)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[113] <- Calls.Counts[113] + 1L
        Calls.Ticks[113] <- Calls.Ticks[113] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_element_shadow_root (node)

let rv_text_selection (node: nativeint, start: byref<int>, ``end``: byref<int>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_text_selection (node, &start, &``end``)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[114] <- Calls.Counts[114] + 1L
        Calls.Ticks[114] <- Calls.Ticks[114] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_text_selection (node, &start, &``end``)

let rv_text_set_selection (node: nativeint, start: int, ``end``: int) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_text_set_selection (node, start, ``end``)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[115] <- Calls.Counts[115] + 1L
        Calls.Ticks[115] <- Calls.Ticks[115] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_text_set_selection (node, start, ``end``)

let rv_element_animations
    (node: nativeint, subtree: int, animations: nativeint[], capacity: int, count: byref<int>)
    : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_element_animations (node, subtree, animations, capacity, &count)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[116] <- Calls.Counts[116] + 1L
        Calls.Ticks[116] <- Calls.Ticks[116] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_element_animations (node, subtree, animations, capacity, &count)

let rv_host_animations (host: nativeint, animations: nativeint[], capacity: int, count: byref<int>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_animations (host, animations, capacity, &count)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[117] <- Calls.Counts[117] + 1L
        Calls.Ticks[117] <- Calls.Ticks[117] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_animations (host, animations, capacity, &count)

let rv_animation_release (animation: nativeint) : unit =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_animation_release (animation)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[118] <- Calls.Counts[118] + 1L
        Calls.Ticks[118] <- Calls.Ticks[118] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_animation_release (animation)

let rv_animation_control (animation: nativeint, action: int) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_animation_control (animation, action)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[119] <- Calls.Counts[119] + 1L
        Calls.Ticks[119] <- Calls.Ticks[119] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_animation_control (animation, action)

let rv_animation_state (animation: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_animation_state (animation)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[120] <- Calls.Counts[120] + 1L
        Calls.Ticks[120] <- Calls.Ticks[120] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_animation_state (animation)

let rv_animation_time (animation: nativeint, milliseconds: byref<double>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_animation_time (animation, &milliseconds)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[121] <- Calls.Counts[121] + 1L
        Calls.Ticks[121] <- Calls.Ticks[121] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_animation_time (animation, &milliseconds)

let rv_animation_seek (animation: nativeint, milliseconds: float) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_animation_seek (animation, milliseconds)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[122] <- Calls.Counts[122] + 1L
        Calls.Ticks[122] <- Calls.Ticks[122] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_animation_seek (animation, milliseconds)

let rv_animation_set_rate (animation: nativeint, rate: float) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_animation_set_rate (animation, rate)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[123] <- Calls.Counts[123] + 1L
        Calls.Ticks[123] <- Calls.Ticks[123] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_animation_set_rate (animation, rate)

let rv_animation_name (animation: nativeint, buffer: byte[], capacity: int, length: int[]) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_animation_name (animation, buffer, capacity, length)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[124] <- Calls.Counts[124] + 1L
        Calls.Ticks[124] <- Calls.Ticks[124] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_animation_name (animation, buffer, capacity, length)

let rv_animation_target (animation: nativeint) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_animation_target (animation)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[125] <- Calls.Counts[125] + 1L
        Calls.Ticks[125] <- Calls.Ticks[125] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_animation_target (animation)

let rv_node_retain (node: nativeint) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_node_retain (node)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[126] <- Calls.Counts[126] + 1L
        Calls.Ticks[126] <- Calls.Ticks[126] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_node_retain (node)

let rv_host_observe_resize (host: nativeint, callback: nativeint, context: nativeint) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_observe_resize (host, callback, context)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[127] <- Calls.Counts[127] + 1L
        Calls.Ticks[127] <- Calls.Ticks[127] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_observe_resize (host, callback, context)

let rv_host_observe_intersection
    (
        host: nativeint,
        callback: nativeint,
        context: nativeint,
        rootMargin: string,
        thresholds: float[],
        thresholdCount: int
    ) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()

        let result =
            Raw.rv_host_observe_intersection (host, callback, context, rootMargin, thresholds, thresholdCount)

        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[128] <- Calls.Counts[128] + 1L
        Calls.Ticks[128] <- Calls.Ticks[128] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_observe_intersection (host, callback, context, rootMargin, thresholds, thresholdCount)

let rv_observer_observe (value: nativeint, element: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_observer_observe (value, element)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[129] <- Calls.Counts[129] + 1L
        Calls.Ticks[129] <- Calls.Ticks[129] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_observer_observe (value, element)

let rv_observer_unobserve (value: nativeint, element: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_observer_unobserve (value, element)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[130] <- Calls.Counts[130] + 1L
        Calls.Ticks[130] <- Calls.Ticks[130] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_observer_unobserve (value, element)

let rv_observer_release (value: nativeint) : unit =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_observer_release (value)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[131] <- Calls.Counts[131] + 1L
        Calls.Ticks[131] <- Calls.Ticks[131] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_observer_release (value)

let rv_element_snapshot (node: nativeint, rgba: byte[], length: int, width: byref<int>, height: byref<int>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_element_snapshot (node, rgba, length, &width, &height)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[132] <- Calls.Counts[132] + 1L
        Calls.Ticks[132] <- Calls.Ticks[132] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_element_snapshot (node, rgba, length, &width, &height)

let rv_host_paint_rgba_rect
    (host: nativeint, rgba: byte[], length: int, x: int, y: int, width: int, height: int)
    : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_paint_rgba_rect (host, rgba, length, x, y, width, height)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[133] <- Calls.Counts[133] + 1L
        Calls.Ticks[133] <- Calls.Ticks[133] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_paint_rgba_rect (host, rgba, length, x, y, width, height)

let rv_host_set_popup_handler (host: nativeint, callback: nativeint, context: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_set_popup_handler (host, callback, context)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[134] <- Calls.Counts[134] + 1L
        Calls.Ticks[134] <- Calls.Ticks[134] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_set_popup_handler (host, callback, context)

let rv_popup_item_count (value: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_popup_item_count (value)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[135] <- Calls.Counts[135] + 1L
        Calls.Ticks[135] <- Calls.Ticks[135] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_popup_item_count (value)

let rv_popup_item
    (value: nativeint, index: int, kind: byref<int>, enabled: byref<int>, buffer: byte[], capacity: int, length: int[])
    : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()

        let result =
            Raw.rv_popup_item (value, index, &kind, &enabled, buffer, capacity, length)

        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[136] <- Calls.Counts[136] + 1L
        Calls.Ticks[136] <- Calls.Ticks[136] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_popup_item (value, index, &kind, &enabled, buffer, capacity, length)

let rv_popup_choose (value: nativeint, index: int) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_popup_choose (value, index)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[137] <- Calls.Counts[137] + 1L
        Calls.Ticks[137] <- Calls.Ticks[137] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_popup_choose (value, index)

let rv_host_tooltip (host: nativeint, buffer: byte[], capacity: int, length: int[]) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_tooltip (host, buffer, capacity, length)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[138] <- Calls.Counts[138] + 1L
        Calls.Ticks[138] <- Calls.Ticks[138] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_tooltip (host, buffer, capacity, length)

let rv_host_set_clipboard (host: nativeint, style: int, write: nativeint, read: nativeint, context: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_set_clipboard (host, style, write, read, context)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[139] <- Calls.Counts[139] + 1L
        Calls.Ticks[139] <- Calls.Ticks[139] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_set_clipboard (host, style, write, read, context)

let rv_clipboard_offer (value: nativeint, ``type``: string, data: string) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_clipboard_offer (value, ``type``, data)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[140] <- Calls.Counts[140] + 1L
        Calls.Ticks[140] <- Calls.Ticks[140] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_clipboard_offer (value, ``type``, data)

let rv_host_edit (host: nativeint, command: int) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_edit (host, command)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[141] <- Calls.Counts[141] + 1L
        Calls.Ticks[141] <- Calls.Ticks[141] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_edit (host, command)

let rv_host_set_drag (host: nativeint, style: int) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_set_drag (host, style)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[142] <- Calls.Counts[142] + 1L
        Calls.Ticks[142] <- Calls.Ticks[142] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_set_drag (host, style)

let rv_drag_data_create () : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_drag_data_create ()
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[143] <- Calls.Counts[143] + 1L
        Calls.Ticks[143] <- Calls.Ticks[143] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_drag_data_create ()

let rv_drag_data_add (value: nativeint, ``type``: string, data: string) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_drag_data_add (value, ``type``, data)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[144] <- Calls.Counts[144] + 1L
        Calls.Ticks[144] <- Calls.Ticks[144] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_drag_data_add (value, ``type``, data)

let rv_drag_data_release (value: nativeint) : unit =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_drag_data_release (value)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[145] <- Calls.Counts[145] + 1L
        Calls.Ticks[145] <- Calls.Ticks[145] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_drag_data_release (value)

let rv_host_drag (host: nativeint, action: int, x: int, y: int, allowed: int, data: nativeint, modifiers: int) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_drag (host, action, x, y, allowed, data, modifiers)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[146] <- Calls.Counts[146] + 1L
        Calls.Ticks[146] <- Calls.Ticks[146] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_drag (host, action, x, y, allowed, data, modifiers)

let rv_host_set_drag_start (host: nativeint, callback: nativeint, context: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_set_drag_start (host, callback, context)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[147] <- Calls.Counts[147] + 1L
        Calls.Ticks[147] <- Calls.Ticks[147] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_set_drag_start (host, callback, context)

let rv_drag_item_count (value: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_drag_item_count (value)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[148] <- Calls.Counts[148] + 1L
        Calls.Ticks[148] <- Calls.Ticks[148] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_drag_item_count (value)

let rv_drag_item_type (value: nativeint, index: int, buffer: byte[], capacity: int, length: int[]) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_drag_item_type (value, index, buffer, capacity, length)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[149] <- Calls.Counts[149] + 1L
        Calls.Ticks[149] <- Calls.Ticks[149] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_drag_item_type (value, index, buffer, capacity, length)

let rv_drag_item_value (value: nativeint, index: int, buffer: byte[], capacity: int, length: int[]) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_drag_item_value (value, index, buffer, capacity, length)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[150] <- Calls.Counts[150] + 1L
        Calls.Ticks[150] <- Calls.Ticks[150] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_drag_item_value (value, index, buffer, capacity, length)

let rv_drag_data (value: nativeint) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_drag_data (value)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[151] <- Calls.Counts[151] + 1L
        Calls.Ticks[151] <- Calls.Ticks[151] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_drag_data (value)

let rv_drag_image
    (
        value: nativeint,
        rgba: byte[],
        length: int,
        width: byref<int>,
        height: byref<int>,
        offsetX: byref<int>,
        offsetY: byref<int>
    ) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()

        let result =
            Raw.rv_drag_image (value, rgba, length, &width, &height, &offsetX, &offsetY)

        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[152] <- Calls.Counts[152] + 1L
        Calls.Ticks[152] <- Calls.Ticks[152] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_drag_image (value, rgba, length, &width, &height, &offsetX, &offsetY)

let rv_drag_end (value: nativeint, x: int, y: int, operation: int) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_drag_end (value, x, y, operation)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[153] <- Calls.Counts[153] + 1L
        Calls.Ticks[153] <- Calls.Ticks[153] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_drag_end (value, x, y, operation)

let rv_host_set_accessibility (host: nativeint, enabled: int, callback: nativeint, context: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_set_accessibility (host, enabled, callback, context)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[154] <- Calls.Counts[154] + 1L
        Calls.Ticks[154] <- Calls.Ticks[154] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_set_accessibility (host, enabled, callback, context)

let rv_host_attach_uia (host: nativeint, hwnd: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_attach_uia (host, hwnd)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[155] <- Calls.Counts[155] + 1L
        Calls.Ticks[155] <- Calls.Ticks[155] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_attach_uia (host, hwnd)

let rv_host_detach_uia (host: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_detach_uia (host)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[156] <- Calls.Counts[156] + 1L
        Calls.Ticks[156] <- Calls.Ticks[156] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_detach_uia (host)

let rv_host_ax_root (host: nativeint) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_ax_root (host)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[157] <- Calls.Counts[157] + 1L
        Calls.Ticks[157] <- Calls.Ticks[157] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_ax_root (host)

let rv_host_ax_focus (host: nativeint) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_ax_focus (host)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[158] <- Calls.Counts[158] + 1L
        Calls.Ticks[158] <- Calls.Ticks[158] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_ax_focus (host)

let rv_host_ax_hit_test (host: nativeint, x: int, y: int) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_ax_hit_test (host, x, y)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[159] <- Calls.Counts[159] + 1L
        Calls.Ticks[159] <- Calls.Ticks[159] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_ax_hit_test (host, x, y)

let rv_node_ax (node: nativeint) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_node_ax (node)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[160] <- Calls.Counts[160] + 1L
        Calls.Ticks[160] <- Calls.Ticks[160] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_node_ax (node)

let rv_ax_dom_node (ax: nativeint) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_ax_dom_node (ax)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[161] <- Calls.Counts[161] + 1L
        Calls.Ticks[161] <- Calls.Ticks[161] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_ax_dom_node (ax)

let rv_ax_retain (ax: nativeint) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_ax_retain (ax)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[162] <- Calls.Counts[162] + 1L
        Calls.Ticks[162] <- Calls.Ticks[162] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_ax_retain (ax)

let rv_ax_release (ax: nativeint) : unit =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_ax_release (ax)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[163] <- Calls.Counts[163] + 1L
        Calls.Ticks[163] <- Calls.Ticks[163] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_ax_release (ax)

let rv_ax_id (ax: nativeint) : int64 =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_ax_id (ax)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[164] <- Calls.Counts[164] + 1L
        Calls.Ticks[164] <- Calls.Ticks[164] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_ax_id (ax)

let rv_ax_role (ax: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_ax_role (ax)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[165] <- Calls.Counts[165] + 1L
        Calls.Ticks[165] <- Calls.Ticks[165] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_ax_role (ax)

let rv_ax_states (ax: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_ax_states (ax)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[166] <- Calls.Counts[166] + 1L
        Calls.Ticks[166] <- Calls.Ticks[166] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_ax_states (ax)

let rv_ax_string (ax: nativeint, property: int, buffer: byte[], capacity: int, length: int[]) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_ax_string (ax, property, buffer, capacity, length)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[167] <- Calls.Counts[167] + 1L
        Calls.Ticks[167] <- Calls.Ticks[167] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_ax_string (ax, property, buffer, capacity, length)

let rv_ax_number (ax: nativeint, property: int, value: byref<double>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_ax_number (ax, property, &value)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[168] <- Calls.Counts[168] + 1L
        Calls.Ticks[168] <- Calls.Ticks[168] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_ax_number (ax, property, &value)

let rv_ax_rect (ax: nativeint, x: byref<double>, y: byref<double>, width: byref<double>, height: byref<double>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_ax_rect (ax, &x, &y, &width, &height)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[169] <- Calls.Counts[169] + 1L
        Calls.Ticks[169] <- Calls.Ticks[169] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_ax_rect (ax, &x, &y, &width, &height)

let rv_ax_parent (ax: nativeint) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_ax_parent (ax)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[170] <- Calls.Counts[170] + 1L
        Calls.Ticks[170] <- Calls.Ticks[170] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_ax_parent (ax)

let rv_ax_children (ax: nativeint, nodes: nativeint[], capacity: int, count: byref<int>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_ax_children (ax, nodes, capacity, &count)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[171] <- Calls.Counts[171] + 1L
        Calls.Ticks[171] <- Calls.Ticks[171] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_ax_children (ax, nodes, capacity, &count)

let rv_ax_relations (ax: nativeint, kind: int, nodes: nativeint[], capacity: int, count: byref<int>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_ax_relations (ax, kind, nodes, capacity, &count)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[172] <- Calls.Counts[172] + 1L
        Calls.Ticks[172] <- Calls.Ticks[172] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_ax_relations (ax, kind, nodes, capacity, &count)

let rv_ax_action (ax: nativeint, action: int) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_ax_action (ax, action)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[173] <- Calls.Counts[173] + 1L
        Calls.Ticks[173] <- Calls.Ticks[173] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_ax_action (ax, action)

let rv_ax_set_value (ax: nativeint, value: string) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_ax_set_value (ax, value)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[174] <- Calls.Counts[174] + 1L
        Calls.Ticks[174] <- Calls.Ticks[174] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_ax_set_value (ax, value)

let rv_ax_set_number (ax: nativeint, value: float) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_ax_set_number (ax, value)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[175] <- Calls.Counts[175] + 1L
        Calls.Ticks[175] <- Calls.Ticks[175] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_ax_set_number (ax, value)

let rv_ax_text_length (ax: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_ax_text_length (ax)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[176] <- Calls.Counts[176] + 1L
        Calls.Ticks[176] <- Calls.Ticks[176] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_ax_text_length (ax)

let rv_ax_text (ax: nativeint, start: int, ``end``: int, buffer: byte[], capacity: int, length: int[]) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_ax_text (ax, start, ``end``, buffer, capacity, length)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[177] <- Calls.Counts[177] + 1L
        Calls.Ticks[177] <- Calls.Ticks[177] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_ax_text (ax, start, ``end``, buffer, capacity, length)

let rv_ax_text_boundary (ax: nativeint, offset: int, unit: int, start: byref<int>, ``end``: byref<int>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_ax_text_boundary (ax, offset, unit, &start, &``end``)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[178] <- Calls.Counts[178] + 1L
        Calls.Ticks[178] <- Calls.Ticks[178] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_ax_text_boundary (ax, offset, unit, &start, &``end``)

let rv_ax_text_selection (ax: nativeint, start: byref<int>, ``end``: byref<int>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_ax_text_selection (ax, &start, &``end``)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[179] <- Calls.Counts[179] + 1L
        Calls.Ticks[179] <- Calls.Ticks[179] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_ax_text_selection (ax, &start, &``end``)

let rv_ax_text_caret (ax: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_ax_text_caret (ax)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[180] <- Calls.Counts[180] + 1L
        Calls.Ticks[180] <- Calls.Ticks[180] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_ax_text_caret (ax)

let rv_ax_text_set_selection (ax: nativeint, start: int, ``end``: int) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_ax_text_set_selection (ax, start, ``end``)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[181] <- Calls.Counts[181] + 1L
        Calls.Ticks[181] <- Calls.Ticks[181] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_ax_text_set_selection (ax, start, ``end``)

let rv_ax_text_rects (ax: nativeint, start: int, ``end``: int, rects: float[], capacity: int, count: byref<int>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_ax_text_rects (ax, start, ``end``, rects, capacity, &count)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[182] <- Calls.Counts[182] + 1L
        Calls.Ticks[182] <- Calls.Ticks[182] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_ax_text_rects (ax, start, ``end``, rects, capacity, &count)

let rv_ax_text_offset_at (ax: nativeint, x: int, y: int) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_ax_text_offset_at (ax, x, y)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[183] <- Calls.Counts[183] + 1L
        Calls.Ticks[183] <- Calls.Ticks[183] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_ax_text_offset_at (ax, x, y)

let rv_ax_text_child_range (ancestor: nativeint, child: nativeint, start: byref<int>, ``end``: byref<int>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_ax_text_child_range (ancestor, child, &start, &``end``)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[184] <- Calls.Counts[184] + 1L
        Calls.Ticks[184] <- Calls.Ticks[184] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_ax_text_child_range (ancestor, child, &start, &``end``)

let rv_host_load_svg (host: nativeint, svg: string) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_load_svg (host, svg)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[185] <- Calls.Counts[185] + 1L
        Calls.Ticks[185] <- Calls.Ticks[185] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_load_svg (host, svg)

let rv_capability_count (category: int) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_capability_count (category)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[186] <- Calls.Counts[186] + 1L
        Calls.Ticks[186] <- Calls.Ticks[186] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_capability_count (category)

let rv_capability_name_at (category: int, index: int, buffer: byte[], capacity: int, length: int[]) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_capability_name_at (category, index, buffer, capacity, length)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[187] <- Calls.Counts[187] + 1L
        Calls.Ticks[187] <- Calls.Ticks[187] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_capability_name_at (category, index, buffer, capacity, length)

let rv_host_capability_fact (host: nativeint, category: int, name: string, dimension: int, fact: byref<int>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_capability_fact (host, category, name, dimension, &fact)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[188] <- Calls.Counts[188] + 1L
        Calls.Ticks[188] <- Calls.Ticks[188] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_capability_fact (host, category, name, dimension, &fact)

let rv_host_capability_value_kind (host: nativeint, category: int, name: string, kind: byref<int>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_capability_value_kind (host, category, name, &kind)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[189] <- Calls.Counts[189] + 1L
        Calls.Ticks[189] <- Calls.Ticks[189] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_capability_value_kind (host, category, name, &kind)

let rv_host_capability_value_number (host: nativeint, category: int, name: string, number: byref<double>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_capability_value_number (host, category, name, &number)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[190] <- Calls.Counts[190] + 1L
        Calls.Ticks[190] <- Calls.Ticks[190] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_capability_value_number (host, category, name, &number)

let rv_host_capability_value_text
    (host: nativeint, category: int, name: string, buffer: byte[], capacity: int, length: int[])
    : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()

        let result =
            Raw.rv_host_capability_value_text (host, category, name, buffer, capacity, length)

        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[191] <- Calls.Counts[191] + 1L
        Calls.Ticks[191] <- Calls.Ticks[191] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_capability_value_text (host, category, name, buffer, capacity, length)

let rv_host_select_svg_view (host: nativeint, fragment: string, selected: byref<int>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_select_svg_view (host, fragment, &selected)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[192] <- Calls.Counts[192] + 1L
        Calls.Ticks[192] <- Calls.Ticks[192] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_select_svg_view (host, fragment, &selected)

let rv_image_decode
    (host: nativeint, image: nativeint, completion: nativeint, context: nativeint, operation: byref<uint64>)
    : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_image_decode (host, image, completion, context, &operation)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[193] <- Calls.Counts[193] + 1L
        Calls.Ticks[193] <- Calls.Ticks[193] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_image_decode (host, image, completion, context, &operation)

let rv_font_load
    (
        host: nativeint,
        family: string,
        data: byte[],
        length: int,
        completion: nativeint,
        context: nativeint,
        operation: byref<uint64>
    ) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()

        let result =
            Raw.rv_font_load (host, family, data, length, completion, context, &operation)

        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[194] <- Calls.Counts[194] + 1L
        Calls.Ticks[194] <- Calls.Ticks[194] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_font_load (host, family, data, length, completion, context, &operation)

let rv_resource_cancel (operation: uint64) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_resource_cancel (operation)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[195] <- Calls.Counts[195] + 1L
        Calls.Ticks[195] <- Calls.Ticks[195] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_resource_cancel (operation)

let rv_resource_release (operation: uint64) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_resource_release (operation)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[196] <- Calls.Counts[196] + 1L
        Calls.Ticks[196] <- Calls.Ticks[196] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_resource_release (operation)

let rv_host_construct_event (host: nativeint, kind: int, ``type``: string, init: byref<EventInit>) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_construct_event (host, kind, ``type``, &init)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[197] <- Calls.Counts[197] + 1L
        Calls.Ticks[197] <- Calls.Ticks[197] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_construct_event (host, kind, ``type``, &init)

let rv_custom_event_detail_json (``event``: nativeint, buffer: byte[], capacity: int, length: int[]) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_custom_event_detail_json (``event``, buffer, capacity, length)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[198] <- Calls.Counts[198] + 1L
        Calls.Ticks[198] <- Calls.Ticks[198] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_custom_event_detail_json (``event``, buffer, capacity, length)

let rv_host_create_event_target (host: nativeint) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_create_event_target (host)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[199] <- Calls.Counts[199] + 1L
        Calls.Ticks[199] <- Calls.Ticks[199] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_create_event_target (host)

let rv_event_target_retain (target: nativeint) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_event_target_retain (target)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[200] <- Calls.Counts[200] + 1L
        Calls.Ticks[200] <- Calls.Ticks[200] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_event_target_retain (target)

let rv_event_target_release (target: nativeint) : unit =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_event_target_release (target)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[201] <- Calls.Counts[201] + 1L
        Calls.Ticks[201] <- Calls.Ticks[201] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_event_target_release (target)

let rv_node_as_event_target (node: nativeint) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_node_as_event_target (node)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[202] <- Calls.Counts[202] + 1L
        Calls.Ticks[202] <- Calls.Ticks[202] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_node_as_event_target (node)

let rv_event_target_as_node (target: nativeint) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_event_target_as_node (target)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[203] <- Calls.Counts[203] + 1L
        Calls.Ticks[203] <- Calls.Ticks[203] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_event_target_as_node (target)

let rv_event_target_equals (left: nativeint, right: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_event_target_equals (left, right)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[204] <- Calls.Counts[204] + 1L
        Calls.Ticks[204] <- Calls.Ticks[204] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_event_target_equals (left, right)

let rv_event_target_add_listener
    (target: nativeint, ``type``: string, flags: int, callback: nativeint, context: nativeint)
    : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()

        let result =
            Raw.rv_event_target_add_listener (target, ``type``, flags, callback, context)

        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[205] <- Calls.Counts[205] + 1L
        Calls.Ticks[205] <- Calls.Ticks[205] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_event_target_add_listener (target, ``type``, flags, callback, context)

let rv_event_target_dispatch (target: nativeint, ``event``: nativeint, defaultPrevented: byref<int>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_event_target_dispatch (target, ``event``, &defaultPrevented)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[206] <- Calls.Counts[206] + 1L
        Calls.Ticks[206] <- Calls.Ticks[206] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_event_target_dispatch (target, ``event``, &defaultPrevented)

let rv_event_get_target (``event``: nativeint, current: int) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_event_get_target (``event``, current)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[207] <- Calls.Counts[207] + 1L
        Calls.Ticks[207] <- Calls.Ticks[207] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_event_get_target (``event``, current)

let rv_event_get_related_target (``event``: nativeint) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_event_get_related_target (``event``)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[208] <- Calls.Counts[208] + 1L
        Calls.Ticks[208] <- Calls.Ticks[208] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_event_get_related_target (``event``)

let rv_host_window_event_target (host: nativeint) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_window_event_target (host)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[209] <- Calls.Counts[209] + 1L
        Calls.Ticks[209] <- Calls.Ticks[209] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_window_event_target (host)

let rv_host_max_touch_points (host: nativeint, value: byref<int>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_max_touch_points (host, &value)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[210] <- Calls.Counts[210] + 1L
        Calls.Ticks[210] <- Calls.Ticks[210] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_max_touch_points (host, &value)

let rv_host_window_metrics (host: nativeint, metrics: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_window_metrics (host, metrics)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[211] <- Calls.Counts[211] + 1L
        Calls.Ticks[211] <- Calls.Ticks[211] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_window_metrics (host, metrics)

let rv_host_set_visible (host: nativeint, visible: int) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_set_visible (host, visible)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[212] <- Calls.Counts[212] + 1L
        Calls.Ticks[212] <- Calls.Ticks[212] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_set_visible (host, visible)

let rv_host_match_media (host: nativeint, query: string) : nativeint =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_match_media (host, query)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[213] <- Calls.Counts[213] + 1L
        Calls.Ticks[213] <- Calls.Ticks[213] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_match_media (host, query)

let rv_media_query_matches (target: nativeint, matches: byref<int>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_media_query_matches (target, &matches)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[214] <- Calls.Counts[214] + 1L
        Calls.Ticks[214] <- Calls.Ticks[214] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_media_query_matches (target, &matches)

let rv_media_query_media (target: nativeint, buffer: byte[], capacity: int, length: int[]) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_media_query_media (target, buffer, capacity, length)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[215] <- Calls.Counts[215] + 1L
        Calls.Ticks[215] <- Calls.Ticks[215] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_media_query_media (target, buffer, capacity, length)

let rv_blob_read_bytes (blob: nativeint, buffer: byte[], capacity: int64, length: byref<int64>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_blob_read_bytes (blob, buffer, capacity, &length)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[216] <- Calls.Counts[216] + 1L
        Calls.Ticks[216] <- Calls.Ticks[216] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_blob_read_bytes (blob, buffer, capacity, &length)

let rv_file_list_create (files: nativeint[], count: int, result: nativeint[]) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_file_list_create (files, count, result)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[217] <- Calls.Counts[217] + 1L
        Calls.Ticks[217] <- Calls.Ticks[217] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_file_list_create (files, count, result)

let rv_blob_read
    (host: nativeint, blob: nativeint, mode: int, completion: nativeint, context: nativeint, operation: byref<uint64>)
    : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_blob_read (host, blob, mode, completion, context, &operation)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[218] <- Calls.Counts[218] + 1L
        Calls.Ticks[218] <- Calls.Ticks[218] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_blob_read (host, blob, mode, completion, context, &operation)

let rv_blob_url_read
    (host: nativeint, url: byte[], url_length: int, completion: nativeint, context: nativeint, operation: byref<uint64>)
    : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()

        let result =
            Raw.rv_blob_url_read (host, url, url_length, completion, context, &operation)

        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[219] <- Calls.Counts[219] + 1L
        Calls.Ticks[219] <- Calls.Ticks[219] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_blob_url_read (host, url, url_length, completion, context, &operation)

let rv_blob_read_result (operation: uint64, buffer: byte[], capacity: int64, length: byref<int64>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_blob_read_result (operation, buffer, capacity, &length)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[220] <- Calls.Counts[220] + 1L
        Calls.Ticks[220] <- Calls.Ticks[220] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_blob_read_result (operation, buffer, capacity, &length)

let rv_blob_read_type (operation: uint64, buffer: byte[], capacity: int, length: int[]) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_blob_read_type (operation, buffer, capacity, length)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[221] <- Calls.Counts[221] + 1L
        Calls.Ticks[221] <- Calls.Ticks[221] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_blob_read_type (operation, buffer, capacity, length)

let rv_blob_read_error (operation: uint64, buffer: byte[], capacity: int, length: int[]) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_blob_read_error (operation, buffer, capacity, length)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[222] <- Calls.Counts[222] + 1L
        Calls.Ticks[222] <- Calls.Ticks[222] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_blob_read_error (operation, buffer, capacity, length)

let rv_file_create_from_path (host: nativeint, path: byte[], path_length: int, result: nativeint[]) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_file_create_from_path (host, path, path_length, result)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[223] <- Calls.Counts[223] + 1L
        Calls.Ticks[223] <- Calls.Ticks[223] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_file_create_from_path (host, path, path_length, result)

let rv_file_reader_result
    (reader: nativeint, kind: byref<int>, buffer: byte[], capacity: int64, length: byref<int64>)
    : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_file_reader_result (reader, &kind, buffer, capacity, &length)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[224] <- Calls.Counts[224] + 1L
        Calls.Ticks[224] <- Calls.Ticks[224] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_file_reader_result (reader, &kind, buffer, capacity, &length)

let rv_file_reader_error (reader: nativeint, buffer: byte[], capacity: int, length: int[]) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_file_reader_error (reader, buffer, capacity, length)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[225] <- Calls.Counts[225] + 1L
        Calls.Ticks[225] <- Calls.Ticks[225] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_file_reader_error (reader, buffer, capacity, length)

let rv_text_segment (granularity: int, locale: string, text: uint16[], length: int, result: byref<TextSegments>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_text_segment (granularity, locale, text, length, &result)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[226] <- Calls.Counts[226] + 1L
        Calls.Ticks[226] <- Calls.Ticks[226] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_text_segment (granularity, locale, text, length, &result)

let rv_text_segments_release (segments: byref<TextSegments>) : unit =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_text_segments_release (&segments)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[227] <- Calls.Counts[227] + 1L
        Calls.Ticks[227] <- Calls.Ticks[227] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_text_segments_release (&segments)

let rv_text_segmentation_version (buffer: byte[], capacity: int, length: int[]) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_text_segmentation_version (buffer, capacity, length)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[228] <- Calls.Counts[228] + 1L
        Calls.Ticks[228] <- Calls.Ticks[228] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_text_segmentation_version (buffer, capacity, length)

let rv_host_set_page_scale (host: nativeint, scale: float, originX: int, originY: int) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_set_page_scale (host, scale, originX, originY)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[229] <- Calls.Counts[229] + 1L
        Calls.Ticks[229] <- Calls.Ticks[229] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_set_page_scale (host, scale, originX, originY)

let rv_host_page_scale (host: nativeint, scale: byref<double>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_page_scale (host, &scale)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[230] <- Calls.Counts[230] + 1L
        Calls.Ticks[230] <- Calls.Ticks[230] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_page_scale (host, &scale)

let rv_host_set_obscured_insets (host: nativeint, top: float, right: float, bottom: float, left: float) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_set_obscured_insets (host, top, right, bottom, left)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[231] <- Calls.Counts[231] + 1L
        Calls.Ticks[231] <- Calls.Ticks[231] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_set_obscured_insets (host, top, right, bottom, left)

let rv_host_set_screen (host: nativeint, metrics: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_set_screen (host, metrics)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[232] <- Calls.Counts[232] + 1L
        Calls.Ticks[232] <- Calls.Ticks[232] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_set_screen (host, metrics)

let rv_host_set_diagnostics (host: nativeint, enabled: int) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_set_diagnostics (host, enabled)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[233] <- Calls.Counts[233] + 1L
        Calls.Ticks[233] <- Calls.Ticks[233] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_set_diagnostics (host, enabled)

let rv_host_inspect_render_tree (host: nativeint, target: nativeint, flags: int, diagnostic: nativeint[]) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_inspect_render_tree (host, target, flags, diagnostic)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[234] <- Calls.Counts[234] + 1L
        Calls.Ticks[234] <- Calls.Ticks[234] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_inspect_render_tree (host, target, flags, diagnostic)

let rv_host_inspect_matched_rules (host: nativeint, element: nativeint, diagnostic: nativeint[]) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_inspect_matched_rules (host, element, diagnostic)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[235] <- Calls.Counts[235] + 1L
        Calls.Ticks[235] <- Calls.Ticks[235] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_inspect_matched_rules (host, element, diagnostic)

let rv_diagnostic_kind (diagnostic: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_diagnostic_kind (diagnostic)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[236] <- Calls.Counts[236] + 1L
        Calls.Ticks[236] <- Calls.Ticks[236] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_diagnostic_kind (diagnostic)

let rv_diagnostic_text (diagnostic: nativeint, buffer: byte[], capacity: int, length: int[]) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_diagnostic_text (diagnostic, buffer, capacity, length)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[237] <- Calls.Counts[237] + 1L
        Calls.Ticks[237] <- Calls.Ticks[237] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_diagnostic_text (diagnostic, buffer, capacity, length)

let rv_diagnostic_count (diagnostic: nativeint) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_diagnostic_count (diagnostic)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[238] <- Calls.Counts[238] + 1L
        Calls.Ticks[238] <- Calls.Ticks[238] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_diagnostic_count (diagnostic)

let rv_diagnostic_entry_string
    (diagnostic: nativeint, index: int, field: int, buffer: byte[], capacity: int, length: int[])
    : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()

        let result =
            Raw.rv_diagnostic_entry_string (diagnostic, index, field, buffer, capacity, length)

        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[239] <- Calls.Counts[239] + 1L
        Calls.Ticks[239] <- Calls.Ticks[239] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_diagnostic_entry_string (diagnostic, index, field, buffer, capacity, length)

let rv_diagnostic_entry_number (diagnostic: nativeint, index: int, field: int, value: byref<double>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_diagnostic_entry_number (diagnostic, index, field, &value)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[240] <- Calls.Counts[240] + 1L
        Calls.Ticks[240] <- Calls.Ticks[240] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_diagnostic_entry_number (diagnostic, index, field, &value)

let rv_diagnostic_release (diagnostic: nativeint) : unit =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_diagnostic_release (diagnostic)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[241] <- Calls.Counts[241] + 1L
        Calls.Ticks[241] <- Calls.Ticks[241] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_diagnostic_release (diagnostic)

let rv_diagnostic_live_count () : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_diagnostic_live_count ()
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[242] <- Calls.Counts[242] + 1L
        Calls.Ticks[242] <- Calls.Ticks[242] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_diagnostic_live_count ()

let rv_host_inspect_box_model (host: nativeint, element: nativeint, values: byref<double>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_inspect_box_model (host, element, &values)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[243] <- Calls.Counts[243] + 1L
        Calls.Ticks[243] <- Calls.Ticks[243] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_inspect_box_model (host, element, &values)

let rv_node_convert_points
    (from: nativeint, fromSpace: int, ``to``: nativeint, toSpace: int, xy: byref<double>, count: int)
    : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()

        let result =
            Raw.rv_node_convert_points (from, fromSpace, ``to``, toSpace, &xy, count)

        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[236] <- Calls.Counts[236] + 1L
        Calls.Ticks[236] <- Calls.Ticks[236] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_node_convert_points (from, fromSpace, ``to``, toSpace, &xy, count)

let rv_node_box_quad (node: nativeint, box: int, ``to``: nativeint, toSpace: int, quad: byref<double>) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_node_box_quad (node, box, ``to``, toSpace, &quad)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[237] <- Calls.Counts[237] + 1L
        Calls.Ticks[237] <- Calls.Ticks[237] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_node_box_quad (node, box, ``to``, toSpace, &quad)

let rv_host_inspect_cascade (host: nativeint, element: nativeint, property: byte[], property_length: int, diagnostic: nativeint[]) : int =
    if Calls.On then
        let started = System.Diagnostics.Stopwatch.GetTimestamp()
        let result = Raw.rv_host_inspect_cascade (host, element, property, property_length, diagnostic)
        let spent = System.Diagnostics.Stopwatch.GetTimestamp() - started
        Calls.Counts[246] <- Calls.Counts[246] + 1L
        Calls.Ticks[246] <- Calls.Ticks[246] + spent
        Calls.Elapsed <- Calls.Elapsed + spent
        result
    else
        Raw.rv_host_inspect_cascade (host, element, property, property_length, diagnostic)

// END GENERATED

let WrongThread = -2
let DomException = -3
let BufferTooSmall = -6
let ListenerFailed = -7

/// <summary>
/// The UTF-8 string a getter of the ABI copies out, or null when the getter reports a null string. The call receives a
/// buffer, its capacity and a one-element length array.
/// </summary>
let readString (operation: string) (call: byte[] -> int -> int[] -> int) : string =
    let length = [| 0 |]
    let mutable buffer = Array.zeroCreate<byte> 256
    let mutable status = call buffer buffer.Length length

    if status = BufferTooSmall then
        buffer <- Array.zeroCreate length[0]
        status <- call buffer buffer.Length length

    if status <> 0 then
        failwith $"{operation} returned {status}"

    if length[0] < 0 then
        null
    else
        Text.Encoding.UTF8.GetString(buffer, 0, length[0])

let check (operation: string) (status: int) =
    if status <> 0 then
        failwith $"{operation} returned {status}"

/// A native WebCore event, valid only inside the handler that receives it.
[<Struct>]
type Event(handle: nativeint) =
    member _.Handle = handle
    member _.Phase = rv_event_phase handle
    member _.DefaultPrevented = rv_event_default_prevented handle = 1

    member _.PreventDefault() = rv_event_prevent_default handle

    member _.StopPropagation() = rv_event_stop_propagation handle

    member _.Type =
        let event = handle
        readString "event_type" (fun buffer capacity length -> rv_event_type (event, buffer, capacity, length))

    member _.Trusted = rv_event_flags handle &&& 16 <> 0

    /// <summary>An <c>RV_NUMBER_*</c> value of the event, or None when its interface has none.</summary>
    member _.Number(number: int) =
        let mutable value = 0.0

        match rv_event_number (handle, number, &value) with
        | 0 -> Some value
        | _ -> None

    /// <summary>An <c>RV_EVENT_STRING_*</c> value of the event, or None when its interface has none.</summary>
    member _.String(property: int) =
        let length = [| 0 |]
        let buffer = Array.zeroCreate<byte> 256

        match rv_event_string (handle, property, buffer, buffer.Length, length) with
        | 0 when length[0] >= 0 -> Some(Text.Encoding.UTF8.GetString(buffer, 0, length[0]))
        | _ -> None

/// Exceptions raised by handlers during the innermost dispatching call, in raise order.
let private handlerFailures = ResizeArray<exn>()

let private invokeHandler (context: nativeint) (event: nativeint) =
    try
        let handler = GCHandle.FromIntPtr(context).Target :?> (Event -> unit)
        handler (Event event)
        0
    with error ->
        handlerFailures.Add error
        1

let private callback = EventCallback invokeHandler
let private callbackPointer = Marshal.GetFunctionPointerForDelegate<_> callback

/// Runs a dispatching ABI call. Handler exceptions are rethrown after the native dispatch returns, as one
/// AggregateException.
let private dispatching (operation: string) (call: unit -> int) =
    let start = handlerFailures.Count
    let status = call ()
    let raised = handlerFailures.GetRange(start, handlerFailures.Count - start)
    handlerFailures.RemoveRange(start, raised.Count)

    if status = ListenerFailed then
        raise (AggregateException($"{operation}: {raised.Count} event handler(s) failed", raised))

    check operation status

/// A registered native event listener. Dispose unregisters it and frees the handler's GC handle.
type Listener(handle: nativeint, context: GCHandle) =
    let mutable removed = false

    member _.Handle = handle

    interface IDisposable with
        member _.Dispose() =
            if not removed then
                removed <- true

                rv_listener_remove handle |> check "listener_remove"

                context.Free()

/// A strong reference to a native WebCore node, released on Dispose. Dispose is valid only on the host thread.
type Node(handle: nativeint) =
    do
        if handle = 0n then
            failwith "native node creation returned NULL"

    member _.Handle = handle

    member this.Append(child: Node) =
        rv_node_append_child (handle, child.Handle) |> check "append_child"

    member _.SetText(text: string) =
        rv_node_set_text_content (handle, text) |> check "set_text_content"

    member _.SetAttribute(name: string, value: string) =
        rv_element_set_attribute (handle, name, value) |> check "set_attribute"

    /// Registers a handler that runs synchronously on the host thread for each matching event.
    member _.Listen(eventType: string, capture: bool, handler: Event -> unit) =
        let context = GCHandle.Alloc handler

        let listener =
            rv_node_add_event_listener (
                handle,
                eventType,
                (if capture then 1 else 0),
                callbackPointer,
                GCHandle.ToIntPtr context
            )

        if listener = 0n then
            context.Free()
            failwith "node_add_event_listener returned NULL"

        new Listener(listener, context)

    /// Dispatches an untrusted event and returns whether a handler cancelled it.
    member _.Dispatch(eventType: string, bubbles: bool, cancelable: bool) =
        let defaultPrevented = ref 0

        dispatching "dispatch_event" (fun () ->
            rv_node_dispatch_event (
                handle,
                eventType,
                (if bubbles then 1 else 0),
                (if cancelable then 1 else 0),
                &defaultPrevented.contents
            ))

        defaultPrevented.Value = 1

    member _.Click() =
        dispatching "element_click" (fun () -> rv_element_click handle)

    member _.Checked =
        match rv_input_checked handle with
        | 1 -> true
        | 0 -> false
        | status -> failwith $"input_checked returned {status}"

    /// <summary>The value of an <c>input</c>, <c>textarea</c>, <c>select</c> or <c>option</c>.</summary>
    member _.Value =
        readString "node_get_string" (fun buffer capacity length ->
            rv_node_get_string (handle, 6, buffer, capacity, length))

    interface IDisposable with
        member _.Dispose() = rv_node_release handle

/// The <c>RV_MOUSE_*</c>, <c>RV_KEY_*</c>, <c>RV_NUMBER_*</c> and <c>RV_EVENT_STRING_*</c> values of the header.
module Input =
    let MouseMove, MouseDown, MouseUp = 0, 1, 2
    let ButtonNone, ButtonLeft = -1, 0
    let KeyDown, KeyUp, KeyChar = 0, 1, 2

    let ClientX, ClientY, Button, Buttons, Modifiers, Detail, DeltaX, DeltaY =
        0, 1, 2, 3, 4, 5, 6, 7

    let Code, Data, InputType = 0, 1, 2

/// A native WebCore page and document, painted into unpremultiplied RGBA8.
type Host(width: int, height: int) =
    let handle = rv_host_create (width, height)

    do
        if handle = 0n then
            failwith "rv_host_create returned NULL"

    // The installed handler's delegate, kept alive while native code holds its function pointer.
    let mutable resourceHandler: ResourceHandler = null
    let mutable frameCallback: FrameCallback = null
    let mutable width = width
    let mutable height = height

    member _.Handle = handle
    member _.Width = width
    member _.Height = height

    member _.Resize(newWidth: int, newHeight: int) =
        rv_host_resize (handle, newWidth, newHeight) |> check "host_resize"

        width <- newWidth
        height <- newHeight

    member _.SetDeviceScale(scale: float32) =
        rv_host_set_device_scale (handle, scale) |> check "host_set_device_scale"

    /// The size in device pixels of the image <c>Paint</c> returns.
    member _.PaintSize =
        let mutable w = 0
        let mutable h = 0

        rv_host_paint_size (handle, &w, &h) |> check "host_paint_size"

        w, h

    /// Native mouse input; returns whether the page or WebCore handled it.
    member _.Mouse(action: int, x: int, y: int, button: int, clickCount: int, modifiers: int) =
        let status = rv_host_mouse (handle, action, x, y, button, clickCount, modifiers)

        if status < 0 then
            failwith $"host_mouse returned {status}"

        status = 1

    member _.Wheel(x: int, y: int, deltaX: float32, deltaY: float32) =
        let status = rv_host_wheel (handle, x, y, deltaX, deltaY, 0)

        if status < 0 then
            failwith $"host_wheel returned {status}"

        status = 1

    member _.Key(action: int, key: string, code: string, text: string, modifiers: int) =
        let status = rv_host_key (handle, action, key, code, text, modifiers, 0)

        if status < 0 then
            failwith $"host_key returned {status}"

        status = 1

    /// Presses and releases a key that produces <c>text</c>, as a platform reports it.
    member this.Type(key: string, code: string, text: string) =
        this.Key(Input.KeyDown, key, code, null, 0) |> ignore

        this.Key(Input.KeyChar, key, code, text, 0) |> ignore

        this.Key(Input.KeyUp, key, code, null, 0) |> ignore

    member _.SetFocused(focused: bool) =
        rv_host_set_focused (handle, (if focused then 1 else 0))
        |> check "host_set_focused"

    /// Calls <c>requested</c> when the page wants a frame; it must not call the ABI.
    member _.OnFrame(requested: unit -> unit) =
        let callback = FrameCallback(fun _ -> requested ())

        rv_host_set_frame_callback (handle, Marshal.GetFunctionPointerForDelegate<_> callback, 0n)
        |> check "host_set_frame_callback"

        frameCallback <- callback

    member _.Update() =
        rv_host_update handle |> check "host_update"

    /// The viewport area invalidated since the last paint, as x, y, width and height, or None.
    member _.DirtyRect =
        let mutable x = 0
        let mutable y = 0
        let mutable w = 0
        let mutable h = 0

        match rv_host_dirty_rect (handle, &x, &y, &w, &h) with
        | 1 -> Some(x, y, w, h)
        | 0 -> None
        | status -> failwith $"host_dirty_rect returned {status}"

    member _.ActiveElement() =
        match rv_document_active_element handle with
        | 0n -> None
        | element -> Some(new Node(element))

    member _.GetElementById(id: string) =
        new Node(rv_document_get_element_by_id (handle, id))

    /// <summary>The <c>RV_CURSOR_*</c> value for the mouse's position.</summary>
    member _.Cursor = rv_host_cursor handle

    member _.ScrollPosition =
        let mutable x = 0
        let mutable y = 0

        rv_host_scroll_position (handle, &x, &y) |> check "host_scroll_position"

        x, y

    member _.ScrollTo(x: int, y: int) =
        rv_host_scroll_to (handle, x, y) |> check "host_scroll_to"

    member _.ImeSetComposition(text: string, selectionStart: int, selectionEnd: int) =
        rv_host_ime_set_composition (handle, text, selectionStart, selectionEnd)
        |> check "host_ime_set_composition"

    member _.ImeCommit(text: string) =
        rv_host_ime_commit (handle, text) |> check "host_ime_commit"

    member _.ImeCancel() =
        rv_host_ime_cancel handle |> check "host_ime_cancel"

    /// The composition's or caret's bounds as x, y, width and height, or None.
    member _.ImeRect =
        let mutable x = 0
        let mutable y = 0
        let mutable w = 0
        let mutable h = 0

        match rv_host_ime_rect (handle, &x, &y, &w, &h) with
        | 1 -> Some(x, y, w, h)
        | 0 -> None
        | status -> failwith $"host_ime_rect returned {status}"

    member _.LoadHtml(html: string) =
        rv_host_load_html (handle, html) |> check "load_html"

    member _.ScriptsEnabled = rv_host_scripts_enabled handle
    member _.VmEntryDisallowed = rv_host_vm_entry_disallowed handle

    member _.Body() = new Node(rv_document_body handle)

    member _.CreateElement(tagName: string) =
        new Node(rv_document_create_element (handle, tagName))

    member _.CreateText(data: string) =
        new Node(rv_document_create_text (handle, data))

    /// Serves the document's resource loads inside the native handler: <c>serve</c> maps a URL to its bytes and
    /// Content-Type, or to None to fail the load. A load whose <c>serve</c> raises fails. The loads complete during
    /// <c>CycleRunLoop</c>.
    member _.ServeResources(serve: string -> (byte[] * string) option) =
        let handler =
            ResourceHandler(fun _ load url ->
                let served =
                    try
                        serve (Marshal.PtrToStringUTF8 url)
                    with _ ->
                        None

                match served with
                | Some(data, contentType) -> rv_resource_load_finish (load, data, data.Length, contentType)
                | None -> rv_resource_load_fail load
                |> ignore)

        rv_host_set_resource_handler (handle, Marshal.GetFunctionPointerForDelegate<_> handler, 0n)
        |> check "host_set_resource_handler"

        resourceHandler <- handler

    /// Cycles the run loop for the given milliseconds, at least once.
    member _.CycleRunLoop(milliseconds: int) =
        let cycles = rv_run_loop_cycle milliseconds

        if cycles < 0 then
            failwith $"run_loop_cycle returned {cycles}"

    member this.Paint() =
        let w, h = this.PaintSize
        let pixels = Array.zeroCreate<byte>(w * h * 4)

        rv_host_paint_rgba (handle, pixels, pixels.Length) |> check "paint_rgba"

        pixels

    interface IDisposable with
        member _.Dispose() = rv_host_destroy handle
