"""Cancel restores rich content and the original nodes and listeners."""

import argparse
import ctypes as C
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import CALLBACK, Case, Native, P, I
from utf8_inputs import Utf8


def main(directory):
    native = Native(directory)
    page = Case(native, '<div id="editor" contenteditable="true"><span>ab</span><span id="kept">cd</span></div>')
    try:
        editor, kept = page.node('editor'), page.node('kept')
        native.ok('rv_host_set_focused', [P, I], page.host, 1)
        native.ok('rv_element_focus', [P], editor)
        clicks, ends = [], []
        on_click = CALLBACK(lambda _context, _event: clicks.append(1) or 0)
        on_end = CALLBACK(lambda _context, _event: ends.append(native.text('rv_dom_element_get_inner_html', [P], editor)) or 0)
        listen = native.bind('rv_node_add_event_listener', P, [P, Utf8, I, CALLBACK, P])
        for node, name, handler in ((kept, b'click', on_click), (editor, b'compositionend', on_end)):
            listener = listen(node, name, 0, handler, None)
            native.expect(bool(listener), 'listener')
            page.listeners.append(listener)
        native.expect(native.call('rv_host_edit', [P, I], page.host, 4) == 1, 'select rich content')
        native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, 'かな'.encode(), 2, 2)
        native.expect(native.integer('rv_dom_node_get_is_connected', kept) == 0, 'preedit detached the selected node')
        native.ok('rv_host_ime_cancel', [P], page.host)
        expected = '<span>ab</span><span id="kept">cd</span>'
        native.expect(ends == [expected], 'compositionend observes restored markup')
        current = native.bind('rv_document_get_element_by_id', P, [P, Utf8])(page.host, b'kept')
        native.expect(bool(current), 'original node is connected again')
        try:
            same = I()
            native.ok('rv_dom_node_is_same_node', [P, P, C.POINTER(I)], current, kept, C.byref(same))
            native.expect(same.value == 1, 'undo restores the same node')
        finally:
            native.bind('rv_node_release', None, [P])(current)
        native.ok('rv_element_click', [P], kept)
        native.expect(clicks == [1], 'original node listener still works')
        native.expect(native.call('rv_host_edit', [P, I], page.host, 7) == 0, 'cancelled composition is not redoable')
    finally:
        page.close()
    print('PASS rich IME cancellation')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    main(parser.parse_args().native_directory)
