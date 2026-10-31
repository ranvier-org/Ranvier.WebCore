/// Checks the generated DOM functions of RanvierWebCoreDom.h (gen/domgen.py): attribute getters and setters of each
/// type mapping, operations with optional and nullable arguments, interface checks, DOM exceptions, the object
/// handle types, enumerations, events, string unions, dictionaries, Range and Selection, settings and the thread
/// check.
module RanvierWebCoreAbi.Dom

open System.Threading
open RanvierWebCoreAbi.Native
open RanvierWebCoreAbi.NativeDom

let private html =
    "<!doctype html><html><head><title>Dom</title></head><body><div id=box class=\"a b\" data-x=1><span id=s1>one</span><span>two</span></div><input id=field value=hello><select id=pick><option>A</option><option selected>B</option></select></body></html>"

/// The UTF-8 bytes of a generated string input, passed with utf8Length of the same value.
let private utf8 (value: string) = System.Text.Encoding.UTF8.GetBytes value

let private utf8Length (value: string) = System.Text.Encoding.UTF8.GetByteCount value

let private require condition (message: string) =
    if not condition then
        failwith $"ASSERTION FAILED: {message}"

let private text operation (call: byte[] -> int -> int[] -> int) = readString operation call

let private exceptionName () =
    readString "last_exception" (fun buffer capacity length -> rv_last_exception (0, buffer, capacity, length))

