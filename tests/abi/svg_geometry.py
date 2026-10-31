import argparse
import ctypes
import math
import os
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utf8_inputs import Utf8, bind as bind_utf8


def verify(native_directory):
    directory = Path(native_directory).resolve()
    filename = {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')
    search = os.add_dll_directory(str(directory)) if sys.platform == 'win32' else None
    library = ctypes.CDLL(str(directory / filename))
    pointer, integer, unsigned = ctypes.c_void_p, ctypes.c_int32, ctypes.c_uint32
    single, double = ctypes.c_float, ctypes.c_double
    retained = []
    watches = []
    assertions = 0

    class PointInit(ctypes.Structure):
        _fields_ = [('size', unsigned), ('x', double), ('y', double), ('z', double), ('w', double)]

    class MatrixInit(ctypes.Structure):
        _fields_ = [('size', unsigned)] + [(field, ctypes.POINTER(double)) for field in ['a', 'b', 'c', 'd', 'e', 'f', 'm11', 'm12', 'm21', 'm22', 'm41', 'm42']]

    def bind(name, result, arguments):
        return bind_utf8(library, name, result, arguments)

    bbox = bind('rv_dom_svg_graphics_element_get_b_box', integer, [pointer, ctypes.POINTER(pointer)])

    def expect(condition, label):
        nonlocal assertions
        assertions += 1
        if not condition:
            raise AssertionError(label)

    def call(name, arguments, *values):
        status = bind(name, integer, arguments)(*values)
        expect(status == 0, f'{name}: status {status}')

    def handle(name, arguments, values, root):
        result = pointer()
        call(name, arguments + [ctypes.POINTER(pointer)], *values, ctypes.byref(result))
        expect(bool(result.value), name + ': nonnull result')
        retained.append(('rv_node_release' if root == 'node' else 'rv_dom_' + root + '_release', result.value))
        return result.value

    def read(root, target, field, number=single):
        result = number()
        call(f'rv_dom_{root}_get_{field}', [pointer, ctypes.POINTER(number)], target, ctypes.byref(result))
        return result.value

    def rectangle(target):
        return tuple(read('svg_rect', target, field) for field in ['x', 'y', 'width', 'height'])

    def matrix(target):
        return tuple(read('svg_matrix', target, field, double) for field in ['a', 'b', 'c', 'd', 'e', 'f'])

    def close(actual, expected, label, tolerance=1e-6):
        expect(len(actual) == len(expected) and all(math.isclose(a, e, rel_tol=0, abs_tol=tolerance) for a, e in zip(actual, expected)), label + ': ' + str(actual))

    host = bind('rv_host_create', pointer, [integer, integer])(320, 240)
    expect(bool(host), 'host creation')
    try:
        body = bind('rv_document_body', pointer, [pointer])(host)
        retained.append(('rv_node_release', body))
        markup = b'''<svg id="root" width="200" height="100" viewBox="0 0 100 50" style="position:absolute;left:0;top:0">
<g id="group" transform="translate(10 20)"><rect id="box" x="1" y="2" width="3" height="4"/></g>
<path id="line" d="M0 0L100 0" stroke="black" fill="none"/>
<path id="curve" d="M0 0Q50 100 100 0" stroke="black" fill="none"/>
<path id="area" d="M0 0H20V20H0Z" fill="red" stroke="blue" stroke-width="2"/>
<text id="text" x="10 20" rotate="5 10">sample</text>
<polygon id="polygon" points="0,0 10,0 10,10"/>
<polyline id="polyline" points="1,2 3,4"/>
</svg>'''
        call('rv_dom_element_set_inner_html', [pointer, Utf8], body, markup)

        def node(identifier):
            value = bind('rv_document_get_element_by_id', pointer, [pointer, ctypes.c_char_p])(host, identifier.encode())
            expect(bool(value), 'find ' + identifier)
            retained.append(('rv_node_release', value))
            return value

        root, box, group = node('root'), node('box'), node('group')
        bounds = handle('rv_dom_svg_graphics_element_get_b_box', [pointer], [box], 'svg_rect')
        close(rectangle(bounds), (1, 2, 3, 4), 'bounds use local graphics coordinates')
        group_bounds = handle('rv_dom_svg_graphics_element_get_b_box', [pointer], [group], 'svg_rect')
        close(rectangle(group_bounds), (1, 2, 3, 4), 'nested group bounds')
        for operation in ['get_ctm', 'get_screen_ctm']:
            value = handle('rv_dom_svg_graphics_element_' + operation, [pointer], [box], 'svg_matrix')
            close(matrix(value), (2, 0, 0, 2, 20, 40), operation + ' includes viewBox and parent transform')

        view_box = handle('rv_dom_svgsvg_element_get_view_box', [pointer], [root], 'svg_animated_rect')
        base = handle('rv_dom_svg_animated_rect_get_base_val', [pointer], [view_box], 'svg_rect')
        close(rectangle(base), (0, 0, 100, 50), 'viewBox base value')
        call('rv_dom_svg_rect_set_width', [pointer, single], base, 200)
        resized = handle('rv_dom_svg_graphics_element_get_ctm', [pointer], [box], 'svg_matrix')
        close(matrix(resized), (1, 0, 0, 1, 10, 45), 'viewBox mutation updates actual CTM')
        aspect = handle('rv_dom_svgsvg_element_get_preserve_aspect_ratio', [pointer], [root], 'svg_animated_preserve_aspect_ratio')
        aspect_base = handle('rv_dom_svg_animated_preserve_aspect_ratio_get_base_val', [pointer], [aspect], 'svg_preserve_aspect_ratio')
        call('rv_dom_svg_preserve_aspect_ratio_set_align', [pointer, ctypes.c_uint16], aspect_base, 1)
        stretched = handle('rv_dom_svg_graphics_element_get_ctm', [pointer], [box], 'svg_matrix')
        close(matrix(stretched), (1, 0, 0, 2, 10, 40), 'preserveAspectRatio none updates scale')

        line, curve, area = node('line'), node('curve'), node('area')
        length = single()
        call('rv_dom_svg_geometry_element_get_total_length', [pointer, ctypes.POINTER(single)], line, ctypes.byref(length))
        expect(length.value == 100, 'line total length')
        middle = handle('rv_dom_svg_geometry_element_get_point_at_length', [pointer, single], [line, 50], 'svg_point')
        close(tuple(read('svg_point', middle, field) for field in ['x', 'y']), (50, 0), 'line midpoint')
        call('rv_dom_svg_geometry_element_get_total_length', [pointer, ctypes.POINTER(single)], curve, ctypes.byref(length))
        expect(147 < length.value < 149, 'quadratic curve actual length')
        curve_middle = handle('rv_dom_svg_geometry_element_get_point_at_length', [pointer, single], [curve, length.value / 2], 'svg_point')
        close(tuple(read('svg_point', curve_middle, field) for field in ['x', 'y']), (50, 50), 'curve midpoint', 0.01)

        for target, operation, x, y, expected in [
            (line, 'stroke', 50, 0, True), (line, 'stroke', 50, 4, False),
            (area, 'fill', 10, 10, True), (area, 'fill', 25, 10, False),
            (area, 'stroke', 0, 10, True), (area, 'stroke', 10, 10, False),
        ]:
            point = PointInit(ctypes.sizeof(PointInit), x, y, 0, 1)
            hit = integer()
            call('rv_dom_svg_geometry_element_is_point_in_' + operation,
                 [pointer, ctypes.POINTER(PointInit), ctypes.POINTER(integer)], target, ctypes.byref(point), ctypes.byref(hit))
            expect(bool(hit.value) == expected, operation + ' hit test in local coordinates')

        def value(factory):
            return handle('rv_dom_svgsvg_element_create_svg_' + factory, [pointer], [root], 'svg_' + factory)

        def set_value(kind, target, field, number, item):
            call('rv_dom_svg_' + kind + '_set_' + field, [pointer, number], target, item)

        def exception(name, arguments, values, expected):
            status = bind(name, integer, arguments)(*values)
            expect(status == -3, name + ': engine exception ' + str(status))
            buffer, size = ctypes.create_string_buffer(256), integer()
            call('rv_last_exception', [integer, pointer, integer, ctypes.POINTER(integer)], 0, buffer, len(buffer), ctypes.byref(size))
            expect(buffer.value.decode() == expected, name + ': ' + repr(buffer.value))

        def text_value(name, target):
            buffer, size = ctypes.create_string_buffer(256), integer()
            call(name, [pointer, pointer, integer, ctypes.POINTER(integer)], target, buffer, len(buffer), ctypes.byref(size))
            return buffer.value.decode()

        number, length_value, angle_value = value('number'), value('length'), value('angle')
        point_value, matrix_value, rect_value, transform_value = (value(kind) for kind in ['point', 'matrix', 'rect', 'transform'])
        expect(read('svg_number', number, 'value') == 0, 'number default')
        expect(read('svg_length', length_value, 'value') == 0 and read('svg_length', length_value, 'unit_type', ctypes.c_uint16) == 1, 'length default number unit')
        expect(read('svg_angle', angle_value, 'value') == 0 and read('svg_angle', angle_value, 'unit_type', ctypes.c_uint16) == 1, 'angle default unspecified unit')
        close((read('svg_point', point_value, 'x'), read('svg_point', point_value, 'y')), (0, 0), 'point default')
        close(rectangle(rect_value), (0, 0, 0, 0), 'rect default')
        close(matrix(matrix_value), (1, 0, 0, 1, 0, 0), 'matrix default')
        expect(read('svg_transform', transform_value, 'type', ctypes.c_uint16) == 1, 'transform default matrix type')
        set_value('point', point_value, 'x', single, 16777217)
        expect(read('svg_point', point_value, 'x') == 16777216, 'SVG point preserves actual float precision')
        set_value('matrix', matrix_value, 'a', double, 16777217)
        expect(read('svg_matrix', matrix_value, 'a', double) == 16777217, 'SVG matrix coefficient preserves double precision')
        for kind, target, field, scalar in [('number', number, 'value', single), ('length', length_value, 'value', single), ('angle', angle_value, 'value', single), ('point', point_value, 'x', single), ('rect', rect_value, 'width', single), ('matrix', matrix_value, 'a', double)]:
            previous = read('svg_' + kind, target, field, scalar)
            for invalid in [math.nan, math.inf, -math.inf]:
                exception('rv_dom_svg_' + kind + '_set_' + field, [pointer, scalar], [target, invalid], 'TypeError')
                expect(read('svg_' + kind, target, field, scalar) == previous, kind + ' rejects nonfinite scalar atomically')
        call('rv_dom_svg_length_new_value_specified_units', [pointer, ctypes.c_uint16, single], length_value, 8, 1)
        expect(read('svg_length', length_value, 'value') == 96, 'one inch is 96 user units')
        call('rv_dom_svg_length_convert_to_specified_units', [pointer, ctypes.c_uint16], length_value, 6)
        expect(math.isclose(read('svg_length', length_value, 'value_in_specified_units'), 2.54, abs_tol=1e-6), 'inch to centimetres')
        call('rv_dom_svg_length_set_value_as_string', [pointer, Utf8], length_value, b'12px')
        expect(text_value('rv_dom_svg_length_get_value_as_string', length_value) == '12px', 'length string roundtrip')
        exception('rv_dom_svg_length_set_value_as_string', [pointer, Utf8], [length_value, b'invalid'], 'SyntaxError')
        exception('rv_dom_svg_length_new_value_specified_units', [pointer, ctypes.c_uint16, single], [length_value, 99, 1], 'NotSupportedError')
        expect(read('svg_length', length_value, 'value') == 12, 'failed length mutations preserve value')
        call('rv_dom_svg_angle_new_value_specified_units', [pointer, ctypes.c_uint16, single], angle_value, 3, math.pi)
        expect(math.isclose(read('svg_angle', angle_value, 'value'), 180, abs_tol=1e-4), 'radians to degrees')
        call('rv_dom_svg_angle_convert_to_specified_units', [pointer, ctypes.c_uint16], angle_value, 4)
        expect(math.isclose(read('svg_angle', angle_value, 'value_in_specified_units'), 200, abs_tol=1e-4), 'degrees to gradians')
        animated_rect = handle('rv_dom_svg_animated_rect_get_anim_val', [pointer], [view_box], 'svg_rect')
        exception('rv_dom_svg_rect_set_width', [pointer, single], [animated_rect, 1], 'NoModificationAllowedError')
        expect(read('svg_rect', base, 'width') == 200, 'animated read-only rejection preserves base')
        base_again = handle('rv_dom_svg_animated_rect_get_base_val', [pointer], [view_box], 'svg_rect')
        expect(base_again == base, 'live baseVal repeated getter identity')
        explicit = bind('rv_dom_svg_rect_retain', pointer, [pointer])(base)
        retained.append(('rv_dom_svg_rect_release', explicit))
        expect(explicit == base, 'explicit SVG retain identity')

        text = node('text')
        rotate = handle('rv_dom_svg_text_positioning_element_get_rotate', [pointer], [text], 'svg_animated_number_list')
        numbers = handle('rv_dom_svg_animated_number_list_get_base_val', [pointer], [rotate], 'svg_number_list')
        x_values = handle('rv_dom_svg_text_positioning_element_get_x', [pointer], [text], 'svg_animated_length_list')
        lengths = handle('rv_dom_svg_animated_length_list_get_base_val', [pointer], [x_values], 'svg_length_list')
        transforms = handle('rv_dom_svg_graphics_element_get_transform', [pointer], [group], 'svg_animated_transform_list')
        transform_list = handle('rv_dom_svg_animated_transform_list_get_base_val', [pointer], [transforms], 'svg_transform_list')
        polygon = node('polygon')
        points = handle('rv_dom_svg_polygon_element_get_points', [pointer], [polygon], 'svg_point_list')
        other_points = handle('rv_dom_svg_polyline_element_get_points', [pointer], [node('polyline')], 'svg_point_list')
        for kind, target, item in [('number', numbers, number), ('length', lengths, length_value), ('point', points, point_value), ('transform', transform_list, transform_value)]:
            prefix, item_root = 'rv_dom_svg_' + kind + '_list_', 'svg_' + kind
            call(prefix + 'clear', [pointer], target)
            expect(read(item_root + '_list', target, 'number_of_items', unsigned) == 0, kind + ' list clear')
            first = handle(prefix + 'initialize', [pointer, pointer], [target, item], item_root)
            expect(first == item, kind + ' detached item inserted by identity')
            obtained = handle(prefix + 'get_item', [pointer, unsigned], [target, 0], item_root)
            expect(obtained == first, kind + ' getter identity')
            inserted_item = value(kind)
            inserted = handle(prefix + 'insert_item_before', [pointer, pointer, unsigned], [target, inserted_item, 0], item_root)
            expect(inserted == inserted_item and read(item_root + '_list', target, 'length', unsigned) == 2, kind + ' insert before')
            replacement = value(kind)
            replaced = handle(prefix + 'replace_item', [pointer, pointer, unsigned], [target, replacement, 1], item_root)
            expect(replaced == replacement, kind + ' replacement identity')
            removed = handle(prefix + 'remove_item', [pointer, unsigned], [target, 0], item_root)
            expect(removed == inserted_item and read(item_root + '_list', target, 'length', unsigned) == 1, kind + ' removal identity')
            appended = handle(prefix + 'append_item', [pointer, pointer], [target, removed], item_root)
            expect(appended == removed and read(item_root + '_list', target, 'length', unsigned) == 2, kind + ' append detached value')
            missing = pointer(123)
            exception(prefix + 'get_item', [pointer, unsigned, ctypes.POINTER(pointer)], [target, 99, ctypes.byref(missing)], 'IndexSizeError')
            expect(missing.value == 123, kind + ' failed get preserves result')
            exception(prefix + 'replace_item', [pointer, pointer, unsigned, ctypes.POINTER(pointer)], [target, item, 99, ctypes.byref(missing)], 'IndexSizeError')
            expect(read(item_root + '_list', target, 'length', unsigned) == 2, kind + ' failed replacement preserves list')
        moved = handle('rv_dom_svg_point_list_get_item', [pointer, unsigned], [points, 0], 'svg_point')
        moved_result = handle('rv_dom_svg_point_list_append_item', [pointer, pointer], [other_points, moved], 'svg_point')
        expect(moved_result != moved, 'cross-list insertion clones an attached item')
        expect(read('svg_point_list', points, 'length', unsigned) == 2 and read('svg_point_list', other_points, 'length', unsigned) == 3, 'cross-list insertion preserves source ownership')
        set_value('point', moved_result, 'x', single, 42)
        expect(read('svg_point', moved, 'x') != 42, 'cloned list member mutates independently')
        animated_points = handle('rv_dom_svg_polygon_element_get_animated_points', [pointer], [polygon], 'svg_point_list')
        exception('rv_dom_svg_point_list_clear', [pointer], [animated_points], 'NoModificationAllowedError')
        animated_item = handle('rv_dom_svg_point_list_get_item', [pointer, unsigned], [animated_points, 0], 'svg_point')
        exception('rv_dom_svg_point_set_x', [pointer, single], [animated_item, 12], 'NoModificationAllowedError')
        call('rv_dom_svg_transform_set_translate', [pointer, single, single], transform_value, 7, 9)
        transform_matrix = handle('rv_dom_svg_transform_get_matrix', [pointer], [transform_value], 'svg_matrix')
        close(matrix(transform_matrix), (1, 0, 0, 1, 7, 9), 'transform translation matrix')
        call('rv_dom_svg_transform_set_scale', [pointer, single, single], transform_value, 2, 3)
        close(matrix(transform_matrix), (2, 0, 0, 3, 0, 0), 'retained transform matrix stays live')
        translated = handle('rv_dom_svg_matrix_translate', [pointer, single, single], [transform_matrix, 4, 5], 'svg_matrix')
        close(matrix(translated), (2, 0, 0, 3, 8, 15), 'SVG matrix translation uses local coordinates')
        inverse = handle('rv_dom_svg_matrix_inverse', [pointer], [translated], 'svg_matrix')
        close(matrix(inverse), (0.5, 0, 0, 1 / 3, -4, -5), 'SVG matrix inverse')
        set_value('point', point_value, 'x', single, 1)
        set_value('point', point_value, 'y', single, 2)
        projected = handle('rv_dom_svg_point_matrix_transform', [pointer, pointer], [point_value, translated], 'svg_point')
        close((read('svg_point', projected, 'x'), read('svg_point', projected, 'y')), (10, 21), 'SVG point matrix transform')
        singular = value('matrix')
        set_value('matrix', singular, 'a', double, 0)
        output = pointer(123)
        exception('rv_dom_svg_matrix_inverse', [pointer, ctypes.POINTER(pointer)], [singular, ctypes.byref(output)], 'InvalidStateError')
        expect(output.value == 123, 'failed SVG inverse preserves result')
        aliases = [double(item) for item in [2, 3, 4, 5, 6, 7]]
        matrix_init = MatrixInit()
        matrix_init.size = ctypes.sizeof(MatrixInit)
        for field, item in zip(['m11', 'm12', 'm21', 'm22', 'm41', 'm42'], aliases):
            setattr(matrix_init, field, ctypes.pointer(item))
        from_aliases = handle('rv_dom_svgsvg_element_create_svg_transform_from_matrix', [pointer, ctypes.POINTER(MatrixInit)], [root, ctypes.byref(matrix_init)], 'svg_transform')
        alias_matrix = handle('rv_dom_svg_transform_get_matrix', [pointer], [from_aliases], 'svg_matrix')
        close(matrix(alias_matrix), (2, 3, 4, 5, 6, 7), 'transform factory normalizes matrix dictionary aliases')
        call('rv_dom_svg_transform_set_matrix', [pointer, ctypes.POINTER(MatrixInit)], transform_value, ctypes.byref(matrix_init))
        close(matrix(transform_matrix), (2, 3, 4, 5, 6, 7), 'transform setter normalizes matrix dictionary aliases')
        list_aliases = handle('rv_dom_svg_transform_list_create_svg_transform_from_matrix', [pointer, ctypes.POINTER(MatrixInit)], [transform_list, ctypes.byref(matrix_init)], 'svg_transform')
        list_alias_matrix = handle('rv_dom_svg_transform_get_matrix', [pointer], [list_aliases], 'svg_matrix')
        close(matrix(list_alias_matrix), (2, 3, 4, 5, 6, 7), 'transform list factory normalizes matrix dictionary aliases')
        mismatch = double(8)
        matrix_init.a = ctypes.pointer(mismatch)
        exception('rv_dom_svgsvg_element_create_svg_transform_from_matrix', [pointer, ctypes.POINTER(MatrixInit), ctypes.POINTER(pointer)], [root, ctypes.byref(matrix_init), ctypes.byref(output)], 'TypeError')
        expect(output.value == 123, 'inconsistent root factory preserves result')
        exception('rv_dom_svg_transform_set_matrix', [pointer, ctypes.POINTER(MatrixInit)], [transform_value, ctypes.byref(matrix_init)], 'TypeError')
        close(matrix(transform_matrix), (2, 3, 4, 5, 6, 7), 'inconsistent setter leaves prior matrix unchanged')
        exception('rv_dom_svg_transform_list_create_svg_transform_from_matrix', [pointer, ctypes.POINTER(MatrixInit), ctypes.POINTER(pointer)], [transform_list, ctypes.byref(matrix_init), ctypes.byref(output)], 'TypeError')
        expect(output.value == 123, 'inconsistent list factory preserves result')
        identity_transform = handle('rv_dom_svgsvg_element_create_svg_transform_from_matrix', [pointer, ctypes.POINTER(MatrixInit)], [root, None], 'svg_transform')
        identity_matrix = handle('rv_dom_svg_transform_get_matrix', [pointer], [identity_transform], 'svg_matrix')
        close(matrix(identity_matrix), (1, 0, 0, 1, 0, 0), 'omitted matrix dictionary creates identity')
        matrix_init.a = ctypes.POINTER(double)()
        for unrestricted in [math.nan, math.inf, -math.inf]:
            aliases[0].value = unrestricted
            unrestricted_transform = handle('rv_dom_svgsvg_element_create_svg_transform_from_matrix', [pointer, ctypes.POINTER(MatrixInit)], [root, ctypes.byref(matrix_init)], 'svg_transform')
            unrestricted_matrix = handle('rv_dom_svg_transform_get_matrix', [pointer], [unrestricted_transform], 'svg_matrix')
            actual = read('svg_matrix', unrestricted_matrix, 'a', double)
            expect(math.isnan(actual) if math.isnan(unrestricted) else actual == unrestricted, 'native matrix dictionary retains unrestricted coefficients')
        consolidated = handle('rv_dom_svg_transform_list_consolidate', [pointer], [transform_list], 'svg_transform')
        expect(read('svg_transform_list', transform_list, 'length', unsigned) == 1, 'transform consolidation replaces list with one member')
        consolidated_again = handle('rv_dom_svg_transform_list_get_item', [pointer, unsigned], [transform_list, 0], 'svg_transform')
        expect(consolidated_again == consolidated, 'consolidated member identity')

        languages = handle('rv_dom_svg_graphics_element_get_system_language', [pointer], [group], 'svg_string_list')
        def string_item(operation, arguments, values):
            buffer, size = ctypes.create_string_buffer(256), integer()
            call('rv_dom_svg_string_list_' + operation, [pointer] + arguments + [pointer, integer, ctypes.POINTER(integer)], languages, *values, buffer, len(buffer), ctypes.byref(size))
            return buffer.value.decode()
        expect(string_item('initialize', [Utf8], [b'en']) == 'en', 'string list initialize')
        expect(string_item('append_item', [Utf8], [b'fr']) == 'fr', 'string list append')
        expect(string_item('insert_item_before', [Utf8, unsigned], [b'de', 1]) == 'de', 'string list insert')
        expect(string_item('replace_item', [Utf8, unsigned], [b'es', 0]) == 'es', 'string list replace')
        expect(string_item('remove_item', [unsigned], [1]) == 'de', 'string list remove')
        expect(string_item('get_item', [unsigned], [1]) == 'fr', 'string list order')
        call('rv_dom_svg_string_list_clear', [pointer], languages)
        expect(read('svg_string_list', languages, 'length', unsigned) == 0, 'string list clear')
        missing_node = pointer(123)
        call('rv_dom_svgsvg_element_get_element_by_id', [pointer, Utf8, ctypes.POINTER(pointer)], root, b'never-interned-svg-name-203948', ctypes.byref(missing_node))
        expect(missing_node.value is None, 'existing-atom lookup missing ID is null')

        wrong = single()
        status = bind('rv_dom_svg_geometry_element_get_total_length', integer, [pointer, ctypes.POINTER(single)])(group, ctypes.byref(wrong))
        expect(status == -11, 'wrong SVG node subtype rejected')
        statuses = []
        def worker():
            value = pointer()
            statuses.append(bbox(box, ctypes.byref(value)))
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        expect(statuses == [-2], 'SVG geometry enforces engine thread')
        document = handle('rv_dom_node_get_owner_document', [pointer], [root], 'node')
        for target in [document, root, polygon]:
            watch = bind('rv_node_watch', pointer, [pointer])(target)
            expect(bool(watch), 'create SVG lifetime watch')
            watches.append(watch)
        for release, item in list(reversed(retained)):
            if release == 'rv_node_release':
                bind(release, None, [pointer])(item)
                retained.remove((release, item))
        bind('rv_host_destroy', None, [pointer])(host)
        host = None
        expect(bind('rv_run_loop_cycle', integer, [integer])(100) >= 0, 'drain SVG disposal events')
        bind('rv_collect_garbage', None, [])()
        close(rectangle(base), (0, 0, 200, 50), 'retained viewBox after host disposal')
        expect(read('svg_number_list', numbers, 'length', unsigned) == 2, 'retained list after host disposal')
        set_value('point', moved, 'x', single, 81)
        expect(read('svg_point', moved, 'x') == 81, 'retained list member after host disposal')
        set_value('length', length_value, 'value', single, 31)
        expect(read('svg_length', length_value, 'value') == 31, 'factory value after host disposal')
    finally:
        for release, value in reversed(retained):
            bind(release, None, [pointer])(value)
        if host:
            bind('rv_host_destroy', None, [pointer])(host)
        bind('rv_release_memory', None, [])()
        bind('rv_collect_garbage', None, [])()
        for watch in watches:
            alive = bind('rv_watch_alive', integer, [pointer])(watch)
            bind('rv_watch_release', None, [pointer])(watch)
            expect(alive == 0, 'SVG owner expires after final handle release and collection')
        if search is not None:
            search.close()
    print(f'PASS SVG geometry: {assertions} assertions', flush=True)
    return assertions


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    verify(parser.parse_args().native_directory)
