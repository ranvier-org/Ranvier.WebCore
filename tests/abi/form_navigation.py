"""Records what HTMLFormElement.requestSubmit and submit do to the host's document: the submit and formdata events
fired, and whether the document is replaced (identity, base URL, body child count, readiness) after the run loop
has fired the navigation scheduler's timer, and fails when a case fires other events or replaces the document."""

import argparse
import ctypes
import json
import os
from pathlib import Path
import sys

P, I = ctypes.c_void_p, ctypes.c_int32
CALLBACK = ctypes.CFUNCTYPE(I, P, P)
MARKUP = ('<!doctype html><body><form id="f" {action}><input name="a" value="1">'
          '<button id="b" name="go" value="yes">Go</button></form><p id="marker">kept</p></body>')
CASES = [
    {'name': 'requestSubmit-no-action', 'action': '', 'call': 'requestSubmit'},
    {'name': 'requestSubmit-https-action', 'action': 'action="https://example.test/x"', 'call': 'requestSubmit'},
    {'name': 'submit-default-action', 'action': '', 'call': 'submit'},
    {'name': 'submit-https-action', 'action': 'action="https://example.test/x"', 'call': 'submit'},
]


def run(directory):
    directory = Path(directory).resolve()
    search = os.add_dll_directory(str(directory)) if sys.platform == 'win32' else None
    library = ctypes.CDLL(str(directory / {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')))

    def bind(name, result, arguments):
        function = getattr(library, name)
        function.restype, function.argtypes = result, arguments
        return function

    create, destroy = bind('rv_host_create', P, [I, I]), bind('rv_host_destroy', None, [P])
    load = bind('rv_host_load_html', I, [P, ctypes.c_char_p])
    document_of = bind('rv_host_document', P, [P])
    by_id = bind('rv_document_get_element_by_id', P, [P, ctypes.c_char_p])
    release = bind('rv_node_release', None, [P])
    listen = bind('rv_node_add_event_listener', P, [P, ctypes.c_char_p, I, CALLBACK, P])
    remove = bind('rv_listener_remove', I, [P])
    cycle = bind('rv_run_loop_cycle', I, [I])
    same = bind('rv_dom_node_is_same_node', I, [P, P, ctypes.POINTER(I)])
    body_of = bind('rv_dom_document_get_body', I, [P, ctypes.POINTER(P)])
    count_of = bind('rv_dom_element_get_child_element_count', I, [P, ctypes.POINTER(ctypes.c_uint32)])
    ready_of = bind('rv_dom_document_get_ready_state', I, [P, ctypes.POINTER(I)])
    base_of = bind('rv_dom_node_get_base_uri', I, [P, ctypes.c_char_p, I, ctypes.POINTER(I)])
    connected_of = bind('rv_dom_node_get_is_connected', I, [P, ctypes.POINTER(I)])
    request_submit = bind('rv_dom_html_form_element_request_submit', I, [P, P])
    submit = bind('rv_dom_html_form_element_submit', I, [P])

    def state(host, original, marker):
        document = document_of(host)
        flag, body, count, ready, connected = I(), P(), ctypes.c_uint32(), I(), I()
        same(document, original, ctypes.byref(flag))
        body_of(document, ctypes.byref(body))
        count_of(body.value, ctypes.byref(count)) if body.value else None
        ready_of(document, ctypes.byref(ready))
        connected_of(marker, ctypes.byref(connected))
        buffer, length = ctypes.create_string_buffer(2048), I()
        base_of(document, buffer, len(buffer), ctypes.byref(length))
        if body.value:
            release(body.value)
        release(document)
        return {'sameDocument': flag.value == 1, 'bodyChildElements': count.value if body.value else None,
                'readyState': ready.value, 'markerConnected': connected.value == 1, 'baseURI': buffer.value.decode()}

    results = []
    for case in CASES:
        host = create(200, 100)
        try:
            assert load(host, MARKUP.format(action=case['action']).encode()) == 0
            original = document_of(host)
            form, button, marker = by_id(host, b'f'), by_id(host, b'b'), by_id(host, b'marker')
            fired = []
            callbacks = [CALLBACK(lambda context, event, kind=kind: fired.append(kind) or 0) for kind in ('submit', 'formdata')]
            listeners = [listen(form, kind.encode(), 0, callback, None) for kind, callback in zip(('submit', 'formdata'), callbacks)]
            before = state(host, original, marker)
            status = request_submit(form, button) if case['call'] == 'requestSubmit' else submit(form)
            immediately = state(host, original, marker)
            cycles = sum(max(cycle(50), 0) for _ in range(10))
            after = state(host, original, marker)
            results.append({'name': case['name'], 'status': status, 'events': list(fired), 'before': before,
                            'immediately': immediately, 'afterRunLoop': after, 'cycles': cycles})
            for listener in listeners:
                remove(listener)
            for node in (form, button, marker, original):
                release(node)
        finally:
            destroy(host)
    if search:
        search.close()
    return results


QUALIFICATION = 'host documents never navigate on form submission; the policy client is not consulted'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--evidence')
    args = parser.parse_args()
    results = run(args.native_directory)
    failures = []
    for case in results:
        wanted = ['submit', 'formdata'] if case['name'].startswith('requestSubmit') else ['formdata']
        if case['status'] != 0 or case['events'] != wanted:
            failures.append(case['name'] + ': status/events ' + str((case['status'], case['events'])))
        for moment in ('immediately', 'afterRunLoop'):
            state, before = case[moment], case['before']
            kept = (state['sameDocument'] and state['markerConnected'] and state['bodyChildElements'] == before['bodyChildElements']
                    and state['readyState'] == before['readyState'] and state['baseURI'] == before['baseURI'])
            if not kept:
                failures.append(case['name'] + ': navigated ' + moment)
    text = json.dumps({'directory': str(Path(args.native_directory).resolve()), 'qualification': QUALIFICATION,
                       'failures': failures, 'cases': results}, indent=2)
    if args.evidence:
        Path(args.evidence).write_text(text + '\n', encoding='utf-8')
    if failures:
        raise SystemExit('\n'.join(failures))
    print(f'PASS form navigation: {len(results)} cases kept the document ({QUALIFICATION})')


if __name__ == '__main__':
    main()
