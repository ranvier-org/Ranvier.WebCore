"""RED for source patch 0039: after an element reflection is set to one target and then to [], each AX relation kind is
read. Writes the JSON named by the second argument."""
import ctypes, json, sys
from pathlib import Path
here = Path(__file__).resolve().parent
sys.path.insert(0, str(here.parents[1] / 'tests/abi'))
from svg_paint_probe import SvgProbe

KINDS = {'ariaControlsElements': 1, 'ariaDescribedByElements': 2, 'ariaDetailsElements': 3, 'ariaErrorMessageElements': 4,
         'ariaFlowToElements': 5, 'ariaLabelledByElements': 6}


class Sequence(ctypes.Structure):
    _fields_ = [('present', ctypes.c_int32), ('count', ctypes.c_int32), ('items', ctypes.POINTER(ctypes.c_void_p))]


def snake(m):
    return ''.join('_' + c.lower() if c.isupper() else c for c in m)


out = {'runtime': sys.argv[1], 'cases': []}
with SvgProbe(sys.argv[1], 320, 240) as p:
    P, I = p.pointer, p.integer
    p.load('<!doctype html><body><p id=t>Target</p><input id=s aria-invalid=true>', standalone=False)
    cb = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int32)(lambda *a: None)
    p.bind('rv_host_set_accessibility', I, [P, I, ctypes.c_void_p, P])(p.host, 1, ctypes.cast(cb, ctypes.c_void_p), None)
    by = p.bind('rv_document_get_element_by_id', P, [P, ctypes.c_char_p])
    target, subject = by(p.host, b't'), by(p.host, b's')
    relations = p.bind('rv_ax_relations', I, [P, I, ctypes.POINTER(P), I, ctypes.POINTER(I)])
    node_ax = p.bind('rv_node_ax', P, [P])
    release = p.bind('rv_ax_release', None, [P])

    def count(kind):
        p.update()
        axn = node_ax(subject)
        c = I()
        status = relations(axn, kind, None, 0, ctypes.byref(c))
        release(axn)
        return c.value if status in (0, -6) else ('status', status)

    for member, kind in KINDS.items():
        setter = p.bind('rv_dom_element_set_' + snake(member), I, [P, ctypes.POINTER(Sequence)])
        one = (P * 1)(target)
        setter(subject, ctypes.byref(Sequence(1, 1, ctypes.cast(one, ctypes.POINTER(P)))))
        with_target = count(kind)
        setter(subject, ctypes.byref(Sequence(1, 0, None)))
        after_empty = count(kind)
        setter(subject, None)
        after_null = count(kind)
        out['cases'].append({'member': member, 'withTarget': with_target, 'afterEmpty': after_empty, 'afterNull': after_null})
    p.bind('rv_node_release', None, [P])(target)
    p.bind('rv_node_release', None, [P])(subject)
    p.bind('rv_host_set_accessibility', I, [P, I, ctypes.c_void_p, P])(p.host, 0, None, None)
Path(sys.argv[2]).write_text(json.dumps(out, indent=1) + '\n')
for c in out['cases']:
    print(c)
