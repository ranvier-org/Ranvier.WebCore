import argparse
import ctypes
import math
import os
from pathlib import Path
import sys
import threading


def verify(native_directory):
    directory = Path(native_directory).resolve()
    filename = {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')
    search = os.add_dll_directory(str(directory)) if sys.platform == 'win32' else None
    library = ctypes.CDLL(str(directory / filename))
    pointer, integer, unsigned, number = ctypes.c_void_p, ctypes.c_int32, ctypes.c_uint32, ctypes.c_double
    retained = []
    assertions = 0

    class PointInit(ctypes.Structure):
        _fields_ = [('size', unsigned), ('x', number), ('y', number), ('z', number), ('w', number)]

    class RectInit(ctypes.Structure):
        _fields_ = [('size', unsigned), ('x', number), ('y', number), ('width', number), ('height', number)]

    class QuadInit(ctypes.Structure):
        _fields_ = [('size', unsigned)] + [(name, ctypes.POINTER(PointInit)) for name in ['p1', 'p2', 'p3', 'p4']]

    def bind(name, result, arguments):
        function = getattr(library, name)
        function.restype, function.argtypes = result, arguments
        return function

    create_point = bind('rv_dom_dom_point_create', integer, [pointer] + [number] * 4 + [ctypes.POINTER(pointer)])

    def expect(condition, label):
        nonlocal assertions
        assertions += 1
        if not condition:
            raise AssertionError(label)

    def call(name, arguments, *values):
        status = bind(name, integer, arguments)(*values)
        expect(status == 0, f'{name}: status {status}')

    def handle(name, arguments, values, release):
        result = pointer()
        call(name, arguments + [ctypes.POINTER(pointer)], *values, ctypes.byref(result))
        expect(bool(result.value), name + ': nonnull result')
        retained.append((release, result.value))
        return result.value

    def read(root, target, field):
        result = number()
        call(f'rv_dom_dom_{root}_read_only_get_{field}', [pointer, ctypes.POINTER(number)], target, ctypes.byref(result))
        return result.value

    def values(root, target, fields):
        return tuple(read(root, target, field) for field in fields)

    def kind(root, target):
        buffer, length = ctypes.create_string_buffer(64), integer()
        call(f'rv_dom_dom_{root}_read_only_get_interface_name', [pointer, pointer, integer, ctypes.POINTER(integer)], target, buffer, len(buffer), ctypes.byref(length))
        return buffer.raw[:length.value].decode('utf-8')

    def point(x=0, y=0, z=0, w=1):
        return PointInit(ctypes.sizeof(PointInit), x, y, z, w)

    def rect(x=0, y=0, width=0, height=0):
        return RectInit(ctypes.sizeof(RectInit), x, y, width, height)

    host = bind('rv_host_create', pointer, [integer, integer])(320, 240)
    expect(bool(host), 'host creation')
    try:
        body = bind('rv_document_body', pointer, [pointer])(host)
        retained.append(('rv_node_release', body))
        document = handle('rv_dom_node_get_owner_document', [pointer], [body], 'rv_node_release')
        for root, factory, fields, defaults in [
            ('point', 'from_point', ['x', 'y', 'z', 'w'], (0, 0, 0, 1)),
            ('rect', 'from_rect', ['x', 'y', 'width', 'height'], (0, 0, 0, 0)),
        ]:
            for readonly in [False, True]:
                name = root + ('_read_only' if readonly else '')
                value = handle(f'rv_dom_dom_{name}_{factory}', [pointer, pointer], [document, None], f'rv_dom_dom_{root}_read_only_release')
                expect(values(root, value, fields) == defaults, name + ': factory defaults')
                expect(kind(root, value) == 'DOM' + root.title() + ('ReadOnly' if readonly else ''), name + ': runtime type')
                setter = bind(f'rv_dom_dom_{root}_set_{fields[0]}', integer, [pointer, number])
                expect(setter(value, 41.5) == (-11 if readonly else 0), name + ': mutable access policy')
                expect(read(root, value, fields[0]) == (defaults[0] if readonly else 41.5), name + ': mutable write result')
                components = (1.125, -2.25, 16777217.5, 0.000000000000003125)
                constructed = handle(f'rv_dom_dom_{name}_create', [pointer] + [number] * 4,
                                     [document, *components], f'rv_dom_dom_{root}_read_only_release')
                expect(values(root, constructed, fields) == components, name + ': constructor component precision')
                expect(kind(root, constructed) == 'DOM' + root.title() + ('ReadOnly' if readonly else ''), name + ': constructor runtime type')

        coordinates = (16777217.125, -0.00000000000003125, 9.25, -2.5)
        mutable = handle('rv_dom_dom_point_create', [pointer] + [number] * 4, [document, *coordinates], 'rv_dom_dom_point_read_only_release')
        expect(values('point', mutable, ['x', 'y', 'z', 'w']) == coordinates, 'point doubles remain exact')
        source_point = point(*coordinates)
        copied = handle('rv_dom_dom_point_from_point', [pointer, pointer], [document, ctypes.byref(source_point)], 'rv_dom_dom_point_read_only_release')
        source_point.x = 999
        expect(read('point', copied, 'x') == coordinates[0], 'fromPoint copies input')
        for field, value in zip(['x', 'y', 'z', 'w'], [float('inf'), -float('inf'), float('nan'), -0.0]):
            call(f'rv_dom_dom_point_set_{field}', [pointer, number], mutable, value)
            actual = read('point', mutable, field)
            expect(math.isnan(actual) if math.isnan(value) else actual == value, 'unrestricted point component ' + field)
        expect(math.copysign(1, read('point', mutable, 'w')) == -1, 'negative zero preserved')

        source_rect = rect(10.5, 20.25, -4.25, -8.125)
        rectangle = handle('rv_dom_dom_rect_from_rect', [pointer, pointer], [document, ctypes.byref(source_rect)], 'rv_dom_dom_rect_read_only_release')
        source_rect.x = 900
        expect(values('rect', rectangle, ['x', 'y', 'width', 'height', 'left', 'top', 'right', 'bottom']) ==
               (10.5, 20.25, -4.25, -8.125, 6.25, 12.125, 10.5, 20.25), 'negative rect extents and independent copy')
        call('rv_dom_dom_rect_set_width', [pointer, number], rectangle, 16777217.125)
        expect(read('rect', rectangle, 'width') == 16777217.125, 'rect mutable double precision')
        call('rv_dom_dom_rect_set_height', [pointer, number], rectangle, float('nan'))
        expect(math.isnan(read('rect', rectangle, 'top')) and math.isnan(read('rect', rectangle, 'bottom')), 'rect NaN bounds propagate')
        for field, value in [('x', -3.25), ('y', 6.125), ('width', -8.5), ('height', 4.25)]:
            call(f'rv_dom_dom_rect_set_{field}', [pointer, number], rectangle, value)
            expect(read('rect', rectangle, field) == value, 'mutable rect field ' + field)
        expect(values('rect', rectangle, ['left', 'top', 'right', 'bottom']) == (-11.75, 6.125, -3.25, 10.375), 'rect bounds follow every setter')

        empty_quad = handle('rv_dom_dom_quad_create', [pointer] * 5, [document, None, None, None, None], 'rv_dom_dom_quad_release')
        for index in range(1, 5):
            empty_point = handle(f'rv_dom_dom_quad_get_p{index}', [pointer], [empty_quad], 'rv_dom_dom_point_read_only_release')
            expect(values('point', empty_point, ['x', 'y', 'z', 'w']) == (0, 0, 0, 1), 'quad constructor default point ' + str(index))

        inputs = [point(1.5, 2.5), point(6.5, 2.5), point(6.5, 7.5), point(1.5, 7.5)]
        quad = handle('rv_dom_dom_quad_create', [pointer] * 5, [document] + [ctypes.byref(item) for item in inputs], 'rv_dom_dom_quad_release')
        inputs[0].x = 1234
        first = handle('rv_dom_dom_quad_get_p1', [pointer], [quad], 'rv_dom_dom_point_read_only_release')
        again = handle('rv_dom_dom_quad_get_p1', [pointer], [quad], 'rv_dom_dom_point_read_only_release')
        expect(first == again and kind('point', first) == 'DOMPoint', 'quad same-object mutable point')
        expect(values('point', first, ['x', 'y', 'z', 'w']) == (1.5, 2.5, 0, 1), 'quad copies point input')
        old_bounds = handle('rv_dom_dom_quad_get_bounds', [pointer], [quad], 'rv_dom_dom_rect_read_only_release')
        call('rv_dom_dom_point_set_x', [pointer, number], first, -4.5)
        new_bounds = handle('rv_dom_dom_quad_get_bounds', [pointer], [quad], 'rv_dom_dom_rect_read_only_release')
        expect(old_bounds != new_bounds, 'bounds are new objects')
        expect(values('rect', old_bounds, ['x', 'y', 'width', 'height']) == (1.5, 2.5, 5, 5), 'old bounds are snapshots')
        expect(values('rect', new_bounds, ['x', 'y', 'width', 'height']) == (-4.5, 2.5, 11, 5), 'fresh bounds include point mutation')

        source_rect = rect(10, 20, -4, -8)
        from_rect = handle('rv_dom_dom_quad_from_rect', [pointer, pointer], [document, ctypes.byref(source_rect)], 'rv_dom_dom_quad_release')
        for index, expected in enumerate([(10, 20), (6, 20), (6, 12), (10, 12)], 1):
            corner = handle(f'rv_dom_dom_quad_get_p{index}', [pointer], [from_rect], 'rv_dom_dom_point_read_only_release')
            expect(values('point', corner, ['x', 'y']) == expected, 'quad fromRect corner ' + str(index))

        partial = point(3.125, 99, 99, 99)
        partial.size = PointInit.y.offset
        source_quad = QuadInit()
        source_quad.size = ctypes.sizeof(QuadInit)
        source_quad.p1 = ctypes.pointer(partial)
        copied_quad = handle('rv_dom_dom_quad_from_quad', [pointer, pointer], [document, ctypes.byref(source_quad)], 'rv_dom_dom_quad_release')
        partial.x = 999
        corner = handle('rv_dom_dom_quad_get_p1', [pointer], [copied_quad], 'rv_dom_dom_point_read_only_release')
        expect(values('point', corner, ['x', 'y', 'z', 'w']) == (3.125, 0, 0, 1), 'short nested dictionary preserves defaults and copies present fields')
        corner2 = handle('rv_dom_dom_quad_get_p2', [pointer], [copied_quad], 'rv_dom_dom_point_read_only_release')
        expect(values('point', corner2, ['x', 'y', 'z', 'w']) == (0, 0, 0, 1), 'null nested dictionary keeps engine defaults')
        source_quad.size = QuadInit.p1.offset
        truncated_quad = handle('rv_dom_dom_quad_from_quad', [pointer, pointer], [document, ctypes.byref(source_quad)], 'rv_dom_dom_quad_release')
        corner3 = handle('rv_dom_dom_quad_get_p1', [pointer], [truncated_quad], 'rv_dom_dom_point_read_only_release')
        expect(values('point', corner3, ['x', 'y', 'z', 'w']) == (0, 0, 0, 1), 'short parent never reads nested field')

        retained_pointer = bind('rv_dom_dom_point_read_only_retain', pointer, [pointer])(first)
        retained.append(('rv_dom_dom_point_read_only_release', retained_pointer))
        expect(retained_pointer == first, 'explicit retain preserves identity')
        retained.remove(('rv_dom_dom_quad_release', quad))
        bind('rv_dom_dom_quad_release', None, [pointer])(quad)
        call('rv_dom_dom_point_set_y', [pointer, number], retained_pointer, 42.25)
        expect(read('point', retained_pointer, 'y') == 42.25, 'point remains mutable after quad release')

        null_result = pointer()
        expect(create_point(None, 0, 0, 0, 1, ctypes.byref(null_result)) == -1, 'null context rejected')
        expect(create_point(body, 0, 0, 0, 1, ctypes.byref(null_result)) == -11, 'non-document context rejected')
        statuses = []
        def worker():
            result = pointer()
            statuses.append(create_point(document, 0, 0, 0, 1, ctypes.byref(result)))
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        expect(statuses == [-2], 'wrong thread rejected')
    finally:
        for release, value in reversed(retained):
            bind(release, None, [pointer])(value)
        bind('rv_host_destroy', None, [pointer])(host)
        if search is not None:
            search.close()
    if assertions != 260:
        raise AssertionError(f'Expected 260 geometry assertions, observed {assertions}')
    print(f'PASS geometry values: {assertions} assertions', flush=True)
    return assertions


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', '--native-dir', dest='native_directory', required=True)
    verify(parser.parse_args().native_directory)
