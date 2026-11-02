"""An application-owned suggestion UI using actual native provider output."""

import argparse
import ctypes as C
import hashlib
import html
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe
from utf8_inputs import Utf8


def run(args):
    provider = json.loads(args.provider_result.read_text(encoding='utf-8'))
    if not provider['available']:
        print(json.dumps({'providerUnavailable': True}))
        return 77
    word = provider['word']
    chosen = next(value for value in provider['suggestions'] if value and value != word)
    original = '🙂 ' + word + ' suffix'
    start, length = provider['start'], provider['length']
    encoded = original.encode('utf-16-le')
    assert encoded[start * 2:(start + length) * 2].decode('utf-16-le') == word
    report = {'providerSha256': hashlib.sha256(args.provider_result.read_bytes()).hexdigest(), 'chosen': chosen,
              'nativeDirectory': str(args.native_directory), 'assertions': 0, 'cases': []}
    for mode in ['apply', 'cancelled', 'stale']:
        with SvgProbe(args.native_directory, 400, 160) as p:
            P, I, U, D = p.pointer, p.integer, p.unsigned, p.double
            markup = ('<style>body{margin:12px;font:18px Arial}#edit{border:1px solid black;height:36px;line-height:36px}'
                      '#suggest{appearance:none;border:0;margin-top:10px;padding:8px;font:18px Arial;background:#305af5;color:white}</style>'
                      '<div id="edit" contenteditable="true">' + html.escape(original) + '</div>'
                      '<button id="suggest">' + html.escape(chosen) + '</button>')
            p.load(markup, standalone=False)
            p.call('rv_host_set_focused', [P, I], p.host, 1)
            editor, button = p.node('edit'), p.node('suggest')
            p.call('rv_element_focus', [P], editor)
            document = p.object('rv_dom_node_get_owner_document', [P], [editor], 'node')
            text_node = p.object('rv_dom_node_get_first_child', [P], [editor], 'node')
            target = p.object('rv_dom_document_create_range', [P], [document], 'abstract_range')
            p.call('rv_dom_range_set_start', [P, P, U], target, text_node, start)
            p.call('rv_dom_range_set_end', [P, P, U], target, text_node, start + length)
            p.expect(p.text('rv_dom_node_get_text_content', [P], button) == chosen, 'actual OS suggestion is the displayed label')
            x, y, width, height = D(), D(), D(), D()
            p.call('rv_element_rect', [P, C.POINTER(D), C.POINTER(D), C.POINTER(D), C.POINTER(D)], button,
                   C.byref(x), C.byref(y), C.byref(width), C.byref(height))
            p.expect(width.value > 0 and height.value > 0, 'suggestion has native rendered geometry')
            rgba = bytes(p.paint())
            pixels = [rgba[(py * 400 + px) * 4:(py * 400 + px) * 4 + 4]
                      for py in range(max(0, int(y.value)), min(160, int(y.value + height.value)))
                      for px in range(max(0, int(x.value)), min(400, int(x.value + width.value)))]
            p.expect(sum(value[:3] == bytes([48, 90, 245]) for value in pixels) > 100, 'suggestion background is painted')
            p.expect(sum(value[:3] == bytes([255, 255, 255]) for value in pixels) > 2, 'suggestion text is painted')
            actions, errors, callbacks, listeners = [], [], [], []
            callback_type = C.CFUNCTYPE(I, P, P)

            def listen(event_name, action):
                @callback_type
                def callback(_, event):
                    try:
                        action(event)
                        return 0
                    except BaseException as failure:
                        errors.append(repr(failure))
                        return 1
                callbacks.append(callback)
                listener = p.bind('rv_node_add_event_listener', P, [P, Utf8, I, callback_type, P])(button, event_name.encode(), 0, callback, None)
                p.expect(bool(listener), 'native suggestion input listener')
                listeners.append(listener)

            def apply(_):
                current = p.text('rv_dom_node_get_text_content', [P], editor)
                if mode == 'cancelled':
                    actions.append('cancelled')
                elif current != original:
                    actions.append('stale')
                else:
                    actions.append(p.bind('rv_host_replace_range', I, [P, P, Utf8])(p.host, target, chosen.encode()))

            listen('mousedown', lambda event: p.bind('rv_event_prevent_default', None, [P])(event))
            listen('click', apply)
            if mode == 'stale':
                p.call('rv_dom_character_data_set_data', [P, Utf8], text_node, '🙂 revised suffix'.encode())
            try:
                mouse = p.bind('rv_host_mouse', I, [P, I, I, I, I, I, I])
                px, py = int(x.value + width.value / 2), int(y.value + height.value / 2)
                for action, button_code, clicks in [(0, -1, 0), (1, 0, 1), (2, 0, 1)]:
                    p.expect(mouse(p.host, action, px, py, button_code, clicks, 0) >= 0, 'trusted native mouse action')
                p.expect(not errors, 'suggestion callbacks succeed: ' + str(errors))
                current = p.text('rv_dom_node_get_text_content', [P], editor)
                history = p.bind('rv_host_edit', I, [P, I])
                if mode == 'apply':
                    p.expect(actions == [1] and current == '🙂 ' + chosen + ' suffix', 'native click applies exact OS-selected range')
                    p.expect(history(p.host, 6) == 1 and p.text('rv_dom_node_get_text_content', [P], editor) == original,
                             'suggestion remains a single undoable edit')
                    p.expect(history(p.host, 7) == 1 and p.text('rv_dom_node_get_text_content', [P], editor) == current,
                             'suggestion remains redoable')
                else:
                    p.expect(actions == [mode], 'application declines cancelled/stale result')
                    p.expect(current == ('🙂 revised suffix' if mode == 'stale' else original), 'declined suggestion preserves current text')
                    p.expect(history(p.host, 6) == 0, 'declined result adds no history')
                report['cases'].append({'mode': mode, 'actions': actions, 'frameSha256': hashlib.sha256(rgba).hexdigest(),
                                        'suggestionBounds': [value.value for value in [x, y, width, height]]})
            finally:
                for listener in listeners:
                    p.call('rv_listener_remove', [P], listener)
            report['assertions'] += p.assertions
    temporary = args.report.with_suffix('.tmp')
    temporary.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    temporary.replace(args.report)
    print(json.dumps(report))
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', type=Path, required=True)
    parser.add_argument('--provider-result', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    raise SystemExit(run(parser.parse_args()))
