"""R03 canvas state, transforms and compositing: save/restore/reset, the current transform and getTransform, globalAlpha,
globalCompositeOperation and filter, checked across consecutive drawing operations with pixel assertions. Pixels are
read from the host's software paint over a white page, so a transparent canvas pixel reads white; only interior pixels
are compared. Canvas layers are behind CanvasLayersEnabled, which the host leaves off. The Chromium oracle is
docs/canvas-state-evidence/red-chromium.json."""
import argparse
import ctypes
import hashlib
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe
from utf8_inputs import Utf8

ABI = 55
OK, NULL_ARGUMENT, DOM_EXCEPTION, UNSUPPORTED = 0, -1, -3, -9
TWO_D = 1
WHITE = [255, 255, 255, 255]
BLUR_TOLERANCE = 12
RED, GREEN, BLUE = [255, 0, 0, 255], [0, 255, 0, 255], [0, 0, 255, 255]
PAGE = ('<!doctype html><style>html,body{margin:0;background:#fff}canvas{display:block;width:60px;height:40px}</style>'
        '<body><canvas id=c width=60 height=40></canvas>')
MATRIX_FIELDS = ['a', 'b', 'c', 'd', 'e', 'f', 'm11', 'm12', 'm21', 'm22', 'm41', 'm42']
COMPOSITES = ['source-over', 'source-in', 'source-out', 'source-atop', 'destination-over', 'destination-in', 'destination-out',
              'destination-atop', 'lighter', 'copy', 'xor', 'multiply', 'screen', 'overlay', 'darken', 'lighten', 'color-dodge',
              'color-burn', 'hard-light', 'soft-light', 'difference', 'exclusion', 'hue', 'saturation', 'color', 'luminosity']


class Span(ctypes.Structure):
    _fields_ = [('data', ctypes.POINTER(ctypes.c_uint8)), ('length', ctypes.c_int32)]


class Style(ctypes.Structure):
    _fields_ = [('present', ctypes.c_int32), ('tag', ctypes.c_int32), ('arm0', Span), ('arm1', ctypes.c_void_p), ('arm2', ctypes.c_void_p)]


class Matrix(ctypes.Structure):
    _fields_ = [('size', ctypes.c_uint32)] + [(name, ctypes.POINTER(ctypes.c_double)) for name in MATRIX_FIELDS]


def matrix(**fields):
    value = Matrix(ctypes.sizeof(Matrix))
    keep = []
    for name, number in fields.items():
        cell = ctypes.c_double(number)
        keep.append(cell)
        setattr(value, name, ctypes.pointer(cell))
    return value, keep


def span(text):
    data = text.encode()
    buffer = (ctypes.c_uint8 * max(len(data), 1)).from_buffer_copy(data or bytes(1))
    return Span(ctypes.cast(buffer, ctypes.POINTER(ctypes.c_uint8)), len(data)), buffer


