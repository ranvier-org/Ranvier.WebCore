"""Native editor undo/redo through the host's existing editing boundary."""

import argparse
import ctypes
from pathlib import Path
import sys
import threading
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe
from utf8_inputs import Utf8


def run(directory):
    with SvgProbe(directory, 320, 160) as p:
        P, I = p.pointer, p.integer
        edit = p.bind('rv_host_edit', I, [P, I])
        commit = p.bind('rv_host_ime_commit', I, [P, Utf8])
        p.load('<input id="edit" value="abc">', standalone=False)
        node = p.node('edit')
        p.call('rv_host_set_focused', [P, I], p.host, 1)
        p.call('rv_element_focus', [P], node)
        p.expect(edit(p.host, 4) == 1, 'select existing text')
        p.expect(commit(p.host, b'changed') == 0, 'native user edit')
        value = lambda: p.text('rv_node_get_string', [P, I], node, 6)
        p.expect(value() == 'changed', 'edit replaces selection')
        p.expect(edit(p.host, 6) == 1, 'undo is handled')
        p.expect(value() == 'abc', 'undo restores previous text')
        p.expect(edit(p.host, 7) == 1, 'redo is handled')
        p.expect(value() == 'changed', 'redo restores edited text')
        callback_type = ctypes.CFUNCTYPE(I, P, P)
        prevent = p.bind('rv_event_prevent_default', None, [P])
        blocked = []

        @callback_type
        def cancel(context, event):
            blocked.append(True)
            prevent(event)
            return 0

        listen = p.bind('rv_node_add_event_listener', P, [P, Utf8, I, callback_type, P])
        listener = listen(node, b'beforeinput', 0, cancel, None)
        p.expect(bool(listener), 'beforeinput cancellation listener')
        p.expect(edit(p.host, 6) == 1, 'canceled undo command is consumed')
        p.expect(blocked and value() == 'changed', 'beforeinput cancels undo mutation')
        p.call('rv_listener_remove', [P], listener)
        p.expect(edit(p.host, 6) == 1, 'undo can repeat')
        p.expect(value() == 'abc', 'canceled undo retained its transaction')
        p.expect(edit(p.host, 6) == 0, 'empty undo history is explicit')
        p.expect(commit(p.host, b'new') == 0, 'new edit after undo')
        p.expect(edit(p.host, 7) == 0, 'new edit invalidates redo')
        p.load('<input id="new" value="fresh">', standalone=False)
        p.expect(edit(p.host, 6) == 0, 'document replacement clears undo')
        p.expect(edit(p.host, 7) == 0, 'document replacement clears redo')
        p.expect(edit(None, 6) == -1, 'null host rejected')
        off_thread = []
        worker = threading.Thread(target=lambda: off_thread.append(edit(p.host, 6)))
        worker.start()
        worker.join()
        p.expect(off_thread == [-2], 'wrong thread rejected')
        node = p.node('new')
        p.call('rv_element_focus', [P], node)
        p.expect(edit(p.host, 4) == 1, 'select replacement document text')
        p.expect(commit(p.host, b'keyboard') == 0, 'edit for keyboard undo')
        key = p.bind('rv_host_key', I, [P, I, ctypes.c_char_p, ctypes.c_char_p, Utf8, I, I])
        p.expect(key(p.host, 0, b'z', b'KeyZ', b'', 2, 0) == 1, 'Ctrl+Z routed to native history')
        p.expect(value() == 'fresh', 'Ctrl+Z restores text')
        p.expect(key(p.host, 0, b'z', b'KeyZ', b'', 3, 0) == 1, 'Ctrl+Shift+Z routed to redo')
        p.expect(value() == 'keyboard', 'keyboard redo restores text')
        has = p.bind('rv_abi_has', I, [ctypes.c_char_p])
        p.expect(has(b'editing-undo') == 1, 'undo capability advertised')
        print(f'Native editing undo: {p.assertions} assertions PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('native_directory', nargs='?')
    parser.add_argument('--native-directory', dest='native_option')
    args = parser.parse_args()
    directory = args.native_option or args.native_directory
    if not directory:
        parser.error('native directory required')
    run(directory)
    callback = Path(__file__).with_name('editing_undo_callback.py')
    cases = [(scenario, operation) for scenario in ['newedit', 'replace', 'destroy'] for operation in ['undo', 'redo']]
    cases.append(('destroy', 'commit'))
    for scenario, operation in cases:
        subprocess.run([sys.executable, '-I', str(callback), directory, scenario, operation], check=True, timeout=30)
    print('Native editing: 7 isolated callback cases PASS')
