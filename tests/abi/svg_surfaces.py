import argparse
import base64
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utf8_inputs import Utf8, bind as bind_utf8


def verify(native_directory, webkit_source, evidence_json=None):
    directory = Path(native_directory).resolve()
    filename = {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')
    search = os.add_dll_directory(str(directory)) if sys.platform == 'win32' else None
    library = ctypes.CDLL(str(directory / filename))
    pointer, integer, unsigned, single, double = ctypes.c_void_p, ctypes.c_int32, ctypes.c_uint32, ctypes.c_float, ctypes.c_double
    retained, listeners, watches = [], [], []
    assertions = 0

    class PointInit(ctypes.Structure):
        _fields_ = [('size', unsigned), ('x', double), ('y', double), ('z', double), ('w', double)]

    def bind(name, result, arguments):
        return bind_utf8(library, name, result, arguments)

    def expect(condition, label):
        nonlocal assertions
        assertions += 1
        if not condition:
            raise AssertionError(label)

    def call(name, arguments, *values):
        status = bind(name, integer, arguments)(*values)
        expect(status == 0, name + ': status ' + str(status))

    def handle(name, arguments, values, root):
        result = pointer()
        call(name, arguments + [ctypes.POINTER(pointer)], *values, ctypes.byref(result))
        expect(bool(result.value), name + ': nonnull')
        retained.append(('rv_node_release' if root == 'node' else 'rv_dom_' + root + '_release', result.value))
        return result.value

    def read(root, target, field, scalar=single):
        result = scalar()
        call('rv_dom_' + root + '_get_' + field, [pointer, ctypes.POINTER(scalar)], target, ctypes.byref(result))
        return result.value

    def number(name, arguments, values, scalar=single):
        result = scalar()
        call(name, arguments + [ctypes.POINTER(scalar)], *values, ctypes.byref(result))
        return result.value

    # FreeType scales advances in 16.16 fixed point: each Ahem glyph may lose one unit.
    quantum = 2 ** -16 if sys.platform.startswith('linux') else 0

    def advance(actual, glyphs, expected, label):
        expect(abs(actual - expected) <= glyphs * quantum, label + ': ' + repr(actual))

    def close(actual, expected, label, tolerance=0.001):
        expect(len(actual) == len(expected) and all(math.isclose(a, b, rel_tol=0, abs_tol=tolerance) for a, b in zip(actual, expected)), label + ': ' + str(actual))

    def rectangle(target):
        return tuple(read('svg_rect', target, field) for field in ['x', 'y', 'width', 'height'])

    def point(target):
        return tuple(read('svg_point', target, field) for field in ['x', 'y'])

    def matrix(target):
        return tuple(read('svg_matrix', target, field, double) for field in ['a', 'b', 'c', 'd', 'e', 'f'])

    def text(name, arguments, *values):
        buffer, size = ctypes.create_string_buffer(4096), integer()
        call(name, arguments + [pointer, integer, ctypes.POINTER(integer)], *values, buffer, len(buffer), ctypes.byref(size))
        return None if size.value < 0 else buffer.value.decode()

    def exception(name, arguments, values, expected):
        status = bind(name, integer, arguments)(*values)
        expect(status == -3, name + ': exception status ' + str(status))
        expect(text('rv_last_exception', [integer], 0) == expected, name + ': exception name ' + expected)

    font_path = Path(webkit_source) / 'Tools/TestWebKitAPI/Resources/cocoa/Ahem.ttf'
    font = font_path.read_bytes()
    expect(hashlib.sha256(font).hexdigest() == '63d2abd0041c3e3b4b52ad8d382353b53c51c6785e76ce56ed9dacad2d2e31c4', 'pinned Ahem fixture identity')
    fixture = Path(__file__).resolve().parents[1] / "fixtures/svg-surfaces.html"
    markup = fixture.read_text().replace("{{FONT_BASE64}}", base64.b64encode(font).decode()).encode()
    host = bind('rv_host_create', pointer, [integer, integer])(500, 300)
    expect(bool(host), 'host creation')
    try:
        call('rv_host_load_html', [pointer, ctypes.c_char_p], host, markup)
        expect(bind('rv_run_loop_cycle', integer, [integer])(20) >= 0, 'SVG document load event readiness')
        expect(bind('rv_host_update', integer, [pointer])(host) >= 0, 'SVG initial rendering update')

        def node(identifier):
            result = bind('rv_document_get_element_by_id', pointer, [pointer, ctypes.c_char_p])(host, identifier.encode())
            expect(bool(result), 'find ' + identifier)
            retained.append(('rv_node_release', result))
            return result

        def bounds(target):
            return rectangle(handle('rv_dom_svg_graphics_element_get_b_box', [pointer], [target], 'svg_rect'))

        def ctm(target, screen=False):
            return matrix(handle('rv_dom_svg_graphics_element_get_' + ('screen_ctm' if screen else 'ctm'), [pointer], [target], 'svg_matrix'))

        def length_property(kind, target, field):
            prefix = 'svgsvg' if kind == 'svg' else 'svg_' + kind
            animated = handle('rv_dom_' + prefix + '_element_get_' + field, [pointer], [target], 'svg_animated_length')
            return animated, handle('rv_dom_svg_animated_length_get_base_val', [pointer], [animated], 'svg_length')

        root, box, plain, path_text = (node(name) for name in ['root', 'box', 'plain', 'pathText'])
        call('rv_dom_svgsvg_element_pause_animations', [pointer], root)
        computed_length = bind('rv_dom_svg_text_content_element_get_computed_text_length', integer, [pointer, ctypes.POINTER(single)])
        deadline, current = time.monotonic() + 5, single()
        while True:
            status = computed_length(plain, ctypes.byref(current))
            if status:
                raise AssertionError('font readiness query status ' + str(status))
            if abs(current.value - 60) < 0.001:
                break
            if time.monotonic() >= deadline:
                raise AssertionError('pinned Ahem was not loaded: ' + str(current.value))
            if bind('rv_run_loop_cycle', integer, [integer])(10) < 0:
                raise AssertionError('font readiness event loop')
            bind('rv_host_update', integer, [pointer])(host)
        advance(current.value, 3, 60, 'actual Ahem font readiness')

        query = handle('rv_dom_svgsvg_element_create_svg_rect', [pointer], [root], 'svg_rect')
        for field, value in zip(['x', 'y', 'width', 'height'], [5, 5, 30, 30]):
            call('rv_dom_svg_rect_set_' + field, [pointer, single], query, value)
        for operation in ['intersection', 'enclosure']:
            result = handle('rv_dom_svgsvg_element_get_' + operation + '_list', [pointer] * 3, [root, query, None], 'node_list')
            expect(read('node_list', result, 'length', unsigned) == 1, operation + ' list count')
            item = handle('rv_dom_node_list_item', [pointer, unsigned], [result, 0], 'node')
            expect(item == box, operation + ' list node identity')
            expect(number('rv_dom_svgsvg_element_check_' + operation, [pointer] * 3, [root, box, query], integer) == 1, operation + ' predicate')
        close(ctm(box), (1, 0, 0, 1, 0, 0), 'initial root viewBox matrix')
        _, width = length_property('svg', root, 'width')
        call('rv_dom_svg_length_set_value', [pointer, single], width, 600)
        close(ctm(box), (1, 0, 0, 1, 50, 0), 'root viewport width changes centering')
        call('rv_dom_svg_length_set_value', [pointer, single], width, 500)
        current_view = handle('rv_dom_svgsvg_element_get_current_view', [pointer], [root], 'svg_view_spec')
        expect(read('svgsvg_element', root, 'use_current_view', integer) == 0, 'native view-spec is inactive initially')
        view = node('detail')
        animated_view_box = handle('rv_dom_svg_view_element_get_view_box', [pointer], [view], 'svg_animated_rect')
        view_box = handle('rv_dom_svg_animated_rect_get_base_val', [pointer], [animated_view_box], 'svg_rect')
        call('rv_dom_svg_rect_set_width', [pointer, single], view_box, 200)
        close(ctm(box), (1, 0, 0, 1, 0, 0), 'inactive named-view edit does not claim an applied root view')
        expect(read('svg_rect', view_box, 'width') == 200, 'view element mutation remains observable')

        for target, baseline_y in [(plain, 100), (path_text, 150)]:
            expect(number('rv_dom_svg_text_content_element_get_number_of_chars', [pointer], [target], integer) == 3, 'text character count')
            advance(number('rv_dom_svg_text_content_element_get_computed_text_length', [pointer], [target]), 3, 60, 'text length')
            advance(number('rv_dom_svg_text_content_element_get_sub_string_length', [pointer, unsigned, unsigned], [target, 0, 2]), 2, 40, 'substring length')
            advance(number('rv_dom_svg_text_content_element_get_sub_string_length', [pointer, unsigned, unsigned], [target, 1, 99]), 2, 40, 'substring count clamps to remaining characters')
            for index in range(3):
                start = handle('rv_dom_svg_text_content_element_get_start_position_of_char', [pointer, unsigned], [target, index], 'svg_point')
                close(point(start), (10 + index * 20, baseline_y), 'character start position')
                extent = handle('rv_dom_svg_text_content_element_get_extent_of_char', [pointer, unsigned], [target, index], 'svg_rect')
                rotation = number('rv_dom_svg_text_content_element_get_rotation_of_char', [pointer, unsigned], [target, index])
                expect(abs(rotation - (index * 10 if target == plain else 0)) < 0.001, 'character rotation')
                end = handle('rv_dom_svg_text_content_element_get_end_position_of_char', [pointer, unsigned], [target, index], 'svg_point')
                expected_end = [(30, 100), (49.6961555, 103.4729614), (68.7938538, 106.8404007)][index] if target == plain else (30 + index * 20, 150)
                close(point(end), expected_end, 'character end position from pinned browser/font oracle')
                if index == 0:
                    close(rectangle(extent), (10, baseline_y - 16, 20, 20), 'Ahem character extent')
                missing = pointer(123)
                exception('rv_dom_svg_text_content_element_get_extent_of_char', [pointer, unsigned, ctypes.POINTER(pointer)], [target, 99, ctypes.byref(missing)], 'IndexSizeError')
                expect(missing.value == 123, 'invalid character index preserves output')
            exception('rv_dom_svg_text_content_element_select_sub_string', [pointer, unsigned, unsigned], [target, 99, 1], 'IndexSizeError')
            for x, y, expected in [(15, baseline_y - 5, 0), (-100, -100, -1)]:
                query_point = PointInit(ctypes.sizeof(PointInit), x, y, 0, 1)
                expect(number('rv_dom_svg_text_content_element_get_char_num_at_position', [pointer, ctypes.POINTER(PointInit)], [target, ctypes.byref(query_point)], integer) == expected, 'actual text character hit query')
            call('rv_dom_svg_text_content_element_select_sub_string', [pointer, unsigned, unsigned], target, 1, 1)
            owner = handle('rv_dom_node_get_owner_document', [pointer], [target], 'node')
            selection = handle('rv_dom_document_get_selection', [pointer], [owner], 'dom_selection')
            expect(text('rv_dom_dom_selection_to_string', [pointer], selection) == 'B', 'actual SVG substring selection')
        x_list = handle('rv_dom_svg_text_positioning_element_get_x', [pointer], [plain], 'svg_animated_length_list')
        x_base = handle('rv_dom_svg_animated_length_list_get_base_val', [pointer], [x_list], 'svg_length_list')
        x_readonly = handle('rv_dom_svg_animated_length_list_get_anim_val', [pointer], [x_list], 'svg_length_list')
        x_first = handle('rv_dom_svg_length_list_get_item', [pointer, unsigned], [x_base, 0], 'svg_length')
        x_animated = handle('rv_dom_svg_length_list_get_item', [pointer, unsigned], [x_readonly, 0], 'svg_length')
        exception('rv_dom_svg_length_set_value', [pointer, single], [x_animated, 99], 'NoModificationAllowedError')
        call('rv_dom_svg_length_set_value', [pointer, single], x_first, 20)
        close(point(handle('rv_dom_svg_text_content_element_get_start_position_of_char', [pointer, unsigned], [plain, 0], 'svg_point')), (20, 100), 'typed text x list changes actual placement')
        call('rv_dom_svg_length_set_value', [pointer, single], x_first, 10)
        text_length = handle('rv_dom_svg_text_content_element_get_text_length', [pointer], [plain], 'svg_animated_length')
        text_length_base = handle('rv_dom_svg_animated_length_get_base_val', [pointer], [text_length], 'svg_length')
        length_adjust = handle('rv_dom_svg_text_content_element_get_length_adjust', [pointer], [plain], 'svg_animated_enumeration')
        call('rv_dom_svg_animated_enumeration_set_base_val', [pointer, ctypes.c_uint16], length_adjust, 2)
        call('rv_dom_svg_length_set_value', [pointer, single], text_length_base, 90)
        adjustment_rows = []
        expected_rows = json.loads((fixture.parent / 'svg-text-query-expectations.json').read_text())['rows']
        for target, kind, rotations in [(plain, 'plain', ['0 0 0', '0 10 20']), (path_text, 'path', ['0 0 0']), (node('vertical'), 'vertical', ['0 0 0', '0 10 20'])]:
            target_length = handle('rv_dom_svg_text_content_element_get_text_length', [pointer], [target], 'svg_animated_length')
            target_base = handle('rv_dom_svg_animated_length_get_base_val', [pointer], [target_length], 'svg_length')
            target_adjust = handle('rv_dom_svg_text_content_element_get_length_adjust', [pointer], [target], 'svg_animated_enumeration')
            for rotation in rotations:
                call('rv_dom_element_set_attribute', [pointer, Utf8, Utf8], target, b'rotate', rotation.encode())
                for adjust in [1, 2]:
                    call('rv_dom_svg_animated_enumeration_set_base_val', [pointer, ctypes.c_uint16], target_adjust, adjust)
                    call('rv_dom_svg_length_set_value', [pointer, single], target_base, 90)
                    row = dict(kind=kind, rotation=rotation, adjust=adjust, computed=number('rv_dom_svg_text_content_element_get_computed_text_length', [pointer], [target]), substring01=number('rv_dom_svg_text_content_element_get_sub_string_length', [pointer, unsigned, unsigned], [target, 0, 2]), substring12=number('rv_dom_svg_text_content_element_get_sub_string_length', [pointer, unsigned, unsigned], [target, 1, 2]), starts=[], ends=[], extents=[])
                    for index in range(3):
                        for operation, field in [('start', 'starts'), ('end', 'ends')]:
                            row[field].append(point(handle('rv_dom_svg_text_content_element_get_' + operation + '_position_of_char', [pointer, unsigned], [target, index], 'svg_point')))
                        row['extents'].append(rectangle(handle('rv_dom_svg_text_content_element_get_extent_of_char', [pointer, unsigned], [target, index], 'svg_rect')))
                    row['hits'] = []
                    hit_points = [(15, 95), (45, 95), (85, 95), (95, 95), (-100, -100)]
                    for x, y in hit_points:
                        hit = PointInit(ctypes.sizeof(PointInit), x, y, 0, 1)
                        row['hits'].append(number('rv_dom_svg_text_content_element_get_char_num_at_position', [pointer, ctypes.POINTER(PointInit)], [target, ctypes.byref(hit)], integer))
                    row['bbox'] = bounds(target)
                    advance(row['computed'], 3, 60 if adjust == 1 else 90, 'adjusted logical text advance ' + kind)
                    expect(row['substring01'] == row['substring12'], 'adjusted substring logical advances agree ' + kind)
                    advance(row['substring01'], 2, 40 if adjust == 1 else 60, 'adjusted substring logical advances ' + kind)
                    expected_row = next((item for item in expected_rows if (item['kind'], item['rotation'], item['adjust']) == (kind, rotation, adjust)), None)
                    if expected_row:
                        for field in ['starts', 'ends', 'extents']:
                            for actual, expected in zip(row[field], expected_row[field]):
                                close(actual, expected, kind + ' ' + field + ' independent retained oracle')
                        if rotation == '0 0 0' or adjust == 2:
                            for (x, y), actual, expected in zip(hit_points, row['hits'], expected_row['hits']):
                                edges = [edge for left, _, width, _ in row['extents'] for edge in (left, left + width)]
                                if quantum and any(abs(x - edge) <= 3 * quantum for edge in edges):
                                    inside = [index for index, (left, top, width, height) in enumerate(row['extents']) if left <= x <= left + width and top <= y <= top + height]
                                    expect(actual == (inside[0] if inside else -1), kind + ' quantized-edge hit matches actual extents')
                                else:
                                    expect(actual == expected, kind + ' independent hit oracle')
                    expect(bind('rv_host_update', integer, [pointer])(host) >= 0, 'adjusted text actual render update')
                    pixels = (ctypes.c_uint8 * (500 * 300 * 4))()
                    call('rv_host_paint_rgba', [pointer, pointer, integer], host, pixels, len(pixels))
                    for index, (x, y, width, height) in enumerate(row['extents']):
                        x, y = int(x + width / 2), int(y + height / 2)
                        hit = PointInit(ctypes.sizeof(PointInit), x, y, 0, 1)
                        expect(number('rv_dom_svg_text_content_element_get_char_num_at_position', [pointer, ctypes.POINTER(PointInit)], [target, ctypes.byref(hit)], integer) == index, 'adjusted extent center hit matches actual glyph ' + kind)
                        expect(list(pixels[(y * 500 + x) * 4:(y * 500 + x) * 4 + 4]) == [0, 0, 0, 255], 'adjusted query extent center matches actual Ahem paint ' + kind)
                    adjustment_rows.append(row)
        if evidence_json:
            output = Path(evidence_json)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(adjustment_rows, indent=2)+'\n')
        adjusted = number('rv_dom_svg_text_content_element_get_computed_text_length', [pointer], [plain])
        print('TEXT_LENGTH_ADJUSTMENT', {'computed': adjusted, 'bbox': bounds(plain), 'end': point(handle('rv_dom_svg_text_content_element_get_end_position_of_char', [pointer, unsigned], [plain, 2], 'svg_point')), 'authored': text('rv_dom_element_get_attribute', [pointer, Utf8], plain, b'textLength'), 'lengthAdjust': read('svg_animated_enumeration', length_adjust, 'base_val', ctypes.c_uint16)}, flush=True)
        close([adjusted], [90], 'textLength/lengthAdjust change actual glyph metrics')
        offset, offset_base = length_property('text_path', path_text, 'start_offset')
        call('rv_dom_svg_length_set_value', [pointer, single], offset_base, 30)
        shifted = handle('rv_dom_svg_text_content_element_get_start_position_of_char', [pointer, unsigned], [path_text, 0], 'svg_point')
        close(point(shifted), (30, 150), 'text-path startOffset updates actual placement')
        for field, expected in [('method', 1), ('spacing', 2)]:
            value = handle('rv_dom_svg_text_path_element_get_' + field, [pointer], [path_text], 'svg_animated_enumeration')
            expect(read('svg_animated_enumeration', value, 'base_val', ctypes.c_uint16) == expected, 'text-path ' + field)

        cases = [
            ('circle', 'circle', (70, 10, 20, 20), [('cx', 100), ('r', 12)], (88, 8, 24, 24)),
            ('ellipse', 'ellipse', (115, 10, 30, 20), [('cx', 135), ('ry', 15)], (120, 5, 30, 30)),
            ('line', 'line', (10, 40, 40, 20), [('x2', 70), ('y2', 80)], (10, 40, 60, 40)),
            ('rect', 'box', (10, 10, 20, 20), [('width', 50), ('height', 30), ('rx', 10), ('ry', 5)], (10, 10, 50, 30)),
        ]
        for kind, identifier, initial, edits, expected in cases:
            target = node(identifier)
            close(bounds(target), initial, kind + ' initial bounds')
            for field, value in edits:
                animated, base = length_property(kind, target, field)
                again = handle('rv_dom_svg_animated_length_get_base_val', [pointer], [animated], 'svg_length')
                expect(again == base, kind + '.' + field + ' live base identity')
                readonly = handle('rv_dom_svg_animated_length_get_anim_val', [pointer], [animated], 'svg_length')
                exception('rv_dom_svg_length_set_value', [pointer, single], [readonly, value + 1], 'NoModificationAllowedError')
                call('rv_dom_svg_length_set_value', [pointer, single], base, value)
                expect(read('svg_length', base, 'value') == value and read('svg_length', readonly, 'value') == value, kind + '.' + field + ' base/animated mutation')
                expect(text('rv_dom_element_get_attribute', [pointer, Utf8], target, field.encode()) is not None, kind + '.' + field + ' reflected attribute')
            close(bounds(target), expected, kind + ' edited bounds')
        for kind, identifier, index, field, value, expected in [('polygon', 'polygon', 0, 'x', 170, (170, 10, 30, 20)), ('polyline', 'polyline', 2, 'y', 40, (220, 10, 20, 30))]:
            target = node(identifier)
            points = handle('rv_dom_svg_' + kind + '_element_get_points', [pointer], [target], 'svg_point_list')
            item = handle('rv_dom_svg_point_list_get_item', [pointer, unsigned], [points, index], 'svg_point')
            call('rv_dom_svg_point_set_' + field, [pointer, single], item, value)
            close(bounds(target), expected, kind + ' point mutation updates bounds')
        path = node('shapePath')
        expect(text('rv_dom_element_get_attribute', [pointer, Utf8], path, b'd') == 'M10 200H110', 'path facade reads authored data')
        call('rv_dom_element_set_attribute', [pointer, Utf8, Utf8], path, b'd', b'M10 200H110V240H10Z')
        close(bounds(path), (10, 200, 100, 40), 'authored path-data edit updates engine bounds')
        expect(number('rv_dom_svg_geometry_element_get_total_length', [pointer], [path]) == 280, 'authored path-data edit updates engine length')
        call('rv_dom_element_set_attribute', [pointer, Utf8, Utf8], path, b'd', b'')
        expect(text('rv_dom_element_get_attribute', [pointer, Utf8], path, b'd') == '', 'empty path data stays present')
        call('rv_dom_element_remove_attribute', [pointer, Utf8], path, b'd')
        expect(text('rv_dom_element_get_attribute', [pointer, Utf8], path, b'd') is None, 'removed path data stays absent')
        expect(number('rv_dom_svg_geometry_element_get_total_length', [pointer], [path]) == 0, 'removed authored path has zero length')

        convolve = node('convolve')
        boolean = handle('rv_dom_svgfe_convolve_matrix_element_get_preserve_alpha', [pointer], [convolve], 'svg_animated_boolean')
        expect(read('svg_animated_boolean', boolean, 'base_val', integer) == 0, 'real Boolean initial state')
        call('rv_dom_svg_animated_boolean_set_base_val', [pointer, integer], boolean, 1)
        expect(read('svg_animated_boolean', boolean, 'base_val', integer) == 1 and read('svg_animated_boolean', boolean, 'anim_val', integer) == 1, 'real Boolean base/animated mutation')
        expect(text('rv_dom_element_get_attribute', [pointer, Utf8], convolve, b'preserveAlpha') == 'true', 'real Boolean reflects actual preserveAlpha attribute')
        order = handle('rv_dom_svgfe_convolve_matrix_element_get_order_x', [pointer], [convolve], 'svg_animated_integer')
        expect(read('svg_animated_integer', order, 'base_val', integer) == 3, 'real integer wrapper initial order')
        call('rv_dom_svg_animated_integer_set_base_val', [pointer, integer], order, 4)
        expect(read('svg_animated_integer', order, 'anim_val', integer) == 4, 'real integer wrapper mutation')

        animation, animated = node('animation'), node('animated')
        callback_type = ctypes.CFUNCTYPE(integer, pointer, pointer)
        events, callback_errors = [], []
        def on_event(context, event):
            try:
                events.append(text('rv_event_type', [pointer], event))
                return 0
            except Exception as error:
                callback_errors.append(str(error))
                return 1
        callback = callback_type(on_event)
        for event_name in ['beginEvent', 'endEvent', 'repeatEvent']:
            listener = bind('rv_node_add_event_listener', pointer, [pointer, ctypes.c_char_p, integer, callback_type, pointer])(animation, event_name.encode(), 0, callback, None)
            expect(bool(listener), 'SMIL event listener ' + event_name)
            listeners.append(listener)
        target = handle('rv_dom_svg_animation_element_get_target_element', [pointer], [animation], 'node')
        expect(target == animated, 'SMIL target identity')
        untouched = single(123)
        exception('rv_dom_svg_animation_element_get_start_time', [pointer, ctypes.POINTER(single)], [animation, ctypes.byref(untouched)], 'InvalidStateError')
        expect(untouched.value == 123, 'unstarted SMIL start time preserves result')
        indefinite = node('indefinite')
        exception('rv_dom_svg_animation_element_get_simple_duration', [pointer, ctypes.POINTER(single)], [indefinite, ctypes.byref(untouched)], 'NotSupportedError')
        call('rv_dom_svgsvg_element_set_current_time', [pointer, single], root, 0)
        call('rv_dom_svg_animation_element_begin_element', [pointer], animation)
        call('rv_dom_svgsvg_element_set_current_time', [pointer, single], root, 1)
        expect(number('rv_dom_svg_animation_element_get_start_time', [pointer], [animation]) == 0, 'SMIL actual start time')
        expect(number('rv_dom_svg_animation_element_get_simple_duration', [pointer], [animation]) == 2, 'SMIL actual duration')
        actual_time = number('rv_dom_svg_animation_element_get_current_time', [pointer], [animation])
        expect(actual_time == 1, 'SMIL actual current time: ' + repr(actual_time) + '; root=' + repr(number('rv_dom_svgsvg_element_get_current_time', [pointer], [root])))
        _, animated_x = length_property('rect', animated, 'x')
        animated_x_wrapper = handle('rv_dom_svg_rect_element_get_x', [pointer], [animated], 'svg_animated_length')
        animated_x_readonly = handle('rv_dom_svg_animated_length_get_anim_val', [pointer], [animated_x_wrapper], 'svg_length')
        close(bounds(animated), (250, 60, 20, 20), 'SMIL seek changes actual rendered geometry')
        expect(read('svg_length', animated_x, 'value') == 200 and read('svg_length', animated_x_readonly, 'value') == 250, 'SMIL base and animated values remain distinct')
        call('rv_dom_svg_animation_element_end_element', [pointer], animation)
        call('rv_dom_svgsvg_element_set_current_time', [pointer, single], root, 1.5)
        close(bounds(animated), (250, 60, 20, 20), 'SMIL end freezes actual value')
        for operation in ['begin_element_at', 'end_element_at']:
            for invalid in [math.nan, math.inf, -math.inf]:
                exception('rv_dom_svg_animation_element_' + operation, [pointer, single], [animation, invalid], 'TypeError')
        expect(bind('rv_run_loop_cycle', integer, [integer])(20) >= 0, 'SMIL event dispatch')
        expect(not callback_errors and 'beginEvent' in events and 'endEvent' in events, 'real SMIL begin/end event delivery: ' + str(events))
        live, live_target = node('liveAnimation'), node('liveTarget')
        events.clear()
        for event_name in ['beginEvent', 'endEvent', 'repeatEvent']:
            listener = bind('rv_node_add_event_listener', pointer, [pointer, ctypes.c_char_p, integer, callback_type, pointer])(live, event_name.encode(), 0, callback, None)
            expect(bool(listener), 'running SMIL listener ' + event_name)
            listeners.append(listener)
        before_resume = number('rv_dom_svgsvg_element_get_current_time', [pointer], [root])
        call('rv_dom_svg_animation_element_begin_element_at', [pointer, single], live, 0.02)
        call('rv_dom_svgsvg_element_unpause_animations', [pointer], root)
        expect(number('rv_dom_svgsvg_element_animations_paused', [pointer], [root], integer) == 0, 'SMIL resumed state')
        deadline = time.monotonic() + 3
        while 'endEvent' not in events and time.monotonic() < deadline:
            if bind('rv_run_loop_cycle', integer, [integer])(10) < 0 or bind('rv_host_update', integer, [pointer])(host) < 0:
                raise AssertionError('running SMIL event/render cycle')
        call('rv_dom_svgsvg_element_pause_animations', [pointer], root)
        expect(not callback_errors and all(name in events for name in ['beginEvent', 'repeatEvent', 'endEvent']), 'running SMIL event delivery: ' + str(events))
        expect(number('rv_dom_svgsvg_element_animations_paused', [pointer], [root], integer) == 1, 'SMIL paused state')
        expect(number('rv_dom_svgsvg_element_get_current_time', [pointer], [root]) > before_resume, 'SMIL real clock advanced')
        close(bounds(live_target), (370, 220, 20, 20), 'running SMIL changes actual rendered geometry')
        stopped = number('rv_dom_svgsvg_element_get_current_time', [pointer], [root])
        expect(bind('rv_run_loop_cycle', integer, [integer])(30) >= 0, 'paused SMIL event cycle')
        expect(number('rv_dom_svgsvg_element_get_current_time', [pointer], [root]) == stopped, 'paused clock remains stable')
        call('rv_dom_svg_animation_element_begin_element', [pointer], live)
        call('rv_dom_svg_animation_element_end_element_at', [pointer, single], live, 0.05)
        call('rv_dom_svgsvg_element_set_current_time', [pointer, single], root, stopped + 0.05)
        close(bounds(live_target), (360, 220, 20, 20), 'positive endElementAt freezes interpolated geometry', tolerance=0.01)
        expect(read('svgsvg_element', root, 'current_scale') == 1, 'embedded SVG scale profile remains one')
        for listener in listeners:
            expect(bind('rv_listener_remove', integer, [pointer])(listener) == 0, 'SMIL listener removal')
        listeners.clear()
        wrong = pointer(123)
        expect(bind('rv_dom_svg_circle_element_get_cx', integer, [pointer, ctypes.POINTER(pointer)])(box, ctypes.byref(wrong)) == -11 and wrong.value == 123, 'shape receiver subtype validation')
        statuses = []
        def worker():
            statuses.append(bind('rv_dom_svg_animation_element_begin_element', integer, [pointer])(animation))
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        expect(statuses == [-2], 'SMIL engine-thread guard')
        document = handle('rv_dom_node_get_owner_document', [pointer], [root], 'node')
        for target in [document, root, animated, convolve]:
            watch = bind('rv_node_watch', pointer, [pointer])(target)
            expect(bool(watch), 'SVG surface owner watch')
            watches.append(watch)
        for release, value in list(reversed(retained)):
            if release == 'rv_node_release':
                bind(release, None, [pointer])(value)
                retained.remove((release, value))
        bind('rv_host_destroy', None, [pointer])(host)
        host = None
        expect(read('svg_animated_boolean', boolean, 'base_val', integer) == 1, 'retained real Boolean after host disposal')
        expect(read('svg_animated_integer', order, 'base_val', integer) == 4, 'retained real integer after host disposal')
        expect(read('svg_length', animated_x_readonly, 'value') > 249.99, 'retained animated length after host disposal')
    finally:
        for listener in listeners:
            bind('rv_listener_remove', integer, [pointer])(listener)
        for release, value in reversed(retained):
            bind(release, None, [pointer])(value)
        if host:
            bind('rv_host_destroy', None, [pointer])(host)
        bind('rv_run_loop_cycle', integer, [integer])(100)
        bind('rv_release_memory', None, [])()
        bind('rv_collect_garbage', None, [])()
        for watch in watches:
            alive = bind('rv_watch_alive', integer, [pointer])(watch)
            bind('rv_watch_release', None, [pointer])(watch)
            expect(alive == 0, 'SVG surface owner expires after final release/collection')
        if search:
            search.close()
    print(f'PASS SVG surfaces: {assertions} assertions', flush=True)
    return assertions


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--webkit-source', required=True)
    parser.add_argument('--evidence-json')
    options = parser.parse_args()
    verify(options.native_directory, options.webkit_source, options.evidence_json)
