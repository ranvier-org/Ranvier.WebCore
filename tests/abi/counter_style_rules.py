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
    retained = []
    assertions = 0

    def bind(name, returns, arguments):
        return bind_utf8(library, name, returns, arguments)

    def expect(condition, label):
        nonlocal assertions
        assertions += 1
        if not condition:
            raise AssertionError(label)

    def call(name, arguments, *values):
        status = bind(name, integer, arguments)(*values)
        expect(status == 0, name + ': status ' + str(status))

    def handle(name, arguments, values, release):
        result = pointer()
        call(name, arguments + [ctypes.POINTER(pointer)], *values, ctypes.byref(result))
        expect(bool(result.value), name + ': non-null handle')
        retained.append((release, result.value))
        return result.value

    def text(name, target):
        buffer, length = ctypes.create_string_buffer(4096), integer()
        call(name, [pointer, pointer, integer, ctypes.POINTER(integer)], target, buffer, len(buffer), ctypes.byref(length))
        expect(length.value >= 0, name + ': non-null text')
        return buffer.raw[:length.value].decode('utf-8')

    host = bind('rv_host_create', pointer, [integer, integer])(640, 320)
    expect(bool(host), 'host creation')
    try:
        body = bind('rv_document_body', pointer, [pointer])(host)
        retained.append(('rv_node_release', body))
        css = b'@counter-style c19-original {system:cyclic;symbols:"WWWW";prefix:"";suffix:""} #never {color:red}'
        markup = b'<style id="first">' + css + b'</style><style id="copy">' + css + b'</style>'
        markup += b'<div style="font:32px/40px serif"><ol style="margin:0;padding:0">'
        markup += b'<li id="item" style="list-style:c19-original inside"><span id="payload" style="display:inline-block">X</span></li>'
        markup += b'<li id="decimal" value="1" style="list-style:decimal inside"><span id="decimal-payload" style="display:inline-block">X</span></li>'
        markup += b'</ol><div id="reference"><span style="display:inline-block">WWWW</span><span id="reference-payload" style="display:inline-block">X</span></div></div>'
        call('rv_dom_element_set_inner_html', [pointer, Utf8], body, markup)
        find = bind('rv_document_get_element_by_id', pointer, [pointer, string])
        nodes = {}
        for name in ['first', 'copy', 'item', 'payload', 'decimal', 'decimal-payload', 'reference', 'reference-payload']:
            value = find(host, name.encode())
            expect(bool(value), 'fixture element ' + name)
            retained.append(('rv_node_release', value))
            nodes[name] = value

        def counter(style):
            sheet = handle('rv_dom_html_style_element_get_sheet', [pointer], [style], 'rv_dom_style_sheet_release')
            rules = handle('rv_dom_css_style_sheet_get_css_rules', [pointer], [sheet], 'rv_dom_css_rule_list_release')
            counter_rule = handle('rv_dom_css_rule_list_item', [pointer, unsigned], [rules, 0], 'rv_dom_css_rule_release')
            plain_rule = handle('rv_dom_css_rule_list_item', [pointer, unsigned], [rules, 1], 'rv_dom_css_rule_release')
            return sheet, counter_rule, plain_rule

        sheet, rule, plain_rule = counter(nodes['first'])
        _, copy, _ = counter(nodes['copy'])
        copied_text = text('rv_dom_css_rule_get_css_text', copy)
        call('rv_node_remove_child', [pointer, pointer], body, nodes['copy'])

        def left(node):
            values = [number() for _ in range(4)]
            call('rv_element_rect', [pointer] + [ctypes.POINTER(number)] * 4, node, *(ctypes.byref(value) for value in values))
            return values[0].value

        def advance(item, payload):
            call('rv_host_update', [pointer], host)
            return left(nodes[payload]) - left(nodes[item])

        literal = advance('reference', 'reference-payload')
        decimal = advance('decimal', 'decimal-payload')
        expect(abs(literal - decimal) > 2, 'reference glyphs distinguish custom and decimal marker output')
        expect(abs(advance('item', 'payload') - literal) < 0.75, 'initial custom name renders wide symbols')
        call('rv_dom_css_counter_style_rule_set_name', [pointer, Utf8], rule, b'c19-renamed')
        actual = text('rv_dom_css_counter_style_rule_get_name', rule)
        expect(actual == 'c19-renamed', 'name edit metadata: expected c19-renamed, got ' + actual)
        expect(text('rv_dom_css_rule_get_css_text', rule).startswith('@counter-style c19-renamed'), 'serialized rule uses new name')
        expect(text('rv_dom_css_counter_style_rule_get_name', copy) == 'c19-original', 'other identical stylesheet retains its name')
        expect(text('rv_dom_css_rule_get_css_text', copy) == copied_text, 'copy-on-write preserves complete other rule')
        expect(abs(advance('item', 'payload') - decimal) < 0.75, 'old counter name stops producing custom output')
        call('rv_element_set_style', [pointer, string, string, integer], nodes['item'], b'list-style-type', b'c19-renamed', 0)
        expect(abs(advance('item', 'payload') - literal) < 0.75, 'new counter name produces custom output')
        previous = text('rv_dom_css_rule_get_css_text', rule)
        call('rv_dom_css_counter_style_rule_set_name', [pointer, Utf8], rule, b'123')
        expect(text('rv_dom_css_rule_get_css_text', rule) == previous, 'invalid name preserves complete rule')
        setter = bind('rv_dom_css_counter_style_rule_set_name', integer, [pointer, Utf8])
        expect(setter(None, b'bad') == -1, 'null target rejected')
        expect(setter(rule, None) == -1, 'null name rejected')
        expect(setter(plain_rule, b'bad') == -11, 'wrong interface rejected')
        statuses = []
        worker = threading.Thread(target=lambda: statuses.append(setter(rule, b'bad')))
        worker.start()
        worker.join()
        expect(statuses == [-2], 'wrong thread rejected')
        expect(text('rv_dom_css_rule_get_css_text', rule) == previous, 'failed checked calls preserve complete rule')
        call('rv_dom_css_style_sheet_delete_rule', [pointer, unsigned], sheet, 0)
        parent = pointer(42)
        call('rv_dom_css_rule_get_parent_style_sheet', [pointer, ctypes.POINTER(pointer)], rule, ctypes.byref(parent))
        expect(not parent.value, 'removed counter has no parent sheet')
        expect(abs(advance('item', 'payload') - decimal) < 0.75, 'removed counter no longer formats marker')
        call('rv_dom_css_counter_style_rule_set_name', [pointer, Utf8], rule, b'c19-detached')
        expect(text('rv_dom_css_counter_style_rule_get_name', rule) == 'c19-detached', 'detached rule remains editable')
    finally:
        for release, value in reversed(retained):
            if value:
                bind(release, None, [pointer])(value)
        bind('rv_host_destroy', None, [pointer])(host)
        if search:
            search.close()
    print(f'PASS counter style name/render effects: {assertions} assertions; retained handles released')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    verify(parser.parse_args().native_directory)
