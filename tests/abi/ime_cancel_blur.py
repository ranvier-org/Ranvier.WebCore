"""A blur and a later cancel end the original composition at most once."""

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
        ends, handlers = [], []
        listen = native.bind('rv_node_add_event_listener', P, [P, Utf8, I, CALLBACK, P])
        for node, label in ((first, 'first'), (second, 'second')):
            callback = CALLBACK(lambda _context, _event, label=label: ends.append(label) or 0)
            handlers.append(callback)
            listener = listen(node, b'compositionend', 0, callback, None)
            native.expect(bool(listener), 'compositionend listener')
            page.listeners.append(listener)
        native.ok('rv_text_set_selection', [P, I, I], first, 1, 2)
        native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, 'かな'.encode(), 2, 2)
        native.ok('rv_element_focus', [P], second)
        native.expect(len(ends) <= 1, 'blur does not duplicate compositionend')
        native.ok('rv_host_ime_cancel', [P], page.host)
        native.ok('rv_host_ime_cancel', [P], page.host)
        native.expect(ends == ['first'], f'only the original control ends once, got {ends!r}')
        active = native.bind('rv_document_active_element', P, [P])(page.host)
        try:
            same = I()
            native.ok('rv_dom_node_is_same_node', [P, P, C.POINTER(I)], active, second, C.byref(same))
            native.expect(same.value == 1, 'later cancel preserves focus')
        finally:
            native.bind('rv_node_release', None, [P])(active)
    finally:
        page.close()
    print('PASS IME blur terminal event')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    main(parser.parse_args().native_directory)
