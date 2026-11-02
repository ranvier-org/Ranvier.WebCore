"""A prevented composition rollback keeps focus and ends on its original control."""

import argparse
import ctypes as C
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import CALLBACK, Case, Native, P, I
from utf8_inputs import Utf8


def main(directory):
    native = Native(directory)
    page = Case(native, '<input id="first" value="abc"><input id="second" value="other">')
    try:
        first, second = page.node('first'), page.node('second')
        native.ok('rv_host_set_focused', [P, I], page.host, 1)
        native.ok('rv_element_focus', [P], first)
        ended = []
        handlers = []
        for node, label in ((first, 'first'), (second, 'second')):
            handler = CALLBACK(lambda _context, _event, label=label: ended.append(label) or 0)
            handlers.append(handler)
            listener = native.bind('rv_node_add_event_listener', P, [P, Utf8, I, CALLBACK, P])(
                node, b'compositionend', 0, handler, None)
            native.expect(bool(listener), 'compositionend listener')
            page.listeners.append(listener)

        def on_beforeinput(_context, event):
            if native.text('rv_dom_input_event_get_input_type', [P], event) == 'historyUndo':
                native.ok('rv_element_focus', [P], second)
                native.ok('rv_dom_event_prevent_default', [P], event)
            return 0

        before = CALLBACK(on_beforeinput)
        listener = native.bind('rv_node_add_event_listener', P, [P, Utf8, I, CALLBACK, P])(
            first, b'beforeinput', 0, before, None)
        native.expect(bool(listener), 'beforeinput listener')
        page.listeners.append(listener)
        native.ok('rv_text_set_selection', [P, I, I], first, 1, 2)
        native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, 'かな'.encode(), 2, 2)
        native.ok('rv_host_ime_cancel', [P], page.host)
        active = native.bind('rv_document_active_element', P, [P])(page.host)
        try:
            same = I()
            native.ok('rv_dom_node_is_same_node', [P, P, C.POINTER(I)], active, second, C.byref(same))
            native.expect(same.value == 1, 'prevented undo keeps application focus')
        finally:
            native.bind('rv_node_release', None, [P])(active)
        native.expect(native.text('rv_dom_html_input_element_get_value', [P], first) == 'aかなc', 'prevented undo preserves the composition text')
        native.expect(ended == ['first'], f'compositionend targets the original control exactly once, got {ended!r}')
    finally:
        page.close()
    print('PASS prevented IME rollback and focus')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    main(parser.parse_args().native_directory)
