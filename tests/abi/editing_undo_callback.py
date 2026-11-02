"""Runs an editor callback lifetime case in its own native process."""

import argparse
import ctypes
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe
from utf8_inputs import Utf8


def run(directory, scenario, operation):
    if sys.platform == 'win32':
        ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
    with SvgProbe(directory, 320, 160) as p:
        P, I = p.pointer, p.integer
        edit = p.bind('rv_host_edit', I, [P, I])
        commit = p.bind('rv_host_ime_commit', I, [P, Utf8])
        p.load('<input id="edit" value="abc">', standalone=False)
        node = p.node('edit')
        p.call('rv_host_set_focused', [P, I], p.host, 1)
        p.call('rv_element_focus', [P], node)
        p.expect(edit(p.host, 4) == 1, 'select text')
        p.expect(commit(p.host, b'changed') == 0, 'initial edit')
        if operation == 'redo':
            p.expect(edit(p.host, 6) == 1, 'prepare redo')
        callback_type = ctypes.CFUNCTYPE(I, P, P)
        entered, nested = [], []

        @callback_type
        def callback(context, event):
            if entered:
                return 0
            entered.append(True)
            if scenario == 'newedit':
                nested.append(commit(p.host, b'nested'))
            elif scenario == 'replace':
                load = p.bind('rv_host_load_html', I, [P, Utf8])
                nested.append(load(p.host, b'<input id="replacement" value="fresh">'))
            else:
                original, p.host = p.host, None
                p.bind('rv_host_destroy', None, [P])(original)
                nested.append(0)
            return 0

        listen = p.bind('rv_node_add_event_listener', P, [P, Utf8, I, callback_type, P])
        listener = listen(node, b'beforeinput', 0, callback, None)
        p.expect(bool(listener), 'beforeinput callback installed')
        if operation == 'commit':
            status = commit(p.host, b'control')
        else:
            status = edit(p.host, 6 if operation == 'undo' else 7)
        p.expect(status >= 0 and entered, 'outer operation returned after callback')
        p.call('rv_listener_remove', [P], listener)
        if scenario == 'newedit':
            p.expect(nested == [-9], 'nested editing during history replay rejected')
        elif scenario == 'replace':
            p.expect(nested == [0], 'replacement completed')
            replacement = p.node('replacement')
            p.expect(p.text('rv_node_get_string', [P, I], replacement, 6) == 'fresh', 'replacement text preserved')
            p.expect(edit(p.host, 6) == 0, 'no stale undo after replacement callback')
            p.expect(edit(p.host, 7) == 0, 'no stale redo after replacement callback')
        else:
            p.expect(p.host is None and nested == [0], 'deferred host destruction returned safely')
        print(f'Native editing {operation}/{scenario}: {p.assertions} assertions PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('native_directory')
    parser.add_argument('scenario', choices=['newedit', 'replace', 'destroy'])
    parser.add_argument('operation', choices=['undo', 'redo', 'commit'])
    args = parser.parse_args()
    run(args.native_directory, args.scenario, args.operation)
