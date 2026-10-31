import argparse
import ctypes
import json
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe
from utf8_inputs import Utf8

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
MATHML = 'http://www.w3.org/1998/Math/MathML'


class Span(ctypes.Structure):
    _fields_ = [('data', ctypes.c_void_p), ('length', ctypes.c_int32)]


class StyleInput(ctypes.Structure):
    _fields_ = [('present', ctypes.c_int32), ('tag', ctypes.c_int32), ('value', ctypes.c_void_p), ('text', Span)]


class StyleInputs(ctypes.Structure):
    _fields_ = [('present', ctypes.c_int32), ('count', ctypes.c_int32), ('items', ctypes.POINTER(StyleInput))]


class FocusOptions(ctypes.Structure):
    _fields_ = [('size', ctypes.c_uint32), ('prevent_scroll', ctypes.c_int32), ('focus_visible', ctypes.POINTER(ctypes.c_int32))]


def verify(native_directory):
    with SvgProbe(native_directory, 320, 240) as p:
        oracle = json.loads((FIXTURES / 'mathml-surface-oracle.json').read_text(encoding='utf-8'))
        has = p.bind('rv_abi_has', p.integer, [ctypes.c_char_p])
        for feature in [b'dom:MathMLElement', b'dom:MathMLMathElement']:
            p.expect(has(feature) == 1, 'compiled typed MathML capability ' + feature.decode())
        p.load((FIXTURES / 'mathml-surface.html').read_bytes(), standalone=False)
        p.update()
        ids = ['math', 'row', 'mi', 'mo', 'frac', 'num', 'den', 'sqrt', 'rad', 'inline', 'focusable', 'second', 'plain']
        n = {name: p.node(name) for name in ids}
        html = p.node('html')
        document = p.object('rv_dom_node_get_owner_document', [p.pointer], [n['math']], 'node')
        state = {}

        def number(name, target, kind=ctypes.c_int32):
            value = kind()
            p.call(name, [p.pointer, ctypes.POINTER(kind)], target, ctypes.byref(value))
            return value.value

        def active():
            element = p.bind('rv_document_active_element', p.pointer, [p.pointer])(p.host)
            p.expect(bool(element), 'active element exists')
            p.retained.append(('rv_node_release', element))
            return p.attribute(element, 'id') or ''

        identity, members = {}, {}
        for name in ids:
            target = n[name]
            rejected = p.pointer(123)
            html_style = p.bind('rv_dom_html_element_get_style', p.integer, [p.pointer, ctypes.POINTER(p.pointer)])
            p.expect(html_style(target, ctypes.byref(rejected)) == -11 and rejected.value == 123, name + ' is not an HTMLElement')
            local = p.text('rv_dom_element_get_local_name', [p.pointer], target)
            identity[name] = {'localName': local, 'namespace': p.text('rv_dom_element_get_namespace_uri', [p.pointer], target)}
            members[name] = {'tabIndex': number('rv_dom_math_ml_element_get_tab_index', target), 'autofocus': bool(number('rv_dom_math_ml_element_get_autofocus', target)),
                             'nonce': p.text('rv_dom_math_ml_element_get_nonce', [p.pointer], target), 'nonceAttribute': p.attribute(target, 'nonce')}
            dataset = p.object('rv_dom_math_ml_element_get_dataset', [p.pointer], [target], 'dom_string_map')
            value = p.text('rv_dom_dom_string_map_named_item', [p.pointer, Utf8], dataset, b'kind')
            present = p.attribute(target, 'data-kind') is not None
            p.expect(present or value == '', name + ' missing dataset key reads as an empty string natively')
            members[name]['dataKind'] = value if present else None
        rejected = p.pointer(123)
        style_getter = p.bind('rv_dom_math_ml_element_get_style', p.integer, [p.pointer, ctypes.POINTER(p.pointer)])
        p.expect(style_getter(html, ctypes.byref(rejected)) == -11 and rejected.value == 123, 'HTML element is rejected by MathMLElement members')
        state['identity'], state['members'] = identity, members

        def rect(name):
            value = p.object('rv_dom_element_get_bounding_client_rect', [p.pointer], [n[name]], 'dom_rect_read_only')
            return [p.read('dom_rect_read_only', value, field, p.double) for field in ['x', 'y', 'width', 'height']]

        def style_map(name):
            return p.object('rv_dom_math_ml_element_get_attribute_style_map', [p.pointer], [n[name]], 'style_property_map_read_only')

        def set_typed(target_map, name, value=None, text=None):
            data = name.encode()
            if value is not None:
                item = StyleInput(1, 1, value, Span())
            else:
                encoded = ctypes.create_string_buffer(text.encode(), len(text.encode()))
                item = StyleInput(1, 2, None, Span(ctypes.cast(encoded, ctypes.c_void_p), len(text.encode())))
            items = (StyleInput * 1)(item)
            p.call('rv_dom_style_property_map_set', [p.pointer, p.pointer, ctypes.c_char_p, p.integer, ctypes.POINTER(StyleInputs)],
                   target_map, document, data, len(data), ctypes.byref(StyleInputs(1, 1, items)))

        layout = {}
        mi0, mo0, frac0, num0, den0, sqrt0, rad0 = (rect(name) for name in ['mi', 'mo', 'frac', 'num', 'den', 'sqrt', 'rad'])
        layout['initial'] = {'numAboveDen': num0[1] + num0[3] <= den0[1] + 0.5, 'fracTallerThanMi': frac0[3] > mi0[3],
                             'sqrtWiderThanRadicand': sqrt0[2] > rad0[2], 'moRightOfMi': mo0[0] >= mi0[0] + mi0[2] - 0.5}
        unit = b'px'
        pixels = p.object('rv_dom_css_unit_value_create', [p.pointer, ctypes.c_double, ctypes.c_char_p, p.integer], [document, 10.0, unit, len(unit)], 'css_style_value')
        mi_map = style_map('mi')
        set_typed(mi_map, 'padding-left', pixels)
        p.update()
        mo1 = rect('mo')
        layout['paddingShift'] = round((mo1[0] - mo0[0]) * 2) / 2
        class Maybe(ctypes.Structure):
            _fields_ = [('present', ctypes.c_int32), ('tag', ctypes.c_int32), ('undefined', ctypes.c_int32), ('value', ctypes.c_void_p)]
        maybe = Maybe()
        p.call('rv_dom_style_property_map_read_only_get', [p.pointer, p.pointer, ctypes.c_char_p, p.integer, ctypes.POINTER(Maybe)], mi_map, document, b'padding-left', 12, ctypes.byref(maybe))
        stored = maybe.value
        p.expect(bool(stored), 'typed padding is stored on the MathML attribute style map')
        layout['paddingTyped'] = [p.text('rv_dom_css_style_value_get_interface_name', [p.pointer], stored),
                                  p.read('css_unit_value', stored, 'value', p.double), p.text('rv_dom_css_unit_value_get_unit', [p.pointer], stored)]
        p.bind('rv_dom_union_undefined_or_css_style_value_release', None, [ctypes.POINTER(Maybe)])(ctypes.byref(maybe))
        math_style = p.object('rv_dom_math_ml_element_get_style', [p.pointer], [n['math']], 'css_style_declaration')
        p.call('rv_dom_css_style_declaration_set_property', [p.pointer, Utf8, Utf8, Utf8], math_style, b'font-size', b'40px', b'')
        p.update()
        mi2 = rect('mi')
        layout['fontScale'] = (mi2[2] - 10) / mi0[2]
        layout['fontScaleRange'] = 1.6 < layout['fontScale'] < 2.4
        set_typed(style_map('frac'), 'background-color', text='rgb(0, 0, 255)')
        frac2 = rect('frac')
        layout['fracBackground'] = p.pixel(p.paint(), int(frac2[0] + 1), int(frac2[1] + 1))
        p.call('rv_dom_css_style_declaration_set_property', [p.pointer, Utf8, Utf8, Utf8], math_style, b'math-style', b'compact', b'')
        p.update()
        layout['compactShrinksFraction'] = rect('frac')[3] < frac2[3]
        computed = p.object('rv_dom_window_get_computed_style', [p.pointer, p.pointer, p.pointer, p.integer], [document, n['frac'], None, -1], 'css_style_declaration')
        layout['mathStyle'] = p.text('rv_dom_css_style_declaration_get_property_value', [p.pointer, Utf8], computed, b'math-style')
        state['layout'] = layout

        focus = {'initialActive': active()}
        options = FocusOptions(ctypes.sizeof(FocusOptions), 1, None)
        p.call('rv_dom_math_ml_element_focus', [p.pointer, ctypes.POINTER(FocusOptions)], n['focusable'], ctypes.byref(options))
        focus['afterFocus'] = active()
        p.call('rv_dom_math_ml_element_focus', [p.pointer, p.pointer], n['plain'], None)
        focus['afterUnfocusable'] = active()
        p.call('rv_dom_math_ml_element_blur', [p.pointer], n['focusable'])
        focus['afterBlur'] = active()
        p.call('rv_dom_math_ml_element_set_tab_index', [p.pointer, ctypes.c_int32], n['plain'], 0)
        focus['plainTabIndex'] = p.attribute(n['plain'], 'tabindex')
        p.update()
        p.call('rv_dom_math_ml_element_focus', [p.pointer, p.pointer], n['plain'], None)
        focus['afterTabIndexFocus'] = active()
        p.call('rv_dom_math_ml_element_blur', [p.pointer], n['plain'])
        p.call('rv_dom_element_remove_attribute', [p.pointer, Utf8], n['plain'], b'tabindex')
        p.call('rv_dom_math_ml_element_set_autofocus', [p.pointer, ctypes.c_int32], n['focusable'], 0)
        focus['autofocusAttribute'] = p.attribute(n['focusable'], 'autofocus')
        p.call('rv_dom_math_ml_element_set_nonce', [p.pointer, Utf8], n['focusable'], b'changed')
        focus['nonceAfterSet'] = p.text('rv_dom_math_ml_element_get_nonce', [p.pointer], n['focusable'])
        focus['nonceAttributeAfterSet'] = p.attribute(n['focusable'], 'nonce')
        dataset = p.object('rv_dom_math_ml_element_get_dataset', [p.pointer], [n['math']], 'dom_string_map')
        p.call('rv_dom_dom_string_map_set_named_item', [p.pointer, Utf8, Utf8], dataset, b'newKey', 'value-λ'.encode())
        focus['datasetAttribute'] = p.attribute(n['math'], 'data-new-key')
        p.call('rv_dom_dom_string_map_delete_named_property', [p.pointer, Utf8], dataset, b'kind')
        focus['datasetDeleted'] = p.attribute(n['math'], 'data-kind')
        p.call('rv_dom_math_ml_element_focus', [p.pointer, p.pointer], n['focusable'], None)
        keyboard = p.bind('rv_host_key', p.integer, [p.pointer, p.integer, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, p.integer, p.integer])
        p.expect(keyboard(p.host, 0, b'Tab', b'Tab', b'', 0, 0) == 1, 'Tab handled by native focus traversal')
        focus['afterTab'] = active()
        state['focus'] = focus

        for section, want in oracle['state'].items():
            got = json.loads(json.dumps(state[section]))
            for field, value in want.items():
                key = section + '.' + field
                if key in oracle['nativeQualifications']:
                    p.expect(got[field] == oracle['nativeQualifications'][key], 'retained native qualification ' + key + ': ' + repr(got[field]))
                elif isinstance(value, float):
                    p.close([got[field]], [value], key + ' matches measured browser', 0.25)
                else:
                    p.expect(got[field] == value, key + ' matches measured browser: native ' + repr(got.get(field)) + ' browser ' + repr(value))

        for function in ['rv_dom_math_ml_element_get_dataset', 'rv_dom_math_ml_element_get_style', 'rv_dom_math_ml_element_get_attribute_style_map']:
            untouched = p.pointer(123)
            getter = p.bind(function, p.integer, [p.pointer, ctypes.POINTER(p.pointer)])
            p.expect(getter(None, ctypes.byref(untouched)) == -1 and untouched.value == 123, 'null rejection preserves output ' + function)
            statuses = []
            worker = threading.Thread(target=lambda: statuses.append(getter(n['mi'], ctypes.byref(untouched))))
            worker.start()
            worker.join()
            p.expect(statuses == [-2] and untouched.value == 123, 'off-thread rejection preserves output ' + function)
        buffer, length = ctypes.create_string_buffer(b'#', 1), ctypes.c_int32(77)
        status = p.bind('rv_dom_math_ml_element_get_nonce', p.integer, [p.pointer, p.pointer, p.integer, ctypes.POINTER(ctypes.c_int32)])(n['focusable'], buffer, 1, ctypes.byref(length))
        p.expect(status == -6 and length.value == 7 and buffer.raw == b'#', 'undersized nonce buffer reports the UTF-8 length and stays untouched')

        # Extra references held past host disposal; every other handle is released exactly once.
        kept_dataset = p.bind('rv_dom_dom_string_map_retain', p.pointer, [p.pointer])(dataset)
        kept_map = p.bind('rv_dom_style_property_map_read_only_retain', p.pointer, [p.pointer])(mi_map)
        p.expect(kept_dataset == dataset and kept_map == mi_map, 'retain returns the same dataset and style map handles')
        watches = [p.watch(owner) for owner in [n['math'], n['mi'], n['inline'], n['row']]]
        p.call('rv_node_remove', [p.pointer], n['math'])
        p.release_all()
        p.dispose_host()
        p.collect()
        alive = p.bind('rv_watch_alive', p.integer, [p.pointer])
        p.expect([alive(watch) for watch in watches] == [1, 1, 0, 1], 'a retained dataset keeps its removed MathML subtree alive after host disposal')
        p.expect(p.text('rv_dom_dom_string_map_named_item', [p.pointer, Utf8], kept_dataset, b'newKey') == 'value-λ', 'retained dataset reads after host disposal')
        p.bind('rv_dom_dom_string_map_release', None, [p.pointer])(kept_dataset)
        p.bind('rv_dom_style_property_map_read_only_release', None, [p.pointer])(kept_map)
        p.collect()
        p.expect_expired()
        print('MATHML_STATE ' + json.dumps(state, sort_keys=True), flush=True)
        print(f'PASS MathML surface: {p.assertions} assertions', flush=True)
        return p.assertions


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    verify(parser.parse_args().native_directory)
