"""I11 ARIA relationship probe against an actual runtime directory. Replays the Chromium oracle
tests/fixtures/aria-relations-oracle.json through the content attributes, the generated Element.aria*Element(s)
reflections and rv_ax_relations, comparing per step the reflected elements, the attributes, the accessible name and
description, and the relations of the subject. Then checks repeated reads, errors and teardown: a removed target, and
handles held past rv_host_destroy."""

import argparse
import ctypes
import json
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe
from utf8_inputs import Utf8

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
OK, NULL_ARGUMENT, WRONG_THREAD, BUFFER_TOO_SMALL, UNSUPPORTED, DETACHED, WRONG_INTERFACE = 0, -1, -2, -6, -9, -10, -11
ABI = 54
KINDS = ['activedescendant', 'controls', 'describedby', 'details', 'errormessage', 'flowto', 'labelledby', 'owns']
NAME, DESCRIPTION = 0, 1
# Steps where WebKit differs from Chromium (docs/element-internals-evidence), keyed by step, with the measured
# difference. Every other step must match exactly.
QUALIFIED = {
    'elements labelledby [l2, l1, l2]': 'WebKit keeps the duplicate in the reflected array (l2, l1, l2); Chromium keeps each element once. Both relations list l2, l1.',
}
# WebKit gates ariaActionsElements behind ARIAActionsSupportEnabled, off in every WebKit configuration: the members
# report RV_ERR_UNSUPPORTED and the comparison leaves them out.
GATED = {'ariaActionsElements'}


class Sequence(ctypes.Structure):
    _fields_ = [('present', ctypes.c_int32), ('count', ctypes.c_int32), ('items', ctypes.POINTER(ctypes.c_void_p))]


