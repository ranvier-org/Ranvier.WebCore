import argparse
import ctypes
import os
import pathlib
import sys
import threading


def verify(native_directory):
    directory = pathlib.Path(native_directory).resolve()
    filename = {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')
    search = os.add_dll_directory(str(directory)) if sys.platform == 'win32' else None
    library = ctypes.CDLL(str(directory / filename))
    pointer, integer = ctypes.c_void_p, ctypes.c_int32
    count = 0

    def bind(name, returns, arguments):
        method = getattr(library, name)
        method.restype, method.argtypes = returns, arguments
        return method

    def expect(condition, message):
        nonlocal count
        count += 1
        if not condition:
            raise AssertionError(message)

    declaration = bind('rv_dom_css_supports_2', integer, [pointer, pointer, integer, pointer, integer, ctypes.POINTER(integer)])
    condition = bind('rv_dom_css_supports_1', integer, [pointer, pointer, integer, ctypes.POINTER(integer)])
    has = bind('rv_abi_has', integer, [ctypes.c_char_p])
    expect(has(b'dom-css-supports') == 1, 'CSS support-query binding capability')
    host = bind('rv_host_create', pointer, [integer, integer])(320, 240)
    expect(bool(host), 'host creation')
    body = document = None
    try:
        body = bind('rv_document_body', pointer, [pointer])(host)
        expect(bool(body), 'body handle')
        owner = pointer()
        status = bind('rv_dom_node_get_owner_document', integer, [pointer, ctypes.POINTER(pointer)])(body, ctypes.byref(owner))
        document = owner.value
        expect(status == 0 and bool(document), 'checked document context')

        def encoded(value):
            data = value.encode('utf-8') if isinstance(value, str) else value
            return ctypes.create_string_buffer(data), len(data)

        def supports(property_name, value):
            name, name_size = encoded(property_name)
            text, text_size = encoded(value)
            result = integer(42)
            status = declaration(document, name, name_size, text, text_size, ctypes.byref(result))
            expect(status == 0, 'declaration status: ' + str(status))
            return result.value

        def supports_condition(value):
            text, size = encoded(value)
            result = integer(42)
            status = condition(document, text, size, ctypes.byref(result))
            expect(status == 0, 'condition status: ' + str(status))
            return result.value

        for name, value, expected in [
            ('display', 'block', 1), ('display', 'not-a-display-value', 0),
            ('color', 'rgb(1 2 3)', 1), ('not-a-real-property', 'red', 0),
            ('', 'red', 0), ('color', '', 0), ('--native-probe', '42', 1),
            ('--\u03c0', '42', 1), ('width', 'calc(1px + 2px)', 1),
            ('width', 'var(--native-probe)', 1), ('display\0unknown', 'block', 0),
            ('display', 'block\0unknown', 0),
        ]:
            expect(supports(name, value) == expected, 'declaration result: ' + repr((name, value)))

        for text, expected in [
            ('', 0), ('(display: block)', 1), ('(display: not-a-display-value)', 0),
            ('not (display: not-a-display-value)', 1),
            ('(display: block) and (color: red)', 1), ('(no-such-property: 1)', 0),
            ('(display: block) or (no-such-property: 1)', 1),
            ('selector(:is(.probe))', 1), ('(display: block)\0junk', 0),
        ]:
            expect(supports_condition(text) == expected, 'condition result: ' + repr(text))

        name, name_size = encoded('display\0unknown')
        value, value_size = encoded('block\0unknown')
        result = integer(42)
        expect(declaration(document, name, 7, value, 5, ctypes.byref(result)) == 0 and result.value == 1,
               'explicit byte lengths select exact prefixes')

        valid, valid_size = encoded('(display: block)')
        invalid, invalid_size = encoded(b'\xff')
        for target, text, size, expected in [
            (document, None, -1, -1), (document, None, 1, -1),
            (document, invalid, invalid_size, -1), (None, valid, valid_size, -1),
            (body, valid, valid_size, -11),
        ]:
            result = integer(42)
            expect(condition(target, text, size, ctypes.byref(result)) == expected, 'invalid condition input status')
            expect(result.value == 42, 'condition error preserves output')
        result = integer(42)
        status = condition(document, None, 0, ctypes.byref(result))
        expect(status == 0 and result.value == 0, f'null zero-length span is empty: status={status}, result={result.value}')
        expect(condition(document, valid, valid_size, None) == -1, 'null output rejected')

        for name_pointer, name_length, value_pointer, value_length in [
            (None, 1, value, 5), (name, -1, value, 5),
            (name, 7, None, 1), (name, 7, value, -1),
            (invalid, invalid_size, value, 5), (name, 7, invalid, invalid_size),
        ]:
            result = integer(42)
            expect(declaration(document, name_pointer, name_length, value_pointer, value_length, ctypes.byref(result)) == -1,
                   'invalid declaration span rejected')
            expect(result.value == 42, 'declaration error preserves output')

        statuses = []
        def other_thread():
            result = integer(42)
            statuses.append((condition(document, valid, valid_size, ctypes.byref(result)), result.value))
        worker = threading.Thread(target=other_thread)
        worker.start()
        worker.join()
        expect(statuses == [(-2, 42)], 'query requires the owning engine thread and preserves output')
    finally:
        release = bind('rv_node_release', None, [pointer])
        if document:
            release(document)
        if body:
            release(body)
        bind('rv_host_destroy', None, [pointer])(host)
        if search:
            search.close()
    print(f'PASS CSS supports: {count} assertions; retained handles released')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    verify(parser.parse_args().native_directory)
