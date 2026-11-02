"""Deletion against a specific input-method surrounding-text snapshot."""

import argparse
import ctypes as C
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import CALLBACK, Case, Native, P, I, U
from ime_surrounding import snapshot_with_token
from utf8_inputs import Utf8


def run(directory):
    native = Native(directory)
    delete = native.bind('rv_host_ime_delete_surrounding', I, [P, C.c_uint64, I, I])
    page = Case(native, '<input id="field" value="A😀BC">')
    try:
        field = page.node('field')
        native.ok('rv_dom_html_element_focus', [P, P], field, None)
        native.ok('rv_dom_html_input_element_set_selection_range', [P, U, U, Utf8], field, 3, 3, b'forward')
        value, token = snapshot_with_token(native, page.host)
        native.expect(value == ('A😀BC', 3, 3) and token != 0, 'snapshot and token')
        native.expect(snapshot_with_token(native, page.host)[1] == token, 'unchanged state retains its token')
        other = Case(native, '<input id="other" value="other">')
        try:
            native.ok('rv_dom_html_element_focus', [P, P], other.node('other'), None)
            _, other_token = snapshot_with_token(native, other.host)
            native.expect(other_token and other_token != token, 'tokens distinguish hosts')
            native.expect(delete(other.host, token, 0, 1) == -10, 'another host cannot consume the token')
        finally:
            other.close()
        native.expect(delete(page.host, token, 2, 3) == -9, 'surrogate split is rejected')
        native.expect(delete(page.host, token, 1, 3) == 1, 'delete complete supplementary scalar')
        native.expect(native.text('rv_dom_html_input_element_get_value', [P], field) == 'ABC', 'deletion edits the value')
        native.expect(delete(page.host, token, 0, 1) == -10, 'consumed token is rejected')
        native.expect(native.call('rv_host_edit', [P, I], page.host, 6) == 1, 'surrounding deletion is undoable')
        native.expect(native.text('rv_dom_html_input_element_get_value', [P], field) == 'A😀BC', 'undo restores deleted text')

        native.ok('rv_dom_html_input_element_set_value', [P, Utf8], field, 'A😀BC'.encode())
        native.ok('rv_dom_html_input_element_set_selection_range', [P, U, U, Utf8], field, 3, 4, b'forward')
        native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, 'か'.encode(), 1, 1)
        value, token = snapshot_with_token(native, page.host)
        native.expect(value == ('A😀BC', 4, 3) and token != 0, 'active snapshot and token')
        native.expect(delete(page.host, token, 1, 3) == 1, 'delete before active preedit')
        selection_start, selection_end, present_start, present_end = U(), U(), I(), I()
        native.ok('rv_dom_html_input_element_get_selection_start', [P, C.POINTER(U), C.POINTER(I)], field, C.byref(selection_start), C.byref(present_start))
        native.ok('rv_dom_html_input_element_get_selection_end', [P, C.POINTER(U), C.POINTER(I)], field, C.byref(selection_end), C.byref(present_end))
        native.expect((present_start.value, present_end.value, selection_start.value, selection_end.value) == (1, 1, 2, 2),
                      'active composition caret follows the deletion')
        after_delete, _ = snapshot_with_token(native, page.host)
        native.expect(after_delete == ('ABC', 2, 1), f'active context reflects the completed surrounding deletion: {after_delete!r}')
        native.ok('rv_host_ime_commit', [P, Utf8], page.host, '仮'.encode())
        committed = native.text('rv_dom_html_input_element_get_value', [P], field)
        native.expect(committed == 'A仮C', f'deletion preserves the active preedit for commit: {committed!r}, snapshot={after_delete!r}')

        native.ok('rv_dom_html_input_element_set_value', [P, Utf8], field, b'abc')
        native.ok('rv_dom_html_input_element_set_selection_range', [P, U, U, Utf8], field, 1, 2, b'backward')
        _, token = snapshot_with_token(native, page.host)
        native.ok('rv_dom_html_input_element_set_selection_range', [P, U, U, Utf8], field, 0, 0, b'forward')
        native.expect(delete(page.host, token, 0, 1) == -10, 'selection change rejects queued delete')

        native.ok('rv_dom_html_input_element_set_selection_range', [P, U, U, Utf8], field, 1, 2, b'backward')
        _, token = snapshot_with_token(native, page.host)
        def cancel(_context, event):
            native.bind('rv_event_prevent_default', None, [P])(event)
            return 0
        callback = CALLBACK(cancel)
        listener = native.bind('rv_node_add_event_listener', P, [P, Utf8, I, CALLBACK, P])(field, b'beforeinput', 0, callback, None)
        native.expect(bool(listener), 'beforeinput listener')
        page.listeners.append(listener)
        native.expect(delete(page.host, token, 0, 1) == 0, 'application may cancel deletion')
        native.expect(native.text('rv_dom_html_input_element_get_value', [P], field) == 'abc', 'cancel preserves application text')
        value, _ = snapshot_with_token(native, page.host)
        native.expect(value == ('abc', 1, 2), f'cancel preserves backwards selection: {value!r}')
    finally:
        page.close()
    page = Case(native, '<input id="field" value="A😀BC">')
    try:
        field = page.node('field')
        native.ok('rv_dom_html_element_focus', [P, P], field, None)
        native.ok('rv_dom_html_input_element_set_selection_range', [P, U, U, Utf8], field, 3, 4, b'forward')
        native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, 'か'.encode(), 1, 1)
        _, token = snapshot_with_token(native, page.host)
        native.expect(delete(page.host, token, 1, 3) == 1, 'delete before selected preedit')
        native.ok('rv_host_ime_cancel', [P], page.host)
        current = native.text('rv_dom_html_input_element_get_value', [P], field)
        native.expect(current == 'ABC', f'cancel restores selection while keeping surrounding deletion: {current!r}')
    finally:
        page.close()
    page = Case(native, '<input id="field" value="A😀BC">')
    try:
        field = page.node('field')
        native.ok('rv_dom_html_element_focus', [P, P], field, None)
        native.ok('rv_dom_html_input_element_set_selection_range', [P, U, U, Utf8], field, 3, 4, b'forward')
        native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, 'かな'.encode(), 2, 2)
        _, token = snapshot_with_token(native, page.host)
        native.expect(delete(page.host, token, 4, 5) == 1, 'delete after longer selected preedit')
        native.ok('rv_host_ime_cancel', [P], page.host)
        native.expect(native.text('rv_dom_html_input_element_get_value', [P], field) == 'A😀B',
                      'cancel keeps the later surrounding deletion')
        native.expect(native.call('rv_host_edit', [P, I], page.host, 6) == 1, 'undo later surrounding deletion')
        native.expect(native.text('rv_dom_html_input_element_get_value', [P], field) == 'A😀BC',
                      'undo restores the correct later text')
        native.expect(native.call('rv_host_edit', [P, I], page.host, 7) == 1, 'redo later surrounding deletion')
        native.expect(native.text('rv_dom_html_input_element_get_value', [P], field) == 'A😀B',
                      'redo removes the correct later text')
    finally:
        page.close()
    page = Case(native, '<input id="field" value="A😀BC">')
    try:
        field = page.node('field')
        native.ok('rv_dom_html_element_focus', [P, P], field, None)
        native.ok('rv_dom_html_input_element_set_selection_range', [P, U, U, Utf8], field, 3, 4, b'forward')
        native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, 'か'.encode(), 1, 1)
        _, first = snapshot_with_token(native, page.host)
        native.expect(delete(page.host, first, 1, 3) == 1, 'first surrounding deletion')
        value, second = snapshot_with_token(native, page.host)
        native.expect(value == ('ABC', 2, 1) and second != first, 'deletion issues updated context and token')
        native.expect(delete(page.host, first, 0, 1) == -10, 'old token cannot delete again')
        native.expect(delete(page.host, second, 0, 1) == 1, 'second surrounding deletion')
        native.ok('rv_host_ime_cancel', [P], page.host)
        current = native.text('rv_dom_html_input_element_get_value', [P], field)
        native.expect(current == 'BC', f'cancel preserves both owned surrounding deletions: {current!r}')
    finally:
        page.close()
    page = Case(native, '<input id="field" value="A😀BC">')
    try:
        field = page.node('field')
        native.ok('rv_dom_html_element_focus', [P, P], field, None)
        native.ok('rv_dom_html_input_element_set_selection_range', [P, U, U, Utf8], field, 3, 4, b'forward')
        native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, 'か'.encode(), 1, 1)
        _, token = snapshot_with_token(native, page.host)
        native.expect(delete(page.host, token, 1, 3) == 1, 'first deletion before rollback veto')
        _, token = snapshot_with_token(native, page.host)
        native.expect(delete(page.host, token, 0, 1) == 1, 'second deletion before rollback veto')
        events = []
        def veto_second(_context, event):
            kind = native.text('rv_dom_input_event_get_input_type', [P], event)
            if kind in ('historyUndo', 'historyRedo'):
                events.append(kind)
                if events == ['historyUndo']:
                    native.bind('rv_event_prevent_default', None, [P])(event)
            return 0
        callback = CALLBACK(veto_second)
        listener = native.bind('rv_node_add_event_listener', P, [P, Utf8, I, CALLBACK, P])(field, b'beforeinput', 0, callback, None)
        native.expect(bool(listener), 'multiple-deletion veto listener')
        page.listeners.append(listener)
        native.ok('rv_host_ime_cancel', [P], page.host)
        current = native.text('rv_dom_html_input_element_get_value', [P], field)
        native.expect(current == 'かC' and events == ['historyUndo'],
                      f'veto preserves both accepted deletions: {current!r}, {events}')
    finally:
        page.close()
    page = Case(native, '<input id="field" value="abc">')
    try:
        field = page.node('field')
        native.ok('rv_host_set_focused', [P, I], page.host, 1)
        native.ok('rv_dom_html_element_focus', [P, P], field, None)
        native.ok('rv_dom_html_input_element_set_selection_range', [P, U, U, Utf8], field, 3, 3, b'forward')
        native.expect(native.call('rv_host_key', [P, I, C.c_char_p, C.c_char_p, Utf8, I, I],
                                  page.host, 2, b'x', b'KeyX', b'x', 0, 0) > 0, 'prior user edit')
        native.ok('rv_dom_html_input_element_set_selection_range', [P, U, U, Utf8], field, 1, 2, b'forward')
        native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, 'か'.encode(), 1, 1)
        _, token = snapshot_with_token(native, page.host)
        native.expect(delete(page.host, token, 0, 1) == 1, 'delete before selected preedit with earlier edit')
        native.ok('rv_host_ime_cancel', [P], page.host)
        native.expect(native.text('rv_dom_html_input_element_get_value', [P], field) == 'bcx', 'earlier edit survives cancellation')
        native.expect(native.call('rv_host_edit', [P, I], page.host, 6) == 1, 'undo surrounding deletion')
        native.expect(native.text('rv_dom_html_input_element_get_value', [P], field) == 'abcx', 'first undo restores surrounding text')
        native.expect(native.call('rv_host_edit', [P, I], page.host, 6) == 1, 'undo earlier user edit')
        native.expect(native.text('rv_dom_html_input_element_get_value', [P], field) == 'abc', 'earlier user edit remains independently undoable')
    finally:
        page.close()
    for veto in ('undo', 'redo'):
        page = Case(native, '<input id="field" value="A😀BC">')
        try:
            field = page.node('field')
            native.ok('rv_dom_html_element_focus', [P, P], field, None)
            native.ok('rv_dom_html_input_element_set_selection_range', [P, U, U, Utf8], field, 3, 4, b'forward')
            native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, 'か'.encode(), 1, 1)
            _, token = snapshot_with_token(native, page.host)
            native.expect(delete(page.host, token, 1, 3) == 1, 'setup surrounding deletion')
            events, ends = [], []
            def on_beforeinput(_context, event):
                kind = native.text('rv_dom_input_event_get_input_type', [P], event)
                if kind in ('historyUndo', 'historyRedo'):
                    events.append(kind)
                    if (veto == 'undo' and kind == 'historyUndo') or (veto == 'redo' and kind == 'historyRedo'):
                        native.bind('rv_event_prevent_default', None, [P])(event)
                return 0
            on_before = CALLBACK(on_beforeinput)
            on_end = CALLBACK(lambda _context, _event: ends.append('end') or 0)
            listen = native.bind('rv_node_add_event_listener', P, [P, Utf8, I, CALLBACK, P])
            for name, handler in ((b'beforeinput', on_before), (b'compositionend', on_end)):
                listener = listen(field, name, 0, handler, None)
                native.expect(bool(listener), 'history veto listener')
                page.listeners.append(listener)
            native.ok('rv_host_ime_cancel', [P], page.host)
            current = native.text('rv_dom_html_input_element_get_value', [P], field)
            expected = 'AかC' if veto == 'undo' else 'ABC'
            native.expect(current == expected and events == ['historyUndo'] and ends == ['end'],
                          f'{veto} preserves accepted deletion and ends once: {current!r}, {events}, {ends}')
        finally:
            page.close()
    for action in ('value', 'focus', 'replace', 'destroy'):
        page = Case(native, '<input id="field" value="A😀BC"><input id="other" value="keep">')
        destroyed = False
        try:
            field, host = page.node('field'), page.host
            native.ok('rv_dom_html_element_focus', [P, P], field, None)
            native.ok('rv_dom_html_input_element_set_selection_range', [P, U, U, Utf8], field, 3, 4, b'forward')
            native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], host, 'か'.encode(), 1, 1)
            _, token = snapshot_with_token(native, host)
            native.expect(delete(host, token, 1, 3) == 1, 'setup reentrant history')
            callbacks, ends, errors = [], [], []
            def change_during_undo(_context, event):
                nonlocal destroyed
                try:
                    if native.text('rv_dom_input_event_get_input_type', [P], event) == 'historyUndo' and not callbacks:
                        callbacks.append(action)
                        if action == 'value':
                            native.ok('rv_dom_html_input_element_set_value', [P, Utf8], field, b'APP')
                        elif action == 'focus':
                            native.ok('rv_dom_html_element_focus', [P, P], page.node('other'), None)
                        elif action == 'replace':
                            native.ok('rv_host_load_html', [P, Utf8], host, b'<p id="replacement">new</p>')
                        else:
                            native.bind('rv_host_destroy', None, [P])(host)
                            destroyed = True
                        native.bind('rv_event_prevent_default', None, [P])(event)
                except Exception as error:
                    errors.append(str(error))
                return 0
            on_before = CALLBACK(change_during_undo)
            on_end = CALLBACK(lambda _context, _event: ends.append('end') or 0)
            listen = native.bind('rv_node_add_event_listener', P, [P, Utf8, I, CALLBACK, P])
            for name, handler in ((b'beforeinput', on_before), (b'compositionend', on_end)):
                listener = listen(field, name, 0, handler, None)
                native.expect(bool(listener), 'reentrant history listener')
                page.listeners.append(listener)
            native.ok('rv_host_ime_cancel', [P], host)
            native.expect(callbacks == [action] and not errors, f'reentrant history callback: {callbacks}, {errors}')
            if action == 'value':
                native.expect(native.text('rv_dom_html_input_element_get_value', [P], field) == 'APP' and ends == ['end'],
                              'application value survives cancelled rollback and ends once')
            elif action == 'focus':
                active = native.handle('rv_dom_document_get_active_element', [P], page.document)
                try:
                    native.expect(active == page.node('other') and ends == ['end'], 'application focus survives rollback and old target ends once')
                finally:
                    native.bind('rv_node_release', None, [P])(active)
            elif action == 'replace':
                replacement = native.bind('rv_document_get_element_by_id', P, [P, Utf8])(host, b'replacement')
                native.expect(bool(replacement) and not ends, 'replacement document survives without a late event')
                native.bind('rv_node_release', None, [P])(replacement)
            else:
                native.expect(destroyed and not ends, 'destroyed host receives no late event')
        finally:
            if not destroyed:
                page.close()
    page = Case(native, '<input id="field" value="abc">')
    try:
        field = page.node('field')
        native.ok('rv_dom_html_element_focus', [P, P], field, None)
        native.ok('rv_dom_html_input_element_set_selection_range', [P, U, U, Utf8], field, 1, 2, b'backward')
        _, token = snapshot_with_token(native, page.host)
        def change_selection(_context, event):
            native.ok('rv_dom_html_input_element_set_selection_range', [P, U, U, Utf8], field, 3, 3, b'forward')
            native.ok('rv_dom_event_prevent_default', [P], event)
            return 0
        callback = CALLBACK(change_selection)
        listener = native.bind('rv_node_add_event_listener', P, [P, Utf8, I, CALLBACK, P])(field, b'beforeinput', 0, callback, None)
        native.expect(bool(listener), 'selection-changing callback')
        page.listeners.append(listener)
        native.expect(delete(page.host, token, 0, 1) == 0, 'selection-changing cancellation is not applied')
        current, _ = snapshot_with_token(native, page.host)
        native.expect(current == ('abc', 3, 3), f'application selection survives: {current!r}')
    finally:
        page.close()
    page = Case(native, '<input id="field" value="A😀BC">')
    try:
        field = page.node('field')
        native.ok('rv_dom_html_element_focus', [P, P], field, None)
        native.ok('rv_dom_html_input_element_set_selection_range', [P, U, U, Utf8], field, 3, 4, b'forward')
        native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, 'か'.encode(), 1, 1)
        _, token = snapshot_with_token(native, page.host)
        callback = CALLBACK(lambda _context, event: native.call('rv_dom_event_prevent_default', [P], event))
        listener = native.bind('rv_node_add_event_listener', P, [P, Utf8, I, CALLBACK, P])(field, b'beforeinput', 0, callback, None)
        native.expect(bool(listener), 'active beforeinput listener')
        ends = []
        on_end = CALLBACK(lambda _context, _event: ends.append('end') or 0)
        end_listener = native.bind('rv_node_add_event_listener', P, [P, Utf8, I, CALLBACK, P])(field, b'compositionend', 0, on_end, None)
        native.expect(bool(end_listener), 'active compositionend listener')
        page.listeners.append(end_listener)
        native.expect(delete(page.host, token, 1, 3) == 2, 'active deletion cancellation ends the owned composition')
        native.expect(ends == ['end'], 'blocked deletion ends the composition once')
        native.call('rv_listener_remove', [P], listener)
        native.expect(native.text('rv_dom_html_input_element_get_value', [P], field) == 'A😀かC',
                      'application-blocked rollback preserves its preedit text')
    finally:
        page.close()
    page = Case(native, '<input id="field" value="A😀BC"><input id="other" value="keep">')
    try:
        field, other = page.node('field'), page.node('other')
        native.ok('rv_dom_html_element_focus', [P, P], field, None)
        native.ok('rv_dom_html_input_element_set_selection_range', [P, U, U, Utf8], field, 3, 4, b'forward')
        native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, 'か'.encode(), 1, 1)
        _, token = snapshot_with_token(native, page.host)
        ends = []
        armed = [True]
        def change_focus(_context, event):
            if armed[0]:
                native.ok('rv_dom_html_element_focus', [P, P], other, None)
                native.ok('rv_dom_event_prevent_default', [P], event)
            return 0
        on_before = CALLBACK(change_focus)
        on_end = CALLBACK(lambda _context, _event: ends.append('field') or 0)
        listen = native.bind('rv_node_add_event_listener', P, [P, Utf8, I, CALLBACK, P])
        for name, handler in ((b'beforeinput', on_before), (b'compositionend', on_end)):
            listener = listen(field, name, 0, handler, None)
            native.expect(bool(listener), 'focus lifecycle listener')
            page.listeners.append(listener)
        native.expect(delete(page.host, token, 1, 3) == 2, 'focus-changing cancellation ends the original composition')
        active = native.handle('rv_dom_document_get_active_element', [P], page.document)
        try:
            native.expect(active == other, 'application focus survives deletion callback')
            native.expect(ends == ['field'], f'original target receives one terminal event: {ends!r}')
        finally:
            native.bind('rv_node_release', None, [P])(active)
        armed[0] = False
        native.ok('rv_dom_html_element_focus', [P, P], field, None)
        native.ok('rv_dom_html_input_element_set_value', [P, Utf8], field, 'A😀BC'.encode())
        native.ok('rv_dom_html_input_element_set_selection_range', [P, U, U, Utf8], field, 3, 3, b'forward')
        native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, 'か'.encode(), 1, 1)
        _, token = snapshot_with_token(native, page.host)
        armed[0] = True
        native.expect(delete(page.host, token, 1, 3) == 2, 'focus-changing cancellation ends the original caret preedit')
        active = native.handle('rv_dom_document_get_active_element', [P], page.document)
        try:
            native.expect(active == other and ends == ['field', 'field'],
                          f'caret preedit ends at its original target and preserves focus: {ends!r}')
        finally:
            native.bind('rv_node_release', None, [P])(active)
    finally:
        page.close()
    page = Case(native, '<div id="rich" contenteditable>前<br><span id="middle">😀中</span><div>後</div></div>')
    owned = []
    try:
        rich, middle = page.node('rich'), page.node('middle')
        native.ok('rv_dom_html_element_focus', [P, P], rich, None)
        child = native.handle('rv_dom_node_get_first_child', [P], middle)
        selection = native.handle('rv_dom_document_get_selection', [P], page.document)
        owned.extend((('rv_node_release', child), ('rv_dom_dom_selection_release', selection)))
        native.ok('rv_dom_dom_selection_set_base_and_extent', [P, P, U, P, U], selection, child, 2, child, 2)
        value, token = snapshot_with_token(native, page.host)
        native.expect(value == ('前\n😀中\n後', 4, 4), 'rich snapshot uses editing text')
        native.expect(delete(page.host, token, 2, 4) == 1, 'delete supplementary scalar from rich content')
        current, _ = snapshot_with_token(native, page.host)
        native.expect(current[0] == '前\n中\n後', 'rich deletion uses editing text boundaries')
        same = native.bind('rv_document_get_element_by_id', P, [P, Utf8])(page.host, b'middle')
        owned.append(('rv_node_release', same))
        native.expect(same == middle, 'rich element identity survives deletion')
    finally:
        for release, value in reversed(owned): native.bind(release, None, [P])(value)
        page.close()
    page = Case(native, '<div id="rich" contenteditable>A<span id="middle">😀B</span>C</div>')
    owned = []
    try:
        rich, middle = page.node('rich'), page.node('middle')
        native.ok('rv_dom_html_element_focus', [P, P], rich, None)
        clicks = []
        on_click = CALLBACK(lambda _context, _event: clicks.append('click') or 0)
        listener = native.bind('rv_node_add_event_listener', P, [P, Utf8, I, CALLBACK, P])(middle, b'click', 0, on_click, None)
        native.expect(bool(listener), 'rich node listener')
        page.listeners.append(listener)
        child = native.handle('rv_dom_node_get_first_child', [P], middle)
        selection = native.handle('rv_dom_document_get_selection', [P], page.document)
        owned.extend((('rv_node_release', child), ('rv_dom_dom_selection_release', selection)))
        native.ok('rv_dom_dom_selection_set_base_and_extent', [P, P, U, P, U], selection, child, 2, child, 3)
        native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, 'か'.encode(), 1, 1)
        _, token = snapshot_with_token(native, page.host)
        native.expect(delete(page.host, token, 1, 3) == 1, 'delete before rich selected preedit')
        native.ok('rv_host_ime_cancel', [P], page.host)
        current, _ = snapshot_with_token(native, page.host)
        same = native.bind('rv_document_get_element_by_id', P, [P, Utf8])(page.host, b'middle')
        owned.append(('rv_node_release', same))
        native.expect(isinstance(current, tuple) and current[0] == 'ABC' and same == middle,
                      f'rich cancel retains original element and surrounding deletion: {current!r}')
        native.call('rv_element_click', [P], middle)
        native.expect(clicks == ['click'], 'original rich node retains its listener')
    finally:
        for release, value in reversed(owned): native.bind(release, None, [P])(value)
        page.close()
    for action in ('replace', 'destroy'):
        page = Case(native, '<input id="field" value="abc">')
        destroyed = False
        try:
            field, host = page.node('field'), page.host
            native.ok('rv_dom_html_element_focus', [P, P], field, None)
            native.ok('rv_dom_html_input_element_set_selection_range', [P, U, U, Utf8], field, 2, 2, b'forward')
            _, token = snapshot_with_token(native, host)
            errors, callbacks = [], []
            def on_beforeinput(_context, _event):
                nonlocal destroyed
                try:
                    callbacks.append(action)
                    if action == 'replace':
                        native.ok('rv_host_load_html', [P, Utf8], host, b'<p id="replacement">new</p>')
                    else:
                        native.bind('rv_host_destroy', None, [P])(host)
                        destroyed = True
                except Exception as error:
                    errors.append(str(error))
                return 0
            callback = CALLBACK(on_beforeinput)
            listener = native.bind('rv_node_add_event_listener', P, [P, Utf8, I, CALLBACK, P])(field, b'beforeinput', 0, callback, None)
            native.expect(bool(listener), 'lifecycle listener')
            page.listeners.append(listener)
            result = delete(host, token, 0, 1)
            native.expect(result <= 0 and callbacks == [action] and not errors,
                          f'{action} during beforeinput remains safe: {result}, {callbacks}, {errors}')
            if action == 'replace':
                replacement = native.bind('rv_document_get_element_by_id', P, [P, Utf8])(host, b'replacement')
                native.expect(bool(replacement), 'replacement document survives deletion callback')
                native.bind('rv_node_release', None, [P])(replacement)
        finally:
            if not destroyed:
                page.close()
    print('PASS IME delete surrounding')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    run(parser.parse_args().native_directory)
