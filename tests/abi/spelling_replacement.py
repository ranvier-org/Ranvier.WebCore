"""Native spelling action over the existing renderer range-edit boundary."""

import argparse
import ctypes as C
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe
from utf8_inputs import Utf8

CASES = ['exact-undo', 'cancel', 'stale-document', 'composition', 'callback-replace', 'callback-replace-newedit', 'callback-destroy']


def exercise(directory, scenario, replacement):
    if sys.platform == 'win32':
        C.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
    with SvgProbe(directory, 400, 140) as p:
        P, I, U = p.pointer, p.integer, p.unsigned
        p.load('<div id="edit" contenteditable="true">🙂 speling suffix</div>', standalone=False)
        edit = p.node('edit')
        document = p.object('rv_dom_node_get_owner_document', [P], [edit], 'node')
        p.call('rv_host_set_focused', [P, I], p.host, 1)
        p.call('rv_element_focus', [P], edit)
        p.update()
        listeners, roots, callback_errors = [], [], []
        callback_type = C.CFUNCTYPE(I, P, P)

        def text():
            return p.text('rv_dom_node_get_text_content', [P], edit)

        def make_range(start=3, end=10):
            node = p.object('rv_dom_node_get_first_child', [P], [edit], 'node')
            value = p.object('rv_dom_document_create_range', [P], [document], 'abstract_range')
            p.call('rv_dom_range_set_start', [P, P, U], value, node, start)
            p.call('rv_dom_range_set_end', [P, P, U], value, node, end)
            return value

        def on(name, action):
            @callback_type
            def callback(_, event):
                try:
                    action(event)
                    return 0
                except BaseException as error:
                    callback_errors.append(repr(error))
                    return 1

            value = p.bind('rv_node_add_event_listener', P, [P, Utf8, I, callback_type, P])(edit, name.encode(), 0, callback, None)
            p.expect(bool(value), name + ' listener installed')
            listeners.append(value)
            roots.append(callback)

        replace = p.bind('rv_host_replace_range', I, [P, P, Utf8])
        history = p.bind('rv_host_edit', I, [P, I])
        original = text()
        chosen = replacement.encode()
        try:
            target = make_range()
            if scenario == 'exact-undo':
                p.expect(replace(p.host, target, chosen) == 1, 'range correction applied')
                p.expect(text() == '🙂 ' + replacement + ' suffix', 'UTF-16 range preserves surrogate prefix and suffix')
                p.expect(history(p.host, 6) == 1 and text() == original, 'one undo restores original misspelling')
                p.expect(history(p.host, 7) == 1 and text() == '🙂 ' + replacement + ' suffix', 'redo restores correction')
            elif scenario == 'cancel':
                events = []
                def cancel(event):
                    events.append('beforeinput')
                    p.bind('rv_event_prevent_default', None, [P])(event)
                on('beforeinput', cancel)
                on('input', lambda _: events.append('input'))
                p.expect(replace(p.host, target, chosen) == 0, 'cancelled correction returns unapplied')
                p.expect(text() == original and events == ['beforeinput'], 'cancelled correction preserves text')
                p.expect(history(p.host, 6) == 0, 'cancelled correction creates no undo record')
            elif scenario == 'stale-document':
                p.load('<div id="fresh" contenteditable="true">fresh</div>', standalone=False)
                p.expect(replace(p.host, target, chosen) == -12, 'old-document correction rejected')
                fresh = p.node('fresh')
                p.expect(p.text('rv_dom_node_get_text_content', [P], fresh) == 'fresh', 'new document remains intact')
            elif scenario == 'composition':
                selection = p.object('rv_dom_document_get_selection', [P], [document], 'dom_selection')
                p.call('rv_dom_dom_selection_remove_all_ranges', [P], selection)
                p.call('rv_dom_dom_selection_add_range', [P, P], selection, target)
                ended = []
                on('compositionend', lambda _: ended.append(True))
                compose = p.bind('rv_host_ime_set_composition', I, [P, Utf8, I, I])
                p.expect(compose(p.host, b'spel', 4, 4) == 0, 'native IME preedit starts')
                before = text()
                p.expect(before == '🙂 spel suffix' and not ended, 'real composition text is present')
                target = make_range(3, 7)
                status = replace(p.host, target, chosen)
                print(json.dumps({'diagnostic': scenario, 'status': status, 'before': before, 'after': text(), 'compositionEnds': len(ended)}), flush=True)
                p.expect(status == -9, 'active composition declines spelling correction')
                p.expect(text() == before and not ended, 'declined spelling does not commit or cancel IME')
                commit = p.bind('rv_host_ime_commit', I, [P, Utf8])
                p.expect(commit(p.host, b'speling') == 0 and len(ended) == 1, 'original composition remains committable')
                p.expect(replace(p.host, make_range(), chosen) == 1, 'correction applies after composition ends')
            else:
                entered = []
                def action(_):
                    if entered:
                        return
                    entered.append(True)
                    if scenario.startswith('callback-replace'):
                        p.load('<div id="fresh" contenteditable="true">fresh</div>', standalone=False)
                        if scenario == 'callback-replace-newedit':
                            fresh = p.node('fresh')
                            p.call('rv_element_focus', [P], fresh)
                            p.expect(history(p.host, 4) == 1, 'select new document text')
                            p.call('rv_host_ime_commit', [P, Utf8], p.host, b'new typed text')
                    else:
                        print(json.dumps({'diagnostic': scenario, 'point': 'before host destruction'}), flush=True)
                        original_host, p.host = p.host, None
                        p.bind('rv_host_destroy', None, [P])(original_host)
                on('beforeinput', action)
                status = replace(p.host, target, chosen)
                p.expect(status >= 0 and entered == [True], 'range callback returns safely')
                if scenario.startswith('callback-replace'):
                    fresh = p.node('fresh')
                    expected = 'new typed text' if scenario.endswith('newedit') else 'fresh'
                    p.expect(p.text('rv_dom_node_get_text_content', [P], fresh) == expected, 'replacement callback keeps new document intact')
                    undo = history(p.host, 6)
                    after_undo = p.text('rv_dom_node_get_text_content', [P], fresh)
                    print(json.dumps({'diagnostic': scenario, 'outerStatus': status, 'undo': undo, 'afterUndo': after_undo}), flush=True)
                    if scenario.endswith('newedit'):
                        p.expect(undo == 1 and after_undo == 'fresh', 'new-document edit remains undoable')
                        p.expect(history(p.host, 6) == 0, 'old-document step not inserted before new-document history')
                        p.expect(history(p.host, 7) == 1 and p.text('rv_dom_node_get_text_content', [P], fresh) == expected,
                                 'new-document edit remains redoable')
                    else:
                        redo = history(p.host, 7)
                        print(json.dumps({'diagnostic': scenario, 'redo': redo}), flush=True)
                        p.expect(undo == 0 and redo == 0, 'no old-document history after replacement')
                else:
                    p.expect(p.host is None, 'host destruction returned after range callback')
            p.expect(not callback_errors, 'native callbacks completed without hidden Python failures: ' + str(callback_errors))
            result = {'case': scenario, 'passed': True}
        finally:
            for listener in listeners:
                p.call('rv_listener_remove', [P], listener)
        result['assertions'] = p.assertions
        return result


def run(arguments):
    if arguments.case:
        print(json.dumps(exercise(arguments.native_directory, arguments.case, arguments.replacement)))
        return 0
    rows = []
    for scenario in CASES:
        command = [sys.executable, '-I', '-B', '-X', 'utf8', str(Path(__file__).resolve()), '--native-directory', str(arguments.native_directory),
                   '--case', scenario, '--replacement', arguments.replacement]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
        rows.append({'case': scenario, 'exit': result.returncode, 'output': result.stdout.decode(errors='replace')})
    report = {'cases': rows, 'failed': sum(row['exit'] != 0 for row in rows)}
    if arguments.report:
        temporary = arguments.report.with_suffix('.tmp')
        temporary.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        temporary.replace(arguments.report)
    print(json.dumps(report, indent=2))
    return int(bool(report['failed']))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--case', choices=CASES)
    parser.add_argument('--replacement', default='spelling')
    raise SystemExit(run(parser.parse_args()))
