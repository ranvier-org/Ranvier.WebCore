"""An application node inserted by a preedit listener is not undone by cancellation."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import CALLBACK, Case, Native, P, I
from utf8_inputs import Utf8


def main(directory):
    native = Native(directory)
    page = Case(native, '<div id="editor" contenteditable="true"><span>ab</span><span>cd</span></div>')
    try:
        editor = page.node('editor')
        native.ok('rv_host_set_focused', [P, I], page.host, 1)
        native.ok('rv_element_focus', [P], editor)
        inserted, ends, errors = [], [], []
        def on_input(_context, event):
            try:
                if not inserted and native.text('rv_dom_input_event_get_input_type', [P], event) == 'insertCompositionText':
                    node = native.bind('rv_document_create_element', P, [P, Utf8])(page.host, b'b')
                    native.expect(bool(node), 'created application node')
                    page.owned.append(node)
                    native.ok('rv_dom_node_set_text_content', [P, Utf8], node, b'APP')
                    native.ok('rv_node_append_child', [P, P], editor, node)
                    inserted.append(node)
            except Exception as error:
                errors.append(str(error))
            return 0
        on_edit = CALLBACK(on_input)
        on_end = CALLBACK(lambda _context, _event: ends.append(1) or 0)
        listen = native.bind('rv_node_add_event_listener', P, [P, Utf8, I, CALLBACK, P])
        for name, callback in ((b'input', on_edit), (b'compositionend', on_end)):
            listener = listen(editor, name, 0, callback, None)
            native.expect(bool(listener), 'listener')
            page.listeners.append(listener)
        native.expect(native.call('rv_host_edit', [P, I], page.host, 4) == 1, 'select rich content')
        native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, 'かな'.encode(), 2, 2)
        native.expect(not errors and len(inserted) == 1, f'application inserted node: {errors!r}')
        native.ok('rv_host_ime_cancel', [P], page.host)
        native.expect(native.integer('rv_dom_node_get_is_connected', inserted[0]) == 1, 'application node remains connected')
        native.expect(native.text('rv_dom_node_get_text_content', [P], inserted[0]) == 'APP', 'application node content survives')
        native.expect(ends == [1], f'composition ends exactly once, got {ends!r}')
    finally:
        page.close()
    print('PASS reentrant IME DOM edit')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    main(parser.parse_args().native_directory)
