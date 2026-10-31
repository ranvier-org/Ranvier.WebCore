import argparse
import ctypes
import math
import os
from pathlib import Path
import sys
import threading


def verify(native_directory):
    directory = Path(native_directory).resolve()
    filename = {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')
    search = os.add_dll_directory(str(directory)) if sys.platform == 'win32' else None
    library = ctypes.CDLL(str(directory / filename))
    pointer, integer, unsigned, number = ctypes.c_void_p, ctypes.c_int32, ctypes.c_uint32, ctypes.c_double
    retained, buffers = [], []
    assertions = 0

    class Span(ctypes.Structure):
        _fields_ = [('data', pointer), ('length', integer)]

    class Segment(ctypes.Structure):
        _fields_ = [('present', integer), ('tag', integer), ('text', Span), ('reference', pointer)]

    class Segments(ctypes.Structure):
        _fields_ = [('present', integer), ('count', integer), ('items', ctypes.POINTER(Segment))]

    class Values(ctypes.Structure):
        _fields_ = [('present', integer), ('count', integer), ('items', ctypes.POINTER(pointer))]

    def bind(name, returns, arguments):
        function = getattr(library, name)
        function.restype, function.argtypes = returns, arguments
        return function

    parse = bind('rv_dom_css_style_value_parse', integer, [pointer, pointer, integer, pointer, integer, ctypes.POINTER(pointer)])
    parse_all = bind('rv_dom_css_style_value_parse_all', integer, [pointer, pointer, integer, pointer, integer, ctypes.POINTER(Values)])
    create_keyword = bind('rv_dom_cssom_keyword_value_create', integer, [pointer, pointer, integer, ctypes.POINTER(pointer)])
    set_keyword = bind('rv_dom_cssom_keyword_value_set_value', integer, [pointer, pointer, integer])
    create_unit = bind('rv_dom_css_unit_value_create', integer, [pointer, number, pointer, integer, ctypes.POINTER(pointer)])
    get_unit_value = bind('rv_dom_css_unit_value_get_value', integer, [pointer, ctypes.POINTER(number)])
    set_unit_value = bind('rv_dom_css_unit_value_set_value', integer, [pointer, number])
    create_unparsed = bind('rv_dom_css_unparsed_value_create', integer, [pointer, ctypes.POINTER(Segments), ctypes.POINTER(pointer)])
    get_length = bind('rv_dom_css_unparsed_value_get_length', integer, [pointer, ctypes.POINTER(unsigned)])
    get_item = bind('rv_dom_css_unparsed_value_item', integer, [pointer, unsigned, ctypes.POINTER(Segment)])
    set_item = bind('rv_dom_css_unparsed_value_set_item', integer, [pointer, unsigned, ctypes.POINTER(Segment)])
    create_reference = bind('rv_dom_cssom_variable_reference_value_create', integer, [pointer, pointer, integer, pointer, ctypes.POINTER(pointer)])
    set_variable = bind('rv_dom_cssom_variable_reference_value_set_variable', integer, [pointer, pointer, integer])
    get_fallback = bind('rv_dom_cssom_variable_reference_value_get_fallback', integer, [pointer, ctypes.POINTER(pointer)])
    release_segment = bind('rv_dom_union_usv_string_or_cssom_variable_reference_value_nullable_release', None, [ctypes.POINTER(Segment)])
    release_values = bind('rv_dom_sequence_css_style_value_release', None, [ctypes.POINTER(Values)])

    def expect(condition, label):
        nonlocal assertions
        assertions += 1
        if not condition:
            raise AssertionError(label)

    def data(value):
        encoded = value.encode('utf-8') if isinstance(value, str) else value
        buffer = ctypes.create_string_buffer(encoded)
        buffers.append(buffer)
        return ctypes.cast(buffer, pointer), len(encoded)

    def owned(value, release='rv_dom_css_style_value_release'):
        expect(bool(value.value), 'owned value is nonnull')
        retained.append((release, value.value))
        return value.value

    def text(name, target):
        buffer, length = ctypes.create_string_buffer(8192), integer()
        status = bind(name, integer, [pointer, pointer, integer, ctypes.POINTER(integer)])(target, buffer, len(buffer), ctypes.byref(length))
        expect(status == 0, name + ' status ' + str(status))
        return buffer.raw[:length.value].decode('utf-8') if length.value >= 0 else None

    def serialized(target):
        return text('rv_dom_css_style_value_to_string', target)

    def exception_name():
        buffer, length = ctypes.create_string_buffer(256), integer()
        expect(bind('rv_last_exception', integer, [integer, pointer, integer, ctypes.POINTER(integer)])(
            0, buffer, len(buffer), ctypes.byref(length)) == 0, 'read exception')
        return buffer.raw[:length.value].decode('utf-8') if length.value >= 0 else None

    def rejected(status, name):
        expect(status == -3, 'engine exception status ' + name + ': ' + str(status))
        actual = exception_name()
        expect(actual == name, f'exact engine exception: expected {name}, got {actual}')

    host = bind('rv_host_create', pointer, [integer, integer])(320, 240)
    expect(bool(host), 'host creation')
    try:
        expect(bind('rv_abi_version', unsigned, [])() == 54, 'Native46 ABI54 cohort')
        expect(bind('rv_abi_has', integer, [ctypes.c_char_p])(b'dom-css-style-values') == 1, 'static parser capability')
        body = bind('rv_document_body', pointer, [pointer])(host)
        retained.append(('rv_node_release', body))
        document = pointer()
        expect(bind('rv_dom_node_get_owner_document', integer, [pointer, ctypes.POINTER(pointer)])(body, ctypes.byref(document)) == 0, 'document context')
        retained.append(('rv_node_release', document.value))

        def parsed(property_name, css):
            result = pointer()
            expect(parse(document, *data(property_name), *data(css), ctypes.byref(result)) == 0, 'parse ' + repr((property_name, css)))
            return owned(result)

        value = parsed('width', '12.5px')
        expect(text('rv_dom_css_style_value_get_interface_name', value) == 'CSSUnitValue', 'unit subtype dispatch')
        expect(serialized(value) == '12.5px', 'unit serialization')
        expect(text('rv_dom_css_unit_value_get_unit', value) == 'px', 'unit getter')
        numeric = number()
        expect(get_unit_value(value, ctypes.byref(numeric)) == 0 and numeric.value == 12.5, 'unit double precision')
        expect(set_unit_value(value, 23.75) == 0 and serialized(value) == '23.75px', 'unit mutation')
        for invalid in [math.nan, math.inf, -math.inf]:
            rejected(set_unit_value(value, invalid), 'TypeError')
            expect(get_unit_value(value, ctypes.byref(numeric)) == 0 and numeric.value == 23.75, 'invalid number preserves value')
            result = pointer()
            rejected(create_unit(document, invalid, *data('px'), ctypes.byref(result)), 'TypeError')
            expect(not result.value, 'invalid number produces no owned value')
        result = pointer()
        expect(create_unit(document, 2.5, *data('em'), ctypes.byref(result)) == 0, 'unit factory')
        expect(serialized(owned(result)) == '2.5em', 'unit factory serialization')
        rejected(create_unit(document, 1, *data('not-a-unit'), ctypes.byref(pointer())), 'TypeError')
        rejected(create_unit(document, 1, *data('px\0junk'), ctypes.byref(pointer())), 'TypeError')

        keyword = parsed('display', 'BLOCK')
        expect(text('rv_dom_css_style_value_get_interface_name', keyword) == 'CSSOMKeywordValue', 'keyword subtype dispatch')
        expect(text('rv_dom_cssom_keyword_value_get_value', keyword) == 'block', 'canonical parsed keyword')
        expect(set_keyword(keyword, *data('inline')) == 0 and serialized(keyword) == 'inline', 'mutable keyword')
        rejected(set_keyword(keyword, *data('')), 'TypeError')
        expect(serialized(keyword) == 'inline', 'invalid keyword preserves value')
        result = pointer()
        expect(create_keyword(document, *data('custom-keyword'), ctypes.byref(result)) == 0, 'keyword factory')
        expect(serialized(owned(result)) == 'custom-keyword', 'keyword factory serialization')
        result = pointer()
        expect(create_keyword(document, *data('a\0b'), ctypes.byref(result)) == 0, 'keyword factory NUL input')
        nul_keyword = owned(result)
        expect(text('rv_dom_cssom_keyword_value_get_value', nul_keyword) == 'a\0b', 'keyword factory preserves NUL')
        expect(set_keyword(nul_keyword, *data('changed\0tail')) == 0, 'keyword setter NUL input')
        expect(text('rv_dom_cssom_keyword_value_get_value', nul_keyword) == 'changed\0tail', 'keyword setter preserves NUL')
        expect(text('rv_dom_css_style_value_get_interface_name', parsed('background-image', 'url(a.png)')) == 'CSSStyleImageValue', 'image subtype dispatch')
        expect(serialized(parsed('margin', '1px 2px')) == '1px 2px', 'opaque shorthand serialization')
        math_value = parsed('width', 'calc(1px + 2%)')
        expect(text('rv_dom_css_style_value_get_interface_name', math_value) == 'CSSNumericValue', 'opaque math base dispatch')
        expect(serialized(math_value) == 'calc(1px + 2%)', 'opaque math serialization')

        values = Values()
        expect(parse_all(document, *data('animation-name'), *data('first, second'), ctypes.byref(values)) == 0, 'parseAll list')
        try:
            expect(values.present == 1 and values.count == 2, 'parseAll cardinality')
            expect([serialized(values.items[index]) for index in range(values.count)] == ['first', 'second'], 'parseAll order')
        finally:
            release_values(ctypes.byref(values))
        expect(values.present == 0 and values.count == 0 and not values.items, 'sequence release resets ownership')
        release_values(ctypes.byref(values))
        expect(serialized(parsed('animation-name', 'first, second')) == 'first', 'parse first list item')
        for property_name, css in [('width', 'invalid-width'), ('not-a-property', 'red'), ('width', '')]:
            rejected(parse(document, *data(property_name), *data(css), ctypes.byref(pointer())), 'TypeError')
            rejected(parse_all(document, *data(property_name), *data(css), ctypes.byref(values)), 'TypeError')
        expect(serialized(parsed('width', '7px')) == '7px', 'parser recovers after errors')
        parsed_variables = parsed('--c14', 'before var(--nested, red) after')
        parsed_length = unsigned()
        expect(get_length(parsed_variables, ctypes.byref(parsed_length)) == 0 and parsed_length.value == 3, 'parsed variable segment structure')
        parsed_segment = Segment()
        expect(get_item(parsed_variables, 1, ctypes.byref(parsed_segment)) == 0, 'parsed variable segment')
        try:
            expect(parsed_segment.present == 1 and parsed_segment.tag == 2, 'parsed reference arm')
            expect(text('rv_dom_cssom_variable_reference_value_get_variable', parsed_segment.reference) == '--nested', 'parsed variable name')
            parsed_fallback = pointer()
            expect(get_fallback(parsed_segment.reference, ctypes.byref(parsed_fallback)) == 0, 'parsed nested fallback getter')
            expect(serialized(owned(parsed_fallback)).strip() == 'red', 'parsed nested fallback tokens')
        finally:
            release_segment(ctypes.byref(parsed_segment))

        def segment_text(value):
            address, length = data(value)
            return Segment(1, 1, Span(address, length), None)

        def unparsed(members):
            array = (Segment * len(members))(*members)
            sequence = Segments(1, len(members), array)
            result = pointer()
            expect(create_unparsed(document, ctypes.byref(sequence), ctypes.byref(result)) == 0, 'unparsed factory')
            return owned(result)

        fallback = unparsed([segment_text('red')])
        reference = pointer()
        expect(create_reference(document, *data('--x'), fallback, ctypes.byref(reference)) == 0, 'variable reference factory')
        reference = owned(reference, 'rv_dom_cssom_variable_reference_value_release')
        result = pointer()
        expect(get_fallback(reference, ctypes.byref(result)) == 0, 'fallback getter')
        expect(owned(result) == fallback, 'fallback identity')
        tokens = unparsed([segment_text('before'), Segment(1, 2, Span(), reference), segment_text('a\0b')])
        length = unsigned()
        expect(get_length(tokens, ctypes.byref(length)) == 0 and length.value == 3, 'unparsed length')
        item = Segment()
        expect(get_item(tokens, 1, ctypes.byref(item)) == 0, 'reference segment getter')
        try:
            expect(item.present == 1 and item.tag == 2 and item.reference == reference, 'variable segment identity')
            expect(text('rv_dom_cssom_variable_reference_value_get_variable', item.reference) == '--x', 'variable getter')
        finally:
            release_segment(ctypes.byref(item))
        expect(item.present == 0 and not item.reference, 'segment release resets ownership')
        expect(get_item(tokens, 2, ctypes.byref(item)) == 0, 'NUL segment getter')
        try:
            expect(item.present == 1 and item.tag == 1 and item.text.length == 3, 'NUL segment byte length')
            expect(ctypes.string_at(item.text.data, item.text.length) == b'a\0b', 'NUL segment exact data')
        finally:
            release_segment(ctypes.byref(item))
        expect(get_item(tokens, 3, ctypes.byref(item)) == 0 and item.present == 0, 'missing segment stays null')
        release_segment(ctypes.byref(item))
        replacement = segment_text('changed\0tail')
        expect(set_item(tokens, 0, ctypes.byref(replacement)) == 0, 'segment mutation')
        expect(get_item(tokens, 0, ctypes.byref(item)) == 0, 'mutated segment getter')
        try:
            expect(ctypes.string_at(item.text.data, item.text.length) == b'changed\0tail', 'mutated NUL segment preserved')
        finally:
            release_segment(ctypes.byref(item))
        rejected(set_item(tokens, 8, ctypes.byref(replacement)), 'RangeError')
        expect(set_variable(reference, *data('--renamed')) == 0, 'variable setter')
        rejected(set_variable(reference, *data('invalid')), 'TypeError')
        expect(text('rv_dom_cssom_variable_reference_value_get_variable', reference) == '--renamed', 'invalid variable preserves name')
        result = pointer()
        expect(create_reference(document, *data('--without-fallback'), None, ctypes.byref(result)) == 0, 'nullable fallback factory')
        no_fallback = owned(result, 'rv_dom_cssom_variable_reference_value_release')
        result = pointer()
        expect(get_fallback(no_fallback, ctypes.byref(result)) == 0 and not result.value, 'omitted fallback stays null')
        for css in ['a\0b', 'a\ufffdb']:
            parsed_tokens = parsed('--c14', css)
            expect(serialized(parsed_tokens) == 'a\ufffdb', 'custom parse token replacement')

        expect(parse(None, *data('width'), *data('1px'), ctypes.byref(pointer())) == -1, 'null parser context')
        expect(parse(body, *data('width'), *data('1px'), ctypes.byref(pointer())) == -11, 'wrong parser context interface')
        expect(parse(document, None, 1, *data('1px'), ctypes.byref(pointer())) == -1, 'null span data')
        expect(parse(document, *data('width'), None, -1, ctypes.byref(pointer())) == -1, 'negative span length')
        expect(parse(document, *data('width'), *data(b'\xff'), ctypes.byref(pointer())) == -1, 'invalid UTF8 parser input')
        expect(set_keyword(keyword, *data(b'\xff')) == -1, 'invalid UTF8 setter input')
        expect(set_unit_value(keyword, 1) == -11, 'wrong typed value interface')
        for invalid in [Segment(0, 1, Span(), None), Segment(2, 1, Span(), None),
                        Segment(1, 1, Span(None, 1), None), Segment(1, 1, Span(None, -1), None),
                        Segment(1, 2, Span(), None)]:
            expect(set_item(tokens, 0, ctypes.byref(invalid)) == -1, 'invalid segment input rejected')
        invalid = segment_text(b'\xff')
        expect(set_item(tokens, 0, ctypes.byref(invalid)) == -1, 'invalid UTF8 segment input')
        for sequence in [Segments(0, 0, None), Segments(2, 0, None), Segments(1, -1, None), Segments(1, 1, None)]:
            expect(create_unparsed(document, ctypes.byref(sequence), ctypes.byref(pointer())) == -1, 'invalid sequence input rejected')
        statuses = []
        property_data, property_length = data('width')
        css_data, css_length = data('1px')
        worker = threading.Thread(target=lambda: statuses.append(parse(document, property_data, property_length, css_data, css_length, ctypes.byref(pointer()))))
        worker.start()
        worker.join()
        expect(statuses == [-2], 'parser engine thread enforced')
    finally:
        for release, value in reversed(retained):
            bind(release, None, [pointer])(value)
        bind('rv_host_destroy', None, [pointer])(host)
        if search:
            search.close()
    if assertions != 190:
        raise AssertionError(f'Incomplete typed CSS value regression: {assertions} assertions, expected 190')
    print(f'PASS typed CSS values: {assertions} assertions; retained handles released', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    verify(parser.parse_args().native_directory)
