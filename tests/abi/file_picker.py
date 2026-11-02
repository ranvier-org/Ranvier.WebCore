"""Native file-control requests and their original control's completion."""

import argparse
import ctypes as C
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import Case, Native, P, I, OK, CALLBACK
from utf8_inputs import Utf8

U64 = C.c_uint64
PICKER = C.CFUNCTYPE(None, P, U64, I, I)


def main(directory):
    n = Native(directory)
    n.expect(n.call('rv_abi_has', [C.c_char_p], b'file-picker') == 1, 'file picker capability')
    page = Case(n, '<input id="first" type="file" multiple accept=".txt,image/png" style="position:absolute;left:0;top:0;width:100px;height:40px"><input id="second" type="file" style="position:absolute;left:0;top:60px;width:100px;height:40px">')
    requests = []
    events = []
    callback = PICKER(lambda context, request, action, flags: requests.append((request, action, flags)))
    try:
        n.expect(n.call('rv_host_file_picker_available', [P], page.host) == 0, 'provider is initially unavailable')
        n.ok('rv_host_set_file_picker_handler', [P, PICKER, P], page.host, callback, None)
        n.expect(n.call('rv_host_file_picker_available', [P], page.host) == 1, 'attached provider is available')
        first, second = page.node('first'), page.node('second')
        handlers = []
        for kind in ('input', 'change', 'cancel'):
            handler = CALLBACK(lambda _, event, kind=kind: events.append(kind) or 0)
            handlers.append(handler)
            listener = n.bind('rv_node_add_event_listener', P, [P, Utf8, I, CALLBACK, P])(first, kind.encode(), 0, handler, None)
            n.expect(bool(listener), kind + ' listener')
            page.listeners.append(listener)

        def click_first():
            for action in (0, 1, 2):
                n.expect(n.call('rv_host_mouse', [P, I, I, I, I, I, I], page.host, action, 20, 20, 0, 1, 0) >= 0, 'trusted pointer input')

        click_first()
        n.expect(len(requests) == 1 and requests[0][1] == 0, 'first file control opens one request')
        request = requests[0][0]
        n.expect(requests[0][2] & 1, 'multiple selection is reported')
        n.expect(n.text('rv_host_file_picker_filter', [P, U64, I, I], page.host, request, 1, 0) == '.txt', 'extension filter')
        n.expect(n.text('rv_host_file_picker_filter', [P, U64, I, I], page.host, request, 0, 0) == 'image/png', 'MIME filter')
        n.ok('rv_dom_html_element_focus', [P, P], second, None)
        with tempfile.TemporaryDirectory(prefix='ranvier-picker-') as directory:
            selected = Path(directory, 'one.txt')
            selected.write_text('picker fixture', encoding='utf-8')
            path = str(selected).encode()
            paths = (C.c_char_p * 1)(path)
            lengths = (I * 1)(len(path))
            n.ok('rv_host_file_picker_complete', [P, U64, I, C.POINTER(C.c_char_p), C.POINTER(I), I],
                 page.host, request, 1, paths, lengths, 1)
            one = n.handle('rv_dom_html_input_element_get_files', [P], first, nullable=False)
            two = n.handle('rv_dom_html_input_element_get_files', [P], second, nullable=False)
            try:
                n.expect(n.integer('rv_dom_file_list_get_length', one, C.c_uint32) == 1, 'selected file reaches original control')
                n.expect(n.integer('rv_dom_file_list_get_length', two, C.c_uint32) == 0, 'other control stays unchanged')
                item = n.handle('rv_dom_file_list_item', [P, C.c_uint32], one, 0, nullable=False)
                try:
                    n.expect(n.text('rv_dom_file_get_name', [P], item) == 'one.txt', 'selected file name')
                    n.expect(n.integer('rv_dom_blob_get_size', item, C.c_uint64) == len('picker fixture'), 'selected file size')
                finally:
                    n.bind('rv_dom_blob_release', None, [P])(item)
            finally:
                n.bind('rv_dom_file_list_release', None, [P])(one)
                n.bind('rv_dom_file_list_release', None, [P])(two)
        n.expect(events == ['input', 'change'], 'native selection emits input and change')
        n.expect(n.call('rv_host_file_picker_complete', [P, U64, I, C.POINTER(C.c_char_p), C.POINTER(I), I],
                        page.host, request, 0, None, None, 0) < 0, 'duplicate completion is rejected')
        events.clear()
        click_first()
        canceled = requests[-1][0]
        relative = b'relative.txt'
        relative_paths = (C.c_char_p * 1)(relative)
        relative_lengths = (I * 1)(len(relative))
        n.expect(n.call('rv_host_file_picker_complete', [P, U64, I, C.POINTER(C.c_char_p), C.POINTER(I), I],
                        page.host, canceled, 1, relative_paths, relative_lengths, 1) < 0, 'relative paths are rejected')
        n.expect(events == [], 'invalid completion leaves request pending')
        n.ok('rv_host_file_picker_complete', [P, U64, I, C.POINTER(C.c_char_p), C.POINTER(I), I],
             page.host, canceled, 0, None, None, 0)
        n.expect(events == ['cancel'], 'cancellation reports cancel without input or change')
        one = n.handle('rv_dom_html_input_element_get_files', [P], first, nullable=False)
        n.expect(n.integer('rv_dom_file_list_get_length', one, C.c_uint32) == 1, 'cancellation preserves selected file')
        n.bind('rv_dom_file_list_release', None, [P])(one)
        click_first()
        detached = requests[-1][0]
        n.ok('rv_dom_element_remove', [P], first)
        n.expect(n.call('rv_run_loop_cycle', [I], 0) >= 0, 'run loop')
        n.expect((detached, 1, 0) in requests, 'removed control invalidates provider request')
        n.expect(n.call('rv_host_file_picker_complete', [P, U64, I, C.POINTER(C.c_char_p), C.POINTER(I), I],
                        page.host, detached, 0, None, None, 0) < 0, 'removed control rejects late completion')
    finally:
        page.close()
    page = Case(n, '<input id="moving" type="file" style="position:absolute;left:0;top:0;width:100px;height:40px">')
    other = Case(n, '<p>other page</p>')
    try:
        n.ok('rv_host_set_file_picker_handler', [P, PICKER, P], page.host, callback, None)
        moving = page.node('moving')
        for action in (0, 1, 2):
            n.expect(n.call('rv_host_mouse', [P, I, I, I, I, I, I], page.host, action, 20, 20, 0, 1, 0) >= 0, 'trusted pointer input')
        moved = requests[-1][0]
        body = n.bind('rv_document_body', P, [P])(other.host)
        try:
            n.ok('rv_node_append_child', [P, P], body, moving)
        finally:
            n.bind('rv_node_release', None, [P])(body)
        n.expect(n.call('rv_run_loop_cycle', [I], 0) >= 0, 'run loop after adoption')
        n.expect((moved, 1, 0) in requests, 'control adopted by another host invalidates request')
        n.expect(n.call('rv_host_file_picker_complete', [P, U64, I, C.POINTER(C.c_char_p), C.POINTER(I), I],
                        page.host, moved, 0, None, None, 0) < 0, 'adopted control rejects old host completion')
    finally:
        other.close()
        page.close()
    for terminate in ('navigation', 'destroy'):
        page = Case(n, '<input type="file" style="position:absolute;left:0;top:0;width:100px;height:40px">')
        try:
            n.ok('rv_host_set_file_picker_handler', [P, PICKER, P], page.host, callback, None)
            for action in (0, 1, 2):
                n.expect(n.call('rv_host_mouse', [P, I, I, I, I, I, I], page.host, action, 20, 20, 0, 1, 0) >= 0, 'trusted pointer input')
            pending = requests[-1][0]
            if terminate == 'navigation':
                n.ok('rv_host_load_html', [P, Utf8], page.host, b'<p>replacement</p>')
                n.expect((pending, 1, 0) in requests, 'navigation invalidates provider request')
                n.expect(n.call('rv_host_file_picker_complete', [P, U64, I, C.POINTER(C.c_char_p), C.POINTER(I), I],
                                page.host, pending, 0, None, None, 0) < 0, 'navigation rejects late completion')
        finally:
            page.close()
        if terminate == 'destroy':
            n.expect((pending, 1, 0) in requests, 'host destruction invalidates provider request')
    print('PASS file-picker:', n.assertions, 'assertions')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    main(parser.parse_args().native_directory)
