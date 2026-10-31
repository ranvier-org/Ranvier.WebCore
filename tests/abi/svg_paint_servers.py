import argparse
import ctypes
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe
from utf8_inputs import Utf8


def verify(native_directory):
    with SvgProbe(native_directory) as p:
        p.load((Path(__file__).resolve().parents[1] / 'fixtures/svg-paint-servers.svg').read_bytes())
        linear = p.node('linear')
        radial, pattern, inherited, root = (p.node(name) for name in ['radial', 'pattern', 'inherited', 'root'])
        lengths = {}
        for kind, target, fields in [
            ('svg_linear_gradient_element', linear, [('x1', 0), ('y1', 0), ('x2', 100), ('y2', 0)]),
            ('svg_radial_gradient_element', radial, [('cx', 200), ('cy', 50), ('r', 50), ('fx', 200), ('fy', 50), ('fr', 0)]),
            ('svg_pattern_element', pattern, [('x', 0), ('y', 120), ('width', 10), ('height', 10)]),
        ]:
            for field, expected in fields:
                animated, base = p.length(kind, target, field)
                lengths[(target, field)] = base
                p.expect(p.read('svg_length', base, 'value') == expected, 'real paint-server coordinate ' + field)
                again = p.property('svg_animated_length', animated, 'base_val', 'svg_length')
                p.expect(again == base, 'live paint-server base identity ' + field)
                readonly = p.property('svg_animated_length', animated, 'anim_val', 'svg_length')
                p.exception('rv_dom_svg_length_set_value', [p.pointer, p.single], [readonly, 99], 'NoModificationAllowedError')
                p.set_length(base, expected + 1)
                p.expect(p.read('svg_length', base, 'value') == expected + 1, 'typed coordinate edit ' + field)
                p.expect(p.attribute(target, field) == str(expected + 1), 'coordinate attribute reflection ' + field)
                p.set_length(base, expected)
        enums = {}
        for kind, target, fields in [('svg_gradient_element', linear, ['gradient_units', 'spread_method']), ('svg_pattern_element', pattern, ['pattern_units', 'pattern_content_units'])]:
            for field in fields:
                value = p.property(kind, target, field, 'svg_animated_enumeration')
                enums[(target, field)] = value
                p.expect(p.read('svg_animated_enumeration', value, 'base_val', p.short) == 1, 'actual paint-server enum ' + field)
                p.exception('rv_dom_svg_animated_enumeration_set_base_val', [p.pointer, p.short], [value, 999], 'TypeError')
                p.expect(p.read('svg_animated_enumeration', value, 'base_val', p.short) == 1, 'invalid enum preserves prior value ' + field)
        def enum(target, field, value):
            p.call('rv_dom_svg_animated_enumeration_set_base_val', [p.pointer, p.short], enums[(target, field)], value)
        def set_lengths(target, edits):
            for field, value in edits:
                p.set_length(lengths[(target, field)], value)
        def transform_list(kind, target, field):
            animated = p.property(kind, target, field, 'svg_animated_transform_list')
            base = p.property('svg_animated_transform_list', animated, 'base_val', 'svg_transform_list')
            readonly = p.property('svg_animated_transform_list', animated, 'anim_val', 'svg_transform_list')
            p.exception('rv_dom_svg_transform_list_clear', [p.pointer], [readonly], 'NoModificationAllowedError')
            return base
        def translate(base, x, y):
            transform = p.object('rv_dom_svgsvg_element_create_svg_transform', [p.pointer], [root], 'svg_transform')
            p.call('rv_dom_svg_transform_set_translate', [p.pointer, p.single, p.single], transform, x, y)
            item = p.object('rv_dom_svg_transform_list_append_item', [p.pointer, p.pointer], [base, transform], 'svg_transform')
            matrix = p.property('svg_transform', item, 'matrix', 'svg_matrix')
            p.close([p.read('svg_matrix', matrix, field, p.double) for field in ['a', 'b', 'c', 'd', 'e', 'f']], [1, 0, 0, 1, x, y], 'actual paint-server transform matrix')
        x2 = lengths[(linear, 'x2')]
        p.expect(p.read('svg_length', x2, 'value') == 100, 'actual gradient coordinate producer')
        before = p.paint()
        p.expect(p.pixel(before, 25, 50)[0] > p.pixel(before, 25, 50)[2], 'initial real linear gradient paint')
        p.expect(p.pixel(before, 325, 50)[0] > p.pixel(before, 325, 50)[2], 'initial inherited gradient paint')
        p.expect(p.pixel(before, 200, 50)[0] > 240 and p.pixel(before, 200, 50)[2] < 10, 'initial radial center paint')
        p.expect(p.pixel(before, 2, 122) == [255, 0, 0, 255] and p.pixel(before, 7, 122) == [0, 0, 255, 255], 'initial real patterned paint')
        href = p.property('svg_gradient_element', inherited, 'href', 'svg_animated_string')
        p.expect(p.text('rv_dom_svg_animated_string_get_base_val', [p.pointer], href) == '#linear', 'actual gradient URI reference')
        inherited_x2 = p.length('svg_linear_gradient_element', inherited, 'x2')[1]
        p.expect(p.read('svg_length', inherited_x2, 'value') == 500, 'authored default remains distinct from inherited rendered coordinate')
        p.set_length(x2, 50)
        p.expect(p.attribute(linear, 'x2') == '50', 'gradient mutation reflects authored coordinate')
        after = p.paint()
        p.expect(p.pixel(after, 75, 50) == [0, 0, 255, 255], 'typed coordinate mutation changes actual gradient paint')
        p.expect(p.pixel(after, 375, 50) == [0, 0, 255, 255], 'base coordinate mutation changes inherited paint')
        gradient_transform = transform_list('svg_gradient_element', linear, 'gradient_transform')
        translate(gradient_transform, 20, 0)
        transformed = p.paint()
        p.expect(p.pixel(transformed, 50, 50)[0] > p.pixel(after, 50, 50)[0], 'gradient transform changes actual paint coordinates')
        p.call('rv_dom_svg_transform_list_clear', [p.pointer], gradient_transform)
        enum(linear, 'spread_method', 3)
        repeated = p.paint()
        p.close(p.pixel(repeated, 25, 50), p.pixel(repeated, 75, 50), 'repeat spread method affects actual paint', tolerance=1)
        enum(linear, 'spread_method', 1)
        enum(linear, 'gradient_units', 2)
        object_units = p.paint()
        p.expect(p.pixel(object_units, 75, 50)[0] > 240 and p.pixel(object_units, 75, 50)[2] < 10, 'gradient objectBoundingBox units affect actual paint')
        enum(linear, 'gradient_units', 1)
        p.call('rv_dom_svg_animated_string_set_base_val', [p.pointer, Utf8], href, b'#missing')
        missing = p.paint()
        p.expect(p.pixel(missing, 325, 50) == [255, 255, 255, 255], 'missing gradient URI produces no invented paint')
        p.call('rv_dom_svg_animated_string_set_base_val', [p.pointer, Utf8], href, b'#linear')
        set_lengths(radial, [('cx', 225), ('cy', 55), ('r', 20), ('fx', 225), ('fy', 55)])
        moved_radial = p.paint()
        p.expect(p.pixel(moved_radial, 225, 55)[0] > 240 and p.pixel(moved_radial, 200, 55) == [0, 0, 255, 255], 'radial coordinate mutation changes actual paint')
        p.set_length(lengths[(radial, 'fr')], 10)
        focal_radius = p.paint()
        p.expect(p.pixel(focal_radius, 230, 55)[0] > p.pixel(moved_radial, 230, 55)[0], 'radial focal-radius mutation changes actual paint')
        start = p.node('start')
        offset = p.property('svg_stop_element', start, 'offset', 'svg_animated_number')
        p.call('rv_dom_svg_animated_number_set_base_val', [p.pointer, p.single], offset, 0.5)
        p.expect(p.attribute(start, 'offset') == '0.5', 'stop offset reflects typed edit')
        style = p.property('svg_element', start, 'style', 'css_style_declaration')
        p.call('rv_dom_css_style_declaration_set_property', [p.pointer, Utf8, Utf8, Utf8], style, b'stop-color', b'rgb(0, 255, 0)', b'')
        green = p.paint()
        p.expect(p.pixel(green, 10, 50) == [0, 255, 0, 255], 'stop offset and CSS color change actual paint')
        p.call('rv_dom_css_style_declaration_set_property', [p.pointer, Utf8, Utf8, Utf8], style, b'stop-opacity', b'0.5', b'')
        faded = p.pixel(p.paint(), 10, 50)
        p.expect(faded[1] == 255 and 120 <= faded[0] <= 135 and 120 <= faded[2] <= 135, 'stop opacity changes actual composited paint')
        set_lengths(pattern, [('x', 5), ('width', 20), ('height', 20)])
        shifted = p.paint()
        p.expect(p.pixel(shifted, 7, 122) == [255, 0, 0, 255] and p.pixel(shifted, 17, 122) == [255, 255, 255, 255] and p.pixel(shifted, 7, 135) == [255, 255, 255, 255], 'pattern coordinate/dimension edits change actual tiles')
        p.set_length(lengths[(pattern, 'y')], 125)
        shifted_y = p.paint()
        p.expect(p.pixel(shifted_y, 7, 122) == [255, 255, 255, 255] and p.pixel(shifted_y, 7, 127) == [255, 0, 0, 255], 'pattern y edit changes actual tiles')
        pattern_transform = transform_list('svg_pattern_element', pattern, 'pattern_transform')
        translate(pattern_transform, 3, 4)
        translated_pattern = p.paint()
        p.expect(p.pixel(translated_pattern, 10, 131) == [255, 0, 0, 255] and p.pixel(translated_pattern, 15, 131) == [0, 0, 255, 255], 'pattern transform changes actual paint')
        p.call('rv_dom_element_set_attribute', [p.pointer, Utf8, Utf8], pattern, b'viewBox', b'0 0 20 20')
        view_box_wrapper = p.property('svg_pattern_element', pattern, 'view_box', 'svg_animated_rect')
        view_box = p.property('svg_animated_rect', view_box_wrapper, 'base_val', 'svg_rect')
        for field, value in [('x', 0), ('y', 0), ('width', 10), ('height', 10)]:
            p.call('rv_dom_svg_rect_set_' + field, [p.pointer, p.single], view_box, value)
        aspect_wrapper = p.property('svg_pattern_element', pattern, 'preserve_aspect_ratio', 'svg_animated_preserve_aspect_ratio')
        aspect = p.property('svg_animated_preserve_aspect_ratio', aspect_wrapper, 'base_val', 'svg_preserve_aspect_ratio')
        p.expect(p.read('svg_preserve_aspect_ratio', aspect, 'align', p.short) == 6, 'actual pattern aspect ratio default')
        p.call('rv_dom_svg_preserve_aspect_ratio_set_align', [p.pointer, p.short], aspect, 1)
        view_box_paint = p.paint()
        print('PATTERN_VIEWBOX', {'attribute': p.attribute(pattern, 'viewBox'), 'rect': [p.read('svg_rect', view_box, field) for field in ['x','y','width','height']], 'pixel15_131': p.pixel(view_box_paint,15,131)}, flush=True)
        p.expect(p.pixel(view_box_paint, 15, 131) == [255, 0, 0, 255], 'pattern viewBox changes actual content scaling')
        p.call('rv_dom_svg_transform_list_clear', [p.pointer], pattern_transform)
        p.call('rv_dom_element_remove_attribute', [p.pointer, Utf8], pattern, b'viewBox')
        set_lengths(pattern, [('x', 0), ('y', 0), ('width', 1), ('height', 1)])
        enum(pattern, 'pattern_units', 2)
        unit_paint = p.paint()
        print('PATTERN_UNITS', {'values': [p.read('svg_length',lengths[(pattern,field)],'value') for field in ['x','y','width','height']], 'samples': {str((x,y)):p.pixel(unit_paint,x,y) for x,y in [(2,122),(12,122),(2,152),(12,152)]}}, flush=True)
        p.expect(p.pixel(unit_paint, 2, 122) == [255, 0, 0, 255] and p.pixel(unit_paint, 12, 122) == [255, 255, 255, 255], 'pattern objectBoundingBox unit effects')
        enum(pattern, 'pattern_content_units', 2)
        content_units = p.paint()
        p.expect(p.pixel(content_units, 12, 122) == [255, 0, 0, 255], 'pattern content units change actual child scale')
        enum(pattern, 'pattern_content_units', 1)
        enum(pattern, 'pattern_units', 1)
        set_lengths(pattern, [('x', 0), ('y', 120), ('width', 10), ('height', 10)])
        for field, value in [('required_extensions', 'urn:unsupported-svg-extension'), ('system_language', 'zz')]:
            items = p.property('svg_pattern_element', pattern, field, 'svg_string_list')
            p.expect(p.read('svg_string_list', items, 'number_of_items', p.unsigned) == 0, 'initial SVGTests list ' + field)
            p.expect(p.text('rv_dom_svg_string_list_append_item', [p.pointer, Utf8], items, value.encode()) == value, 'SVGTests typed list edit ' + field)
            p.expect(p.read('svg_string_list', items, 'number_of_items', p.unsigned) == 1, 'SVGTests edit changes actual list length ' + field)
            p.expect(p.text('rv_dom_svg_string_list_get_item', [p.pointer, p.unsigned], items, 0) == value, 'SVGTests edited item is readable ' + field)
            invalid_pattern = p.paint()
            p.expect(p.pixel(invalid_pattern, 2, 122) == [255, 0, 0, 255], 'measured native/browser pattern paint is unaffected by SVGTests state ' + field)
            p.call('rv_dom_svg_string_list_clear', [p.pointer], items)
            p.expect(p.read('svg_string_list', items, 'number_of_items', p.unsigned) == 0, 'SVGTests clear changes actual list length ' + field)
            p.expect(p.pixel(p.paint(), 2, 122) == [255, 0, 0, 255], 'cleared SVGTests restores actual paint ' + field)
        pattern_href = p.property('svg_pattern_element', p.node('patternDerived'), 'href', 'svg_animated_string')
        p.expect(p.text('rv_dom_svg_animated_string_get_base_val', [p.pointer], pattern_href) == '#pattern', 'pattern inheritance URI')
        p.call('rv_dom_svg_animated_string_set_base_val', [p.pointer, Utf8], pattern_href, b'#missing')
        p.expect(p.pixel(p.paint(), 202, 122) == [255, 255, 255, 255], 'missing pattern reference has no invented paint')
        wrong = p.pointer(123)
        p.expect(p.bind('rv_dom_svg_linear_gradient_element_get_x2', p.integer, [p.pointer, ctypes.POINTER(p.pointer)])(root, ctypes.byref(wrong)) == -11 and wrong.value == 123, 'gradient subtype error preserves output')
        statuses = []
        def worker():
            statuses.append(p.bind('rv_dom_svg_linear_gradient_element_get_x2', p.integer, [p.pointer, ctypes.POINTER(p.pointer)])(linear, ctypes.byref(wrong)))
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        p.expect(statuses == [-2] and wrong.value == 123, 'gradient thread error preserves output')
        for owner in [root, linear, radial, pattern]:
            p.watch(owner)
        for release, value in list(reversed(p.retained)):
            if value != x2:
                p.bind(release, None, [p.pointer])(value)
                p.retained.remove((release, value))
        p.dispose_host()
        p.collect()
        p.expect_expired()
        p.expect(p.read('svg_length', x2, 'value') == 50, 'retained gradient coordinate survives owner destruction')
        p.set_length(x2, 88)
        p.expect(p.read('svg_length', x2, 'value') == 88, 'detached gradient coordinate remains safely mutable')
        print(f'PASS SVG paint servers: {p.assertions} assertions', flush=True)
        return p.assertions


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    verify(parser.parse_args().native_directory)
