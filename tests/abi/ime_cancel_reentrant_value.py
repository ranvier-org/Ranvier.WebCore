"""An application edit during preedit survives and composition ends once."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import CALLBACK, Case, Native, P, I
from utf8_inputs import Utf8


def main(directory):
    native = Native(directory)
    page = Case(native, '<input id="field" value="abc">')
    try:
        field = page.node('field')
        native.ok('rv_host_set_focused', [P, I], page.host, 1)
        native.ok('rv_element_focus', [P], field)
        ended = []
        nested = []
        def on_input(_context, event):
            if native.text('rv_dom_input_event_get_input_type', [P], event) == 'insertCompositionText':
                native.ok('rv_dom_html_input_element_set_value', [P, Utf8], field, b'APP')
            return 0
        def end(_context, _event):
            ended.append(native.text('rv_dom_html_input_element_get_value', [P], field))
            nested.append(native.call('rv_host_ime_cancel', [P], page.host))
            return 0
        on_end = CALLBACK(end)
        on_edit = CALLBACK(on_input)
        listen = native.bind('rv_node_add_event_listener', P, [P, Utf8, I, CALLBACK, P])
        for name, handler in ((b'input', on_edit), (b'compositionend', on_end)):
            listener = listen(field, name, 0, handler, None)
            native.expect(bool(listener), 'listener')
            page.listeners.append(listener)
        native.ok('rv_text_set_selection', [P, I, I], field, 1, 2)
        native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, 'かな'.encode(), 2, 2)
        native.ok('rv_host_ime_cancel', [P], page.host)
        native.expect(native.text('rv_dom_html_input_element_get_value', [P], field) == 'APP', 'application edit survives cancellation')
        native.expect(ended == ['APP'], f'original control observes one end with application text, got {ended!r}')
        native.expect(nested == [0], 'reentrant cancellation is handled without a second end')
        native.ok('rv_host_ime_cancel', [P], page.host)
        native.expect(ended == ['APP'], 'repeated cancellation does not end twice')
    finally:
        page.close()
    print('PASS IME cancellation after application edit')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    main(parser.parse_args().native_directory)