def verify(directory, evidence_json=None):
    directory = Path(directory).resolve()
    before = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
    report = {}
    with SvgProbe(directory, 320, 240) as p:
        P, I, D = p.pointer, p.integer, ctypes.c_double
        expect = p.expect
        expect(p.bind('rv_abi_version', I, [])() == ABI, 'ABI version ' + str(ABI))
        has = p.bind('rv_abi_has', I, [ctypes.c_char_p])
        for feature in ['canvas-context', 'canvas-filters', 'dom:CanvasRenderingContext2D']:
            expect(has(feature.encode()) == 1, 'rv_abi_has ' + feature)
        C = 'rv_dom_canvas_rendering_context2_d_'

        def fn(name, arguments):
            return p.bind(C + name, I, arguments)

        get_context = p.bind('rv_canvas_get_context', I, [P, I, P, ctypes.POINTER(P)])
        set_style = fn('set_fill_style', [P, ctypes.POINTER(Style)])
        get_style = fn('get_fill_style', [P, ctypes.POINTER(Style)])
        release_style = p.bind('rv_dom_union_dom_string_or_canvas_gradient_or_canvas_pattern_release', None, [ctypes.POINTER(Style)])
        fill_rect = fn('fill_rect', [P] + [D] * 4)
        simple = {name: fn(name, [P]) for name in ['save', 'restore', 'reset', 'reset_transform', 'begin_path', 'begin_layer', 'end_layer']}
        scale = fn('scale', [P, D, D])
        rotate = fn('rotate', [P, D])
        translate = fn('translate', [P, D, D])
        transform = fn('transform', [P] + [D] * 6)
        set_transform_6 = fn('set_transform_6', [P] + [D] * 6)
        set_transform_1 = fn('set_transform_1', [P, ctypes.POINTER(Matrix)])
        get_transform = fn('get_transform', [P, ctypes.POINTER(P)])
        get_alpha = fn('get_global_alpha', [P, ctypes.POINTER(D)])
        set_alpha = fn('set_global_alpha', [P, D])
        set_composite = fn('set_global_composite_operation', [P, Utf8])
        set_filter = fn('set_filter', [P, Utf8])
        rect = fn('rect', [P] + [D] * 4)
        clip = fn('clip_1', [P, I])
        hit = fn('is_point_in_path_3', [P, D, D, I, ctypes.POINTER(I)])
        hit_path = fn('is_point_in_path_4', [P, P, D, D, I, ctypes.POINTER(I)])
        release_matrix = p.bind('rv_dom_dom_matrix_read_only_release', None, [P])

        def ok(status, label):
            expect(status == OK, label + ': status ' + str(status))

        def text(name):
            return p.text(C + 'get_' + name, [P], ctx)

        def set_fill(value):
            arm, keep = span(value)
            ok(set_style(ctx, ctypes.byref(Style(1, 1, arm, None, None))), 'fillStyle ' + value)

        def fill_style():
            value = Style()
            ok(get_style(ctx, ctypes.byref(value)), 'fillStyle getter')
            result = ctypes.string_at(value.arm0.data, value.arm0.length).decode()
            release_style(ctypes.byref(value))
            return result

        def alpha():
            value = D()
            ok(get_alpha(ctx, ctypes.byref(value)), 'globalAlpha getter')
            return value.value

        def current():
            handle = P()
            ok(get_transform(ctx, ctypes.byref(handle)), 'getTransform')
            values = []
            for name in 'abcdef':
                value = D()
                p.call('rv_dom_dom_matrix_read_only_get_' + name, [P, ctypes.POINTER(D)], handle, ctypes.byref(value))
                values.append(round(value.value, 6) + 0)
            for name in ['is2_d', 'is_identity']:
                flag = I()
                p.call('rv_dom_dom_matrix_read_only_get_' + name, [P, ctypes.POINTER(I)], handle, ctypes.byref(flag))
                values.append(bool(flag.value))
            return values, handle.value

        def matrix_values():
            values, handle = current()
            release_matrix(handle)
            return values

        def hits(x, y):
            out = I(-1)
            ok(hit(ctx, x, y, 0, ctypes.byref(out)), 'isPointInPath')
            return bool(out.value)

        def pixels(*points):
            rgba = p.paint()
            return [p.pixel(rgba, x, y) for x, y in points]

        def near(actual, expected, label, tolerance=2):
            expect(len(actual) == len(expected) and all(abs(a - b) <= tolerance for a, b in zip(actual, expected)), label + ': ' + str(actual))

        def reset_bitmap():
            p.call('rv_dom_html_canvas_element_set_width', [P, p.unsigned], c, 60)

        p.load(PAGE, standalone=False)
        c = p.node('c')
        handle = P()
        ok(get_context(c, TWO_D, None, ctypes.byref(handle)), 'getContext 2d')
        ctx = handle.value

        # Defaults.
        report['defaults'] = {'transform': matrix_values(), 'alpha': alpha(), 'composite': text('global_composite_operation'), 'filter': text('filter')}
        expect(report['defaults'] == {'transform': [1, 0, 0, 1, 0, 0, True, True], 'alpha': 1.0, 'composite': 'source-over', 'filter': 'none'},
               'defaults: ' + str(report['defaults']))

        # 1. Transforms.
        ok(translate(ctx, 10, 5), 'translate')
        report['translate'] = matrix_values()
        ok(scale(ctx, 2, 3), 'scale')
        report['scale'] = matrix_values()
        ok(simple['reset_transform'](ctx), 'resetTransform')
        ok(rotate(ctx, math.pi / 2), 'rotate')
        report['rotate'] = matrix_values()
        ok(set_transform_6(ctx, 1, 0, 0, 1, 0, 0), 'setTransform(6)')
        ok(transform(ctx, 1, 0, 0, 1, 5, 5), 'transform')
        ok(transform(ctx, 2, 0, 0, 2, 0, 0), 'transform')
        report['transform'] = matrix_values()
        init, keep = matrix(a=1, b=0, c=0, d=1, e=7, f=8)
        ok(set_transform_1(ctx, ctypes.byref(init)), 'setTransform(init)')
        report['setTransformInit'] = matrix_values()
        init, keep = matrix(m41=3, m42=4)
        ok(set_transform_1(ctx, ctypes.byref(init)), 'setTransform(m41, m42)')
        report['setTransformM'] = matrix_values()
        ok(set_transform_1(ctx, None), 'setTransform()')
        report['setTransformDefault'] = matrix_values()
        conflict, keep = matrix(a=1, m11=2)
        status = set_transform_1(ctx, ctypes.byref(conflict))
        expect(status == DOM_EXCEPTION and p.text('rv_last_exception', [I], 0) == 'TypeError', 'setTransform conflicting members: TypeError')
        ok(set_transform_6(ctx, 1, 0, 0, 1, 0, 0), 'setTransform(6)')
        for call in [lambda: translate(ctx, float('nan'), 1), lambda: scale(ctx, float('inf'), 1),
                     lambda: set_transform_6(ctx, float('nan'), 0, 0, 1, 0, 0), lambda: rotate(ctx, float('nan'))]:
            ok(call(), 'non-finite transform call')
        report['nonFinite'] = matrix_values()
        held, held_handle = current()
        ok(translate(ctx, 1, 1), 'translate after getTransform')
        report['getTransformIsCopy'] = current()[0][:6] != held[:6] and matrix_values() is not None
        values = []
        for name in 'ef':
            value = D()
            p.call('rv_dom_dom_matrix_read_only_get_' + name, [P, ctypes.POINTER(D)], held_handle, ctypes.byref(value))
            values.append(value.value)
        expect(values == [0.0, 0.0], 'a held getTransform matrix is a copy')
        release_matrix(held_handle)
        expect(report == {**report, 'translate': [1, 0, 0, 1, 10, 5, True, False], 'scale': [2, 0, 0, 3, 10, 5, True, False],
                          'rotate': [0, 1, -1, 0, 0, 0, True, False], 'transform': [2, 0, 0, 2, 5, 5, True, False],
                          'setTransformInit': [1, 0, 0, 1, 7, 8, True, False], 'setTransformM': [1, 0, 0, 1, 3, 4, True, False],
                          'setTransformDefault': [1, 0, 0, 1, 0, 0, True, True], 'nonFinite': [1, 0, 0, 1, 0, 0, True, True]},
               'transform matrices: ' + json.dumps({k: report[k] for k in ['translate', 'scale', 'rotate', 'transform', 'setTransformInit',
                                                                          'setTransformM', 'setTransformDefault', 'nonFinite']}))
        ok(simple['reset_transform'](ctx), 'resetTransform')
        # Drawing under a transform, and hit tests against the transform at construction and at test time.
        ok(translate(ctx, 20, 10), 'translate')
        ok(scale(ctx, 2, 2), 'scale')
        set_fill('#ff0000')
        ok(fill_rect(ctx, 0, 0, 5, 5), 'fillRect under a transform')
        ok(simple['reset_transform'](ctx), 'resetTransform')
        report['drawTransformed'] = pixels((25, 15), (2, 2), (32, 15))
        expect(report['drawTransformed'] == [RED, WHITE, WHITE], 'drawing under a transform: ' + str(report['drawTransformed']))
        ok(set_transform_6(ctx, 1, 0, 0, 1, 40, 0), 'setTransform')
        ok(simple['begin_path'](ctx), 'beginPath')
        ok(rect(ctx, 0, 0, 10, 10), 'rect')
        ok(simple['reset_transform'](ctx), 'resetTransform')
        expect([hits(45, 5), hits(5, 5)] == [True, False], 'the current path keeps the transform it was built under')
        square = P()
        document = p.bind('rv_host_document', P, [P])(p.host)
        p.retained.append(('rv_node_release', document))
        ok(p.bind('rv_dom_path2_d_create_0', I, [P, ctypes.POINTER(P)])(document, ctypes.byref(square)), 'Path2D')
        ok(p.bind('rv_dom_path2_d_rect', I, [P] + [D] * 4)(square, 0, 0, 10, 10), 'Path2D.rect')
        ok(translate(ctx, 40, 0), 'translate')
        out = I()
        ok(hit_path(ctx, square, 45, 5, 0, ctypes.byref(out)), 'isPointInPath(path)')
        expect(out.value == 1, 'a Path2D hit test applies the current transform')
        ok(hit_path(ctx, square, 5, 5, 0, ctypes.byref(out)), 'isPointInPath(path)')
        expect(out.value == 0, 'a Path2D hit test misses the untransformed square')
        p.bind('rv_dom_path2_d_release', None, [P])(square)
        ok(simple['reset_transform'](ctx), 'resetTransform')

        # 2. save/restore: fillStyle, transform, alpha, composite and clip, nested, and an unmatched restore.
        reset_bitmap()
        set_fill('#0000ff')
        ok(set_alpha(ctx, 0.5), 'globalAlpha')
        ok(translate(ctx, 5, 5), 'translate')
        ok(simple['save'](ctx), 'save')
        set_fill('#00ff00')
        ok(set_alpha(ctx, 1), 'globalAlpha')
        ok(translate(ctx, 10, 0), 'translate')
        ok(set_composite(ctx, 'copy'), 'globalCompositeOperation')
        ok(simple['begin_path'](ctx), 'beginPath')
        ok(rect(ctx, 0, 0, 20, 20), 'rect')
        ok(clip(ctx, 0), 'clip')
        ok(simple['save'](ctx), 'save')
        set_fill('#ff0000')
        ok(simple['restore'](ctx), 'restore')
        expect(fill_style() == '#00ff00', 'a nested restore')
        ok(simple['restore'](ctx), 'restore')
        report['restored'] = {'fillStyle': fill_style(), 'alpha': alpha(), 'composite': text('global_composite_operation'), 'transform': matrix_values()}
        expect(report['restored'] == {'fillStyle': '#0000ff', 'alpha': 0.5, 'composite': 'source-over', 'transform': [1, 0, 0, 1, 5, 5, True, False]},
               'restored state: ' + str(report['restored']))
        ok(simple['restore'](ctx), 'unmatched restore')
        ok(simple['restore'](ctx), 'unmatched restore')
        expect(fill_style() == '#0000ff' and matrix_values() == [1, 0, 0, 1, 5, 5, True, False], 'an unmatched restore changes nothing')
        ok(simple['reset_transform'](ctx), 'resetTransform')
        ok(set_alpha(ctx, 1), 'globalAlpha')
        set_fill('#ff0000')
        ok(fill_rect(ctx, 0, 0, 60, 40), 'fillRect after restore')
        expect(pixels((50, 35))[0] == RED, 'restore removes the saved clip')

        # 3. reset(): bitmap, state stack, path, transform and styles return to defaults.
        ok(simple['save'](ctx), 'save')
        ok(translate(ctx, 3, 3), 'translate')
        set_fill('#123456')
        ok(set_alpha(ctx, 0.25), 'globalAlpha')
        ok(set_composite(ctx, 'xor'), 'globalCompositeOperation')
        ok(simple['begin_path'](ctx), 'beginPath')
        ok(rect(ctx, 0, 0, 10, 10), 'rect')
        ok(simple['reset'](ctx), 'reset')
        report['reset'] = {'pixel': pixels((50, 35))[0], 'fillStyle': fill_style(), 'alpha': alpha(), 'composite': text('global_composite_operation'),
                           'transform': matrix_values(), 'path': hits(5, 5)}
        ok(simple['restore'](ctx), 'restore after reset')
        report['reset']['restoreAfterReset'] = fill_style()
        expect(report['reset'] == {'pixel': WHITE, 'fillStyle': '#000000', 'alpha': 1.0, 'composite': 'source-over',
                                   'transform': [1, 0, 0, 1, 0, 0, True, True], 'path': False, 'restoreAfterReset': '#000000'},
               'reset: ' + str(report['reset']))

        # 4. globalAlpha.
        ok(set_alpha(ctx, 0.5), 'globalAlpha')
        set_fill('#ff0000')
        ok(fill_rect(ctx, 0, 0, 10, 10), 'half-alpha fillRect')
        report['alphaPixel'] = pixels((5, 5))[0]
        near(report['alphaPixel'], [255, 127, 127, 255], 'half-alpha red over white')
        for value in [2, -1, float('nan'), float('inf')]:
            ok(set_alpha(ctx, value), 'globalAlpha %r' % value)
            expect(alpha() == 0.5, 'globalAlpha %r is ignored' % value)
        ok(set_alpha(ctx, 0), 'globalAlpha 0')
        ok(fill_rect(ctx, 20, 0, 10, 10), 'fillRect at alpha 0')
        expect(pixels((25, 5))[0] == WHITE, 'alpha 0 draws nothing')
        ok(set_alpha(ctx, 1), 'globalAlpha 1')

        # 5. globalCompositeOperation.
        accepted = []
        for name in COMPOSITES:
            ok(set_composite(ctx, name), 'globalCompositeOperation ' + name)
            if text('global_composite_operation') == name:
                accepted.append(name)
        expect(accepted == COMPOSITES, 'every composite operation name: ' + str(sorted(set(COMPOSITES) - set(accepted))))
        ok(set_composite(ctx, 'multiply'), 'multiply')
        for invalid in ['bogus', 'Copy', '', 'source-over ']:
            ok(set_composite(ctx, invalid), 'globalCompositeOperation ' + repr(invalid))
            expect(text('global_composite_operation') == 'multiply', 'an invalid operation %r is ignored' % invalid)
        # WebKit also accepts its own operator names, which Chromium ignores (an engine difference, not a binding one).
        report['webkitOnlyComposites'] = {}
        for legacy in ['darker', 'plus-darker', 'plus-lighter', 'clear']:
            ok(set_composite(ctx, legacy), 'globalCompositeOperation ' + legacy)
            report['webkitOnlyComposites'][legacy] = text('global_composite_operation')
            expect(report['webkitOnlyComposites'][legacy] == legacy, 'WebKit keeps its operator name ' + legacy)
            ok(set_composite(ctx, 'multiply'), 'multiply')

        def tile(operation, x):
            ok(set_composite(ctx, 'source-over'), 'source-over')
            set_fill('#0000ff')
            ok(fill_rect(ctx, x, 20, 10, 10), 'destination tile')
            ok(set_composite(ctx, operation), operation)
            set_fill('#ff0000')
            ok(fill_rect(ctx, x + 5, 20, 10, 10), 'source tile')
            ok(set_composite(ctx, 'source-over'), 'source-over')
            overlap, dst, src = pixels((x + 7, 25), (x + 2, 25), (x + 12, 25))
            return {'overlap': overlap, 'dst': dst, 'src': src}

        reset_bitmap()
        report['composite'] = {'source-over': tile('source-over', 0), 'destination-over': tile('destination-over', 15),
                               'xor': tile('xor', 30), 'lighter': tile('lighter', 45)}
        reset_bitmap()
        report['composite'].update({'source-in': tile('source-in', 0), 'destination-out': tile('destination-out', 15),
                                    'multiply': tile('multiply', 30), 'screen': tile('screen', 45)})
        reset_bitmap()
        report['composite']['copy'] = tile('copy', 0)
        MAGENTA = [255, 0, 255, 255]
        oracle = {'source-over': [RED, BLUE, RED], 'destination-over': [BLUE, BLUE, RED], 'xor': [WHITE, BLUE, RED], 'lighter': [MAGENTA, BLUE, RED],
                  'source-in': [RED, WHITE, WHITE], 'destination-out': [WHITE, BLUE, WHITE], 'multiply': [[0, 0, 0, 255], BLUE, RED],
                  'screen': [MAGENTA, BLUE, RED], 'copy': [RED, WHITE, RED]}
        for name, (overlap, dst, src) in oracle.items():
            expect(report['composite'][name] == {'overlap': overlap, 'dst': dst, 'src': src}, name + ': ' + str(report['composite'][name]))

        # 6. filter (CanvasFiltersEnabled, on in the host).
        reset_bitmap()
        report['filter'] = {'initial': text('filter')}
        ok(set_filter(ctx, 'blur(2px)'), 'filter blur')
        report['filter']['blurString'] = text('filter')
        ok(set_filter(ctx, 'not a filter'), 'invalid filter')
        report['filter']['invalidKept'] = text('filter')
        ok(set_filter(ctx, 'invert(1)'), 'filter invert')
        set_fill('#ff0000')
        ok(fill_rect(ctx, 0, 0, 10, 10), 'inverted fillRect')
        ok(set_filter(ctx, 'none'), 'filter none')
        ok(fill_rect(ctx, 10, 0, 10, 10), 'unfiltered fillRect')
        ok(set_filter(ctx, 'opacity(50%)'), 'filter opacity')
        ok(fill_rect(ctx, 20, 0, 10, 10), 'half-opacity fillRect')
        ok(set_filter(ctx, 'blur(2px)'), 'filter blur')
        ok(fill_rect(ctx, 40, 10, 10, 10), 'blurred fillRect')
        ok(set_filter(ctx, 'none'), 'filter none')
        report['filter']['pixels'] = pixels((5, 5), (15, 5), (25, 5))
        # Chromium's blur(2px) alphas at the centre, the inside and outside edge columns, and 5px out: 249, 148, 104, 3,
        # over white. A blur kernel may differ by a few levels, so each channel is within BLUR_TOLERANCE.
        report['filter']['blur'] = pixels((45, 15), (40, 15), (39, 15), (35, 15))
        for (label, actual), alpha_value in zip(zip(['centre', 'inside edge', 'outside edge', 'far'], report['filter']['blur']), [249, 148, 104, 3]):
            level = round(255 * (1 - alpha_value / 255))
            near(actual, [255, level, level, 255], 'blur(2px) ' + label, BLUR_TOLERANCE)
        expect({k: report['filter'][k] for k in ['initial', 'blurString', 'invalidKept']} == {'initial': 'none', 'blurString': 'blur(2px)', 'invalidKept': 'blur(2px)'},
               'filter strings: ' + str(report['filter']))
        expect(report['filter']['pixels'][:2] == [[0, 255, 255, 255], RED], 'invert and none filters: ' + str(report['filter']['pixels']))
        near(report['filter']['pixels'][2], [255, 128, 128, 255], 'opacity(50%) red over white')

        # 7. Layers stay behind CanvasLayersEnabled, which the host leaves off.
        expect(simple['begin_layer'](ctx) == UNSUPPORTED and simple['end_layer'](ctx) == UNSUPPORTED, 'canvas layers are unsupported')
        expect(simple['save'](None) == NULL_ARGUMENT and set_transform_1(None, None) == NULL_ARGUMENT, 'NULL target')
        out_matrix = P()
        expect(get_transform(ctx, None) == NULL_ARGUMENT, 'NULL getTransform result')

        canvas_watch = p.watch(c)
        p.bind(C + 'release', None, [P])(ctx)
        p.release_all()
        p.dispose_host()
        p.collect()
        expect(p.bind('rv_watch_alive', I, [P])(canvas_watch) == 0, 'the canvas expires after host destruction')
        report['assertions'] = p.assertions
        assertions = p.assertions
    after = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
    if before != after:
        raise AssertionError('runtime changed')
    if evidence_json:
        Path(evidence_json).write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8')
    print('PASS: canvas_state %d assertions' % assertions, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--evidence-json')
    arguments = parser.parse_args()
    verify(arguments.native_directory, arguments.evidence_json)
