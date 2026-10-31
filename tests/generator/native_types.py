"""Exercise the generated DOM transports against a compiled native runtime."""

import argparse
import ctypes as c
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'abi'))
from utf8_inputs import Utf8, Span, bind as bind_utf8, span


class NodeOrString(c.Structure):
    _fields_ = [('present', c.c_int32), ('tag', c.c_int32), ('arm0', c.c_void_p), ('arm1', Span)]


class Sequence(c.Structure):
    _fields_ = [('present', c.c_int32), ('count', c.c_int32), ('items', c.c_void_p)]


class Hidden(c.Structure):
    _fields_ = [('present', c.c_int32), ('tag', c.c_int32), ('arm0', c.c_int32), ('arm1', c.c_double), ('arm2', Span)]


class ImportOptions(c.Structure):
    _fields_ = [('size', c.c_uint32), ('self_only', c.c_int32)]


class ImportUnion(c.Structure):
    _fields_ = [('present', c.c_int32), ('tag', c.c_int32), ('arm0', c.c_int32), ('arm1', c.POINTER(ImportOptions))]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-dir', required=True)
    parser.add_argument('--dependencies')
    args = parser.parse_args()
    native = Path(args.native_dir).resolve()
    directories = []
    if sys.platform == 'win32':
        for directory in (native, Path(args.dependencies).resolve() if args.dependencies else native):
            directories.append(os.add_dll_directory(str(directory)))
        c.CDLL(str(native / 'WebCore.dll'))
        host_name = 'RanvierWebCoreHost.dll'
    else:
        host_name = 'libRanvierWebCoreHost.dylib' if sys.platform == 'darwin' else 'libRanvierWebCoreHost.so'
    library = c.CDLL(str(native / host_name))

    def bind(name, parameters, result=c.c_int32):
        return bind_utf8(library, name, result, parameters)

    def ok(status):
        assert status == 0, f'native status {status}'

    pointer = c.c_void_p
    out = c.POINTER(pointer)
    create = bind('rv_host_create', [c.c_int32, c.c_int32], pointer)
    destroy = bind('rv_host_destroy', [pointer], None)
    release = bind('rv_node_release', [pointer], None)
    load = bind('rv_host_load_html', [pointer, c.c_char_p])
    host_document = bind('rv_host_document', [pointer], pointer)
    get_implementation = bind('rv_dom_document_get_implementation', [pointer, out])
    release_implementation = bind('rv_dom_dom_implementation_release', [pointer], None)
    create_document = bind('rv_dom_dom_implementation_create_html_document', [pointer, Utf8, out])
    create_ns = bind('rv_dom_document_create_element_ns', [pointer, Utf8, Utf8, pointer, out])
    get_body = bind('rv_dom_document_get_body', [pointer, out])
    append = bind('rv_dom_element_append', [pointer, c.POINTER(Sequence)])
    import_node = bind('rv_dom_document_import_node', [pointer, pointer, c.POINTER(ImportUnion), out])
    get_hidden = bind('rv_dom_html_element_get_hidden', [pointer, c.POINTER(Hidden)])
    set_hidden = bind('rv_dom_html_element_set_hidden', [pointer, c.POINTER(Hidden)])
    clear_hidden = bind('rv_dom_union_boolean_or_unrestricted_double_or_dom_string_nullable_release', [c.POINTER(Hidden)], None)
    set_attribute = bind('rv_element_set_attribute', [pointer, c.c_char_p, c.c_char_p])
    attribute_names = bind('rv_dom_element_get_attribute_names', [pointer, c.POINTER(Sequence)])
    clear_strings = bind('rv_dom_sequence_dom_string_release', [c.POINTER(Sequence)], None)
    get_classes = bind('rv_dom_element_get_class_list', [pointer, out])
    add_classes = bind('rv_dom_dom_token_list_add', [pointer, c.POINTER(Sequence)])
    contains_class = bind('rv_dom_dom_token_list_contains', [pointer, Utf8, c.POINTER(c.c_int32)])
    release_classes = bind('rv_dom_dom_token_list_release', [pointer], None)

    def text(name, target):
        function = bind(name, [pointer, pointer, c.c_int32, c.POINTER(c.c_int32)])
        buffer = c.create_string_buffer(256)
        length = c.c_int32()
        ok(function(target, buffer, len(buffer), c.byref(length)))
        return None if length.value == -1 else buffer.raw[:length.value].decode('utf-8')

    host = create(200, 100)
    assert host
    owned = []
    try:
        ok(load(host, b'<!doctype html><html><body></body></html>'))
        document = host_document(host)
        owned.append(document)
        implementation = pointer()
        ok(get_implementation(document, c.byref(implementation)))
        second = pointer()
        try:
            ok(create_document(implementation, b'Second document', c.byref(second)))
        finally:
            release_implementation(implementation)
        owned.append(second)
        assert second.value != document
        assert text('rv_dom_document_get_title', second) == 'Second document'
        body = pointer()
        ok(get_body(second, c.byref(body)))
        owned.append(body)
        callback_type = c.CFUNCTYPE(c.c_int32, pointer, pointer)
        add_listener = bind('rv_node_add_event_listener', [pointer, c.c_char_p, c.c_int32, callback_type, pointer], pointer)
        remove_listener = bind('rv_listener_remove', [pointer])
        dispatch = bind('rv_node_dispatch_event', [pointer, c.c_char_p, c.c_int32, c.c_int32, c.POINTER(c.c_int32)])
        prevent_default = bind('rv_event_prevent_default', [pointer], None)
        event_phase = bind('rv_event_phase', [pointer])
        event_child = pointer()
        ok(create_ns(second, b'http://www.w3.org/1999/xhtml', b'button', None, c.byref(event_child)))
        owned.append(event_child)
        event_nodes = (NodeOrString * 1)(NodeOrString(1, 1, event_child))
        ok(append(body, c.byref(Sequence(1, 1, c.cast(event_nodes, pointer)))))
        for flags in (0, 1, 6, 7, 4, 5, 2, 3):
            phases = []

            @callback_type
            def cancel_event(context, event):
                phases.append(event_phase(event))
                prevent_default(event)
                return 0

            listener = add_listener(body, b'ranvier-passive-test', flags, cancel_event, None)
            assert listener
            try:
                prevented = c.c_int32(-1)
                ok(dispatch(event_child, b'ranvier-passive-test', 1, 1, c.byref(prevented)))
                expected = 0 if flags & 4 and flags & 2 else 1
                assert prevented.value == expected, f'flags {flags}: defaultPrevented={prevented.value}, expected {expected}'
                assert phases == [1 if flags & 1 else 3], f'flags {flags}: capture phase {phases}'
            finally:
                ok(remove_listener(listener))
            ok(dispatch(event_child, b'ranvier-passive-test', 1, 1, c.byref(prevented)))
            assert prevented.value == 0 and len(phases) == 1, f'flags {flags}: removed listener still ran'
        ok(bind('rv_node_remove', [pointer])(event_child))
        print('NATIVE_EVENT_OPTIONS PASS: passive true/false/unspecified, capture phases, removal')
        svg = pointer()
        ok(create_ns(second, b'http://www.w3.org/2000/svg', b'svg:svg', None, c.byref(svg)))
        owned.append(svg)
        assert text('rv_dom_element_get_namespace_uri', svg) == 'http://www.w3.org/2000/svg'
        empty_names = Sequence()
        ok(attribute_names(svg, c.byref(empty_names)))
        try:
            assert empty_names.count == 0 and not empty_names.items, 'empty sequence must have a null item buffer'
        finally:
            clear_strings(c.byref(empty_names))
        owner = pointer()
        ok(bind('rv_dom_node_get_owner_document', [pointer, out])(svg, c.byref(owner)))
        assert owner.value == second.value
        release(owner)
        parts = (NodeOrString * 2)(NodeOrString(1, 1, svg.value), NodeOrString(1, 2, None, span('tail')))
        mixed = Sequence(1, len(parts), c.cast(parts, pointer))
        ok(append(body, c.byref(mixed)))
        assert text('rv_dom_node_get_text_content', body) == 'tail'
        shallow_options = ImportOptions(c.sizeof(ImportOptions), 1)
        deep_options = ImportOptions(c.sizeof(ImportOptions), 0)
        for options, expected_text in [
            (None, ''), (ImportUnion(1, 1, 0, None), ''), (ImportUnion(1, 1, 1, None), 'tail'),
            (ImportUnion(1, 2, 0, c.pointer(shallow_options)), ''),
            (ImportUnion(1, 2, 0, c.pointer(deep_options)), 'tail'),
        ]:
            imported = pointer()
            ok(import_node(document, body, c.byref(options) if options is not None else None, c.byref(imported)))
            owned.append(imported)
            assert imported.value != body.value, 'importNode must clone, not adopt the source object'
            assert text('rv_dom_node_get_text_content', imported) == expected_text
            imported_owner = pointer()
            ok(bind('rv_dom_node_get_owner_document', [pointer, out])(imported, c.byref(imported_owner)))
            assert imported_owner.value == document
            release(imported_owner)
            if expected_text:
                child = pointer()
                ok(bind('rv_dom_node_get_first_child', [pointer, out])(imported, c.byref(child)))
                assert child.value != svg.value
                assert text('rv_dom_element_get_namespace_uri', child) == 'http://www.w3.org/2000/svg'
                release(child)
        assert text('rv_dom_node_get_text_content', body) == 'tail', 'importNode must leave the source tree intact'
        invalid = (NodeOrString * 1)(NodeOrString(1, 99, None))
        invalid_sequence = Sequence(1, 1, c.cast(invalid, pointer))
        assert append(body, c.byref(invalid_sequence)) == -9
        assert text('rv_dom_node_get_text_content', body) == 'tail'
        missing_string = (NodeOrString * 1)(NodeOrString(1, 2, None, Span(None, -1)))
        missing_sequence = Sequence(1, 1, c.cast(missing_string, pointer))
        assert append(body, c.byref(missing_sequence)) == -1
        assert text('rv_dom_node_get_text_content', body) == 'tail'
        ok(set_attribute(body, b'data-proof', b'yes'))
        names = Sequence()
        ok(attribute_names(body, c.byref(names)))
        try:
            values = c.cast(names.items, c.POINTER(Span))
            assert 'data-proof' in [values[index].text() for index in range(names.count)]
        finally:
            clear_strings(c.byref(names))
        assert names.count == 0 and not names.items
        hidden = Hidden(1, 3, 0, 0, span('until-found'))
        ok(set_hidden(body, c.byref(hidden)))
        returned_hidden = Hidden()
        ok(get_hidden(body, c.byref(returned_hidden)))
        try:
            assert returned_hidden.present == 1 and returned_hidden.tag == 3
            assert returned_hidden.arm2.text() == 'until-found'
        finally:
            clear_hidden(c.byref(returned_hidden))
        assert returned_hidden.present == 0 and not returned_hidden.arm2.data
        classes = pointer()
        ok(get_classes(body, c.byref(classes)))
        try:
            tokens = (Span * 2)(span('one'), span('two'))
            sequence = Sequence(1, 2, c.cast(tokens, pointer))
            ok(add_classes(classes, c.byref(sequence)))
            for token in (b'one', b'two'):
                found = c.c_int32()
                ok(contains_class(classes, token, c.byref(found)))
                assert found.value == 1
        finally:
            release_classes(classes)
        print('NATIVE_DOM_TYPES PASS: namespaces, second-document identity/lifetime, cross-document import, mixed append, union results, sequences, validation, owned release')
    finally:
        for handle in reversed(owned):
            release(handle)
        destroy(host)


if __name__ == '__main__':
    main()
