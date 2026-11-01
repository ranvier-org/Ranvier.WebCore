"""R04 canvas paints: line styles, dashes, gradients, patterns, shadows and image smoothing, asserted as paint parameters
and as representative pixels. Pixels are read from the host's software paint over a white page, so a transparent canvas
pixel reads white; gradient and blurred-shadow pixels are compared within GRADIENT_TOLERANCE of Chromium's values. The
pattern sources are a 4x4 canvas and a decoded 4x4 PNG <img>, each red in its left half and blue in its right half.
The Chromium oracle is docs/canvas-paints-evidence/red-chromium.json."""
import argparse
import base64
import ctypes
import hashlib
import json
from pathlib import Path
import struct
import sys
import time
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe
from utf8_inputs import Utf8

ABI = 59
OK, NULL_ARGUMENT, DOM_EXCEPTION, UNSUPPORTED = 0, -1, -3, -9
TWO_D = 1
HANG_SECONDS = 20
GRADIENT_TOLERANCE = 6
WHITE, BLACK = [255, 255, 255, 255], [0, 0, 0, 255]
RED, GREEN, BLUE = [255, 0, 0, 255], [0, 255, 0, 255], [0, 0, 255, 255]
HEADER = Path(__file__).resolve().parents[2] / 'host/RanvierWebCoreDom.h'


def png_4x4():
    rows = b''.join(b'\x00' + (b'\xff\x00\x00\xff' * 2 + b'\x00\x00\xff\xff' * 2) for _ in range(4))

    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 4, 4, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b'')


PAGE = ('<!doctype html><style>html,body{margin:0;background:#fff}canvas{display:block}#c{width:60px;height:40px}'
        '#s,#i{position:absolute;left:200px;top:200px}</style><body><canvas id=c width=60 height=40></canvas>'
        '<canvas id=s width=4 height=4></canvas><img id=i src="data:image/png;base64,' + base64.b64encode(png_4x4()).decode() + '">')


def header_constants(prefix):
    import re
    text = HEADER.read_text(encoding='utf-8')
    return {name.removeprefix(prefix): int(value) for name, value in re.findall(r'(' + prefix + r'\w+) = (\d+)', text)}


CAP = header_constants('RV_DOM_CANVAS_LINE_CAP_')
JOIN = header_constants('RV_DOM_CANVAS_LINE_JOIN_')
QUALITY = header_constants('RV_DOM_IMAGE_SMOOTHING_QUALITY_')
SOURCE = header_constants('RV_DOM_UNION_HTML_IMAGE_ELEMENT_OR_SVG_IMAGE_ELEMENT_OR_HTML_CANVAS_ELEMENT_OR_IMAGE_BITMAP_OR_CSS_STYLE_IMAGE_VALUE_')
STYLE_STRING, STYLE_GRADIENT, STYLE_PATTERN = 1, 2, 3
MATRIX_FIELDS = ['a', 'b', 'c', 'd', 'e', 'f', 'm11', 'm12', 'm21', 'm22', 'm41', 'm42']


class Span(ctypes.Structure):
    _fields_ = [('data', ctypes.POINTER(ctypes.c_uint8)), ('length', ctypes.c_int32)]


class Style(ctypes.Structure):
    _fields_ = [('present', ctypes.c_int32), ('tag', ctypes.c_int32), ('arm0', Span), ('arm1', ctypes.c_void_p), ('arm2', ctypes.c_void_p)]


class Source(ctypes.Structure):
    _fields_ = [('present', ctypes.c_int32), ('tag', ctypes.c_int32)] + [('arm%d' % i, ctypes.c_void_p) for i in range(5)]