let run (_: string) =
    require (rv_abi_has "dom-generated" = 1) "rv_abi_has dom-generated"
    require (rv_abi_has "dom:HTMLInputElement" = 1) "rv_abi_has dom:HTMLInputElement"
    require (rv_abi_has "dom:HTMLMarqueeElement" = 1) "rv_abi_has dom:HTMLMarqueeElement"
    require (rv_abi_has "dom:RanvierUnknownElement" = 0) "rv_abi_has of an unknown interface"
    require (RV_DOM_NODE_ELEMENT_NODE = 1) "Node.ELEMENT_NODE"

    use host = new Host(200, 100)
    host.LoadHtml html
    use box = host.GetElementById "box"
    use field = host.GetElementById "field"
    use pick = host.GetElementById "pick"

    // DOMString attributes: Element.id (reflected), Element.tagName (read-only).
    let id () =
        text "element_get_id" (fun b c l -> rv_dom_element_get_id (box.Handle, b, c, l))

    require (id () = "box") "Element.id getter"
    rv_dom_element_set_id (box.Handle, utf8 "panel", utf8Length "panel") |> check "element_set_id"
    require (id () = "panel") "Element.id setter"
    rv_dom_element_set_id (box.Handle, utf8 "box", utf8Length "box") |> check "element_set_id"

    let tag =
        text "element_get_tag_name" (fun b c l -> rv_dom_element_get_tag_name (box.Handle, b, c, l))

    require (tag = "DIV") "Element.tagName"

    // A nullable string result: getAttribute of a missing attribute is null.
    let attribute name =
        text "element_get_attribute" (fun b c l -> rv_dom_element_get_attribute (box.Handle, utf8 name, utf8Length name, b, c, l))

    require (attribute "data-x" = "1") "Element.getAttribute"
    require (isNull (attribute "data-missing")) "Element.getAttribute of a missing attribute is null"

    // An optional boolean argument without a default: NULL toggles, a value forces.
    let mutable present = 0

    rv_dom_element_toggle_attribute (box.Handle, utf8 "hidden", utf8Length "hidden", null, &present)
    |> check "element_toggle_attribute"

    require (present = 1) "toggleAttribute with force absent adds the attribute"

    rv_dom_element_toggle_attribute (box.Handle, utf8 "hidden", utf8Length "hidden", [| 1 |], &present)
    |> check "element_toggle_attribute"

    require (present = 1) "toggleAttribute with force true keeps it"

    rv_dom_element_toggle_attribute (box.Handle, utf8 "hidden", utf8Length "hidden", null, &present)
    |> check "element_toggle_attribute"

    require (present = 0) "toggleAttribute with force absent removes it"

    // Booleans and numbers on HTMLInputElement, and a nullable number.
    let value () =
        text "input_get_value" (fun b c l -> rv_dom_html_input_element_get_value (field.Handle, b, c, l))

    require (value () = "hello") "HTMLInputElement.value getter"

    rv_dom_html_input_element_set_value (field.Handle, utf8 "native", utf8Length "native")
    |> check "input_set_value"

    require (value () = "native") "HTMLInputElement.value setter"

    let mutable selectionStart = 0u
    let mutable hasSelection = 0

    rv_dom_html_input_element_get_selection_start (field.Handle, &selectionStart, &hasSelection)
    |> check "input_get_selection_start"

    require (hasSelection = 1) "selectionStart of a text input is present"

    rv_dom_html_input_element_set_type (field.Handle, utf8 "checkbox", utf8Length "checkbox")
    |> check "input_set_type"

    rv_dom_html_input_element_get_selection_start (field.Handle, &selectionStart, &hasSelection)
    |> check "input_get_selection_start"

    require (hasSelection = 0) "selectionStart of a checkbox is null"

    let mutable flag = 0

    rv_dom_html_input_element_set_checked (field.Handle, 1)
    |> check "input_set_checked"

    rv_dom_html_input_element_get_checked (field.Handle, &flag)
    |> check "input_get_checked"

    require (flag = 1 && field.Checked) "HTMLInputElement.checked"

    rv_dom_html_input_element_set_disabled (field.Handle, 1)
    |> check "input_set_disabled"

    let disabledAttribute =
        readString "element_get_attribute" (fun b c l ->
            rv_dom_element_get_attribute (field.Handle, utf8 "disabled", utf8Length "disabled", b, c, l))

    require (disabledAttribute = "") "a reflected boolean sets its content attribute"

    // A DOM exception: a negative maxLength throws IndexSizeError.
    let status = rv_dom_html_input_element_set_max_length (field.Handle, -1)
    require (status = DomException) $"maxLength = -1 returns RV_ERR_DOM_EXCEPTION, got {status}"
    require (exceptionName () = "IndexSizeError") "the exception is IndexSizeError"

    // The interface check: an input member on a div.
    let wrong = rv_dom_html_input_element_set_value (box.Handle, utf8 "x", utf8Length "x")

    require (wrong = WrongInterface) $"an HTMLInputElement member on a div returns RV_ERR_WRONG_INTERFACE, got {wrong}"

    // Node handles: appendChild returns its argument, with the identity of the existing ABI's handles.
    use document = new Node(rv_host_document host.Handle)
    let mutable created = 0n

    rv_dom_document_create_text_node (document.Handle, utf8 "three", utf8Length "three", &created)
    |> check "document_create_text_node"

    use createdNode = new Node(created)
    let mutable appended = 0n

    rv_dom_node_append_child (box.Handle, createdNode.Handle, &appended)
    |> check "node_append_child"

    use appendedNode = new Node(appended)
    require (appended = created) "appendChild returns the appended node's handle"

    let content =
        text "node_get_text_content" (fun b c l -> rv_dom_node_get_text_content (box.Handle, b, c, l))

    require (content = "onetwothree") "Node.textContent after appendChild"

    // Mixins: ParentNode.querySelector on an element, with an invalid selector throwing.
    let mutable found = 0n

    rv_dom_element_query_selector (box.Handle, utf8 "span", utf8Length "span", &found)
    |> check "element_query_selector"

    use first = new Node(found)
    require (rv_node_contains (box.Handle, first.Handle) = 1) "querySelector finds a descendant"

    let mutable none = 0n
    let invalid = rv_dom_element_query_selector (box.Handle, utf8 "[", utf8Length "[", &none)
    require (invalid = DomException && exceptionName () = "SyntaxError") "an invalid selector throws SyntaxError"

    // Object handles: NodeList, DOMTokenList and CSSStyleDeclaration.
    let mutable list = 0n

    rv_dom_element_query_selector_all (box.Handle, utf8 "span", utf8Length "span", &list)
    |> check "element_query_selector_all"

    let mutable count = 0u
    rv_dom_node_list_get_length (list, &count) |> check "node_list_get_length"
    require (count = 2u) "NodeList.length"
    let mutable second = 0n
    rv_dom_node_list_item (list, 1u, &second) |> check "node_list_item"
    use secondNode = new Node(second)

    require (text "second" (fun b c l -> rv_dom_node_get_text_content (second, b, c, l)) = "two") "NodeList.item"

    rv_dom_node_list_release list

    let mutable classes = 0n

    rv_dom_element_get_class_list (box.Handle, &classes)
    |> check "element_get_class_list"

    let mutable has = 0

    rv_dom_dom_token_list_toggle (classes, utf8 "c", utf8Length "c", null, &has)
    |> check "dom_token_list_toggle"

    rv_dom_dom_token_list_contains (classes, utf8 "b", utf8Length "b", &has)
    |> check "dom_token_list_contains"

    require (has = 1) "DOMTokenList.contains"
    let mutable tokens = 0u

    rv_dom_dom_token_list_get_length (classes, &tokens)
    |> check "dom_token_list_get_length"

    require (tokens = 3u) "DOMTokenList.length after toggle"
    rv_dom_dom_token_list_release classes

    let className =
        text "element_get_class_name" (fun b c l -> rv_dom_element_get_class_name (box.Handle, b, c, l))

    require (className = "a b c") "Element.className follows classList"

    let mutable style = 0n

    rv_dom_html_element_get_style (box.Handle, &style)
    |> check "html_element_get_style"

    rv_dom_css_style_declaration_set_property (style, utf8 "color", utf8Length "color", utf8 "rgb(1, 2, 3)", utf8Length "rgb(1, 2, 3)", utf8 "", utf8Length "")
    |> check "css_style_declaration_set_property"

    let color =
        text "get_property_value" (fun b c l ->
            rv_dom_css_style_declaration_get_property_value (style, utf8 "color", utf8Length "color", b, c, l))

    require (color = "rgb(1, 2, 3)") "CSSStyleDeclaration.setProperty and getPropertyValue"
    rv_dom_css_style_declaration_release style

    // A select's selectedIndex.
    let mutable index = 0

    rv_dom_html_select_element_get_selected_index (pick.Handle, &index)
    |> check "select_get_selected_index"

    require (index = 1) "HTMLSelectElement.selectedIndex"

    // Enumerations: Document.readyState and ShadowRoot.mode.
    let mutable state = -1

    rv_dom_document_get_ready_state (document.Handle, &state)
    |> check "document_get_ready_state"

    require (state = RV_DOM_DOCUMENT_READY_STATE_COMPLETE) $"Document.readyState is complete, got {state}"
    use host2 = host.CreateElement "div"
    let mutable shadowStatus = 0
    use shadow = new Node(rv_element_attach_shadow (host2.Handle, &shadowStatus))
    let mutable mode = -1

    rv_dom_shadow_root_get_mode (shadow.Handle, &mode)
    |> check "shadow_root_get_mode"

    require (mode = RV_DOM_SHADOW_ROOT_MODE_OPEN) "ShadowRoot.mode is open"

    // Events: the generated Event and UIEvent getters inside a listener.
    let seen = ResizeArray<string>()

    use _click =
        first.Listen(
            "click",
            false,
            fun e ->
                let handle = e.Handle
                let mutable bubbles = 0
                let mutable detail = -1
                let mutable current = 0n

                rv_dom_event_get_bubbles (handle, &bubbles) |> check "event_get_bubbles"
                rv_dom_ui_event_get_detail (handle, &detail) |> check "ui_event_get_detail"

                rv_dom_event_get_current_target (handle, &current)
                |> check "event_get_current_target"

                rv_node_release current

                let kind =
                    readString "event_get_type" (fun b c l -> rv_dom_event_get_type (handle, b, c, l))

                seen.Add $"{kind}:{bubbles}:{detail >= 0}:{current = first.Handle}"
        )

    first.Click()
    require (List.ofSeq seen = [ "click:1:True:True" ]) $"event getters in a listener: {List.ofSeq seen}"

    // String unions: innerHTML and setAttribute take (TrustedHTML or DOMString) as a C string.
    use holder = host.CreateElement "div"

    rv_dom_element_set_inner_html (holder.Handle, utf8 "<b>bold</b>", utf8Length "<b>bold</b>")
    |> check "element_set_inner_html"

    let inner =
        text "element_get_inner_html" (fun b c l -> rv_dom_element_get_inner_html (holder.Handle, b, c, l))

    require (inner = "<b>bold</b>") $"Element.innerHTML through a string union: {inner}"

    rv_dom_element_set_attribute (holder.Handle, utf8 "data-y", utf8Length "data-y", utf8 "2", utf8Length "2")
    |> check "element_set_attribute"

    let dataY =
        text "element_get_attribute" (fun b c l -> rv_dom_element_get_attribute (holder.Handle, utf8 "data-y", utf8Length "data-y", b, c, l))

    require (dataY = "2") "Element.setAttribute through a string union"

    // DOMStringMap: the named getter, setter and deleter of dataset.
    let mutable dataset = 0n

    rv_dom_html_element_get_dataset (box.Handle, &dataset)
    |> check "html_element_get_dataset"

    let named key =
        text "dom_string_map_named_item" (fun b c l -> rv_dom_dom_string_map_named_item (dataset, utf8 key, utf8Length key, b, c, l))

    require (named "x" = "1") "dataset.x"

    rv_dom_dom_string_map_set_named_item (dataset, utf8 "fooBar", utf8Length "fooBar", utf8 "v", utf8Length "v")
    |> check "dom_string_map_set_named_item"

    require (attribute "data-foo-bar" = "v") "dataset.fooBar sets data-foo-bar"

    rv_dom_dom_string_map_delete_named_property (dataset, utf8 "fooBar", utf8Length "fooBar")
    |> check "dom_string_map_delete_named_property"

    require (isNull (attribute "data-foo-bar")) "deleting dataset.fooBar removes data-foo-bar"
    rv_dom_dom_string_map_release dataset

    // Range and Selection: a Range handle is an RvAbstractRange, and Selection takes it.
    let mutable range = 0n

    rv_dom_document_create_range (document.Handle, &range)
    |> check "document_create_range"

    rv_dom_range_select_node_contents (range, first.Handle)
    |> check "range_select_node_contents"

    let mutable collapsed = -1

    rv_dom_abstract_range_get_collapsed (range, &collapsed)
    |> check "abstract_range_get_collapsed"

    require (collapsed = 0) "a range over a span's contents is not collapsed"
    let mutable selection = 0n

    rv_dom_document_get_selection (document.Handle, &selection)
    |> check "document_get_selection"

    rv_dom_dom_selection_remove_all_ranges selection
    |> check "dom_selection_remove_all_ranges"

    rv_dom_dom_selection_add_range (selection, range)
    |> check "dom_selection_add_range"

    let mutable ranges = 0u

    rv_dom_dom_selection_get_range_count (selection, &ranges)
    |> check "dom_selection_get_range_count"

    let selected =
        text "dom_selection_to_string" (fun b c l -> rv_dom_dom_selection_to_string (selection, b, c, l))

    require (ranges = 1u && selected = "one") $"Selection.addRange and toString: {ranges} {selected}"

    rv_dom_dom_selection_remove_all_ranges selection
    |> check "dom_selection_remove_all_ranges"

    rv_dom_dom_selection_release selection
    rv_dom_abstract_range_release range

    // HTMLSlotElement.
    use slot = host.CreateElement "slot"

    rv_dom_html_slot_element_set_name (slot.Handle, utf8 "header", utf8Length "header")
    |> check "html_slot_element_set_name"

    let slotName =
        text "html_slot_element_get_name" (fun b c l -> rv_dom_html_slot_element_get_name (slot.Handle, b, c, l))

    require (slotName = "header") "HTMLSlotElement.name"

    // A dictionary argument: getRootNode({ composed }) from inside a shadow tree, with NULL for the defaults and a
    // size that leaves composed out.
    use page = host.Body()
    use shadowHost = host.CreateElement "div"
    page.Append shadowHost
    let mutable attachStatus = 0

    use openShadow =
        new Node(rv_element_attach_shadow (shadowHost.Handle, &attachStatus))

    use inShadow = host.CreateElement "span"
    openShadow.Append inShadow

    let rootOf (options: RvDomGetRootNodeOptions[]) =
        let mutable root = 0n

        rv_dom_node_get_root_node (inShadow.Handle, options, &root)
        |> check "node_get_root_node"

        rv_node_release root
        root

    let full =
        System.Runtime.InteropServices.Marshal.SizeOf<RvDomGetRootNodeOptions>()
        |> uint32

    let mutable composed = RvDomGetRootNodeOptions()
    composed.size <- full
    composed.composed <- 1
    let mutable truncated = composed
    truncated.size <- 4u
    require (rootOf null = openShadow.Handle) "getRootNode with NULL options is the shadow root"
    require (rootOf [| composed |] = document.Handle) "getRootNode({ composed: true }) is the document"
    require (rootOf [| truncated |] = openShadow.Handle) "a field past size takes its IDL default"

    // [EnabledBySetting]: InputTypeColorEnhancementsEnabled is on by default on Cocoa only, HeadingOffsetEnabled on
    // everywhere.
    let mutable alpha = 0
    let alphaStatus = rv_dom_html_input_element_get_alpha (field.Handle, &alpha)

    if System.OperatingSystem.IsMacOS() then
        require (alphaStatus = 0) $"a member whose setting is on succeeds, got {alphaStatus}"
    else
        require (alphaStatus = -9) $"a member whose setting is off returns RV_ERR_UNSUPPORTED, got {alphaStatus}"

    let mutable offset = 0u

    rv_dom_html_element_get_heading_offset (box.Handle, &offset)
    |> check "html_element_get_heading_offset"

    // The thread check.
    let mutable threadStatus = 0

    let worker =
        Thread(fun () -> threadStatus <- rv_dom_element_set_id (box.Handle, utf8 "elsewhere", utf8Length "elsewhere"))

    worker.Start()
    worker.Join()
    require (threadStatus = WrongThread) "a generated function on another thread returns RV_ERR_WRONG_THREAD"
    require (id () = "box") "the call on another thread changed nothing"

    printfn "RANVIER_FSHARP_DOM PASS"
