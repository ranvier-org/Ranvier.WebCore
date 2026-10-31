import argparse
import ctypes
import math
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utf8_inputs import Utf8, bind as bind_utf8


def verify(native_directory):
    directory = Path(native_directory).resolve()
    filename = {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')
    search = os.add_dll_directory(str(directory)) if sys.platform == 'win32' else None
    library = ctypes.CDLL(str(directory / filename))
    pointer, integer, single, double = ctypes.c_void_p, ctypes.c_int32, ctypes.c_float, ctypes.c_double
    assertions = 0
    retained = []

    def bind(name, result, arguments):
        return bind_utf8(library, name, result, arguments)

    def expect(condition, label):
        nonlocal assertions
        assertions += 1
        if not condition:
            raise AssertionError(label)

    def call(name, arguments, *values):
        status = bind(name, integer, arguments)(*values)
        expect(status == 0, name + ': ' + str(status))

    def handle(name, target, root):
        result = pointer()
        call(name, [pointer, ctypes.POINTER(pointer)], target, ctypes.byref(result))
        expect(bool(result.value), name + ': nonnull')
        retained.append(('rv_dom_' + root + '_release', result.value))
        return result.value

    def values(root, target, fields, scalar):
        result = []
        for field in fields:
            value = scalar()
            call('rv_dom_' + root + '_get_' + field, [pointer, ctypes.POINTER(scalar)], target, ctypes.byref(value))
            result.append(value.value)
        return result

    def close(actual, expected, label):
        expect(len(actual) == len(expected) and all(math.isclose(a, b, abs_tol=0.002, rel_tol=0) for a, b in zip(actual, expected)), label + ': ' + str(actual) + ' expected ' + str(expected))

    host = bind('rv_host_create', pointer, [integer, integer])(1000, 800)
    expect(bool(host), 'view-controls host')
    try:
        for standalone, style, view_box in [
            (True, '', '0 0 500 300'),
            (False, '', '0 0 240 160'),
            (False, 'border:7px solid black;padding:11px;', '0 0 240 160'),
            (False, 'border:7px solid black;padding:11px;zoom:1.5;', '0 0 120 80'),
            (False, 'border:7px solid black;padding:11px;transform:translate(40px,50px) rotate(30deg);transform-origin:0 0;', '0 0 120 80'),
            (False, 'border:7px solid black;padding:11px;zoom:1.5;transform:translate(40px,50px) rotate(30deg);transform-origin:0 0;', '0 0 120 80'),
        ]:
            size = 'width="500" height="300"' if standalone else 'width="240" height="160"'
            svg = '<svg xmlns="http://www.w3.org/2000/svg" id="root" ' + size + ' viewBox="' + view_box + '" style="' + style + '"><rect id="box" x="10" y="20" width="20" height="10" fill="red"/></svg>'
            markup = svg if standalone else '<body style="margin:40px">' + svg + '</body>'
            call('rv_host_load_svg' if standalone else 'rv_host_load_html', [pointer, Utf8], host, markup.encode())
            def node(identifier):
                result = bind('rv_document_get_element_by_id', pointer, [pointer, Utf8])(host, identifier.encode())
                expect(bool(result), 'view-controls node ' + identifier)
                retained.append(('rv_node_release', result))
                return result
            root, box = node('root'), node('box')
            translate = handle('rv_dom_svgsvg_element_get_current_translate', root, 'svg_point')
            for scale, pan in ([(1, (0, 0)), (2, (20, 30)), (2, (60, 60))] if standalone else [(1, (0, 0)), (1, (20, 30))]):
                call('rv_dom_svgsvg_element_set_current_scale', [pointer, single], root, scale)
                for field, value in zip(['x', 'y'], pan):
                    call('rv_dom_svg_point_set_' + field, [pointer, single], translate, value)
                expect(bind('rv_host_update', integer, [pointer])(host) >= 0, 'view-controls render update')
                matrix = values('svg_matrix', handle('rv_dom_svg_graphics_element_get_screen_ctm', box, 'svg_matrix'), ['a', 'b', 'c', 'd', 'e', 'f'], double)
                bcr = values('dom_rect_read_only', handle('rv_dom_element_get_bounding_client_rect', box, 'dom_rect_read_only'), ['x', 'y', 'width', 'height'], double)
                a, b, c, d, e, f = matrix
                corners = [(a*x+c*y+e, b*x+d*y+f) for x in [10, 30] for y in [20, 30]]
                xs, ys = [p[0] for p in corners], [p[1] for p in corners]
                close(bcr, [min(xs), min(ys), max(xs)-min(xs), max(ys)-min(ys)], 'screen CTM/BCR coherence ' + repr((standalone, style, scale, pan)))
                pixels = (ctypes.c_uint8 * (1000*800*4))()
                call('rv_host_paint_rgba', [pointer, pointer, integer], host, pixels, len(pixels))
                x, y = round((a*20+c*25+e)*scale), round((b*20+d*25+f)*scale)
                expect(0 <= x < 1000 and 0 <= y < 800, 'mapped center inside host')
                expect(list(pixels[(y*1000+x)*4:(y*1000+x)*4+4]) == [255, 0, 0, 255], 'screen coordinates map to actual red paint ' + repr((standalone, style, scale, pan, x, y)))
            if standalone:
                call('rv_dom_svgsvg_element_set_current_scale', [pointer, single], root, 1)
            for release, value in reversed(retained):
                bind(release, None, [pointer])(value)
            retained.clear()
    finally:
        for release, value in reversed(retained):
            bind(release, None, [pointer])(value)
        bind('rv_host_destroy', None, [pointer])(host)
        if search:
            search.close()
    print(f'PASS SVG view controls: {assertions} assertions', flush=True)
    return assertions


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    verify(parser.parse_args().native_directory)
