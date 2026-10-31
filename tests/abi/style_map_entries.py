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
    pointer, integer, string = ctypes.c_void_p, ctypes.c_int32, ctypes.c_char_p
    retained = []
    assertions = 0

    class Span(ctypes.Structure):
        _fields_ = [('data', pointer), ('length', integer)]

    class Values(ctypes.Structure):
        _fields_ = [('present', integer), ('count', integer), ('items', ctypes.POINTER(pointer))]

    class Entry(ctypes.Structure):
        _fields_ = [('present', integer), ('key', Span), ('value', Values)]

    class Entries(ctypes.Structure):
        _fields_ = [('present', integer), ('count', integer), ('items', ctypes.POINTER(Entry))]

    def bind(name, result, arguments):
        return bind_utf8(library, name, result, arguments)

    entries = bind('rv_dom_style_property_map_read_only_entries', integer, [pointer, pointer, ctypes.POINTER(Entries)])
    release = bind('rv_dom_sequence_pair_usv_string_and_sequence_css_style_value_nullable_element_release', None, [ctypes.POINTER(Entries)])
    release_entry = bind('rv_dom_pair_usv_string_and_sequence_css_style_value_nullable_element_release', None, [ctypes.POINTER(Entry)])

    def expect(condition, label):
        nonlocal assertions
        assertions += 1
        if not condition:
            raise AssertionError(label)

    def call(name, arguments, *values):
        status = bind(name, integer, arguments)(*values)
        expect(status == 0, f'{name}: status {status}')

    def handle(name, arguments, values, drop):
        result = pointer()
        call(name, arguments + [ctypes.POINTER(pointer)], *values, ctypes.byref(result))
        expect(bool(result.value), name + ': nonnull handle')
        retained.append((drop, result.value))
        return result.value

    def text(value):
        buffer, length = ctypes.create_string_buffer(8192), integer()
        call('rv_dom_css_style_value_to_string', [pointer, pointer, integer, ctypes.POINTER(integer)], value, buffer, len(buffer), ctypes.byref(length))
        expect(length.value >= 0, 'typed value serialization is present')
        return buffer.raw[:length.value].decode('utf-8')

    def snapshot(map_value, document):
        result = Entries()
        expect(entries(map_value, document, ctypes.byref(result)) == 0, 'entry snapshot status')
        expect(result.present == 1 and result.count >= 0, 'entry snapshot presence/count')
        expect(result.count == 0 or bool(result.items), 'entry snapshot array storage')
        return result

    def decoded(result, select=None):
        output = []
        def invariant(condition, label):
            if not condition:
                raise AssertionError(label)
        for index in range(result.count):
            entry = result.items[index]
            invariant(entry.present == 1 and entry.key.length >= 0, 'present entry/key')
            invariant(entry.key.length == 0 or bool(entry.key.data), 'owned key storage')
            key = ctypes.string_at(entry.key.data, entry.key.length).decode('utf-8')
            invariant(entry.value.present == 1 and entry.value.count >= 0, 'present nullable value sequence')
            invariant(entry.value.count == 0 or bool(entry.value.items), 'entry value sequence storage')
            if select is None or key in select:
                values = [text(entry.value.items[item]) if entry.value.items[item] else None for item in range(entry.value.count)]
                output.append((key, values))
        return output

    host = bind('rv_host_create', pointer, [integer, integer])(320, 240)
    expect(bool(host), 'host creation')
    try:
        body = bind('rv_document_body', pointer, [pointer])(host)
        retained.append(('rv_node_release', body))
        document = handle('rv_dom_node_get_owner_document', [pointer], [body], 'rv_node_release')
        inline = handle('rv_dom_html_element_get_attribute_style_map', [pointer], [body], 'rv_dom_style_property_map_read_only_release')
        expect(bind('rv_abi_has', integer, [string])(b'dom-css-style-map-entries') == 1, 'entry snapshot feature advertised')
        empty = snapshot(inline, document)
        expect(empty.count == 0 and not empty.items, 'empty map snapshot owns no array')
        release(ctypes.byref(empty))
        expect(empty.present == 0 and empty.count == 0 and not empty.items, 'empty snapshot release resets')
        for name, value in [('height', '20px'), ('animation-name', 'first, second'), ('--c13-π', 'var(--other, red)')]:
            call('rv_element_set_style', [pointer, string, string, integer], body, name.encode('utf-8'), value.encode('utf-8'), 0)
        before = snapshot(inline, document)
        try:
            actual = decoded(before)
            expect(actual == [('height', ['20px']), ('animation-name', ['first', 'second']), ('--c13-π', ['var(--other, red)'])], 'declared snapshot preserves order, lists and Unicode key')
            call('rv_element_set_style', [pointer, string, string, integer], body, b'height', b'25px', 0)
            expect(decoded(before) == actual, 'snapshot preserves reified values after later mutation')
            after = snapshot(inline, document)
            try:
                expect(dict(decoded(after))['height'] == ['25px'], 'new snapshot reads current declarations')
            finally:
                release(ctypes.byref(after))
            computed = handle('rv_dom_element_computed_style_map', [pointer], [body], 'rv_dom_style_property_map_read_only_release')
            computed_values = snapshot(computed, document)
            try:
                selected = dict(decoded(computed_values, {'height', '--c13-π'}))
                expect(selected['height'] == ['25px'], 'computed entries contain current canonical height')
                expect('--c13-π' in selected, 'computed entries include custom property')
            finally:
                release(ctypes.byref(computed_values))
            first_value = before.items[0].value.items[0]
            independent = bind('rv_dom_css_style_value_retain', pointer, [pointer])(first_value)
            expect(independent == first_value, 'retain snapshot value identity')
            retained.append(('rv_dom_css_style_value_release', independent))
            call('rv_dom_style_property_map_clear', [pointer], inline)
            expect(decoded(before) == actual, 'snapshot survives clearing source map')
            release_entry(ctypes.byref(before.items[0]))
            expect(before.items[0].present == 0 and not before.items[0].key.data, 'individual entry release resets owned key')
            expect(before.items[0].value.present == 0 and before.items[0].value.count == 0 and not before.items[0].value.items, 'individual entry release resets nested references')
            expect(text(independent) == '20px', 'independently retained value survives entry release')
        finally:
            release(ctypes.byref(before))
        expect(before.present == 0 and before.count == 0 and not before.items, 'outer release resets result')
        release(ctypes.byref(before))
        expect(text(independent) == '20px', 'independent value survives complete snapshot release')

        markup = '<style id="entry-sheet">.entry{height:8px;animation-name:first,second;--c13-π:var(--other, red)}</style>'
        call('rv_dom_element_set_inner_html', [pointer, Utf8], body, markup.encode('utf-8'))
        style = bind('rv_document_get_element_by_id', pointer, [pointer, string])(host, b'entry-sheet')
        expect(bool(style), 'declared entry fixture style')
        retained.append(('rv_node_release', style))
        sheet = handle('rv_dom_html_style_element_get_sheet', [pointer], [style], 'rv_dom_style_sheet_release')
        rules = handle('rv_dom_css_style_sheet_get_css_rules', [pointer], [sheet], 'rv_dom_css_rule_list_release')
        rule = handle('rv_dom_css_rule_list_item', [pointer, ctypes.c_uint32], [rules, 0], 'rv_dom_css_rule_release')
        declared = handle('rv_dom_css_style_rule_get_style_map', [pointer], [rule], 'rv_dom_style_property_map_read_only_release')
        captured = snapshot(declared, document)
        try:
            original = decoded(captured)
            expect(original == [('height', ['8px']), ('animation-name', ['first', 'second']), ('--c13-π', ['var(--other, red)'])], 'declared entries preserve canonical order and structure')
            declaration = handle('rv_dom_css_style_rule_get_style', [pointer], [rule], 'rv_dom_css_style_declaration_release')
            call('rv_dom_css_style_declaration_set_property', [pointer, Utf8, Utf8, Utf8], declaration, b'height', b'9px', b'')
            expect(decoded(captured) == original, 'declared snapshot survives later CSSOM mutation')
            current = snapshot(declared, document)
            try:
                expect(dict(decoded(current))['height'] == ['9px'], 'new declared snapshot reads edited rule')
            finally:
                release(ctypes.byref(current))
            call('rv_dom_css_style_sheet_delete_rule', [pointer, ctypes.c_uint32], sheet, 0)
            detached = snapshot(declared, document)
            try:
                expect(dict(decoded(detached))['height'] == ['9px'], 'retained detached declared map uses explicit live context')
            finally:
                release(ctypes.byref(detached))
        finally:
            release(ctypes.byref(captured))

        for context, expected in [(None, -1), (body, -11)]:
            output = Entries(77, 88, None)
            expect(entries(inline, context, ctypes.byref(output)) == expected, 'invalid snapshot context rejected')
            expect(output.present == 77 and output.count == 88 and not output.items, 'checked error preserves unowned output')
        expect(entries(inline, document, None) == -1, 'null snapshot output rejected')
        statuses = []
        worker = threading.Thread(target=lambda: statuses.append(entries(inline, document, ctypes.byref(Entries()))))
        worker.start()
        worker.join()
        expect(statuses == [-2], 'snapshot engine thread enforced')
    finally:
        for drop, value in reversed(retained):
            bind(drop, None, [pointer])(value)
        bind('rv_host_destroy', None, [pointer])(host)
        if search:
            search.close()
    if assertions != 144:
        raise AssertionError(f'Incomplete typed entry snapshot proof: {assertions} assertions, expected144')
    print(f'PASS typed style map entries: {assertions} assertions; owned snapshots released', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    verify(parser.parse_args().native_directory)