def verify(native_directory):
    oracle = json.loads((FIXTURES / 'aria-relations-oracle.json').read_text())
    report = {'browser': oracle['browser'], 'steps': [], 'qualified': []}
    with SvgProbe(native_directory, 500, 400) as p:
        P, I = p.pointer, p.integer
        p.expect(p.bind('rv_abi_version', I, [])() == ABI, 'ABI version ' + str(ABI))
        has = p.bind('rv_abi_has', I, [ctypes.c_char_p])
        p.expect(has(b'accessibility-relations') == 1 and has(b'accessibility') == 1, 'accessibility-relations advertised')
        getters = {m: p.bind('rv_dom_element_get_' + snake(m), I, [P, ctypes.POINTER(Sequence)]) for m in oracle['members']}
        setters = {m: p.bind('rv_dom_element_set_' + snake(m), I, [P, ctypes.POINTER(Sequence)]) for m in oracle['members']}
        release_sequence = p.bind('rv_dom_sequence_element_nullable_release', None, [ctypes.POINTER(Sequence)])
        get_active = p.bind('rv_dom_element_get_aria_active_descendant_element', I, [P, ctypes.POINTER(P)])
        relations = p.bind('rv_ax_relations', I, [P, I, ctypes.POINTER(P), I, ctypes.POINTER(I)])
        node_ax = p.bind('rv_node_ax', P, [P])
        ax_dom = p.bind('rv_ax_dom_node', P, [P])
        ax_release = p.bind('rv_ax_release', None, [P])
        ax_string = p.bind('rv_ax_string', I, [P, I, P, I, ctypes.POINTER(I)])
        node_release = p.bind('rv_node_release', None, [P])
        set_attribute = p.bind('rv_element_set_attribute', I, [P, ctypes.c_char_p, ctypes.c_char_p])
        remove_attribute = p.bind('rv_dom_element_remove_attribute', I, [P, Utf8])
        remove = p.bind('rv_dom_element_remove', I, [P])
        by_id = p.bind('rv_document_get_element_by_id', P, [P, ctypes.c_char_p])
        callback = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int32)(lambda *a: None)
        set_accessibility = p.bind('rv_host_set_accessibility', I, [P, I, ctypes.c_void_p, P])
        p.load(oracle['page'], standalone=False)
        p.expect(set_accessibility(p.host, 1, ctypes.cast(callback, ctypes.c_void_p), None) == OK, 'accessibility on')
        ids = ['l1', 'l2', 'd1', 'd2', 'e1', 'x1', 'f1', 'b', 'list', 'o1', 'o2', 'i', 'host']
        nodes = {k: by_id(p.host, k.encode()) for k in ids}
        p.expect(all(nodes.values()), 'page elements')
        # #host's shadow root holds #inner, as the oracle's attachShadow does.
        init = (ctypes.c_int32 * 6)(24, 2, 0, 0, 0, 0)
        root = P()
        p.expect(p.bind('rv_dom_element_attach_shadow', I, [P, P, ctypes.POINTER(P)])(nodes['host'], ctypes.cast(init, P), ctypes.byref(root)) == OK, 'attachShadow')
        inner = p.bind('rv_document_create_element', P, [P, ctypes.c_char_p])(p.host, b'span')
        p.expect(set_attribute(inner, b'id', b'inner') == OK and p.bind('rv_node_set_text_content', I, [P, ctypes.c_char_p])(inner, b'Inner') == OK
                 and p.bind('rv_node_append_child', I, [P, P])(root, inner) == OK, 'shadow span')
        nodes['inner'] = inner
        node_release(root)

        def id_of(node):
            return p.attribute(node, 'id') if node else None

        def read_sequence(subject, member):
            value = Sequence()
            if member in GATED:
                p.expect(getters[member](subject, ctypes.byref(value)) == UNSUPPORTED, member + ' is gated')
                return 'unsupported'
            p.expect(getters[member](subject, ctypes.byref(value)) == OK, member)
            try:
                return None if not value.present else [id_of(value.items[i]) for i in range(value.count)]
            finally:
                release_sequence(ctypes.byref(value))

        def write_sequence(subject, member, targets):
            if targets is None:
                return setters[member](subject, None)
            array = (P * max(len(targets), 1))(*[nodes[t] for t in targets])
            value = Sequence(1, len(targets), ctypes.cast(array, ctypes.POINTER(P)))
            return setters[member](subject, ctypes.byref(value))

        def ax_state(subject):
            p.update()
            axn = node_ax(subject)
            p.expect(bool(axn), 'accessible subject')
            try:
                strings = []
                for prop in [NAME, DESCRIPTION]:
                    buffer, length = ctypes.create_string_buffer(256), I()
                    p.expect(ax_string(axn, prop, buffer, 256, ctypes.byref(length)) == OK, 'ax string')
                    strings.append(buffer.raw[:length.value].decode())
                found = {}
                for index, kind in enumerate(KINDS):
                    count = I()
                    p.expect(relations(axn, index, None, 0, ctypes.byref(count)) in (OK, BUFFER_TOO_SMALL), 'relation count ' + kind)
                    handles = (P * max(count.value, 1))()
                    p.expect(relations(axn, index, handles, count.value, ctypes.byref(count)) == OK, 'relations ' + kind)
                    targets = []
                    for i in range(count.value):
                        dom = ax_dom(handles[i])
                        targets.append(id_of(dom) or None)
                        if dom:
                            node_release(dom)
                        ax_release(handles[i])
                    found[kind] = targets
                return {'name': strings[0], 'description': strings[1], 'relations': found}
            finally:
                ax_release(axn)

        for step in oracle['steps']:
            subject = nodes[step['subject']]
            operation, key, argument = step['operation'], step['key'], step['argument']
            if operation == 'attr':
                status = remove_attribute(subject, key.encode()) if argument is None else set_attribute(subject, key.encode(), argument.encode())
            elif operation == 'elements':
                status = write_sequence(subject, key, argument)
            elif operation == 'remove':
                status = remove(nodes[argument])
            elif operation == 'shadow':
                status = write_sequence(subject, key, ['inner'])
            else:
                status = OK
                for element in [nodes['b'], nodes['i']]:
                    for attribute in oracle['relations'].values():
                        status |= remove_attribute(element, attribute.encode())
            p.expect(status == (UNSUPPORTED if operation == 'elements' and key in GATED else OK), step['name'] + ' operation')
            reflected = {m: read_sequence(subject, m) for m in oracle['members'] if m not in GATED}
            for m in GATED:
                read_sequence(subject, m)
            active = P()
            p.expect(get_active(subject, ctypes.byref(active)) == OK, 'ariaActiveDescendantElement')
            reflected['ariaActiveDescendantElement'] = id_of(active.value) if active.value else None
            if active.value:
                node_release(active)
            attributes = {a: p.text('rv_dom_element_get_attribute', [P, Utf8], subject, a.encode()) for a in oracle['relations'].values()}
            # Repeated reads give the same elements in the same order; each read is a new snapshot buffer.
            p.expect(read_sequence(subject, 'ariaLabelledByElements') == reflected['ariaLabelledByElements'], step['name'] + ' repeated read')
            ax = ax_state(subject)
            native = {'reflected': reflected, 'attributes': attributes, 'ax': ax}
            chromium = {'reflected': {k: v for k, v in step['reflected'].items() if k not in GATED}, 'attributes': step['attributes'], 'ax': step['ax']}
            differs = native != chromium
            p.expect(differs == (step['name'] in QUALIFIED), step['name'] + ' qualification: native ' + json.dumps(native) + ' Chromium ' + json.dumps(chromium))
            if differs:
                report['qualified'].append({'step': step['name'], 'reason': QUALIFIED[step['name']], 'native': native, 'chromium': chromium})
            report['steps'].append({'name': step['name'], 'native': native})

        # Errors.
        value = Sequence()
        text = p.bind('rv_document_create_text', P, [P, ctypes.c_char_p])(p.host, b'text')
        p.expect(getters['ariaLabelledByElements'](None, ctypes.byref(value)) == NULL_ARGUMENT
                 and getters['ariaLabelledByElements'](nodes['b'], None) == NULL_ARGUMENT, 'reflection nulls')
        p.expect(getters['ariaLabelledByElements'](text, ctypes.byref(value)) == WRONG_INTERFACE, 'a text node has no reflection')
        axb = node_ax(nodes['b'])
        count = I()
        p.expect(relations(axb, 8, None, 0, ctypes.byref(count)) == UNSUPPORTED and relations(axb, -1, None, 0, ctypes.byref(count)) == UNSUPPORTED, 'unknown relation kinds')
        p.expect(relations(axb, 0, None, 0, None) == NULL_ARGUMENT and relations(None, 0, None, 0, ctypes.byref(count)) == NULL_ARGUMENT, 'relation nulls')
        p.expect(write_sequence(nodes['b'], 'ariaLabelledByElements', ['l1', 'l2']) == OK, 'labelledby for the buffer check')
        p.update()
        small = (P * 1)()
        p.expect(relations(axb, 6, small, 1, ctypes.byref(count)) == BUFFER_TOO_SMALL and count.value == 2, 'capacity below the count')
        results = []

        def off_thread():
            v, c = Sequence(), I()
            results.append((getters['ariaLabelledByElements'](nodes['b'], ctypes.byref(v)), write_sequence(nodes['b'], 'ariaLabelledByElements', None),
                            relations(axb, 6, None, 0, ctypes.byref(c))))

        worker = threading.Thread(target=off_thread)
        worker.start()
        worker.join()
        p.expect(results[0][:2] == (WRONG_THREAD, WRONG_THREAD) and results[0][2] in (WRONG_THREAD, NULL_ARGUMENT), 'wrong thread ' + str(results))
        p.expect(read_sequence(nodes['b'], 'ariaLabelledByElements') == ['l1', 'l2'], 'off-thread calls change nothing')
        # Source patch 0039: an emptied reflection clears its relation, for every array kind.
        target = nodes['x1']
        for member, kind in [('ariaControlsElements', 1), ('ariaDescribedByElements', 2), ('ariaDetailsElements', 3),
                             ('ariaErrorMessageElements', 4), ('ariaFlowToElements', 5), ('ariaLabelledByElements', 6)]:
            p.expect(write_sequence(nodes['i'], member, ['x1']) == OK, member + ' one target')
            p.update()
            axi = node_ax(nodes['i'])
            p.expect(relations(axi, kind, None, 0, ctypes.byref(count)) in (OK, BUFFER_TOO_SMALL) and count.value == 1, member + ' relation with one target')
            p.expect(write_sequence(nodes['i'], member, []) == OK, member + ' emptied')
            p.update()
            p.expect(relations(axi, kind, None, 0, ctypes.byref(count)) in (OK, BUFFER_TOO_SMALL) and count.value == 0, member + ' [] clears the relation')
            p.expect(read_sequence(nodes['i'], member) == [], member + ' [] reads []')
            p.expect(write_sequence(nodes['i'], member, None) == OK, member + ' cleared')
            ax_release(axi)
        # A removed target leaves the reflection and the relation.
        p.expect(remove(nodes['l2']) == OK, 'remove l2')
        p.update()
        p.expect(read_sequence(nodes['b'], 'ariaLabelledByElements') == ['l1'], 'a removed target leaves the reflection')
        p.expect(relations(axb, 6, small, 1, ctypes.byref(count)) == OK and count.value == 1, 'a removed target leaves the relation')
        ax_release(small[0])
        # Handles held past rv_host_destroy.
        held_sequence = Sequence()
        p.expect(getters['ariaLabelledByElements'](nodes['b'], ctypes.byref(held_sequence)) == OK and held_sequence.count == 1, 'sequence held past destroy')
        p.expect(set_accessibility(p.host, 0, None, None) == OK, 'accessibility off')
        node_release(text)
        p.dispose_host()
        status = relations(axb, 6, None, 0, ctypes.byref(count))
        p.expect(status == DETACHED, 'relations after destroy: ' + str(status))
        ax_release(axb)
        after = Sequence()
        status = getters['ariaLabelledByElements'](nodes['b'], ctypes.byref(after))
        p.expect(status == OK and after.present in (0, 1), 'reflection after destroy: ' + str(status))
        release_sequence(ctypes.byref(after))
        release_sequence(ctypes.byref(held_sequence))
        for node in nodes.values():
            node_release(node)
        p.collect()
        report['assertions'] = p.assertions
        return p.assertions, report


def snake(member):
    out = ''
    for ch in member:
        out += '_' + ch.lower() if ch.isupper() else ch
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--report')
    args = parser.parse_args()
    assertions, report = verify(args.native_directory)
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2) + '\n')
    print(f'PASS aria_relations: {assertions} assertions', flush=True)
