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
    pointer, integer, number = ctypes.c_void_p, ctypes.c_int32, ctypes.c_double
    retained, buffers = [], []
    assertions = 0
    optional_fields = ['a', 'b', 'c', 'd', 'e', 'f', 'm11', 'm12', 'm21', 'm22', 'm41', 'm42']
    default_fields = ['m13', 'm14', 'm23', 'm24', 'm31', 'm32', 'm33', 'm34', 'm43', 'm44']
    components = [f'm{column}{row}' for column in range(1, 5) for row in range(1, 5)]
    identity = tuple(1 if column == row else 0 for column in range(4) for row in range(4))

    class MatrixInit(ctypes.Structure):
        _fields_ = [('size', ctypes.c_uint32)] + [(name, ctypes.POINTER(number)) for name in optional_fields] + [(name, number) for name in default_fields] + [('is2_d', ctypes.POINTER(integer))]

    class PointInit(ctypes.Structure):
        _fields_ = [('size', ctypes.c_uint32)] + [(name, number) for name in ['x', 'y', 'z', 'w']]

    class Span(ctypes.Structure):
        _fields_ = [('data', pointer), ('length', integer)]

    class Sequence(ctypes.Structure):
        _fields_ = [('present', integer), ('count', integer), ('items', ctypes.POINTER(number))]

    class Input(ctypes.Structure):
        _fields_ = [('present', integer), ('tag', integer), ('text', Span), ('numbers', Sequence)]

    def bind(name, result, arguments):
        function = getattr(library, name)
        function.restype, function.argtypes = result, arguments
        return function

    create = bind('rv_dom_dom_matrix_create', integer, [pointer, pointer, ctypes.POINTER(pointer)])

    def expect(condition, label):
        nonlocal assertions
        assertions += 1
        if not condition:
            raise AssertionError(label)

    def call(name, arguments, *values):
        status = bind(name, integer, arguments)(*values)
        expect(status == 0, f'{name}: status {status}')

    def handle(name, arguments, values, release='rv_dom_dom_matrix_read_only_release'):
        result = pointer()
        call(name, arguments + [ctypes.POINTER(pointer)], *values, ctypes.byref(result))
        expect(bool(result.value), name + ': nonnull result')
        retained.append((release, result.value))
        return result.value

    def matrix_init(**values):
        result = MatrixInit()
        result.size = ctypes.sizeof(MatrixInit)
        result.m33 = result.m44 = 1
        for name, value in values.items():
            if name in optional_fields or name == 'is2_d':
                storage = integer(value) if name == 'is2_d' else number(value)
                buffers.append(storage)
                setattr(result, name, ctypes.pointer(storage))
            else:
                setattr(result, name, value)
        return result

    def input_value(value):
        if value is None:
            return None
        result = Input(1, 1 if isinstance(value, str) else 2)
        if isinstance(value, str):
            encoded = value.encode('utf-8')
            storage = ctypes.create_string_buffer(encoded)
            buffers.append(storage)
            result.text = Span(ctypes.cast(storage, pointer), len(encoded))
        else:
            storage = (number * len(value))(*value)
            buffers.append(storage)
            result.numbers = Sequence(1, len(value), storage)
        buffers.append(result)
        return ctypes.byref(result)

    def construct(value=None, readonly=False):
        return handle('rv_dom_dom_matrix' + ('_read_only' if readonly else '') + '_create',
                      [pointer, pointer], [document, input_value(value)])

    def read(target, field, boolean=False):
        result = integer() if boolean else number()
        call('rv_dom_dom_matrix_read_only_get_' + field, [pointer, ctypes.POINTER(type(result))], target, ctypes.byref(result))
        return result.value

    def snapshot(target):
        return tuple(read(target, field) for field in components)

    def affine(target):
        return tuple(read(target, field) for field in ['a', 'b', 'c', 'd', 'e', 'f'])

    def transformed(target, point=None):
        result = handle('rv_dom_dom_matrix_read_only_transform_point', [pointer, pointer],
                        [target, ctypes.byref(point) if point is not None else None], 'rv_dom_dom_point_read_only_release')
        values = []
        for field in ['x', 'y', 'z', 'w']:
            value = number()
            call('rv_dom_dom_point_read_only_get_' + field, [pointer, ctypes.POINTER(number)], result, ctypes.byref(value))
            values.append(value.value)
        return tuple(values)

    def rejected(status, name):
        expect(status == -3, 'engine exception status: ' + name)
        buffer, length = ctypes.create_string_buffer(256), integer()
        call('rv_last_exception', [integer, pointer, integer, ctypes.POINTER(integer)], 0, buffer, len(buffer), ctypes.byref(length))
        expect(buffer.raw[:length.value].decode() == name, 'exact exception: ' + name)

    def serialize(target):
        buffer, length = ctypes.create_string_buffer(4096), integer()
        call('rv_dom_dom_matrix_read_only_to_string', [pointer, pointer, integer, ctypes.POINTER(integer)],
             target, buffer, len(buffer), ctypes.byref(length))
        return buffer.raw[:length.value].decode('utf-8')

    host = bind('rv_host_create', pointer, [integer, integer])(320, 240)
    expect(bool(host), 'host creation')
    try:
        body = bind('rv_document_body', pointer, [pointer])(host)
        retained.append(('rv_node_release', body))
        document = handle('rv_dom_node_get_owner_document', [pointer], [body], 'rv_node_release')
        for readonly in [False, True]:
            for source in [None, '', 'none']:
                value = construct(source, readonly)
                expect(snapshot(value) == identity and read(value, 'is2_d', True) == 1 and read(value, 'is_identity', True) == 1, 'identity constructor ' + repr(source))
            value = construct([2, 0, 0, 3, 10, 20], readonly)
            expect(affine(value) == (2, 0, 0, 3, 10, 20) and read(value, 'is2_d', True) == 1, 'six component initialization')
            setter = bind('rv_dom_dom_matrix_set_a', integer, [pointer, number])
            expect(setter(value, 5) == (-11 if readonly else 0), 'readonly mutation policy')
            expect(affine(value) == (2 if readonly else 5, 0, 0, 3, 10, 20), 'mutation policy preserves other components')
            value16 = construct(identity, readonly)
            expect(snapshot(value16) == identity and read(value16, 'is2_d', True) == 0, 'sixteen component identity stays 3D')
        output = pointer()
        for invalid in [[], [1], [1] * 7, [1] * 15, [1] * 17]:
            rejected(create(document, input_value(invalid), ctypes.byref(output)), 'TypeError')
        for invalid in ['translate(10%)', 'nonsense', 'matrix(1,2)']:
            rejected(create(document, input_value(invalid), ctypes.byref(output)), 'SyntaxError')
        rejected(create(document, input_value('matrix(1,0,0,1,0,0)\0invalid'), ctypes.byref(output)), 'SyntaxError')
        for malformed, expected in [(Input(0, 1), -1), (Input(1, 99), -9)]:
            expect(create(document, ctypes.byref(malformed), ctypes.byref(output)) == expected, 'present invalid union is not absence')
        expect(create(None, None, ctypes.byref(output)) == -1, 'null matrix document rejected')
        expect(create(body, None, ctypes.byref(output)) == -11, 'matrix document brand checked')
        literal = construct('matrix(1, 2, 3, 4, 5, 6)')
        expect(affine(literal) == (1, 2, 3, 4, 5, 6), 'literal matrix string')
        roundtrip_literal = construct(serialize(literal))
        expect(snapshot(roundtrip_literal) == snapshot(literal), 'finite serialization roundtrip')
        parsed = construct('translate(10px, 20px) scale(2, 3)')
        expect(affine(parsed) == (2, 0, 0, 3, 10, 20), 'full transform list parser')
        expect(transformed(parsed, PointInit(ctypes.sizeof(PointInit), 1, 1, 0, 1)) == (12, 23, 0, 1), '2D point transformation')
        inverse = handle('rv_dom_dom_matrix_read_only_inverse', [pointer], [parsed])
        roundtrip = transformed(inverse, PointInit(ctypes.sizeof(PointInit), 12, 23, 0, 1))
        expect(all(math.isclose(actual, expected, abs_tol=1e-12) for actual, expected in zip(roundtrip, (1, 1, 0, 1))), 'inverse point roundtrip')

        for premultiply, expected in [(False, (2, 0, 0, 3, 10, 20)), (True, (2, 0, 0, 3, 20, 60))]:
            target = construct([1, 0, 0, 1, 10, 20])
            scale = matrix_init(a=2, d=3)
            method = 'pre_multiply_self' if premultiply else 'multiply_self'
            result = handle('rv_dom_dom_matrix_' + method, [pointer, pointer], [target, ctypes.byref(scale)])
            expect(result == target and affine(target) == expected, 'ordered self multiply ' + method)
        original = construct([1, 0, 0, 1, 10, 20], True)
        original_snapshot = snapshot(original)
        scale = matrix_init(a=2, d=3)
        result = handle('rv_dom_dom_matrix_read_only_multiply', [pointer, pointer], [original, ctypes.byref(scale)])
        expect(result != original and affine(result) == (2, 0, 0, 3, 10, 20) and snapshot(original) == original_snapshot, 'immutable multiply copies')

        three_d = (2, 0, 0, 0.5, 0, 3, 0, 0, 0, 0, 4, 0, 5, 6, 7, 2)
        matrix3d = construct(three_d)
        literal3d = construct('matrix3d(' + ','.join(str(value) for value in three_d) + ')')
        expect(snapshot(literal3d) == three_d and read(literal3d, 'is2_d', True) == 0, 'literal matrix3d string')
        expect(serialize(literal3d).startswith('matrix3d('), '3D serialization uses matrix3d')
        expect(transformed(matrix3d, PointInit(ctypes.sizeof(PointInit), 1, 2, 3, 4)) == (22, 30, 40, 8.5), 'homogeneous 3D transform does not divide w')
        expect(transformed(matrix3d) == (5, 6, 7, 2), 'default point has w=1')
        precise = construct([16777217.125, 0.000000000000003125, 0, 1, 0, 0])
        expect(read(precise, 'a') == 16777217.125 and read(precise, 'b') == 0.000000000000003125, 'matrix double precision')
        for readonly in [False, True]:
            source = matrix_init(a=2, m11=2, e=9)
            value = handle('rv_dom_dom_matrix' + ('_read_only' if readonly else '') + '_from_matrix', [pointer, pointer], [document, ctypes.byref(source)])
            expect(affine(value) == (2, 0, 0, 1, 9, 0), 'dictionary aliases/defaults')
        for source in [matrix_init(a=1, m11=1.0000000000000002), matrix_init(is2_d=1, m13=1)]:
            rejected(bind('rv_dom_dom_matrix_from_matrix', integer, [pointer, pointer, ctypes.POINTER(pointer)])(document, ctypes.byref(source), ctypes.byref(output)), 'TypeError')
            before = snapshot(parsed), read(parsed, 'is2_d', True)
            rejected(bind('rv_dom_dom_matrix_multiply_self', integer, [pointer, pointer, ctypes.POINTER(pointer)])(parsed, ctypes.byref(source), ctypes.byref(output)), 'TypeError')
            expect((snapshot(parsed), read(parsed, 'is2_d', True)) == before, 'invalid multiply preserves every component and flag')
        for source in [matrix_init(a=float('nan'), m11=float('nan')), matrix_init(a=-0.0, m11=0.0)]:
            value = handle('rv_dom_dom_matrix_from_matrix', [pointer, pointer], [document, ctypes.byref(source)])
            expect(math.isnan(read(value, 'a')) if math.isnan(source.a.contents.value) else read(value, 'a') == 0, 'same-value-zero aliases accepted')

        sticky = construct()
        call('rv_dom_dom_matrix_set_m13', [pointer, number], sticky, 2)
        call('rv_dom_dom_matrix_set_m13', [pointer, number], sticky, 0)
        expect(read(sticky, 'is2_d', True) == 0, 'is2D remains false after restoring 3D component')
        setter = bind('rv_dom_dom_matrix_set_matrix_value', integer, [pointer, pointer, pointer, integer, ctypes.POINTER(pointer)])
        before = snapshot(matrix3d), read(matrix3d, 'is2_d', True)
        invalid = ctypes.create_string_buffer(b'translate(20%)')
        rejected(setter(matrix3d, document, invalid, len(invalid.value), ctypes.byref(output)), 'SyntaxError')
        expect((snapshot(matrix3d), read(matrix3d, 'is2_d', True)) == before, 'invalid setMatrixValue preserves all components and flag')
        valid = ctypes.create_string_buffer(b'translate(7px, 9px)')
        reset = handle('rv_dom_dom_matrix_set_matrix_value', [pointer, pointer, pointer, integer], [matrix3d, document, valid, len(valid.value)])
        expect(reset == matrix3d and affine(reset) == (1, 0, 0, 1, 7, 9) and read(reset, 'is2_d', True) == 1, 'setMatrixValue returns self and resets 2D flag')

        point_source = handle('rv_dom_dom_point_create', [pointer] + [number] * 4, [document, 2, 3, 4, 1], 'rv_dom_dom_point_read_only_release')
        point_matrix = matrix_init(a=2, d=3, e=5, f=7)
        point_result = handle('rv_dom_dom_point_read_only_matrix_transform', [pointer, pointer], [point_source, ctypes.byref(point_matrix)], 'rv_dom_dom_point_read_only_release')
        for target, expected in [(point_source, (2, 3, 4, 1)), (point_result, (9, 16, 4, 1))]:
            actual = []
            for field in ['x', 'y', 'z', 'w']:
                value = number()
                call('rv_dom_dom_point_read_only_get_' + field, [pointer, ctypes.POINTER(number)], target, ctypes.byref(value))
                actual.append(value.value)
            expect(tuple(actual) == expected, 'point matrixTransform result/copy')

        zero = number(0)
        buffers.append(zero)
        transforms = [
            ('translate', [number] * 3, [2, 3, 4], (1, 1, 1, 1), (3, 4, 5, 1)),
            ('scale', [number, pointer] + [number] * 4, [2, None, 1, 0, 0, 0], (1, 1, 1, 1), (2, 2, 1, 1)),
            ('scale', [number, pointer] + [number] * 4, [2, ctypes.byref(zero), 1, 0, 0, 0], (1, 1, 1, 1), (2, 0, 1, 1)),
            ('scale3d', [number] * 4, [2, 0, 0, 0], (1, 1, 1, 1), (2, 2, 2, 1)),
            ('rotate', [number, pointer, pointer], [90, None, None], (1, 0, 0, 1), (0, 1, 0, 1)),
            ('rotate', [number, pointer, pointer], [90, ctypes.byref(zero), ctypes.byref(zero)], (0, 1, 0, 1), (0, 0, 1, 1)),
            ('rotate_from_vector', [number] * 2, [0, 1], (1, 0, 0, 1), (0, 1, 0, 1)),
            ('rotate_axis_angle', [number] * 4, [0, 0, 1, 90], (1, 0, 0, 1), (0, 1, 0, 1)),
            ('skew_x', [number], [45], (1, 1, 0, 1), (2, 1, 0, 1)),
            ('skew_y', [number], [45], (1, 1, 0, 1), (1, 2, 0, 1)),
        ]
        for name, arguments, inputs, source_point, expected in transforms:
            for mutable in [False, True]:
                target = construct(readonly=not mutable)
                function = 'rv_dom_dom_matrix_' + (name + '_self' if mutable else 'read_only_' + name)
                result = handle(function, [pointer] + arguments, [target, *inputs])
                expect((result == target) == mutable, 'transform result identity: ' + function)
                actual = transformed(result, PointInit(ctypes.sizeof(PointInit), *source_point))
                expect(all(math.isclose(actual_value, expected_value, abs_tol=1e-12) for actual_value, expected_value in zip(actual, expected)), 'transform numeric result: ' + function)
                if not mutable:
                    expect(snapshot(target) == identity, 'immutable transform original unchanged: ' + function)
        for name, expected in [('flip_x', (-1, 1, 0, 1)), ('flip_y', (1, -1, 0, 1))]:
            target = construct(readonly=True)
            result = handle('rv_dom_dom_matrix_read_only_' + name, [pointer], [target])
            expect(transformed(result, PointInit(ctypes.sizeof(PointInit), 1, 1, 0, 1)) == expected and snapshot(target) == identity, name + ' immutable result')
        target = construct(readonly=True)
        result = handle('rv_dom_dom_matrix_read_only_scale_non_uniform', [pointer, number, number], [target, 2, 3])
        expect(transformed(result, PointInit(ctypes.sizeof(PointInit), 1, 1, 1, 1)) == (2, 3, 1, 1), 'legacy non-uniform scale')
        singular = construct([0, 0, 0, 0, 0, 0])
        inverted = handle('rv_dom_dom_matrix_invert_self', [pointer], [singular])
        expect(inverted == singular and all(math.isnan(value) for value in snapshot(singular)) and read(singular, 'is2_d', True) == 0, 'singular inverse yields NaNs and preserves self identity')
        buffer, length = ctypes.create_string_buffer(1024), integer()
        rejected(bind('rv_dom_dom_matrix_read_only_to_string', integer, [pointer, pointer, integer, ctypes.POINTER(integer)])(singular, buffer, len(buffer), ctypes.byref(length)), 'InvalidStateError')

        statuses = []
        def worker():
            result = pointer()
            statuses.append(create(document, None, ctypes.byref(result)))
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        expect(statuses == [-2], 'matrix factory thread enforced')
    finally:
        for release, value in reversed(retained):
            bind(release, None, [pointer])(value)
        bind('rv_host_destroy', None, [pointer])(host)
        if search is not None:
            search.close()
    if assertions != 1091:
        raise AssertionError(f'Expected 1091 matrix assertions, observed {assertions}')
    print(f'PASS matrix values: {assertions} assertions', flush=True)
    return assertions


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    verify(parser.parse_args().native_directory)
