"""RED measurement on a runtime directory: which ElementInternals and ARIA element-reflection members the runtime
exports, and what the accessibility tree reports for the ARIA attributes and the one generated element reflection
(ariaActiveDescendantElement). Writes the JSON named by the second argument."""
import ctypes, json, sys
from pathlib import Path
here = Path(__file__).resolve().parent
sys.path.insert(0, str(here.parents[1] / 'tests/abi'))
sys.path.insert(0, str(here))
from svg_paint_probe import SvgProbe
from pe_exports import exports

directory = Path(sys.argv[1])
names = exports(directory / 'RanvierWebCoreHost.dll')
out = {'runtime': str(directory),
       'elementReflectionExports': sorted(n for n in names if 'aria' in n and 'element' in n.split('aria', 1)[1]),
       'internalsExports': sorted(n for n in names if 'internals' in n or 'custom_element' in n),
       'steps': []}
PAGE = ('<!doctype html><body><span id=l1>First</span><span id=l2>Second</span><p id=d1>Describe</p>'
        '<button id=b>Plain</button><div id=list role=listbox aria-label=Choices tabindex=0><div id=o1 role=option>One</div>'
        '<div id=o2 role=option>Two</div></div><x-toggle id=t role=button aria-label=Toggle aria-pressed=true></x-toggle><input id=i>')
NAME, DESCRIPTION, ROLE_NAME = 0, 1, 3
with SvgProbe(str(directory), 320, 240) as p:
    P, I = p.pointer, p.integer
    out['abi'] = p.bind('rv_abi_version', I, [])()
    has = p.bind('rv_abi_has', I, [ctypes.c_char_p])
    out['features'] = {n: has(n.encode()) for n in ['accessibility', 'dom:ElementInternals', 'dom:CustomElementRegistry']}
    p.load(PAGE, standalone=False)
    callback = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int32)(lambda *a: None)
    p.bind('rv_host_set_accessibility', I, [P, I, ctypes.c_void_p, P])(p.host, 1, ctypes.cast(callback, ctypes.c_void_p), None)
    node_ax = p.bind('rv_node_ax', P, [P])
    ax_string = p.bind('rv_ax_string', I, [P, I, P, I, ctypes.POINTER(I)])
    ax_release = p.bind('rv_ax_release', None, [P])
    by_id = p.bind('rv_document_get_element_by_id', P, [P, ctypes.c_char_p])
    set_attr = p.bind('rv_element_set_attribute', I, [P, ctypes.c_char_p, ctypes.c_char_p])
    get_active = p.bind('rv_dom_element_get_aria_active_descendant_element', I, [P, ctypes.POINTER(P)])
    set_active = p.bind('rv_dom_element_set_aria_active_descendant_element', I, [P, P])
    nodes = {k: by_id(p.host, k.encode()) for k in ['l1', 'l2', 'd1', 'b', 'list', 'o1', 'o2', 't', 'i']}

    def text(axn, prop):
        buf, n = ctypes.create_string_buffer(256), I()
        status = ax_string(axn, prop, buf, 256, ctypes.byref(n))
        return buf.raw[:n.value].decode() if status == 0 else ('status', status)

    def ax(key):
        p.update()
        axn = node_ax(nodes[key])
        if not axn:
            return None
        try:
            return {'role': text(axn, ROLE_NAME), 'name': text(axn, NAME), 'description': text(axn, DESCRIPTION)}
        finally:
            ax_release(axn)

    def step(name, action, keys):
        result = action()
        out['steps'].append({'name': name, 'result': result, 'ax': {k: ax(k) for k in keys}})

    step('custom element with role/aria attributes (no definition)', lambda: None, ['t'])
    step('aria-labelledby="l2 l1"', lambda: set_attr(nodes['b'], b'aria-labelledby', b'l2 l1'), ['b'])
    step('aria-describedby="d1"', lambda: set_attr(nodes['b'], b'aria-describedby', b'd1'), ['b'])

    def active(target):
        status = set_active(nodes['list'], nodes[target] if target else None)
        got = P()
        read = get_active(nodes['list'], ctypes.byref(got))
        same = None
        if got:
            same = p.bind('rv_node_equals', I, [P, P])(got, nodes[target]) if target and hasattr(p.library, 'rv_node_equals') else (got.value == nodes[target] if target else False)
            p.bind('rv_node_release', None, [P])(got)
        attribute = p.text('rv_dom_element_get_attribute', [P, ctypes.c_char_p], nodes['list'], b'aria-activedescendant')
        return {'set': status, 'get': read, 'sameNode': same, 'attribute': attribute}
    step('ariaActiveDescendantElement = o2', lambda: active('o2'), ['list'])
    step('ariaActiveDescendantElement = null', lambda: active(None), ['list'])
    for n in nodes.values():
        p.bind('rv_node_release', None, [P])(n)
    p.bind('rv_host_set_accessibility', I, [P, I, ctypes.c_void_p, P])(p.host, 0, None, None)
Path(sys.argv[2]).write_text(json.dumps(out, indent=1) + '\n')
print(json.dumps(out, indent=1))
