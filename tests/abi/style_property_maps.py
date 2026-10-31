import argparse
import ctypes
import os
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utf8_inputs import Utf8, bind as bind_utf8


def verify(native_directory):
    directory = Path(native_directory).resolve()
    filename = {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')
    search = os.add_dll_directory(str(directory)) if sys.platform == 'win32' else None
    library = ctypes.CDLL(str(directory / filename))
    pointer, integer, unsigned, string, number = ctypes.c_void_p, ctypes.c_int32, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_double
    retained, buffers = [], []
    assertions = 0

    class Span(ctypes.Structure):
        _fields_ = [('data', pointer), ('length', integer)]

    class InputValue(ctypes.Structure):
        _fields_ = [('present', integer), ('tag', integer), ('value', pointer), ('text', Span)]

    class InputValues(ctypes.Structure):
        _fields_ = [('present', integer), ('count', integer), ('items', ctypes.POINTER(InputValue))]

    class MaybeValue(ctypes.Structure):
        _fields_ = [('present', integer), ('tag', integer), ('undefined', integer), ('value', pointer)]

    class Values(ctypes.Structure):
        _fields_ = [('present', integer), ('count', integer), ('items', ctypes.POINTER(pointer))]

    def bind(name, returns, arguments):
        return bind_utf8(library, name, returns, arguments)

    get = bind('rv_dom_style_property_map_read_only_get', integer, [pointer, pointer, pointer, integer, ctypes.POINTER(MaybeValue)])
    get_all = bind('rv_dom_style_property_map_read_only_get_all', integer, [pointer, pointer, pointer, integer, ctypes.POINTER(Values)])
    set_value = bind('rv_dom_style_property_map_set', integer, [pointer, pointer, pointer, integer, ctypes.POINTER(InputValues)])
    append = bind('rv_dom_style_property_map_append', integer, [pointer, pointer, pointer, integer, ctypes.POINTER(InputValues)])
    release_maybe = bind('rv_dom_union_undefined_or_css_style_value_release', None, [ctypes.POINTER(MaybeValue)])
    release_values = bind('rv_dom_sequence_css_style_value_nullable_element_release', None, [ctypes.POINTER(Values)])

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

    def call(name, arguments, *values):
        status = bind(name, integer, arguments)(*values)
        expect(status == 0, f'{name}: status {status}')

    def handle(name, arguments, values, release):
        result = pointer()
        call(name, arguments + [ctypes.POINTER(pointer)], *values, ctypes.byref(result))
        expect(bool(result.value), name + ': nonnull result')
        retained.append((release, result.value))
        return result.value

    def text(name, target):
        buffer, length = ctypes.create_string_buffer(8192), integer()
        call(name, [pointer, pointer, integer, ctypes.POINTER(integer)], target, buffer, len(buffer), ctypes.byref(length))
        expect(length.value >= 0, name + ': nonnull text')
        return buffer.raw[:length.value].decode('utf-8')

    def serialized(value):
        return text('rv_dom_css_style_value_to_string', value)

    def input_values(values):
        entries = []
        for value in values:
            entries.append(InputValue(1, 2, None, Span(*data(value))) if isinstance(value, str) else InputValue(1, 1, value, Span()))
        array = (InputValue * len(entries))(*entries)
        return InputValues(1, len(entries), array)

    host = bind('rv_host_create', pointer, [integer, integer])(640, 320)
    expect(bool(host), 'host creation')
    try:
        body = bind('rv_document_body', pointer, [pointer])(host)
        retained.append(('rv_node_release', body))
        document = handle('rv_dom_node_get_owner_document', [pointer], [body], 'rv_node_release')
        css = b'.probe {width:30px; height:10px} #never {color:red}'
        markup = b'<style id="first">' + css + b'</style><style id="copy">' + css + b'</style><div id="item" class="probe"></div>'
        call('rv_dom_element_set_inner_html', [pointer, Utf8], body, markup)
        find = bind('rv_document_get_element_by_id', pointer, [pointer, string])
        nodes = {}
        for name in ['first', 'copy', 'item']:
            nodes[name] = find(host, name.encode())
            expect(bool(nodes[name]), 'fixture element ' + name)
            retained.append(('rv_node_release', nodes[name]))
        inline = handle('rv_dom_html_element_get_attribute_style_map', [pointer], [nodes['item']], 'rv_dom_style_property_map_read_only_release')
        again = handle('rv_dom_html_element_get_attribute_style_map', [pointer], [nodes['item']], 'rv_dom_style_property_map_read_only_release')
        expect(inline == again, 'inline map SameObject identity')
        computed = handle('rv_dom_element_computed_style_map', [pointer], [nodes['item']], 'rv_dom_style_property_map_read_only_release')
        expect(text('rv_dom_style_property_map_read_only_get_interface_name', inline) == 'StylePropertyMap', 'mutable dispatch')
        expect(text('rv_dom_style_property_map_read_only_get_interface_name', computed) == 'StylePropertyMapReadOnly', 'readonly dispatch')

        def read(map_value, property_name):
            result = MaybeValue()
            expect(get(map_value, document, *data(property_name), ctypes.byref(result)) == 0, 'map get ' + property_name)
            try:
                expect(result.present == 1 and result.tag in [1, 2], 'get tagged result')
                if result.tag == 1:
                    expect(result.undefined == 0 and not result.value, 'undefined has no value handle')
                    return None
                expect(bool(result.value), 'present style value handle')
                return serialized(result.value)
            finally:
                release_maybe(ctypes.byref(result))
                expect(result.present == 0 and not result.value, 'get release resets ownership')

        def write(map_value, property_name, values, method=set_value):
            sequence = input_values(values)
            status = method(map_value, document, *data(property_name), ctypes.byref(sequence))
            details = []
            if status == -3:
                for part in [0, 1]:
                    buffer, length = ctypes.create_string_buffer(8192), integer()
                    bind('rv_last_exception', integer, [integer, pointer, integer, ctypes.POINTER(integer)])(part, buffer, len(buffer), ctypes.byref(length))
                    details.append(buffer.value.decode('utf-8'))
            expect(status == 0, f'map write {property_name}: status {status}, {details}')

        expect(read(inline, 'height') is None, 'missing get stays undefined')
        expect(read(computed, 'height') == '10px', 'computed stylesheet value')
        write(inline, 'height', ['20px'])
        expect(read(inline, 'height') == '20px' and read(computed, 'height') == '20px', 'inline and computed maps update')
        unit = handle('rv_dom_css_unit_value_create', [pointer, number, pointer, integer], [document, 25.5, *data('px')], 'rv_dom_css_style_value_release')
        write(inline, 'height', [unit])
        expect(read(computed, 'height') == '25.5px', 'typed object arm updates computed value')
        call('rv_dom_css_unit_value_set_value', [pointer, number], unit, 99)
        expect(read(inline, 'height') == '25.5px', 'mutating input object does not write back')
        write(inline, 'background-image', ['url("a.png")', 'url("b.png")'])
        write(inline, 'background-image', ['url("c.png")'], append)
        values = Values()
        expect(get_all(inline, document, *data('background-image'), ctypes.byref(values)) == 0, 'getAll list')
        try:
            expect(values.present == 1 and values.count == 3, 'getAll preserves cardinality')
            expect([serialized(values.items[i]) for i in range(values.count)] == ['url("a.png")', 'url("b.png")', 'url("c.png")'], 'getAll preserves order')
        finally:
            release_values(ctypes.byref(values))
        expect(values.present == 0 and values.count == 0 and not values.items, 'getAll release resets ownership')
        expect(get_all(inline, document, *data('width'), ctypes.byref(values)) == 0 and values.count == 0, 'missing getAll is empty')
        release_values(ctypes.byref(values))

        def read_all(map_value, property_name):
            result = Values()
            expect(get_all(map_value, document, *data(property_name), ctypes.byref(result)) == 0, 'getAll ' + property_name)
            try:
                expect(result.present == 1, 'getAll present ' + property_name)
                return [serialized(result.items[index]) if result.items[index] else None for index in range(result.count)]
            finally:
                release_values(ctypes.byref(result))
                expect(result.present == 0 and result.count == 0 and not result.items, 'getAll cleanup ' + property_name)

        for property_name, layers in [
            ('background-clip', ['border-box', 'content-box']),
            ('background-origin', ['padding-box', 'border-box']),
            ('background-size', ['10px 20px', '30px 40px']),
        ]:
            write(inline, property_name, layers[:1])
            write(inline, property_name, layers[1:], append)
            expect(read_all(inline, property_name) == layers, 'outer commas preserve inner layer spaces: ' + property_name)
        write(inline, 'animation-name', ['first', 'second'])
        write(inline, 'animation-name', ['third'], append)
        expect(read_all(inline, 'animation-name') == ['first', 'second', 'third'], 'existing comma-list control')
        write(inline, 'grid-auto-columns', ['10px', '20px'])
        expect(read_all(inline, 'grid-auto-columns') == ['10px', '20px'], 'legitimate space-list control')

        sequence = input_values(['1px'])
        expect(set_value(computed, document, *data('height'), ctypes.byref(sequence)) == -11, 'readonly map rejects mutator')
        expect(get(inline, None, *data('height'), ctypes.byref(MaybeValue())) == -1, 'null explicit context rejected')
        expect(get(inline, body, *data('height'), ctypes.byref(MaybeValue())) == -11, 'non-document context rejected')
        expect(get(inline, document, *data(b'\xff'), ctypes.byref(MaybeValue())) == -1, 'invalid UTF8 property rejected')
        statuses = []
        name_data, name_length = data('height')
        worker = threading.Thread(target=lambda: statuses.append(get(inline, document, name_data, name_length, ctypes.byref(MaybeValue()))))
        worker.start()
        worker.join()
        expect(statuses == [-2], 'map operation owning thread enforced')
        call('rv_dom_style_property_map_delete', [pointer, pointer, pointer, integer], inline, document, *data('height'))
        expect(read(inline, 'height') is None, 'delete removes inline value')
        call('rv_dom_style_property_map_clear', [pointer], inline)
        size = unsigned(42)
        call('rv_dom_style_property_map_read_only_get_size', [pointer, ctypes.POINTER(unsigned)], inline, ctypes.byref(size))
        expect(size.value == 0, 'clear removes all inline entries')
        print(f'BASIC typed maps: {assertions} assertions', flush=True)

        def declared(style):
            sheet = handle('rv_dom_html_style_element_get_sheet', [pointer], [style], 'rv_dom_style_sheet_release')
            rules = handle('rv_dom_css_style_sheet_get_css_rules', [pointer], [sheet], 'rv_dom_css_rule_list_release')
            rule = handle('rv_dom_css_rule_list_item', [pointer, unsigned], [rules, 0], 'rv_dom_css_rule_release')
            map_value = handle('rv_dom_css_style_rule_get_style_map', [pointer], [rule], 'rv_dom_style_property_map_read_only_release')
            return rule, map_value

        rule, map_value = declared(nodes['first'])
        copy_rule, copy_map = declared(nodes['copy'])
        copied_text = text('rv_dom_css_rule_get_css_text', copy_rule)
        call('rv_node_remove_child', [pointer, pointer], body, nodes['copy'])
        expect(read(map_value, 'width') == '30px', 'initial declared width')
        write(map_value, 'width', ['44px'])
        expect(read(map_value, 'width') == '44px', 'declared map edits owning rule after COW')
        expect(read(copy_map, 'width') == '30px', 'declared map preserves cache-sharing copy')
        expect(text('rv_dom_css_rule_get_css_text', copy_rule) == copied_text, 'complete cache-sharing rule unchanged')
        call('rv_host_update', [pointer], host)
        bounds = [number() for _ in range(4)]
        call('rv_element_rect', [pointer] + [ctypes.POINTER(number)] * 4, nodes['item'], *(ctypes.byref(value) for value in bounds))
        expect(abs(bounds[2].value - 44) < .01, 'declared map edit reaches actual layout')
    finally:
        for release, value in reversed(retained):
            bind(release, None, [pointer])(value)
        bind('rv_host_destroy', None, [pointer])(host)
        if search:
            search.close()
    if assertions != 189:
        raise AssertionError(f'Incomplete typed style map regression: {assertions} assertions, expected 189')
    print(f'PASS typed style maps: {assertions} assertions; retained handles released', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    verify(parser.parse_args().native_directory)
