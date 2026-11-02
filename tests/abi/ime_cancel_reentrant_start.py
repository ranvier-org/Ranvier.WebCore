"""A composition started by the previous composition's end remains owned."""

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
        ends, nested, errors = [], [], []
        def on_end(_context, _event):
            try:
                ends.append(native.text('rv_dom_html_input_element_get_value', [P], field))
                if len(ends) == 1:
                    nested.append(native.call('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, '字'.encode(), 1, 1))
            except Exception as error:
                errors.append(str(error))
            return 0
        callback = CALLBACK(on_end)
        listener = native.bind('rv_node_add_event_listener', P, [P, Utf8, I, CALLBACK, P])(
            field, b'compositionend', 0, callback, None)
        native.expect(bool(listener), 'compositionend listener')
        page.listeners.append(listener)
        native.ok('rv_text_set_selection', [P, I, I], field, 1, 2)
        native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, 'かな'.encode(), 2, 2)
        native.ok('rv_host_ime_cancel', [P], page.host)
        native.expect(not errors and nested == [0], f'new composition starts during end: {errors}, {nested}')
        native.expect(ends == ['abc'], 'first end sees restored selection')
        native.expect(native.text('rv_dom_html_input_element_get_value', [P], field) == 'a字c', 'new preedit remains active')
        native.ok('rv_host_ime_cancel', [P], page.host)
        native.expect(ends == ['abc', 'abc'], 'second composition restores and ends once')
    finally:
        page.close()
    print('PASS reentrant IME composition start')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    main(parser.parse_args().native_directory)
