import argparse
import ctypes
import math
import os
from pathlib import Path
import sys


def verify(native_directory):
    directory = Path(native_directory).resolve()
    filename = {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')
    search = os.add_dll_directory(str(directory)) if sys.platform == 'win32' else None
    library = ctypes.CDLL(str(directory / filename))
    pointer, integer, single, double = ctypes.c_void_p, ctypes.c_int32, ctypes.c_float, ctypes.c_double
    retained = []
    assertions = 0

    def bind(name, result, arguments):
        function = getattr(library, name)
        function.restype, function.argtypes = result, arguments
        return function

    def expect(condition, label):
        nonlocal assertions
        assertions += 1
        if not condition:
            raise AssertionError(label)

    def call(name, arguments, *values):
        expect(bind(name, integer, arguments)(*values) == 0, name)

    def handle(name, target, root):
        result = pointer()
        call(name, [pointer, ctypes.POINTER(pointer)], target, ctypes.byref(result))
        expect(bool(result.value), name + ': nonnull')
        retained.append(('rv_node_release' if root == 'node' else 'rv_dom_' + root + '_release', result.value))
        return result.value

    def values(root, target, fields, scalar):
        result = []
        for field in fields:
            value = scalar()
            call('rv_dom_' + root + '_get_' + field, [pointer, ctypes.POINTER(scalar)], target, ctypes.byref(value))
            result.append(value.value)
        return result

    def close(actual, expected, label):
        expect(len(actual) == len(expected) and all(math.isclose(a, b, abs_tol=0.002, rel_tol=0) for a, b in zip(actual, expected)), label + ': ' + str(actual))

    def text(target):
        buffer, length = ctypes.create_string_buffer(256), integer()
        call('rv_dom_svg_animated_string_get_base_val', [pointer, pointer, integer, ctypes.POINTER(integer)], target, buffer, 256, ctypes.byref(length))
        return buffer.value.decode()

    host = bind('rv_host_create', pointer, [integer, integer])(500, 300)
    expect(bool(host), 'animation variants host')
    try:
        markup = (Path(__file__).resolve().parents[1] / 'fixtures/svg-animation-variants.svg').read_bytes()
        call('rv_host_load_svg', [pointer, ctypes.c_char_p], host, markup)
        def node(identifier):
            result = bind('rv_document_get_element_by_id', pointer, [pointer, ctypes.c_char_p])(host, identifier.encode())
            expect(bool(result), 'actual concrete SVG node ' + identifier)
            retained.append(('rv_node_release', result))
            return result
        root = node('root')
        call('rv_dom_svgsvg_element_pause_animations', [pointer], root)
        call('rv_dom_svgsvg_element_set_current_time', [pointer, single], root, 0)
        pairs = [(node(kind), node(kind + 'Target')) for kind in ['motion', 'transform', 'set']]
        reference = handle('rv_dom_svgm_path_element_get_href', node('motionReference'), 'svg_animated_string')
        expect(text(reference) == '#motionPath', 'real mpath reference')
        for animation, target in pairs:
            expect(handle('rv_dom_svg_animation_element_get_target_element', animation, 'node') == target, 'concrete animation target identity')
            call('rv_dom_svg_animation_element_begin_element', [pointer], animation)
        call('rv_dom_svgsvg_element_set_current_time', [pointer, single], root, 1)
        motion = handle('rv_dom_svg_graphics_element_get_screen_ctm', pairs[0][1], 'svg_matrix')
        close(values('svg_matrix', motion, ['a', 'b', 'c', 'd', 'e', 'f'], double), [1, 0, 0, 1, 70, 30], 'animateMotion follows actual mpath midpoint')
        transform = handle('rv_dom_svg_graphics_element_get_screen_ctm', pairs[1][1], 'svg_matrix')
        close(values('svg_matrix', transform, ['a', 'b', 'c', 'd', 'e', 'f'], double), [math.sqrt(0.5), math.sqrt(0.5), -math.sqrt(0.5), math.sqrt(0.5), 0, 0], 'animateTransform actual rotation midpoint')
        set_bounds = handle('rv_dom_svg_graphics_element_get_b_box', pairs[2][1], 'svg_rect')
        close(values('svg_rect', set_bounds, ['x', 'y', 'width', 'height'], single), [350, 100, 10, 10], 'SVG set changes actual geometry')
        expect(bind('rv_host_update', integer, [pointer])(host) >= 0, 'animation variants update')
        pixels = (ctypes.c_uint8 * (500*300*4))()
        call('rv_host_paint_rgba', [pointer, pointer, integer], host, pixels, len(pixels))
        for x, y in [(75, 35), (355, 105), (141, 148)]:
            expect(list(pixels[(y*500+x)*4:(y*500+x)*4+4]) == [255, 0, 0, 255], 'concrete animation actual paint ' + str((x, y)))
        for animation, target in pairs:
            call('rv_dom_svg_animation_element_end_element', [pointer], animation)
        call('rv_dom_svgsvg_element_set_current_time', [pointer, single], root, 1.5)
        close(values('svg_matrix', handle('rv_dom_svg_graphics_element_get_screen_ctm', pairs[0][1], 'svg_matrix'), ['e', 'f'], double), [70, 30], 'motion end freezes actual matrix')
        bind('rv_host_destroy', None, [pointer])(host)
        host = None
        for release, value in list(reversed(retained)):
            if release == 'rv_node_release':
                bind(release, None, [pointer])(value)
                retained.remove((release, value))
        expect(text(reference) == '#motionPath', 'retained real mpath value after document disposal')
    finally:
        for release, value in reversed(retained):
            bind(release, None, [pointer])(value)
        if host:
            bind('rv_host_destroy', None, [pointer])(host)
        if search:
            search.close()
    print(f'PASS SVG animation variants: {assertions} assertions', flush=True)
    return assertions


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    verify(parser.parse_args().native_directory)