class Doubles(ctypes.Structure):
    _fields_ = [('present', ctypes.c_int32), ('count', ctypes.c_int32), ('items', ctypes.POINTER(ctypes.c_double))]


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
        for feature in ['dom:CanvasGradient', 'dom:CanvasPattern', 'dom:ImageBitmap']:
            expect(has(feature.encode()) == 1, 'rv_abi_has ' + feature)
        expect(CAP == {'BUTT': 0, 'ROUND': 1, 'SQUARE': 2} and set(JOIN) == {'ROUND', 'BEVEL', 'MITER'} and QUALITY == {'LOW': 0, 'MEDIUM': 1, 'HIGH': 2},
               'enumeration constants: %s %s %s' % (CAP, JOIN, QUALITY))
        C = 'rv_dom_canvas_rendering_context2_d_'

        def fn(name, arguments, prefix=C):
            return p.bind(prefix + name, I, arguments)

        get_context = p.bind('rv_canvas_get_context', I, [P, I, P, ctypes.POINTER(P)])
        styles = {kind: (fn('get_' + kind + '_style', [P, ctypes.POINTER(Style)]), fn('set_' + kind + '_style', [P, ctypes.POINTER(Style)]))
                  for kind in ['fill', 'stroke']}
        release_style = p.bind('rv_dom_union_dom_string_or_canvas_gradient_or_canvas_pattern_release', None, [ctypes.POINTER(Style)])
        numbers = {name: (fn('get_' + name, [P, ctypes.POINTER(D)]), fn('set_' + name, [P, D]))
                   for name in ['line_width', 'miter_limit', 'line_dash_offset', 'shadow_offset_x', 'shadow_offset_y', 'shadow_blur']}
        indices = {name: (fn('get_' + name, [P, ctypes.POINTER(I)]), fn('set_' + name, [P, I]))
                   for name in ['line_cap', 'line_join', 'image_smoothing_enabled', 'image_smoothing_quality']}
        set_shadow_color = fn('set_shadow_color', [P, Utf8])
        set_dash = fn('set_line_dash', [P, ctypes.POINTER(Doubles)])
        get_dash = fn('get_line_dash', [P, ctypes.POINTER(Doubles)])
        release_doubles = p.bind('rv_dom_sequence_unrestricted_double_release', None, [ctypes.POINTER(Doubles)])
        linear = fn('create_linear_gradient', [P] + [D] * 4 + [ctypes.POINTER(P)])
        radial = fn('create_radial_gradient', [P] + [D] * 6 + [ctypes.POINTER(P)])
        conic = fn('create_conic_gradient', [P] + [D] * 3 + [ctypes.POINTER(P)])
        add_stop = fn('add_color_stop', [P, P, D, Utf8], 'rv_dom_canvas_gradient_')
        release_gradient = p.bind('rv_dom_canvas_gradient_release', None, [P])
        create_pattern = fn('create_pattern', [P, ctypes.POINTER(Source), Utf8, ctypes.POINTER(P)])
        pattern_transform = fn('set_transform', [P, ctypes.POINTER(Matrix)], 'rv_dom_canvas_pattern_')
        release_pattern = p.bind('rv_dom_canvas_pattern_release', None, [P])
        fill_rect = fn('fill_rect', [P] + [D] * 4)
        begin_path = fn('begin_path', [P])
        move_to = fn('move_to', [P, D, D])
        line_to = fn('line_to', [P, D, D])
        stroke = fn('stroke_0', [P])
        reset = fn('reset', [P])
        translate = fn('translate', [P, D, D])
        reset_transform = fn('reset_transform', [P])
        handles = []

        def ok(status, label):
            expect(status == OK, label + ': status ' + str(status))

        def exception(status, name, label):
            expect(status == DOM_EXCEPTION and p.text('rv_last_exception', [I], 0) == name, '%s: %s (status %d)' % (label, name, status))

        def text(name):
            return p.text(C + 'get_' + name, [P], ctx)

        def number(name):
            value = D()
            ok(numbers[name][0](ctx, ctypes.byref(value)), name)
            return value.value

        def index(name):
            value = I(-1)
            ok(indices[name][0](ctx, ctypes.byref(value)), name)
            return value.value

        def style(kind):
            value = Style()
            ok(styles[kind][0](ctx, ctypes.byref(value)), kind + 'Style getter')
            if value.tag == STYLE_STRING:
                result = ctypes.string_at(value.arm0.data, value.arm0.length).decode()
            else:
                result = (value.tag, value.arm1 or value.arm2)
            release_style(ctypes.byref(value))
            return result

        def set_style(kind, value):
            if isinstance(value, str):
                arm, keep = span(value)
                ok(styles[kind][1](ctx, ctypes.byref(Style(1, STYLE_STRING, arm, None, None))), kind + 'Style ' + value)
            else:
                tag, handle = value
                ok(styles[kind][1](ctx, ctypes.byref(Style(1, tag, Span(), handle if tag == STYLE_GRADIENT else None,
                                                           handle if tag == STYLE_PATTERN else None))), kind + 'Style object')

        def dash():
            value = Doubles()
            ok(get_dash(ctx, ctypes.byref(value)), 'getLineDash')
            result = [value.items[i] for i in range(value.count)]
            release_doubles(ctypes.byref(value))
            return result

        def set_line_dash(values):
            array = (ctypes.c_double * max(len(values), 1))(*values)
            return set_dash(ctx, ctypes.byref(Doubles(1, len(values), array)))

        def gradient(maker, *args):
            out = P()
            ok(maker(ctx, *args, ctypes.byref(out)), 'create gradient')
            handles.append((release_gradient, out.value))
            return out.value

        def pattern(source_tag, source, repetition):
            value = Source(1, source_tag)
            setattr(value, 'arm%d' % (source_tag - 1), source)
            out = P()
            status = create_pattern(ctx, ctypes.byref(value), repetition, ctypes.byref(out))
            if out.value:
                handles.append((release_pattern, out.value))
            return status, out.value

        def pixels(*points):
            rgba = p.paint()
            return [p.pixel(rgba, x, y) for x, y in points]

        def misses(labels, actuals, expecteds):
            # Every pixel beyond GRADIENT_TOLERANCE, so one failure reports them all.
            return [label + ': ' + str(actual) + ' expected ' + str(expected) for label, actual, expected in zip(labels, actuals, expecteds)
                    if not all(abs(a - b) <= GRADIENT_TOLERANCE for a, b in zip(actual, expected))]

        def over_white(rgba):
            # A Chromium getImageData value composited over the white page.
            r, g, b, a = rgba
            return [round(c * a / 255 + 255 * (1 - a / 255)) for c in (r, g, b)] + [255]

        def line(x0, y0, x1, y1):
            ok(begin_path(ctx), 'beginPath')
            ok(move_to(ctx, x0, y0), 'moveTo')
            ok(line_to(ctx, x1, y1), 'lineTo')
            ok(stroke(ctx), 'stroke')

        p.load(PAGE, standalone=False)
        c, s, img = (p.node(name) for name in 'csi')
        document = p.bind('rv_host_document', P, [P])(p.host)
        p.retained.append(('rv_node_release', document))
        handle = P()
        ok(get_context(s, TWO_D, None, ctypes.byref(handle)), 'getContext 2d on the pattern source')
        ctx = handle.value
        set_style('fill', '#ff0000')
        ok(fill_rect(ctx, 0, 0, 2, 4), 'source red half')
        set_style('fill', '#0000ff')
        ok(fill_rect(ctx, 2, 0, 2, 4), 'source blue half')
        source_context = ctx
        ok(get_context(c, TWO_D, None, ctypes.byref(handle)), 'getContext 2d')
        ctx = handle.value

        # 1. Defaults and validation of line, dash, shadow and smoothing styles.
        report['defaults'] = {'strokeStyle': style('stroke'), 'lineWidth': number('line_width'), 'lineCap': index('line_cap'),
                              'lineJoin': index('line_join'), 'miterLimit': number('miter_limit'), 'lineDash': dash(),
                              'lineDashOffset': number('line_dash_offset'), 'shadowOffsetX': number('shadow_offset_x'),
                              'shadowOffsetY': number('shadow_offset_y'), 'shadowBlur': number('shadow_blur'), 'shadowColor': text('shadow_color'),
                              'imageSmoothingEnabled': index('image_smoothing_enabled'), 'imageSmoothingQuality': index('image_smoothing_quality')}
        expect(report['defaults'] == {'strokeStyle': '#000000', 'lineWidth': 1.0, 'lineCap': CAP['BUTT'], 'lineJoin': JOIN['MITER'], 'miterLimit': 10.0,
                                      'lineDash': [], 'lineDashOffset': 0.0, 'shadowOffsetX': 0.0, 'shadowOffsetY': 0.0, 'shadowBlur': 0.0,
                                      'shadowColor': 'rgba(0, 0, 0, 0)', 'imageSmoothingEnabled': 1, 'imageSmoothingQuality': QUALITY['LOW']},
               'defaults: ' + str(report['defaults']))
        for value in [4, 0, -1, float('nan'), float('inf')]:
            ok(numbers['line_width'][1](ctx, value), 'lineWidth %r' % value)
        for value in [3, 0, -2]:
            ok(numbers['miter_limit'][1](ctx, value), 'miterLimit %r' % value)
        ok(indices['line_cap'][1](ctx, CAP['ROUND']), 'lineCap round')
        ok(indices['line_join'][1](ctx, JOIN['BEVEL']), 'lineJoin bevel')
        expect(indices['line_cap'][1](ctx, 3) == UNSUPPORTED and indices['line_join'][1](ctx, -1) == UNSUPPORTED, 'unknown cap and join indices')
        ok(set_line_dash([4, 2]), 'setLineDash')
        report['lineDash'] = dash()
        ok(set_line_dash([1, 2, 3]), 'setLineDash odd')
        report['lineDashOdd'] = dash()
        ok(set_line_dash([1, -1]), 'setLineDash negative')
        ok(set_line_dash([1, float('nan')]), 'setLineDash NaN')
        report['lineDashKept'] = dash()
        ok(numbers['line_dash_offset'][1](ctx, 1.5), 'lineDashOffset')
        ok(numbers['line_dash_offset'][1](ctx, float('nan')), 'lineDashOffset NaN')
        ok(numbers['shadow_blur'][1](ctx, 3), 'shadowBlur')
        ok(numbers['shadow_blur'][1](ctx, -1), 'shadowBlur negative')
        ok(set_shadow_color(ctx, 'rgba(0, 0, 255, 0.5)'), 'shadowColor')
        ok(set_shadow_color(ctx, 'nope'), 'invalid shadowColor')
        ok(indices['image_smoothing_enabled'][1](ctx, 0), 'imageSmoothingEnabled')
        ok(indices['image_smoothing_quality'][1](ctx, QUALITY['HIGH']), 'imageSmoothingQuality')
        expect(indices['image_smoothing_quality'][1](ctx, 3) == UNSUPPORTED, 'unknown smoothing quality index')
        set_style('stroke', '#00ff00')
        set_style('stroke', 'bogus')
        report['validated'] = {'lineWidth': number('line_width'), 'miterLimit': number('miter_limit'), 'lineCap': index('line_cap'),
                               'lineJoin': index('line_join'), 'lineDashOffset': number('line_dash_offset'), 'shadowBlur': number('shadow_blur'),
                               'shadowColor': text('shadow_color'), 'smoothing': index('image_smoothing_enabled'),
                               'quality': index('image_smoothing_quality'), 'strokeStyle': style('stroke')}
        expect(report['lineDash'] == [4, 2] and report['lineDashOdd'] == [1, 2, 3, 1, 2, 3] and report['lineDashKept'] == [1, 2, 3, 1, 2, 3],
               'line dashes: ' + str([report['lineDash'], report['lineDashOdd'], report['lineDashKept']]))
        expect(report['validated'] == {'lineWidth': 4.0, 'miterLimit': 3.0, 'lineCap': CAP['ROUND'], 'lineJoin': JOIN['BEVEL'], 'lineDashOffset': 1.5,
                                       'shadowBlur': 3.0, 'shadowColor': 'rgba(0, 0, 255, 0.5)', 'smoothing': 0, 'quality': QUALITY['HIGH'],
                                       'strokeStyle': '#00ff00'}, 'validated styles: ' + str(report['validated']))
        ok(reset(ctx), 'reset')

        # 2. Strokes: a 4px line with butt and square caps, and dashed lines with and without an offset.
        ok(numbers['line_width'][1](ctx, 4), 'lineWidth 4')
        set_style('stroke', '#ff0000')
        line(10, 5, 30, 5)
        ok(indices['line_cap'][1](ctx, CAP['SQUARE']), 'lineCap square')
        line(10, 15, 30, 15)
        report['caps'] = pixels((20, 5), (9, 5), (9, 15), (7, 15), (20, 8))
        expect(report['caps'] == [RED, WHITE, RED, WHITE, WHITE], 'caps: ' + str(report['caps']))
        ok(indices['line_cap'][1](ctx, CAP['BUTT']), 'lineCap butt')
        ok(numbers['line_width'][1](ctx, 2), 'lineWidth 2')
        ok(set_line_dash([4, 4]), 'setLineDash')
        set_style('stroke', '#0000ff')
        line(0, 25, 60, 25)
        ok(numbers['line_dash_offset'][1](ctx, 4), 'lineDashOffset')
        set_style('stroke', '#00ff00')
        line(0, 35, 60, 35)
        report['dash'] = pixels((2, 25), (6, 25), (10, 25), (2, 35), (6, 35))
        expect(report['dash'] == [BLUE, WHITE, BLUE, WHITE, GREEN], 'dashes: ' + str(report['dash']))

        # 3. Gradients.
        ok(reset(ctx), 'reset')
        lin = gradient(linear, 0, 0, 60, 0)
        ok(add_stop(lin, document, 0, '#ff0000'), 'addColorStop 0')
        ok(add_stop(lin, document, 1, '#0000ff'), 'addColorStop 1')
        set_style('fill', (STYLE_GRADIENT, lin))
        expect(style('fill') == (STYLE_GRADIENT, lin), 'fillStyle reads back the gradient')
        ok(fill_rect(ctx, 0, 0, 60, 10), 'linear fill')
        rad = gradient(radial, 30, 20, 0, 30, 20, 10)
        ok(add_stop(rad, document, 0, '#00ff00'), 'addColorStop')
        ok(add_stop(rad, document, 1, '#000000'), 'addColorStop')
        set_style('fill', (STYLE_GRADIENT, rad))
        ok(fill_rect(ctx, 10, 10, 40, 20), 'radial fill')
        con = gradient(conic, 0, 30, 35)
        for offset, colour in [(0, '#ff0000'), (0.5, '#0000ff'), (1, '#ff0000')]:
            ok(add_stop(con, document, offset, colour), 'conic stop')
        set_style('fill', (STYLE_GRADIENT, con))
        ok(fill_rect(ctx, 20, 30, 20, 10), 'conic fill')
        report['gradients'] = pixels((0, 5), (30, 5), (59, 5), (30, 20), (35, 20), (45, 20), (38, 35), (22, 35))
        oracle = [[253, 0, 2, 255], [126, 0, 130, 255], [2, 0, 253, 255], [0, 237, 0, 255], [0, 115, 0, 255], BLACK, [250, 0, 5, 255], [6, 0, 250, 255]]
        if sys.platform == 'darwin':
            # CoreGraphics rasterises the gradient itself (CGContextDrawRadialGradient, called from
            # GradientRendererCG::drawRadialGradient in Source/WebCore/platform/graphics/cg/GradientRendererCG.cpp). At the
            # centre pixel it gives t = 9/255; Skia samples the pixel centre, 0.707px out, at t = 0.0707.
            oracle[3] = [0, 246, 0, 255]
        labels = ['linear left', 'linear middle', 'linear right', 'radial centre', 'radial half', 'radial outside', 'conic east', 'conic west']
        missed = misses(labels, report['gradients'], oracle)
        expect(not missed, 'gradients: ' + '; '.join(missed))
        exception(add_stop(lin, document, -0.1, 'red'), 'IndexSizeError', 'addColorStop below 0')
        exception(add_stop(lin, document, 1.1, 'red'), 'IndexSizeError', 'addColorStop above 1')
        exception(add_stop(lin, document, float('nan'), 'red'), 'TypeError', 'addColorStop NaN')
        exception(add_stop(lin, document, 0.5, 'not a colour'), 'SyntaxError', 'addColorStop colour')
        expect(add_stop(lin, None, 0.5, 'red') == NULL_ARGUMENT and add_stop(lin, c, 0.5, 'red') == -11, 'addColorStop needs a Document context')
        out = P()
        exception(linear(ctx, float('nan'), 0, 1, 1, ctypes.byref(out)), 'TypeError', 'createLinearGradient NaN')
        exception(radial(ctx, 0, 0, -1, 0, 0, 1, ctypes.byref(out)), 'IndexSizeError', 'createRadialGradient negative radius')
        exception(conic(ctx, float('inf'), 0, 0, ctypes.byref(out)), 'TypeError', 'createConicGradient Infinity')

        # 4. Patterns from the canvas and the image.
        deadline = time.monotonic() + HANG_SECONDS
        complete = I()
        while True:
            p.bind('rv_run_loop_cycle', I, [I])(2)
            ok_status = p.bind('rv_dom_html_image_element_get_complete', I, [P, ctypes.POINTER(I)])(img, ctypes.byref(complete))
            if ok_status == OK and complete.value:
                break
            if time.monotonic() > deadline:
                raise AssertionError('hang: the pattern image never completed')
        ok(reset(ctx), 'reset')
        status, repeat = pattern(SOURCE['HTML_CANVAS_ELEMENT'], s, 'repeat')
        ok(status, 'createPattern(canvas, repeat)')
        set_style('fill', (STYLE_PATTERN, repeat))
        ok(fill_rect(ctx, 0, 0, 20, 8), 'repeat fill')
        status, no_repeat = pattern(SOURCE['HTML_IMAGE_ELEMENT'], img, 'no-repeat')
        ok(status, 'createPattern(img, no-repeat)')
        expect(bool(no_repeat), 'a decoded image makes a pattern')
        ok(translate(ctx, 20, 0), 'translate')
        set_style('fill', (STYLE_PATTERN, no_repeat))
        ok(fill_rect(ctx, 0, 0, 20, 8), 'no-repeat fill')
        status, repeat_x = pattern(SOURCE['HTML_CANVAS_ELEMENT'], s, 'repeat-x')
        ok(status, 'createPattern(canvas, repeat-x)')
        ok(translate(ctx, 20, 0), 'translate')
        set_style('fill', (STYLE_PATTERN, repeat_x))
        ok(fill_rect(ctx, 0, 0, 20, 8), 'repeat-x fill')
        ok(reset_transform(ctx), 'resetTransform')
        report['patterns'] = pixels((0, 0), (3, 0), (4, 0), (6, 5), (21, 1), (30, 1), (45, 1), (45, 6))
        expect(report['patterns'] == [RED, BLUE, RED, BLUE, RED, WHITE, RED, WHITE], 'patterns: ' + str(report['patterns']))
        status, empty_repetition = pattern(SOURCE['HTML_CANVAS_ELEMENT'], s, '')
        expect(status == OK and bool(empty_repetition), 'an empty repetition means repeat')
        exception(pattern(SOURCE['HTML_CANVAS_ELEMENT'], s, 'diagonal')[0], 'SyntaxError', 'createPattern bad repetition')
        status, scaled = pattern(SOURCE['HTML_CANVAS_ELEMENT'], s, 'repeat')
        four, keep = matrix(a=4, d=4)
        ok(pattern_transform(scaled, ctypes.byref(four)), 'CanvasPattern.setTransform')
        ok(indices['image_smoothing_enabled'][1](ctx, 0), 'smoothing off')
        set_style('fill', (STYLE_PATTERN, scaled))
        ok(fill_rect(ctx, 0, 10, 32, 16), 'scaled pattern fill')
        report['patternScaled'] = pixels((3, 12), (10, 12), (17, 12))
        expect(report['patternScaled'] == [RED, BLUE, RED], 'scaled pattern: ' + str(report['patternScaled']))
        conflict, keep = matrix(a=1, m11=2)
        exception(pattern_transform(scaled, ctypes.byref(conflict)), 'TypeError', 'CanvasPattern.setTransform conflict')
        empty = P()
        p.call('rv_dom_document_create_element', [P, ctypes.c_char_p, I, P, ctypes.POINTER(P)], document, b'canvas', 6, None, ctypes.byref(empty))
        p.call('rv_dom_html_canvas_element_set_width', [P, p.unsigned], empty.value, 0)
        exception(pattern(SOURCE['HTML_CANVAS_ELEMENT'], empty.value, 'repeat')[0], 'InvalidStateError', 'createPattern zero-size canvas')
        p.bind('rv_node_release', None, [P])(empty.value)
        expect(pattern(SOURCE['IMAGE_BITMAP'], None, 'repeat')[0] == NULL_ARGUMENT, 'an ImageBitmap arm needs a handle')
        set_style('stroke', (STYLE_PATTERN, repeat))
        expect(style('stroke') == (STYLE_PATTERN, repeat), 'strokeStyle reads back the pattern')

        # 5. Shadows.
        ok(reset(ctx), 'reset')
        ok(set_shadow_color(ctx, '#0000ff'), 'shadowColor')
        ok(numbers['shadow_offset_x'][1](ctx, 20), 'shadowOffsetX')
        set_style('fill', '#ff0000')
        ok(fill_rect(ctx, 5, 5, 10, 10), 'shadowed fill')
        ok(numbers['shadow_blur'][1](ctx, 4), 'shadowBlur')
        ok(numbers['shadow_offset_x'][1](ctx, 0), 'shadowOffsetX 0')
        ok(numbers['shadow_offset_y'][1](ctx, 20), 'shadowOffsetY')
        ok(fill_rect(ctx, 40, 0, 10, 10), 'blurred shadow fill')
        report['shadow'] = pixels((10, 10), (30, 10), (45, 10), (45, 25), (45, 31), (45, 38))
        expect(report['shadow'][:3] == [RED, BLUE, WHITE], 'shadow: ' + str(report['shadow'][:3]))
        # CoreGraphics draws a blurred shadow with its private CGStyleCreateShadow2 (GraphicsContextCG.cpp), whose kernel
        # gives the edge alpha 55 where Chromium gives 63; the value is the one measured on macOS (run 41289077910).
        shadow_alphas = [249, 55 if sys.platform == 'darwin' else 63, 0]
        missed = misses(['blurred centre', 'blurred edge', 'blurred far'], report['shadow'][3:], [over_white([0, 0, 255, alpha]) for alpha in shadow_alphas])
        expect(not missed, 'blurred shadow: ' + '; '.join(missed))
        ok(reset(ctx), 'reset')
        ok(numbers['shadow_offset_x'][1](ctx, 20), 'shadowOffsetX')
        set_style('fill', '#ff0000')
        ok(fill_rect(ctx, 5, 5, 10, 10), 'fill with the default shadow colour')
        expect(pixels((30, 10))[0] == WHITE, 'the default shadow colour draws no shadow')
        expect(styles['stroke'][1](None, None) == NULL_ARGUMENT and get_dash(ctx, None) == NULL_ARGUMENT, 'NULL arguments')

        canvas_watch = p.watch(c)
        for release, target in handles:
            release(target)
        p.bind(C + 'release', None, [P])(ctx)
        p.bind(C + 'release', None, [P])(source_context)
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
    print('PASS: canvas_paints %d assertions' % assertions, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--evidence-json')
    arguments = parser.parse_args()
    verify(arguments.native_directory, arguments.evidence_json)
