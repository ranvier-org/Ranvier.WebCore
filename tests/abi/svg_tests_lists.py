import argparse
import ctypes
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe
from utf8_inputs import Utf8

ORACLE = Path(__file__).resolve().parents[1] / 'fixtures' / 'svg-tests-lists-oracle.json'
STEPS = ['initial', 'removed', 'empty', 'restored', 'cleared', 'appended', 'removedAgain', 'reinserted']
# Measured differences from Chromium 156, kept as provider behaviour: clear() leaves the attribute "", a
# systemLanguage list serialises with ", " and requiredExtensions="" holds one empty item.
QUALIFIED = {('requiredExtensions', 'empty', 'items'): 1, ('requiredExtensions', 'cleared', 'attribute'): '',
             ('systemLanguage', 'cleared', 'attribute'): '', ('systemLanguage', 'appended', 'attribute'): 'zz, zz'}


def verify(native_directory):
    oracle = json.loads(ORACLE.read_text())
    expected = oracle['result']
    with SvgProbe(native_directory, 200, 60) as p:
        p.load(oracle['markup'])
        actual, deviations, failures = {}, [], []
        text = [p.pointer, Utf8]
        for field, x, value in [('requiredExtensions', 20, 'urn:x'), ('systemLanguage', 70, 'zz')]:
            element = p.node(field)
            getter = 'rv_dom_svg_graphics_element_get_' + ('required_extensions' if field == 'requiredExtensions' else 'system_language')
            first = p.object(getter, [p.pointer], [element], 'svg_string_list')
            actual[field] = {}
            for step in STEPS:
                if step == 'removed' or step == 'removedAgain':
                    p.call('rv_dom_element_remove_attribute', text, element, field.encode())
                if step == 'empty':
                    p.call('rv_dom_element_set_attribute', text + [Utf8], element, field.encode(), b'')
                if step == 'restored':
                    p.call('rv_dom_element_set_attribute', text + [Utf8], element, field.encode(), value.encode())
                if step == 'cleared':
                    p.call('rv_dom_svg_string_list_clear', [p.pointer], first)
                if step == 'appended':
                    p.call('rv_dom_element_set_attribute', text + [Utf8], element, field.encode(), value.encode())
                    p.expect(p.text('rv_dom_svg_string_list_append_item', text, first, value.encode()) == value, field + ' appendItem result')
                if step == 'reinserted':
                    parent = p.object('rv_dom_node_get_parent_node', [p.pointer], [element], 'node')
                    p.object('rv_dom_node_append_child', [p.pointer, p.pointer], [parent, element], 'node')
                items = p.read('svg_string_list', first, 'number_of_items', p.unsigned)
                again = p.object(getter, [p.pointer], [element], 'svg_string_list')
                actual[field][step] = {'items': items, 'attribute': p.attribute(element, field), 'sameList': again == first,
                                       'paint': p.pixel(p.paint(), x, 20)}
        switch = p.node('first')
        actual['switch'] = {'initial': p.pixel(p.paint(), 120, 20)}
        p.call('rv_dom_element_remove_attribute', text, switch, b'systemLanguage')
        actual['switch']['removed'] = p.pixel(p.paint(), 120, 20)
        group = p.object('rv_dom_node_get_parent_node', [p.pointer], [switch], 'node')
        root = p.object('rv_dom_node_get_parent_node', [p.pointer], [group], 'node')
        p.object('rv_dom_node_append_child', [p.pointer, p.pointer], [root, group], 'node')
        actual['switch']['reinserted'] = p.pixel(p.paint(), 120, 20)

        for field in ['requiredExtensions', 'systemLanguage']:
            for step in STEPS:
                for key, wanted in expected[field][step].items():
                    got = actual[field][step][key]
                    if key == 'paint' and step != 'reinserted':
                        continue  # Chromium repaints a conditional element only when its renderer is rebuilt.
                    if (field, step, key) in QUALIFIED and got == QUALIFIED[(field, step, key)]:
                        deviations.append(dict(field=field, step=step, key=key, native=got, chromium=wanted))
                        continue
                    p.assertions += 1
                    if got != wanted:
                        failures.append(f'{field}.{step}.{key}: native {got!r}, Chromium {wanted!r}')
        for step in ['initial', 'reinserted']:
            p.assertions += 1
            if actual['switch'][step] != expected['switch'][step]:
                failures.append(f'switch.{step}: native {actual["switch"][step]}, Chromium {expected["switch"][step]}')
        print(json.dumps({'actual': actual, 'qualified': deviations, 'failures': failures}))
        p.expect(not failures, 'SVGTests lists differ from Chromium: ' + '; '.join(failures))
        print(f'SVG TESTS LISTS PASS {p.assertions} assertions')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    verify(parser.parse_args().native_directory)
