import argparse
import ctypes
import json
import os
from pathlib import Path
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--native-directory', required=True)
args = parser.parse_args()
directory = Path(args.native_directory).resolve()
search = os.add_dll_directory(str(directory)) if sys.platform == 'win32' else None
library = ctypes.CDLL(str(directory / 'RanvierWebCoreHost.dll'))
webcore = ctypes.CDLL(str(directory / 'WebCore.dll'))
pointer, integer, single, double = ctypes.c_void_p, ctypes.c_int32, ctypes.c_float, ctypes.c_double
retained = []
def bind(name, result, arguments):
    f = getattr(library, name)
    f.restype, f.argtypes = result, arguments
    return f
load_svg = bind('rv_host_load_svg', integer, [pointer, ctypes.c_char_p])
def call(name, arguments, *values):
    status = bind(name, integer, arguments)(*values)
    assert status == 0, (name, status)
def handle(name, values, root):
    result = pointer()
    call(name, [pointer] * len(values) + [ctypes.POINTER(pointer)], *values, ctypes.byref(result))
    assert result.value, name
    retained.append(('rv_node_release' if root == 'node' else 'rv_dom_' + root + '_release', result.value))
    return result.value
def read(prefix, target, field, scalar=single):
    value = scalar()
    call('rv_dom_' + prefix + '_get_' + field, [pointer, ctypes.POINTER(scalar)], target, ctypes.byref(value))
    return value.value
host = bind('rv_host_create', pointer, [integer, integer])(500, 300)
assert host
try:
    svg = b'''<svg xmlns="http://www.w3.org/2000/svg" id="root" width="500" height="300" viewBox="0 0 500 300">
<view id="detail" viewBox="0 0 100 50"/>
<rect id="box" x="10" y="10" width="20" height="20" fill="red"/>
<script><![CDATA[document.getElementById('box').setAttribute('x','999');]]></script>
<foreignObject x="300" y="200" width="100" height="50"><div xmlns="http://www.w3.org/1999/xhtml"><script>document.getElementById('box').setAttribute('x','999');</script>safe</div></foreignObject>
</svg>'''
    assert load_svg(host, svg) == 0
    def node(identifier):
        item = bind('rv_document_get_element_by_id', pointer, [pointer, ctypes.c_char_p])(host, identifier.encode())
        assert item, identifier
        retained.append(('rv_node_release', item))
        return item
    root, box = node('root'), node('box')
    def snapshot(label):
        values = {}
        for operation in ['get_ctm', 'get_screen_ctm']:
            matrix = handle('rv_dom_svg_graphics_element_' + operation, [box], 'svg_matrix')
            values[operation] = [read('svg_matrix', matrix, field, double) for field in ['a', 'b', 'c', 'd', 'e', 'f']]
        values.update(label=label, currentScale=read('svgsvg_element', root, 'current_scale'))
        bounds = handle('rv_dom_element_get_bounding_client_rect', [box], 'dom_rect_read_only')
        values['bcr'] = [read('dom_rect_read_only', bounds, field, double) for field in ['x', 'y', 'width', 'height']]
        root_bounds = handle('rv_dom_element_get_bounding_client_rect', [root], 'dom_rect_read_only')
        values['rootBcr'] = [read('dom_rect_read_only', root_bounds, field, double) for field in ['x', 'y', 'width', 'height']]
        metrics = (double * 3)()
        probe = webcore.ranvier_svg_probe_window_metrics
        probe.restype, probe.argtypes = integer, [pointer, ctypes.POINTER(double)]
        assert probe(root, metrics) == 0
        values['window'] = dict(zip(['innerWidth', 'innerHeight', 'devicePixelRatio'], metrics))
        values['hostViewport'] = [500, 300]
        rgba = (ctypes.c_uint8 * (500 * 300 * 4))()
        call('rv_host_paint_rgba', [pointer, pointer, integer], host, rgba, len(rgba))
        values['pixels'] = {str((x, y)): list(rgba[(y * 500 + x) * 4:(y * 500 + x) * 4 + 4]) for x, y in [(15, 15), (25, 25), (45, 55), (85, 85)]}
        return values
    rows = [snapshot('initial')]
    call('rv_dom_svgsvg_element_set_current_scale', [pointer, single], root, 2)
    translate = handle('rv_dom_svgsvg_element_get_current_translate', [root], 'svg_point')
    call('rv_dom_svg_point_set_x', [pointer, single], translate, 20)
    call('rv_dom_svg_point_set_y', [pointer, single], translate, 30)
    assert bind('rv_host_update', integer, [pointer])(host) >= 0
    rows.append(snapshot('scaleTranslate'))
    call('rv_dom_svg_point_set_x', [pointer, single], translate, 60)
    call('rv_dom_svg_point_set_y', [pointer, single], translate, 60)
    assert bind('rv_host_update', integer, [pointer])(host) >= 0
    rows.append(snapshot('panAgain'))
    value = handle('rv_dom_svg_rect_element_get_x', [box], 'svg_animated_length')
    base = handle('rv_dom_svg_animated_length_get_base_val', [value], 'svg_length')
    output = {'rows': rows, 'scriptsEnabled': bind('rv_host_scripts_enabled', integer, [pointer])(host), 'vmEntryDisallowed': bind('rv_host_vm_entry_disallowed', integer, [pointer])(host), 'scriptGuardRectX': read('svg_length', base, 'value')}
    Path('artifacts/svg-standalone-native-metrics-' + ('before' if directory.parent.name.endswith('before') else 'after') + '.json').write_bytes((json.dumps(output, indent=2) + '\n').encode())
    print(json.dumps(output), flush=True)
finally:
    for release, item in reversed(retained):
        bind(release, None, [pointer])(item)
    bind('rv_host_destroy', None, [pointer])(host)
    if search:
        search.close()
