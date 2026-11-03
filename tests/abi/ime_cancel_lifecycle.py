"""Exercise cancellation callbacks that replace or destroy their host."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import CALLBACK, Case, Native, P, I
from utf8_inputs import Utf8


def main(directory, action):
    native = Native(directory)
    page = Case(native, '<input id="field" value="abc">')
    destroyed = False
    try:
        field = page.node('field')
        native.ok('rv_host_set_focused', [P, I], page.host, 1)
        native.ok('rv_element_focus', [P], field)
        callbacks = []
        ends = []
        errors = []
        host = page.host

        def on_beforeinput(_context, event):
            nonlocal destroyed
            try:
                if native.text('rv_dom_input_event_get_input_type', [P], event) == 'historyUndo':
                    if action == 'replace':
                        native.ok('rv_host_load_html', [P, Utf8], host, b'<p id="replacement">new</p>')
                    elif action == 'destroy':
                        native.bind('rv_host_destroy', None, [P])(host)
                        destroyed = True
            except Exception as error:
                errors.append(str(error))
            return 0

        before = CALLBACK(on_beforeinput)
        on_end = CALLBACK(lambda _context, _event: ends.append('end') or 0)
        callbacks.extend((before, on_end))
        listen = native.bind('rv_node_add_event_listener', P, [P, Utf8, I, CALLBACK, P])
        for name, handler in ((b'beforeinput', before), (b'compositionend', on_end)):
            listener = listen(field, name, 0, handler, None)
            native.expect(bool(listener), 'listener')
            page.listeners.append(listener)
        native.ok('rv_text_set_selection', [P, I, I], field, 1, 2)
        native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], host, 'かな'.encode(), 2, 2)
        status = native.call('rv_host_ime_cancel', [P], host)
        native.expect(status >= 0, f'cancel status {status}')
        native.expect(not errors, f'callback errors: {errors}')
        if action == 'replace':
            replacement = native.bind('rv_document_get_element_by_id', P, [P, Utf8])(host, b'replacement')
            native.expect(bool(replacement), 'new document survives rollback callback')
            native.bind('rv_node_release', None, [P])(replacement)
            native.expect(ends == [], 'old document receives no late compositionend after replacement')
        else:
            native.expect(destroyed and ends == [], 'destroy callback has no late compositionend')
    finally:
        if not destroyed:
            page.close()
    print('PASS IME cancellation lifecycle ' + action)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--action', choices=('replace', 'destroy'), required=True)
    args = parser.parse_args()
    main(args.native_directory, args.action)
