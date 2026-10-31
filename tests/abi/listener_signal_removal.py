import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sys

# Evidence for the I01 cancellation facade (WebCore #99): the native listener ABI carries the removal
# semantics an AbortSignal-bound listener needs. Every scenario runs the same steps as
# listener_signal_removal_browser.mjs, where Chromium removes through AbortController.abort().

CASES = Path(__file__).resolve().parents[1] / 'fixtures' / 'listener-signal-removal-cases.json'


def verify(directory, evidence_json=None):
    directory = Path(directory).resolve()
    before = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
    print('RUNTIME_BEFORE=' + json.dumps(before, sort_keys=True), flush=True)
    if sys.platform == 'win32':
        os.add_dll_directory(str(directory))
    filename = {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')
    library = ctypes.CDLL(str(directory / filename))
    pointer, integer = ctypes.c_void_p, ctypes.c_int32
    assertions = 0

    def expect(condition, message):
        nonlocal assertions
        assertions += 1
        if not condition:
            raise AssertionError(message)

    def bind(name, result, arguments):
        function = getattr(library, name)
        function.restype, function.argtypes = result, arguments
        return function

    create = bind('rv_host_create', pointer, [integer, integer])
    destroy = bind('rv_host_destroy', None, [pointer])
    load_html = bind('rv_host_load_html', integer, [pointer, ctypes.c_char_p])
    by_id = bind('rv_document_get_element_by_id', pointer, [pointer, ctypes.c_char_p])
    release_node = bind('rv_node_release', None, [pointer])
    Callback = ctypes.CFUNCTYPE(integer, pointer, pointer)
    add = bind('rv_node_add_event_listener', pointer, [pointer, ctypes.c_char_p, integer, Callback, pointer])
    remove = bind('rv_listener_remove', integer, [pointer])
    dispatch = bind('rv_node_dispatch_event', integer, [pointer, ctypes.c_char_p, integer, integer, ctypes.POINTER(integer)])
    cycle = bind('rv_run_loop_cycle', integer, [integer])

    cases = json.loads(CASES.read_text(encoding='utf-8'))
    host = create(64, 64)
    expect(bool(host), 'Host created')
    results = {}
    for case in cases['scenarios']:
        expect(load_html(host, b'<div id="parent"><div id="child"></div></div><div id="other"></div>') == 0, case['name'] + ' load')
        nodes = {name: by_id(host, name.encode()) for name in ('parent', 'child', 'other')}
        log = []
        handles = {}
        keep = []
        fired_once = set()

        def register(spec):
            label, node, capture = spec['label'], spec['node'], 1 if spec.get('capture') else 0
            actions = spec.get('onFire', [])

            def run(context, event, label=label, actions=actions):
                log.append(label)
                for action in actions:
                    if action.get('once') and (label, json.dumps(action)) in fired_once:
                        continue
                    fired_once.add((label, json.dumps(action)))
                    if action['do'] == 'remove':
                        for handle in handles.pop(action['group'], []):
                            expect(remove(handle) == 0, case['name'] + ' remove in dispatch ' + action['group'])
                    elif action['do'] == 'add':
                        register(action['listener'])
                return 0

            callback = Callback(run)
            keep.append(callback)
            handle = add(nodes[node], b'ping', capture, callback, None)
            expect(bool(handle), case['name'] + ' add ' + label)
            handles.setdefault(spec['group'], []).append(handle)

        for spec in case['listeners']:
            register(spec)
        observed = []
        for step in case['steps']:
            if step['do'] == 'dispatch':
                log.clear()
                prevented = integer(0)
                expect(dispatch(nodes[step['node']], b'ping', 1, 0, ctypes.byref(prevented)) == 0, case['name'] + ' dispatch')
                cycle(0)
                observed.append(list(log))
            elif step['do'] == 'remove':
                for handle in handles.pop(step['group'], []):
                    expect(remove(handle) == 0, case['name'] + ' remove ' + step['group'])
        expected = case.get('native', case['expected'])
        expect(observed == expected, case['name'] + ' order ' + repr(observed) + ' != ' + repr(expected))
        results[case['name']] = observed
        for group in list(handles):
            for handle in handles.pop(group):
                expect(remove(handle) == 0, case['name'] + ' cleanup')
        for node in nodes.values():
            release_node(node)
    destroy(host)
    after = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
    expect(before == after, 'Runtime unchanged')
    summary = dict(assertions=assertions, cases=results,
                   qualified=[c['name'] for c in cases['scenarios'] if 'native' in c])
    if evidence_json:
        Path(evidence_json).write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print('PASS listener signal removal: %d assertions' % assertions, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--evidence-json')
    arguments = parser.parse_args()
    verify(arguments.native_directory, arguments.evidence_json)
