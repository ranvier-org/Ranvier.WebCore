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
    pointer, integer, unsigned, number = ctypes.c_void_p, ctypes.c_int32, ctypes.c_uint32, ctypes.c_double
    retained, buffers, failures = [], [], []
    assertions = 0

    class Numberish(ctypes.Structure):
        _fields_ = [('present', integer), ('tag', integer), ('number', number), ('numeric', pointer)]

    class Components(ctypes.Structure):
        _fields_ = [('present', integer), ('count', integer), ('items', ctypes.POINTER(pointer))]

    class Span(ctypes.Structure):
        _fields_ = [('data', pointer), ('length', integer)]

    class PerspectiveValue(ctypes.Structure):
        _fields_ = [('present', integer), ('tag', integer), ('numeric', pointer), ('text', Span), ('keyword', pointer)]

    class StyleInput(ctypes.Structure):
        _fields_ = [('present', integer), ('tag', integer), ('value', pointer), ('text', Span)]

    class StyleInputs(ctypes.Structure):
        _fields_ = [('present', integer), ('count', integer), ('items', ctypes.POINTER(StyleInput))]

    class MatrixOptions(ctypes.Structure):
        _fields_ = [('size', unsigned), ('is2_d', ctypes.POINTER(integer))]

    def bind(name, result, arguments):
        return bind_utf8(library, name, result, arguments)

    translate_create = bind('rv_dom_css_translate_create', integer, [pointer] * 4 + [ctypes.POINTER(pointer)])

    def expect(condition, label, fatal=False):
        nonlocal assertions
        assertions += 1
        if not condition:
            if fatal:
                raise AssertionError(label)
            failures.append(label)

    def call(name, arguments, *values):
        status = bind(name, integer, arguments)(*values)
        expect(status == 0, f'{name}: status {status}', True)

    def handle(name, arguments, values, release='rv_dom_css_transform_component_release'):
        result = pointer()
        call(name, arguments + [ctypes.POINTER(pointer)], *values, ctypes.byref(result))
        expect(bool(result.value), name + ': nonnull handle', True)
        retained.append((release, result.value))
        return result.value

    def text_input(value):
        encoded = value.encode('utf-8')
        buffer = ctypes.create_string_buffer(encoded)
        buffers.append(buffer)
        return buffer, len(encoded)

    def unit(value, symbol):
        data, length = text_input(symbol)
        return handle('rv_dom_css_unit_value_create', [pointer, number, pointer, integer], [document, value, data, length], 'rv_dom_css_style_value_release')

    def scalar(target, field):
        result = number()
        call('rv_dom_dom_matrix_read_only_get_' + field, [pointer, ctypes.POINTER(number)], target, ctypes.byref(result))
        return result.value

    def affine(target):
        return tuple(scalar(target, field) for field in ['a', 'b', 'c', 'd', 'e', 'f'])

    def flag(target, matrix=False):
        result = integer()
        call('rv_dom_' + ('dom_matrix_read_only' if matrix else 'css_transform_component') + '_get_is2_d', [pointer, ctypes.POINTER(integer)], target, ctypes.byref(result))
        return bool(result.value)

    def to_matrix(target):
        return handle('rv_dom_css_transform_component_to_matrix', [pointer], [target], 'rv_dom_dom_matrix_read_only_release')

    def component_text(target):
        buffer, length = ctypes.create_string_buffer(4096), integer()
        call('rv_dom_css_transform_component_to_string', [pointer, pointer, integer, ctypes.POINTER(integer)], target, buffer, len(buffer), ctypes.byref(length))
        return buffer.raw[:length.value].decode('utf-8')

    def type_name(target):
        buffer, length = ctypes.create_string_buffer(256), integer()
        call('rv_dom_css_transform_component_get_interface_name', [pointer, pointer, integer, ctypes.POINTER(integer)], target, buffer, len(buffer), ctypes.byref(length))
        return buffer.raw[:length.value].decode('utf-8')

    def component_list(values):
        array = (pointer * len(values))(*values)
        buffers.append(array)
        sequence = Components(1, len(values), array)
        return handle('rv_dom_css_transform_value_create', [pointer, pointer], [document, ctypes.byref(sequence)], 'rv_dom_css_style_value_release')

    def scale_number(target, field):
        result = Numberish()
        call('rv_dom_css_scale_get_' + field, [pointer, ctypes.POINTER(Numberish)], target, ctypes.byref(result))
        try:
            expect(result.present == 1 and result.tag in (1, 2), 'scale numeric result is present', True)
            if result.tag == 1:
                return result.number
            value = number()
            call('rv_dom_css_unit_value_get_value', [pointer, ctypes.POINTER(number)], result.numeric, ctypes.byref(value))
            return value.value
        finally:
            bind('rv_dom_union_double_or_css_numeric_value_release', None, [ctypes.POINTER(Numberish)])(ctypes.byref(result))

    def expect_type_error(status, label):
        expect(status == -3, label + ': engine exception status')
        if status == -3:
            buffer, length = ctypes.create_string_buffer(256), integer()
            call('rv_last_exception', [integer, pointer, integer, ctypes.POINTER(integer)], 0, buffer, len(buffer), ctypes.byref(length))
            expect(buffer.raw[:length.value] == b'TypeError', label + ': TypeError')

    host = bind('rv_host_create', pointer, [integer, integer])(320, 240)
    expect(bool(host), 'host creation', True)
    try:
        body = bind('rv_document_body', pointer, [pointer])(host)
        retained.append(('rv_node_release', body))
        document = handle('rv_dom_node_get_owner_document', [pointer], [body], 'rv_node_release')
        x, y, z = unit(10, 'px'), unit(20, 'px'), unit(0, 'px')
        angle = unit(90, 'deg')
        translate = handle('rv_dom_css_translate_create', [pointer] * 4, [document, x, y, None])
        expect(type_name(translate) == 'CSSTranslate' and flag(translate), 'translate actual type/default 2D')
        owned_x = handle('rv_dom_css_translate_get_x', [pointer], [translate], 'rv_dom_css_style_value_release')
        expect(owned_x == x, 'const numeric getter preserves retained value identity')
        expect(affine(to_matrix(translate)) == (1, 0, 0, 1, 10, 20), 'translate matrix')
        translate3d = handle('rv_dom_css_translate_create', [pointer] * 4, [document, x, y, z])
        expect(not flag(translate3d) and not flag(to_matrix(translate3d), True), 'explicit translate z keeps 3D')

        two, three = Numberish(1, 1, 2, None), Numberish(1, 1, 3, None)
        scale = handle('rv_dom_css_scale_create', [pointer] * 4, [document, ctypes.byref(two), ctypes.byref(three), None])
        expect(type_name(scale) == 'CSSScale' and flag(scale), 'scale type/default 2D')
        expect(affine(to_matrix(scale)) == (2, 0, 0, 3, 0, 0), 'scale matrix')
        rotation = handle('rv_dom_css_rotate_create_1', [pointer, pointer], [document, angle])
        expect(type_name(rotation) == 'CSSRotate' and flag(rotation), 'angle-only rotate 2D')
        rotated = affine(to_matrix(rotation))
        expect(all(math.isclose(actual, expected, abs_tol=1e-12) for actual, expected in zip(rotated, (0, 1, -1, 0, 0, 0))), 'rotate matrix')
        zero, one = Numberish(1, 1, 0, None), Numberish(1, 1, 1, None)
        axis = handle('rv_dom_css_rotate_create_4', [pointer] * 5, [document, ctypes.byref(zero), ctypes.byref(zero), ctypes.byref(one), angle])
        expect(not flag(axis), 'axis rotate 3D')
        for name, members in [('css_skew', [unit(0, 'deg'), unit(0, 'deg')]), ('css_skew_x', [unit(45, 'deg')]), ('css_skew_y', [unit(45, 'deg')])]:
            value = handle('rv_dom_' + name + '_create', [pointer] * (len(members) + 1), [document, *members])
            call('rv_dom_css_transform_component_set_is2_d', [pointer, integer], value, 0)
            expect(flag(value), name + ': is2D setter no-op')
            expect(bool(component_text(value)), name + ': serialization')

        transforms = component_list([translate, scale])
        transformed = handle('rv_dom_css_transform_value_to_matrix', [pointer], [transforms], 'rv_dom_dom_matrix_read_only_release')
        expect(affine(transformed) == (2, 0, 0, 3, 10, 20), 'list postmultiplication order')
        first = handle('rv_dom_css_transform_value_item', [pointer, unsigned], [transforms, 0])
        expect(first == translate, 'list retains component identity')
        call('rv_dom_css_transform_value_set_item', [pointer, unsigned, pointer], transforms, 2, rotation)
        length = unsigned()
        call('rv_dom_css_transform_value_get_length', [pointer, ctypes.POINTER(unsigned)], transforms, ctypes.byref(length))
        expect(length.value == 3, 'indexed setter at length appends')

        invalid_unit = unit(3, 'deg')
        status = bind('rv_dom_css_translate_set_x', integer, [pointer, pointer])(translate, invalid_unit)
        expect_type_error(status, 'translate x rejects angle')
        after = handle('rv_dom_css_translate_get_x', [pointer], [translate], 'rv_dom_css_style_value_release')
        expect(after == x, 'invalid translate setter preserves input')
        status = bind('rv_dom_css_translate_set_y', integer, [pointer, pointer])(translate, invalid_unit)
        expect_type_error(status, 'translate y rejects angle')
        after_y = handle('rv_dom_css_translate_get_y', [pointer], [translate], 'rv_dom_css_style_value_release')
        expect(after_y == y, 'invalid translate y preserves input')
        translated_z = handle('rv_dom_css_translate_get_z', [pointer], [translate3d], 'rv_dom_css_style_value_release')
        expect(translated_z == z, 'translate z getter retains original numeric object')
        invalid_number = Numberish(1, 2, 0, x)
        for field, expected in [('x', 2), ('y', 3), ('z', 1)]:
            before = scale_number(scale, field)
            status = bind('rv_dom_css_scale_set_' + field, integer, [pointer, pointer])(scale, ctypes.byref(invalid_number))
            expect_type_error(status, 'scale ' + field + ' rejects length')
            expect(before == expected and scale_number(scale, field) == expected, 'invalid scale ' + field + ' preserves input')
        for invalid in [float('nan'), float('inf'), -float('inf')]:
            invalid_number = Numberish(1, 1, invalid, None)
            result = pointer()
            expect_type_error(bind('rv_dom_css_scale_create', integer, [pointer] * 4 + [ctypes.POINTER(pointer)])(document, ctypes.byref(invalid_number), ctypes.byref(one), None, ctypes.byref(result)), 'restricted scale number')

        matrix = handle('rv_dom_dom_matrix_create', [pointer, pointer], [document, None], 'rv_dom_dom_matrix_read_only_release')
        false_value = integer(0)
        options = MatrixOptions(ctypes.sizeof(MatrixOptions), ctypes.pointer(false_value))
        matrix_component = handle('rv_dom_css_matrix_component_create', [pointer] * 3, [document, matrix, ctypes.byref(options)])
        internal = handle('rv_dom_css_matrix_component_get_matrix', [pointer], [matrix_component], 'rv_dom_dom_matrix_read_only_release')
        expect(internal != matrix, 'matrix component copies constructor input')
        converted = to_matrix(matrix_component)
        converted_again = to_matrix(matrix_component)
        expect(converted != internal and converted_again != internal and converted != converted_again, 'every 3D matrix conversion is independent')
        expect(not flag(converted, True), 'forced 3D component produces 3D matrix')
        call('rv_dom_dom_matrix_set_a', [pointer, number], converted, 9)
        expect(scalar(internal, 'a') == 1, 'mutating converted matrix preserves component')

        none_text, none_length = text_input('none')
        perspective_value = PerspectiveValue(1, 2, None, Span(ctypes.cast(none_text, pointer), none_length), None)
        perspective = handle('rv_dom_css_perspective_create', [pointer, pointer], [document, ctypes.byref(perspective_value)])
        expect(not flag(perspective), 'perspective none component is 3D')
        perspective_matrix = to_matrix(perspective)
        expect(not flag(perspective_matrix, True), 'perspective none matrix keeps component 3D flag')
        perspective_list = component_list([perspective])
        perspective_list_matrix = handle('rv_dom_css_transform_value_to_matrix', [pointer], [perspective_list], 'rv_dom_dom_matrix_read_only_release')
        expect(not flag(perspective_list_matrix, True), 'perspective none list matrix stays 3D')

        length_value = PerspectiveValue(1, 1, unit(200, 'px'), Span(), None)
        positive_perspective = handle('rv_dom_css_perspective_create', [pointer, pointer], [document, ctypes.byref(length_value)])
        positive_matrix = to_matrix(positive_perspective)
        expect(scalar(positive_matrix, 'm34') == -0.005 and not flag(positive_matrix, True), 'positive perspective matrix')
        for symbol in ['percent', 'em']:
            relative = handle('rv_dom_css_translate_create', [pointer] * 4, [document, unit(10, symbol), unit(0, 'px'), None])
            result = pointer()
            expect_type_error(bind('rv_dom_css_transform_component_to_matrix', integer, [pointer, ctypes.POINTER(pointer)])(relative, ctypes.byref(result)), 'nonabsolute translation ' + symbol)

        result = pointer()
        empty = Components(1, 0, None)
        expect_type_error(bind('rv_dom_css_transform_value_create', integer, [pointer, pointer, ctypes.POINTER(pointer)])(document, ctypes.byref(empty), ctypes.byref(result)), 'empty transform list')
        missing = pointer(123)
        call('rv_dom_css_transform_value_item', [pointer, unsigned, ctypes.POINTER(pointer)], transforms, 99, ctypes.byref(missing))
        expect(not missing.value, 'missing transform item is null in the native ABI')
        for index in [4, 4294967295]:
            status = bind('rv_dom_css_transform_value_set_item', integer, [pointer, unsigned, pointer])(transforms, index, rotation)
            expect(status == -3, 'out-of-range transform index rejected')
            if status == -3:
                buffer, size = ctypes.create_string_buffer(256), integer()
                call('rv_last_exception', [integer, pointer, integer, ctypes.POINTER(integer)], 0, buffer, len(buffer), ctypes.byref(size))
                expect(buffer.raw[:size.value] == b'RangeError', 'indexed setter RangeError')
        call('rv_dom_css_transform_value_get_length', [pointer, ctypes.POINTER(unsigned)], transforms, ctypes.byref(length))
        expect(length.value == 3, 'failed indexed writes preserve list length')
        call('rv_dom_css_transform_value_set_item', [pointer, unsigned, pointer], transforms, 0, scale)
        replaced = handle('rv_dom_css_transform_value_item', [pointer, unsigned], [transforms, 0])
        expect(replaced == scale, 'indexed replacement keeps component identity')

        property_name, property_length = text_input('transform')
        css, css_length = text_input('translate(10px, 20px) scale(2, 3)')
        parsed = handle('rv_dom_css_style_value_parse', [pointer, pointer, integer, pointer, integer], [document, property_name, property_length, css, css_length], 'rv_dom_css_style_value_release')
        parsed_matrix = handle('rv_dom_css_transform_value_to_matrix', [pointer], [parsed], 'rv_dom_dom_matrix_read_only_release')
        expect(affine(parsed_matrix) == (2, 0, 0, 3, 10, 20), 'parsed CSS transform exposes structured list')
        markup = b'<style>#paint {position:absolute;left:0;top:0;width:10px;height:10px;transform-origin:0 0}</style><div id="paint"></div>'
        call('rv_dom_element_set_inner_html', [pointer, Utf8], body, markup)
        painted = bind('rv_document_get_element_by_id', pointer, [pointer, ctypes.c_char_p])(host, b'paint')
        expect(bool(painted), 'find rendering fixture element', True)
        retained.append(('rv_node_release', painted))
        style_map = handle('rv_dom_html_element_get_attribute_style_map', [pointer], [painted], 'rv_dom_style_property_map_read_only_release')
        style_value_array = (StyleInput * 1)(StyleInput(1, 1, parsed, Span()))
        style_values = StyleInputs(1, 1, style_value_array)
        call('rv_dom_style_property_map_set', [pointer, pointer, pointer, integer, ctypes.POINTER(StyleInputs)],
             style_map, document, property_name, property_length, ctypes.byref(style_values))
        rectangle = handle('rv_dom_element_get_bounding_client_rect', [pointer], [painted], 'rv_dom_dom_rect_read_only_release')
        rendered = []
        for field in ['x', 'y', 'width', 'height']:
            value = number()
            call('rv_dom_dom_rect_read_only_get_' + field, [pointer, ctypes.POINTER(number)], rectangle, ctypes.byref(value))
            rendered.append(value.value)
        expect(tuple(rendered) == (10, 20, 20, 30), 'typed transform list updates actual element geometry through StylePropertyMap')

        temporary_angle = unit(13, 'deg')
        temporary_rotation = handle('rv_dom_css_rotate_create_1', [pointer, pointer], [document, temporary_angle])
        retained_unit = handle('rv_dom_css_rotate_get_angle', [pointer], [temporary_rotation], 'rv_dom_css_style_value_release')
        for release, value in [('rv_dom_css_style_value_release', temporary_angle), ('rv_dom_css_transform_component_release', temporary_rotation)]:
            retained.remove((release, value))
            bind(release, None, [pointer])(value)
        numeric = number()
        call('rv_dom_css_unit_value_get_value', [pointer, ctypes.POINTER(number)], retained_unit, ctypes.byref(numeric))
        expect(retained_unit == temporary_angle and numeric.value == 13, 'returned numeric value survives component and initial-value release')

        call('rv_dom_dom_matrix_set_m13', [pointer, number], matrix, 5)
        true_value = integer(1)
        options_2d = MatrixOptions(ctypes.sizeof(MatrixOptions), ctypes.pointer(true_value))
        forced_2d = handle('rv_dom_css_matrix_component_create', [pointer] * 3, [document, matrix, ctypes.byref(options_2d)])
        forced_2d_matrix = to_matrix(forced_2d)
        expect(flag(forced_2d) and flag(forced_2d_matrix, True) and scalar(forced_2d_matrix, 'm13') == 0, 'forced 2D matrix conversion flattens a copied 3D matrix')
        forced_internal = handle('rv_dom_css_matrix_component_get_matrix', [pointer], [forced_2d], 'rv_dom_dom_matrix_read_only_release')
        expect(scalar(forced_internal, 'm13') == 5 and forced_internal != forced_2d_matrix, '2D conversion preserves internal 3D matrix')

        keyword_text, keyword_length = text_input('none')
        keyword = handle('rv_dom_cssom_keyword_value_create', [pointer, pointer, integer], [document, keyword_text, keyword_length], 'rv_dom_css_style_value_release')
        keyword_value = PerspectiveValue(1, 3, None, Span(), keyword)
        keyword_perspective = handle('rv_dom_css_perspective_create', [pointer, pointer], [document, ctypes.byref(keyword_value)])
        expect(not flag(to_matrix(keyword_perspective), True), 'perspective keyword reference produces 3D identity')
        for field in [length_value, perspective_value, keyword_value]:
            value = handle('rv_dom_css_perspective_create', [pointer, pointer], [document, ctypes.byref(field)])
            matrix_result = to_matrix(value)
            expected_m34 = -0.005 if field.tag == 1 else 0
            expected = tuple(expected_m34 if (column, row) == (3, 4) else 1 if column == row else 0
                             for column in range(1, 5) for row in range(1, 5))
            actual = tuple(scalar(matrix_result, f'm{column}{row}') for column in range(1, 5) for row in range(1, 5))
            expect(actual == expected and not flag(matrix_result, True), 'complete perspective matrix for each union arm')

        for family, argument_units, expected in [
            ('css_skew', [(45, 'deg'), (0, 'deg')], (1, 0, 1, 1, 0, 0)),
            ('css_skew_x', [(45, 'deg')], (1, 0, 1, 1, 0, 0)),
            ('css_skew_y', [(45, 'deg')], (1, 1, 0, 1, 0, 0)),
        ]:
            arguments = [unit(value, symbol) for value, symbol in argument_units]
            value = handle('rv_dom_' + family + '_create', [pointer] * (len(arguments) + 1), [document, *arguments])
            actual = affine(to_matrix(value))
            expect(all(math.isclose(actual_value, expected_value, abs_tol=1e-12) for actual_value, expected_value in zip(actual, expected)), family + ': matrix coefficients')

        wrong = pointer()
        expect(bind('rv_dom_css_translate_get_x', integer, [pointer, ctypes.POINTER(pointer)])(scale, ctypes.byref(wrong)) == -11, 'wrong component subtype rejected')
        statuses = []
        def worker():
            output = pointer()
            statuses.append(translate_create(document, x, y, None, ctypes.byref(output)))
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        expect(statuses == [-2], 'transform construction enforces engine thread')
    finally:
        for release, value in reversed(retained):
            bind(release, None, [pointer])(value)
        bind('rv_host_destroy', None, [pointer])(host)
        if search is not None:
            search.close()
    if failures:
        raise AssertionError('\n'.join(failures))
    if assertions != 405:
        raise AssertionError(f'Expected 405 typed transform assertions, observed {assertions}')
    print(f'PASS typed CSS transforms: {assertions} assertions', flush=True)
    return assertions


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    verify(parser.parse_args().native_directory)
