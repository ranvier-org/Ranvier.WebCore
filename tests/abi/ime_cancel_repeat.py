"""Ending one IME composition does not end it again or suppress the next one."""

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
        ends = []
        handler = CALLBACK(lambda _context, _event: ends.append(native.text('rv_dom_html_input_element_get_value', [P], field)) or 0)
        listener = native.bind('rv_node_add_event_listener', P, [P, Utf8, I, CALLBACK, P])(
            field, b'compositionend', 0, handler, None)
        native.expect(bool(listener), 'compositionend listener')
        page.listeners.append(listener)
        native.ok('rv_text_set_selection', [P, I, I], field, 1, 2)
        native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, 'かな'.encode(), 2, 2)
        native.ok('rv_host_ime_commit', [P, Utf8], page.host, '字'.encode())
        native.expect(ends == ['a字c'], 'commit ends the first composition once')
        native.ok('rv_host_ime_cancel', [P], page.host)
        native.expect(ends == ['a字c'], 'cancel after commit does not end it again')
        native.ok('rv_text_set_selection', [P, I, I], field, 1, 2)
        native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, 'か'.encode(), 1, 1)
        native.ok('rv_host_ime_cancel', [P], page.host)
        native.expect(ends == ['a字c', 'a字c'], 'a later composition ends independently')
        native.ok('rv_host_ime_cancel', [P], page.host)
        native.expect(len(ends) == 2, 'repeated cancel is a no-op')
    finally:
        page.close()
    print('PASS IME terminal event ownership')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    main(parser.parse_args().native_directory)
