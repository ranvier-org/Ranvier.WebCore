"""Selected text survives cancellation of an input method composition."""

import argparse
import ctypes as C
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import CALLBACK, Case, Native, P, I
from utf8_inputs import Utf8


def main(directory, clear, synthetic):
    native = Native(directory)
    page = Case(native, '<input id="field" value="前中後"><span id="sibling"></span>')
    try:
        field = page.node('field')
        ended_values = []
        on_end = CALLBACK(lambda _context, _event: ended_values.append(
            native.text('rv_dom_html_input_element_get_value', [P], field)) or 0)
        listener = native.bind('rv_node_add_event_listener', P, [P, Utf8, I, CALLBACK, P])(
            field, b'compositionend', 0, on_end, None)
        native.expect(bool(listener), 'compositionend listener')
        page.listeners.append(listener)
        native.ok('rv_dom_html_element_focus', [P, P], field, None)
        native.ok('rv_text_set_selection', [P, I, I], field, 1, 2)
        native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, 'かな'.encode(), 2, 2)
        native.expect(native.text('rv_dom_html_input_element_get_value', [P], field) == '前かな後', 'preedit replaces selected text')
        if synthetic:
            prevented = I()
            event_type = b'compositionend'
            native.ok('rv_node_dispatch_event', [P, C.c_char_p, I, I, I, C.POINTER(I)],
                      field, event_type, len(event_type), 1, 0, C.byref(prevented))
        native.ok('rv_element_set_attribute', [P, C.c_char_p, Utf8], page.node('sibling'), b'title', b'unrelated')
        if clear:
            native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, b'', 0, 0)
        else:
            native.ok('rv_host_ime_cancel', [P], page.host)
        value = native.text('rv_dom_html_input_element_get_value', [P], field)
        start, end = I(), I()
        native.ok('rv_text_selection', [P, C.POINTER(I), C.POINTER(I)], field, C.byref(start), C.byref(end))
        native.ok('rv_host_ime_cancel', [P], page.host)
        expected_events = ['前かな後', '前中後'] if synthetic else ['前中後']
        native.expect(ended_values == expected_events, f'compositionend observes restored text once; got {ended_values!r}')
        native.expect((value, start.value, end.value) == ('前中後', 1, 2),
                      f'cancellation restores value and selection; got {value!r}, {start.value}, {end.value}')
    finally:
        page.close()
    print('PASS selected-text IME cancellation')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--clear', action='store_true')
    parser.add_argument('--synthetic', action='store_true')
    args = parser.parse_args()
    main(args.native_directory, args.clear, args.synthetic)
