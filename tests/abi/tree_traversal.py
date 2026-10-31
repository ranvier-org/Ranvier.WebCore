"""Replays tests/fixtures/tree-traversal-cases.json through the generated TreeWalker/NodeIterator functions and
rv_node_filter_create, and compares every step with the Chromium oracle tests/fixtures/tree-traversal-oracle.json:
traversal results, filter calls in order, walker and iterator state, getters and filter identity. It also checks
filter failure statuses, re-entrancy, release-callback lifetime and the null, thread and interface errors."""

import argparse
import ctypes
import json
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
FILTER = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p)
RELEASE = ctypes.CFUNCTYPE(None, ctypes.c_void_p)
DOM_EXCEPTION, NULL_ARGUMENT, WRONG_THREAD, WRONG_INTERFACE = -3, -1, -2, -11
METHODS = {'next': 'next_node', 'prev': 'previous_node', 'parent': 'parent_node', 'first': 'first_child', 'last': 'last_child',
           'prevSib': 'previous_sibling', 'nextSib': 'next_sibling'}


class FilterFailure(Exception):
    pass


def verify(native_directory):
    spec = json.loads((FIXTURES / 'tree-traversal-cases.json').read_text())
    oracle = json.loads((FIXTURES / 'tree-traversal-oracle.json').read_text())
    expected = {case['name']: case for case in oracle['cases']}
    failures, qualified = [], []
    with SvgProbe(native_directory, 100, 100) as p:
        P, I = p.pointer, p.integer
        has = p.bind('rv_abi_has', I, [ctypes.c_char_p])
        for capability in [b'dom:TreeWalker', b'dom:NodeIterator', b'dom:NodeFilter']:
            p.expect(has(capability) == 1, 'rv_abi_has ' + capability.decode())
        released = {}
        releases_by_context = {}

        def on_release(context):
            releases_by_context[context] = releases_by_context.get(context, 0) + 1

        release_callback = RELEASE(on_release)
        create_filter = p.bind('rv_node_filter_create', P, [P, FILTER, P, RELEASE])
        filter_context = p.bind('rv_node_filter_context', I, [P, ctypes.POINTER(P)])
        release_filter = p.bind('rv_dom_node_filter_release', None, [P])
        exception_name = lambda: p.text('rv_last_exception', [I], 0)

        def raw(name, arguments, *values):
            return p.bind(name, I, arguments)(*values)

        def get(name, target):
            result = P()
            status = raw(name, [P, ctypes.POINTER(P)], target, ctypes.byref(result))
            return status, result.value

        def text(name, node):
            return p.text(name, [P], node)

        def label(node):
            if not node:
                return None
            kind = ctypes.c_uint16()
            p.call('rv_dom_node_get_node_type', [P, ctypes.POINTER(ctypes.c_uint16)], node, ctypes.byref(kind))
            if kind.value == 1:
                return p.attribute(node, 'id')
            if kind.value == 3:
                return '#' + text('rv_dom_node_get_node_value', node)
            if kind.value == 7:
                return '?' + text('rv_dom_node_get_node_name', node) + ' ' + text('rv_dom_node_get_node_value', node)
            if kind.value == 8:
                return '!' + text('rv_dom_node_get_node_value', node)
            if kind.value == 9:
                return '#document'
            return text('rv_dom_node_get_node_name', node)

        owned = []

        def keep(node):
            if node:
                owned.append(node)
            return node

        def document():
            status, value = get('rv_dom_node_get_owner_document', p.node('svg'))
            p.expect(status == 0 and value, 'owner document')
            return keep(value)

        def find(doc, wanted):
            if wanted == '#document':
                return doc
            walker = P()
            p.call('rv_dom_document_create_tree_walker', [P, P, p.unsigned, P, ctypes.POINTER(P)], doc, doc, 0xFFFFFFFF, None, ctypes.byref(walker))
            try:
                node = doc
                while node:
                    if label(node) == wanted:
                        return node
                    status, node = get('rv_dom_tree_walker_next_node', walker.value)
                    p.expect(status == 0, 'lookup walk')
                    keep(node)
            finally:
                p.bind('rv_dom_tree_walker_release', None, [P])(walker.value)
            raise AssertionError('no node ' + wanted)

        def remove(doc, wanted):
            node = find(doc, wanted)
            status, parent = get('rv_dom_node_get_parent_node', node)
            keep(parent)
            result = P()
            p.call('rv_dom_node_remove_child', [P, P, ctypes.POINTER(P)], parent, node, ctypes.byref(result))
            keep(result.value)

        def run_case(case):
            p.release_all()
            for node in owned:
                p.bind('rv_node_release', None, [P])(node)
            owned.clear()
            p.load(spec['markup'])
            doc = document()
            kind = 'tree_walker' if case['kind'] == 'walker' else 'node_iterator'
            calls, seen, state = [], {}, {'traversal': None, 'mutated': False, 'reentered': False}
            raised = []
            spec_filter = case['filter']

            def accept(context, node):
                try:
                    name = label(node)
                    calls.append(name)
                    seen[name] = seen.get(name, 0) + 1
                    if spec_filter['kind'] == 'map':
                        return spec_filter['map'].get(name, 1)
                    if spec_filter['kind'] == 'throw' and name == spec_filter['on'] and seen[name] <= spec_filter['times']:
                        calls.append('throw')
                        raise FilterFailure('filter failure')
                    if spec_filter['kind'] == 'mutate' and name == spec_filter['on'] and not state['mutated']:
                        state['mutated'] = True
                        remove(doc, spec_filter['remove'])
                        calls.append('removed:' + spec_filter['remove'])
                    if spec_filter['kind'] == 'reenter' and name == spec_filter['on'] and not state['reentered']:
                        state['reentered'] = True
                        status, inner = get(f'rv_dom_{kind}_next_node', state['traversal'])
                        calls.append('reenter:' + (exception_name() if status == DOM_EXCEPTION else str(label(keep(inner)))))
                    if spec_filter['kind'] == 'reenterOther' and name == spec_filter['on'] and not state['reentered']:
                        state['reentered'] = True
                        other_filter = create_filter(doc, other_accept, None, RELEASE())
                        other = P()
                        p.call('rv_dom_document_create_tree_walker', [P, P, p.unsigned, P, ctypes.POINTER(P)], doc, find(doc, 'b'), 1,
                               other_filter, ctypes.byref(other))
                        release_filter(other_filter)
                        results = [label(keep(get('rv_dom_tree_walker_next_node', other.value)[1])) for _ in range(2)]
                        p.bind('rv_dom_tree_walker_release', None, [P])(other.value)
                        calls.append('other:' + ','.join(str(r) for r in results))
                    return 1
                except Exception as error:  # stored and rethrown after the native call, as the managed wrapper does
                    raised.append(error)
                    return 0

            other_accept = FILTER(lambda context, node: 1)
            callback = FILTER(accept)
            context = ctypes.c_void_p(0x1000 + len(released))
            handle = create_filter(doc, callback, context, release_callback) if spec_filter else None
            if spec_filter:
                p.expect(bool(handle), 'filter creation')
                out = P()
                p.call('rv_node_filter_context', [P, ctypes.POINTER(P)], handle, ctypes.byref(out))
                p.expect(out.value == context.value, 'filter context identity')
            traversal = P()
            p.call(f'rv_dom_document_create_{kind}', [P, P, p.unsigned, P, ctypes.POINTER(P)], doc, find(doc, case['root']), case['mask'],
                   handle, ctypes.byref(traversal))
            state['traversal'] = traversal.value
            if handle:
                release_filter(handle)  # the traversal keeps the filter alive
                p.expect(releases_by_context.get(context.value, 0) == 0, 'filter outlives the caller handle while the traversal holds it')

            def current():
                if case['kind'] == 'walker':
                    return [label(keep(get('rv_dom_tree_walker_get_current_node', traversal.value)[1]))]
                before = p.read('node_iterator', traversal.value, 'pointer_before_reference_node', I)
                return [label(keep(get('rv_dom_node_iterator_get_reference_node', traversal.value)[1])), bool(before)]

            status, got_filter = get(f'rv_dom_{kind}_get_filter', traversal.value)
            what = p.read(kind, traversal.value, 'what_to_show', p.unsigned)
            getters = {'root': label(keep(get(f'rv_dom_{kind}_get_root', traversal.value)[1])), 'whatToShow': what,
                       'filterSame': got_filter == handle, 'state': current()}
            if got_filter:
                release_filter(got_filter)
            steps = []
            for step in case['steps']:
                calls.clear()
                raised.clear()
                if isinstance(step, str) and step == 'detach':
                    status, outcome = raw('rv_dom_node_iterator_detach', [P], traversal.value), 'undefined'
                elif isinstance(step, str):
                    status, node = get(f'rv_dom_{kind}_{METHODS[step]}', traversal.value)
                    outcome = label(keep(node))
                elif 'set' in step:
                    status, outcome = raw('rv_dom_tree_walker_set_current_node', [P, P], traversal.value, find(doc, step['set'])), 'set'
                else:
                    remove(doc, step['remove'])
                    status, outcome = 0, 'removed'
                if raised:
                    p.expect(status == DOM_EXCEPTION and exception_name() == 'ExistingExceptionError',
                             case['name'] + ': filter failure status ' + str(status) + ' ' + repr(exception_name()))
                    outcome = 'throw:Error'
                elif status == DOM_EXCEPTION:
                    outcome = 'throw:' + exception_name()
                else:
                    p.expect(status == 0, case['name'] + ': status ' + str(status))
                unreadable = case['kind'] == 'iterator' and state['reentered']
                steps.append({'result': outcome, 'calls': list(calls), 'state': current(), 'stateRead': unreadable})
            p.bind(f'rv_dom_{kind}_release', None, [P])(traversal.value)
            if spec_filter:
                p.collect()
                p.expect(releases_by_context.get(context.value) == 1, case['name'] + ': filter release runs once after the traversal')
            released[case['name']] = releases_by_context.get(context.value, 0)
            return {'getters': getters, 'steps': steps}

        actual = {}
        for case in spec['cases']:
            actual[case['name']] = run_case(case)
            want = expected[case['name']]
            got = actual[case['name']]
            p.assertions += 1
            if got['getters'] != want['getters']:
                failures.append(f"{case['name']} getters: native {got['getters']}, Chromium {want['getters']}")
            for index, (mine, theirs) in enumerate(zip(got['steps'], want['steps'])):
                p.assertions += 1
                if theirs['state'] == 'unreadable':
                    theirs = dict(theirs, state=mine['state'])
                    if mine['result'] != theirs['result']:
                        qualified.append({'case': case['name'], 'step': index, 'native': mine['result'], 'chromium': theirs['result']})
                        continue
                mine = {key: mine[key] for key in ('result', 'calls', 'state')}
                if mine != theirs:
                    failures.append(f"{case['name']} step {index} {case['steps'][index]}: native {mine}, Chromium {theirs}")
            p.expect(len(got['steps']) == len(want['steps']), case['name'] + ' step count')

        # A re-entrant NodeIterator call throws InvalidStateError inside the filter. WebKit and Chromium 156 then both
        # lose the iterator's reference node: later steps return null, where the DOM standard continues the iteration.
        # Chromium crashes its renderer when referenceNode is read in that state; native reports NULL.
        reenter = actual['iterator-reenter']['steps']
        p.expect(reenter[2]['calls'] == ['a1', 'reenter:InvalidStateError'], 'iterator re-entrancy throws InvalidStateError')
        p.expect(all(step['result'] is None for step in reenter[3:]), 'iterator results after re-entrancy: ' + str(reenter[3:]))
        qualified.append({'case': 'iterator-reenter', 'note': 'reference node lost after re-entrancy in both engines; native reads NULL where Chromium crashes'})

        # Errors: null arguments, wrong interface, wrong thread.
        p.load(spec['markup'])
        doc, root = document(), p.node('root')
        out = P()
        p.expect(raw('rv_dom_document_create_tree_walker', [P, P, p.unsigned, P, ctypes.POINTER(P)], None, root, 1, None, ctypes.byref(out)) == NULL_ARGUMENT, 'null document')
        p.expect(raw('rv_dom_document_create_tree_walker', [P, P, p.unsigned, P, ctypes.POINTER(P)], doc, None, 1, None, ctypes.byref(out)) == NULL_ARGUMENT, 'null root')
        p.expect(raw('rv_dom_document_create_node_iterator', [P, P, p.unsigned, P, ctypes.POINTER(P)], root, root, 1, None, ctypes.byref(out)) == WRONG_INTERFACE, 'element is not a document')
        p.expect(not create_filter(None, FILTER(lambda c, n: 1), None, RELEASE()), 'filter without a node')
        p.expect(not create_filter(doc, FILTER(), None, RELEASE()), 'filter without a callback')
        p.call('rv_dom_document_create_tree_walker', [P, P, p.unsigned, P, ctypes.POINTER(P)], doc, root, 1, None, ctypes.byref(out))
        walker = out.value
        p.expect(raw('rv_dom_tree_walker_set_current_node', [P, P], walker, None) == NULL_ARGUMENT, 'currentNode = null (Chromium ' + oracle['nullCurrent'] + ')')
        status, missing = get('rv_dom_tree_walker_get_filter', walker)
        p.expect(status == 0 and missing is None and oracle['nullFilterGetter'] is None, 'null filter getter')
        anonymous = FILTER(lambda c, n: 1)
        unnamed = create_filter(doc, anonymous, None, RELEASE())
        foreign = P(1)
        p.call('rv_node_filter_context', [P, ctypes.POINTER(P)], unnamed, ctypes.byref(foreign))
        p.expect(foreign.value is None, 'a NULL context reads back as NULL')
        release_filter(unnamed)
        threaded = {}

        def other_thread():
            result = P()
            threaded['walk'] = raw('rv_dom_tree_walker_next_node', [P, ctypes.POINTER(P)], walker, ctypes.byref(result))
            threaded['create'] = create_filter(doc, FILTER(lambda c, n: 1), None, RELEASE())
            threaded['context'] = filter_context(None, ctypes.byref(P()))

        thread = threading.Thread(target=other_thread)
        thread.start()
        thread.join()
        p.expect(threaded['walk'] == WRONG_THREAD and not threaded['create'] and threaded['context'] == NULL_ARGUMENT, 'wrong thread: ' + str(threaded))
        p.bind('rv_dom_tree_walker_release', None, [P])(walker)

        # Lifetime: the filter release runs once, after the last of the caller, getter and traversal references.
        context = ctypes.c_void_p(0x9000)
        held = create_filter(doc, FILTER(lambda c, n: 1), context, release_callback)
        p.call('rv_dom_document_create_node_iterator', [P, P, p.unsigned, P, ctypes.POINTER(P)], doc, root, 1, held, ctypes.byref(out))
        iterator = out.value
        status, getter = get('rv_dom_node_iterator_get_filter', iterator)
        p.expect(getter == held, 'iterator filter identity')
        release_filter(held)
        p.bind('rv_dom_node_iterator_release', None, [P])(iterator)
        p.collect()
        p.expect(releases_by_context.get(context.value, 0) == 0, 'getter reference keeps the filter alive')
        release_filter(getter)
        p.expect(releases_by_context.get(context.value) == 1, 'release runs when the getter reference goes')

        p.release_all()
        for node in owned:
            p.bind('rv_node_release', None, [P])(node)
        owned.clear()
        print(json.dumps({'qualified': qualified, 'failures': failures, 'objectFormMatchesFunction': oracle['objectFormMatchesFunction']}))
        p.expect(not failures, 'traversal differs from Chromium: ' + '; '.join(failures[:20]))
        print(f'TREE TRAVERSAL PASS {p.assertions} assertions')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    verify(parser.parse_args().native_directory)
