"""R02 canvas paths and hit testing: the current path and reusable Path2D objects drawn with fill, stroke and clip, and
tested with isPointInPath and isPointInStroke, inside and outside transformed paths. Pixels are read from the host's
software paint over a white page, so a transparent canvas pixel reads white; only interior pixels are compared. The
Chromium oracle is docs/canvas-paths-evidence/red-chromium.json."""
import argparse
import ctypes
import hashlib
import json
import math
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe
from utf8_inputs import Utf8

ABI = 60
OK, NULL_ARGUMENT, DOM_EXCEPTION, UNSUPPORTED = 0, -1, -3, -9
TWO_D = 1
WHITE, BLACK = [255, 255, 255, 255], [0, 0, 0, 255]
RED, GREEN, BLUE, YELLOW = [255, 0, 0, 255], [0, 255, 0, 255], [0, 0, 255, 255], [255, 255, 0, 255]
PAGE = ('<!doctype html><style>html,body{margin:0;background:#fff}canvas{display:block;width:60px;height:40px}</style>'
        '<body><canvas id=c width=60 height=40></canvas>')
HEADER = Path(__file__).resolve().parents[2] / 'host/RanvierWebCoreDom.h'


def header_constants(prefix):
    """The generated enumeration constants with the prefix, read from the public header."""
    text = HEADER.read_text(encoding='utf-8')
    return {name.removeprefix(prefix): int(value) for name, value in re.findall(r'(' + prefix + r'\w+) = (\d+)', text)}


FILL_RULE = header_constants('RV_DOM_CANVAS_FILL_RULE_')
UNION_ARM = header_constants('RV_DOM_UNION_UNRESTRICTED_DOUBLE_OR_DOM_POINT_INIT_')


class Span(ctypes.Structure):
    _fields_ = [('data', ctypes.POINTER(ctypes.c_uint8)), ('length', ctypes.c_int32)]


class Style(ctypes.Structure):
    _fields_ = [('present', ctypes.c_int32), ('tag', ctypes.c_int32), ('arm0', Span), ('arm1', ctypes.c_void_p), ('arm2', ctypes.c_void_p)]


class Point(ctypes.Structure):
    _fields_ = [('size', ctypes.c_uint32), ('x', ctypes.c_double), ('y', ctypes.c_double), ('z', ctypes.c_double), ('w', ctypes.c_double)]


class Radius(ctypes.Structure):
    _fields_ = [('present', ctypes.c_int32), ('tag', ctypes.c_int32), ('arm0', ctypes.c_double), ('arm1', ctypes.POINTER(Point))]


class Radii(ctypes.Structure):
    _fields_ = [('present', ctypes.c_int32), ('count', ctypes.c_int32), ('items', ctypes.POINTER(Radius))]


MATRIX_FIELDS = ['a', 'b', 'c', 'd', 'e', 'f', 'm11', 'm12', 'm21', 'm22', 'm41', 'm42']


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


def radius(value):
    if isinstance(value, tuple):
        point = Point(ctypes.sizeof(Point), value[0], value[1], 0, 1)
        return Radius(1, UNION_ARM['DOM_POINT_INIT'], 0, ctypes.pointer(point)), point
    return Radius(1, UNION_ARM['NUMBER'], value, None), None


def radii(values):
    items = [radius(v) for v in values]
    array = (Radius * max(len(items), 1))(*[item for item, _ in items])
    return Radii(1, len(items), array if items else None), (array, items)


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
        expect(FILL_RULE == {'NONZERO': 0, 'EVENODD': 1}, 'CanvasFillRule constants in IDL order: ' + str(FILL_RULE))
        expect(p.bind('rv_abi_version', I, [])() == ABI, 'ABI version ' + str(ABI))
        has = p.bind('rv_abi_has', I, [ctypes.c_char_p])
        for feature in ['canvas-context', 'dom:CanvasRenderingContext2D', 'dom:Path2D']:
            expect(has(feature.encode()) == 1, 'rv_abi_has ' + feature)
        C = 'rv_dom_canvas_rendering_context2_d_'
        Q = 'rv_dom_path2_d_'

        def fn(name, arguments):
            return p.bind(name, I, arguments)

        get_context = fn('rv_canvas_get_context', [P, I, P, ctypes.POINTER(P)])
        release_context = p.bind(C + 'release', None, [P])
        set_style = fn(C + 'set_fill_style', [P, ctypes.POINTER(Style)])
        release_path = p.bind(Q + 'release', None, [P])
        retain_path = p.bind(Q + 'retain', P, [P])
        create_0 = fn(Q + 'create_0', [P, ctypes.POINTER(P)])
        create_copy = fn(Q + 'create_1_path', [P, P, ctypes.POINTER(P)])
        create_data = fn(Q + 'create_1_d', [P, Utf8, ctypes.POINTER(P)])
        add_path = fn(Q + 'add_path', [P, P, ctypes.POINTER(Matrix)])
        segments = {'close_path': 0, 'move_to': 2, 'line_to': 2, 'quadratic_curve_to': 4, 'bezier_curve_to': 6, 'arc_to': 5, 'rect': 4}
        on_context = {name: fn(C + name, [P] + [D] * count) for name, count in segments.items()}
        on_path = {name: fn(Q + name, [P] + [D] * count) for name, count in segments.items()}
        for table, prefix in [(on_context, C), (on_path, Q)]:
            table['arc'] = fn(prefix + 'arc', [P] + [D] * 5 + [I])
            table['ellipse'] = fn(prefix + 'ellipse', [P] + [D] * 7 + [I])
            table['round_rect_5_list'] = fn(prefix + 'round_rect_5_list', [P] + [D] * 4 + [ctypes.POINTER(Radii)])
            table['round_rect_5_value'] = fn(prefix + 'round_rect_5_value', [P] + [D] * 4 + [ctypes.POINTER(Radius)])
        begin_path = fn(C + 'begin_path', [P])
        fill_current = fn(C + 'fill_1', [P, I])
        fill_path = fn(C + 'fill_2', [P, P, I])
        stroke_current = fn(C + 'stroke_0', [P])
        stroke_path = fn(C + 'stroke_1', [P, P])
        clip_current = fn(C + 'clip_1', [P, I])
        clip_path = fn(C + 'clip_2', [P, P, I])
        hit_current = fn(C + 'is_point_in_path_3', [P, D, D, I, ctypes.POINTER(I)])
        hit_path = fn(C + 'is_point_in_path_4', [P, P, D, D, I, ctypes.POINTER(I)])
        stroke_hit_current = fn(C + 'is_point_in_stroke_2', [P, D, D, ctypes.POINTER(I)])
        stroke_hit_path = fn(C + 'is_point_in_stroke_3', [P, P, D, D, ctypes.POINTER(I)])
        stroke_rect = fn(C + 'stroke_rect', [P] + [D] * 4)
        fill_rect = fn(C + 'fill_rect', [P] + [D] * 4)
        paths = []

        def new_path(data=None, copy=None):
            out = P(1234)
            if data is not None:
                status = create_data(document, data, ctypes.byref(out))
            elif copy is not None:
                status = create_copy(document, copy, ctypes.byref(out))
            else:
                status = create_0(document, ctypes.byref(out))
            expect(status == OK and bool(out.value), 'Path2D created: status %d' % status)
            paths.append(out.value)
            return out.value

        def ok(status, label):
            expect(status == OK, label + ': status ' + str(status))

        def set_fill(text):
            arm, keep = span(text)
            ok(set_style(ctx, ctypes.byref(Style(1, 1, arm, None, None))), 'fillStyle ' + text)

        def hit(x, y, rule='NONZERO', path=None):
            out = I(-7)
            status = hit_path(ctx, path, x, y, FILL_RULE[rule], ctypes.byref(out)) if path else hit_current(ctx, x, y, FILL_RULE[rule], ctypes.byref(out))
            ok(status, 'isPointInPath')
            expect(out.value in (0, 1), 'isPointInPath result is a boolean')
            return bool(out.value)

        def stroke_hit(x, y, path=None):
            out = I(-7)
            ok(stroke_hit_path(ctx, path, x, y, ctypes.byref(out)) if path else stroke_hit_current(ctx, x, y, ctypes.byref(out)), 'isPointInStroke')
            return bool(out.value)

        def pixels(*points):
            rgba = p.paint()
            return [p.pixel(rgba, x, y) for x, y in points]

        def reset():
            p.call('rv_dom_html_canvas_element_set_width', [P, p.unsigned], c, 60)

        def exception(status, name, label):
            expect(status == DOM_EXCEPTION, label + ': status ' + str(status))
            expect(p.text('rv_last_exception', [I], 0) == name, label + ': ' + name)

        p.load(PAGE, standalone=False)
        c = p.node('c')
        document = p.bind('rv_host_document', P, [P])(p.host)
        expect(bool(document), 'host document')
        p.retained.append(('rv_node_release', document))
        handle = P()
        ok(get_context(c, TWO_D, None, ctypes.byref(handle)), 'getContext 2d')
        ctx = handle.value

        # 1. The current path: a triangle filled red, hit tested against its fill and its stroke.
        ok(begin_path(ctx), 'beginPath')
        for name, args in [('move_to', (10, 10)), ('line_to', (50, 10)), ('line_to', (30, 30)), ('close_path', ())]:
            ok(on_context[name](ctx, *args), name)
        set_fill('#ff0000')
        ok(fill_current(ctx, FILL_RULE['NONZERO']), 'fill()')
        report['triangle'] = {'inside': pixels((30, 15))[0], 'outside': pixels((5, 35))[0], 'hitInside': hit(30, 15), 'hitOutside': hit(5, 35),
                              'strokeOnEdge': stroke_hit(30, 10), 'strokeInside': stroke_hit(30, 15)}
        expect(report['triangle'] == {'inside': RED, 'outside': WHITE, 'hitInside': True, 'hitOutside': False,
                                      'strokeOnEdge': True, 'strokeInside': False}, 'triangle: ' + str(report['triangle']))
        ok(begin_path(ctx), 'beginPath')
        expect(not hit(30, 15), 'beginPath empties the current path')

        # 2. Path2D reuse: a square filled blue, then added to another path translated by 40 and filled green.
        square = new_path()
        ok(on_path['rect'](square, 0, 0, 10, 10), 'Path2D.rect')
        set_fill('rgb(0, 0, 255)')
        ok(fill_path(ctx, square, FILL_RULE['NONZERO']), 'fill(square)')
        moved = new_path()
        shift, keep = matrix(e=40, f=0)
        ok(add_path(moved, square, ctypes.byref(shift)), 'addPath with a translation')
        set_fill('#00ff00')
        ok(fill_path(ctx, moved, FILL_RULE['NONZERO']), 'fill(moved)')
        report['reuse'] = {'pixels': pixels((5, 5), (45, 5), (25, 5)), 'hitSquare': hit(5, 5, path=square),
                           'hitMovedAtOrigin': hit(5, 5, path=moved), 'hitMoved': hit(45, 5, path=moved), 'squareUnchanged': hit(45, 5, path=square)}
        expect(report['reuse'] == {'pixels': [BLUE, GREEN, WHITE], 'hitSquare': True, 'hitMovedAtOrigin': False, 'hitMoved': True,
                                   'squareUnchanged': False}, 'reuse: ' + str(report['reuse']))
        identity = new_path()
        ok(add_path(identity, square, None), 'addPath with the default transform')
        expect(hit(5, 5, path=identity), 'addPath without a transform keeps the geometry')

        # 3. SVG path data, the copy constructor, and independence of the copy.
        data = new_path('M20 20 h10 v10 h-10 Z')
        copy = new_path(copy=data)
        ok(on_path['rect'](data, 50, 30, 5, 5), 'rect after copying')
        report['pathData'] = [hit(25, 25, path=data), hit(35, 25, path=data), hit(25, 25, path=copy), hit(52, 32, path=copy), hit(52, 32, path=data)]
        expect(report['pathData'] == [True, False, True, False, True], 'path data and copy: ' + str(report['pathData']))
        # The parse stops at the first error and keeps the segments before it.
        invalid = new_path('M 0 0 L bogus')
        # 'M 0 0' remains: a subpath of one point. CoreGraphics counts that point as inside it: PathCG::contains closes
        # the subpath and calls CGPathContainsPoint (Source/WebCore/platform/graphics/cg/PathCG.cpp). Skia does not.
        expect(hit(0, 0, path=invalid) == (sys.platform == 'darwin'), 'invalid path data keeps its first point, without an error')
        expect(not hit(1, 1, path=invalid), 'invalid path data encloses no area')
        prefix = new_path('M 40 0 h10 v10 h-10 Z L bogus M 60 0 h10 v10 h-10 Z')
        expect(hit(45, 5, path=prefix) and not hit(65, 5, path=prefix), 'invalid path data keeps the segments before the error only')
        empty_data = new_path('')
        expect(not hit(0, 0, path=empty_data), 'empty path data')

        # 4. Fill rules: two nested squares with the same winding.
        nested = new_path()
        ok(on_path['rect'](nested, 0, 20, 20, 20), 'outer rect')
        ok(on_path['rect'](nested, 5, 25, 10, 10), 'inner rect')
        report['fillRule'] = [hit(10, 30, path=nested), hit(10, 30, 'EVENODD', nested), hit(2, 30, 'EVENODD', nested)]
        expect(report['fillRule'] == [True, False, True], 'fill rules: ' + str(report['fillRule']))
        set_fill('#ffff00')
        ok(fill_path(ctx, nested, FILL_RULE['EVENODD']), 'fill(nested, evenodd)')
        expect(pixels((2, 30), (10, 30)) == [YELLOW, WHITE], 'evenodd fill leaves the hole unpainted')
        out = I()
        expect(fill_path(ctx, nested, 2) == UNSUPPORTED and fill_current(ctx, -1) == UNSUPPORTED, 'an unknown fill rule index fails')
        expect(hit_current(ctx, 1, 1, 7, ctypes.byref(out)) == UNSUPPORTED and clip_path(ctx, nested, 9) == UNSUPPORTED, 'unknown fill rule in hit and clip')

        # 5. Curves, arcs and rounded rectangles, hit tested on the current path.
        pi = math.pi

        def hits(build, points):
            ok(begin_path(ctx), 'beginPath')
            build()
            return [hit(x, y) for x, y in points]

        def call(name, *args):
            ok(on_context[name](ctx, *args), name)

        def round_list(values, *box):
            value, keep = radii(values)
            ok(on_context['round_rect_5_list'](ctx, *box, ctypes.byref(value)), 'roundRect list')

        def round_value(value, *box):
            item, keep = radius(value)
            ok(on_context['round_rect_5_value'](ctx, *box, ctypes.byref(item)), 'roundRect value')

        report['shapes'] = {
            'arc': hits(lambda: call('arc', 30, 20, 10, 0, pi * 2, 0), [(30, 20), (30, 32), (37, 20)]),
            'halfArc': hits(lambda: call('arc', 30, 20, 10, 0, pi, 0), [(30, 25), (30, 15)]),
            'anticlockwiseArc': hits(lambda: call('arc', 30, 20, 10, 0, pi, 1), [(30, 25), (30, 15)]),
            'ellipse': hits(lambda: call('ellipse', 30, 20, 20, 5, 0, 0, pi * 2, 0), [(45, 20), (30, 24), (30, 27)]),
            'rotatedEllipse': hits(lambda: call('ellipse', 30, 20, 20, 5, pi / 2, 0, pi * 2, 0), [(45, 20), (30, 35)]),
            'quadratic': hits(lambda: [call('move_to', 0, 0), call('quadratic_curve_to', 30, 40, 60, 0), call('close_path')], [(30, 10), (30, 25)]),
            'bezier': hits(lambda: [call('move_to', 0, 0), call('bezier_curve_to', 0, 40, 60, 40, 60, 0), call('close_path')], [(30, 20), (30, 35)]),
            'arcTo': hits(lambda: [call('move_to', 0, 0), call('arc_to', 40, 0, 40, 40, 20), call('line_to', 40, 40), call('line_to', 0, 40),
                                   call('close_path')], [(10, 10), (38, 2), (25, 5)]),
            'rect': hits(lambda: call('rect', 10, 10, 20, 10), [(15, 15), (35, 15)]),
            'roundRectList': hits(lambda: round_list([10], 0, 0, 40, 40), [(1, 1), (20, 20), (5, 20)]),
            'roundRectValue': hits(lambda: round_value(10, 0, 0, 40, 40), [(1, 1), (20, 20)]),
            'roundRectPoint': hits(lambda: round_value((20, 5), 0, 0, 40, 40), [(2, 10), (2, 2), (20, 20)]),
            'roundRectFour': hits(lambda: round_list([0, 0, 0, 20], 0, 0, 40, 40), [(1, 1), (39, 39), (1, 39)]),
        }
        oracle = {'arc': [True, False, True], 'halfArc': [True, False], 'anticlockwiseArc': [False, True], 'ellipse': [True, True, False],
                  'rotatedEllipse': [False, True], 'quadratic': [True, False], 'bezier': [True, False], 'arcTo': [True, False, True],
                  'rect': [True, False], 'roundRectList': [False, True, True], 'roundRectValue': [False, True],
                  'roundRectPoint': [True, False, True], 'roundRectFour': [True, True, False]}
        for name, expected in oracle.items():
            expect(report['shapes'][name] == expected, name + ': ' + str(report['shapes'][name]))
        # The same shapes on a Path2D.
        shape = new_path()
        ok(on_path['arc'](shape, 30, 20, 10, 0, pi * 2, 0), 'Path2D.arc')
        ok(on_path['ellipse'](shape, 10, 10, 5, 2, 0, 0, pi * 2, 0), 'Path2D.ellipse')
        value, keep = radii([3])
        ok(on_path['round_rect_5_list'](shape, 45, 30, 10, 8, ctypes.byref(value)), 'Path2D.roundRect list')
        item, keep2 = radius(2)
        ok(on_path['round_rect_5_value'](shape, 0, 30, 8, 8, ctypes.byref(item)), 'Path2D.roundRect value')
        curve = new_path()
        for name, args in [('move_to', (0, 0)), ('quadratic_curve_to', (30, 40, 60, 0)), ('bezier_curve_to', (60, 0, 60, 0, 60, 0)),
                           ('arc_to', (60, 0, 60, 0, 1)), ('line_to', (0, 0)), ('close_path', ())]:
            ok(on_path[name](curve, *args), 'Path2D.' + name)
        report['pathShapes'] = [hit(30, 20, path=shape), hit(10, 10, path=shape), hit(50, 34, path=shape), hit(4, 34, path=shape),
                                hit(30, 35, path=shape), hit(30, 10, path=curve), hit(30, 25, path=curve)]
        expect(report['pathShapes'] == [True, True, True, True, False, True, False], 'Path2D shapes: ' + str(report['pathShapes']))

        # 6. Argument errors and non-finite values.
        scratch = new_path()
        exception(on_context['arc'](ctx, 0, 0, -1, 0, 1, 0), 'IndexSizeError', 'arc negative radius')
        exception(on_path['arc'](scratch, 0, 0, -1, 0, 1, 0), 'IndexSizeError', 'Path2D.arc negative radius')
        exception(on_context['ellipse'](ctx, 0, 0, -1, 1, 0, 0, 1, 0), 'IndexSizeError', 'ellipse negative radius')
        exception(on_context['arc_to'](ctx, 0, 0, 1, 1, -1), 'IndexSizeError', 'arcTo negative radius')
        for label, values in [('negative', [-1]), ('five', [1, 2, 3, 4, 5]), ('empty', [])]:
            value, keep = radii(values)
            exception(on_context['round_rect_5_list'](ctx, 0, 0, 10, 10, ctypes.byref(value)), 'RangeError', 'roundRect ' + label)
        item, keep = radius(-1)
        exception(on_path['round_rect_5_value'](scratch, 0, 0, 10, 10, ctypes.byref(item)), 'RangeError', 'Path2D.roundRect negative value')
        conflict, keep = matrix(a=1, m11=2)
        exception(add_path(scratch, square, ctypes.byref(conflict)), 'TypeError', 'addPath conflicting matrix members')
        nan_matrix, keep = matrix(a=float('nan'))
        ok(add_path(scratch, square, ctypes.byref(nan_matrix)), 'addPath accepts a non-finite unrestricted member')
        ok(begin_path(ctx), 'beginPath')
        ok(on_context['rect'](ctx, 0, 0, 10, 10), 'rect')
        ok(on_context['line_to'](ctx, float('nan'), 5), 'lineTo NaN is ignored')
        ok(on_context['move_to'](ctx, float('inf'), 0), 'moveTo Infinity is ignored')
        report['nonFinite'] = [hit(5, 5), hit(float('nan'), 5), stroke_hit(5, float('nan'))]
        expect(report['nonFinite'] == [True, False, False], 'non-finite: ' + str(report['nonFinite']))
        expect(begin_path(None) == NULL_ARGUMENT and fill_path(ctx, None, 0) == NULL_ARGUMENT and hit_current(ctx, 1, 1, 0, None) == NULL_ARGUMENT,
               'NULL target, path and result')
        expect(create_0(None, ctypes.byref(handle)) == NULL_ARGUMENT and add_path(scratch, None, None) == NULL_ARGUMENT, 'NULL receiver and path')
        expect(create_0(c, ctypes.byref(handle)) == -11, 'Path2D creation needs a Document receiver')

        # 7. Clip to a Path2D, then to the current path; a bitmap reset clears the clip.
        reset()
        clip_square = new_path()
        ok(on_path['rect'](clip_square, 20, 10, 20, 20), 'clip rect')
        ok(clip_path(ctx, clip_square, FILL_RULE['NONZERO']), 'clip(path)')
        set_fill('#ff0000')
        ok(fill_rect(ctx, 0, 0, 60, 40), 'fillRect under the clip')
        report['clip'] = pixels((30, 20), (5, 5))
        expect(report['clip'] == [RED, WHITE], 'clip(path): ' + str(report['clip']))
        reset()
        ok(begin_path(ctx), 'beginPath')
        ok(on_context['rect'](ctx, 0, 0, 30, 40), 'rect')
        ok(clip_current(ctx, FILL_RULE['NONZERO']), 'clip()')
        set_fill('rgb(0, 0, 255)')
        ok(fill_rect(ctx, 0, 0, 60, 40), 'fillRect under the current-path clip')
        report['clipCurrent'] = pixels((10, 20), (45, 20))
        expect(report['clipCurrent'] == [BLUE, WHITE], 'clip(): ' + str(report['clipCurrent']))

        # 8. Stroke and strokeRect at the default 1px width on pixel centres; isPointInStroke on a Path2D.
        reset()
        line = new_path()
        ok(on_path['move_to'](line, 0, 5.5), 'moveTo')
        ok(on_path['line_to'](line, 60, 5.5), 'lineTo')
        ok(stroke_path(ctx, line), 'stroke(path)')
        ok(stroke_rect(ctx, 10.5, 10.5, 20, 20), 'strokeRect')
        ok(begin_path(ctx), 'beginPath')
        ok(on_context['move_to'](ctx, 0, 35.5), 'moveTo')
        ok(on_context['line_to'](ctx, 60, 35.5), 'lineTo')
        ok(stroke_current(ctx), 'stroke()')
        report['stroke'] = {'pixels': pixels((30, 5), (30, 7), (10, 20), (20, 20), (30, 35)),
                            'hitLine': stroke_hit(30, 5.5, line), 'missLine': stroke_hit(30, 8, line)}
        expect(report['stroke'] == {'pixels': [BLACK, WHITE, BLACK, WHITE, BLACK], 'hitLine': True, 'missLine': False},
               'stroke: ' + str(report['stroke']))
        ok(stroke_rect(ctx, float('nan'), 0, 5, 5), 'non-finite strokeRect is accepted')

        # 9. Ownership: drawing copies a path's geometry, so a path released after fill and clip leaves the context valid.
        reset()
        transient = new_path()
        ok(on_path['rect'](transient, 0, 0, 30, 40), 'transient rect')
        expect(retain_path(transient) == transient, 'retain returns the path')
        release_path(transient)
        ok(clip_path(ctx, transient, FILL_RULE['NONZERO']), 'clip(transient)')
        set_fill('#00ff00')
        ok(fill_path(ctx, transient, FILL_RULE['NONZERO']), 'fill(transient)')
        paths.remove(transient)
        release_path(transient)
        p.collect()
        ok(fill_rect(ctx, 0, 0, 60, 40), 'fillRect after the clip path is released')
        expect(pixels((10, 20), (45, 20)) == [GREEN, WHITE], 'the clip outlives the released path')
        ok(fill_current(ctx, FILL_RULE['NONZERO']), 'fill() after the path is released')

        canvas_watch = p.watch(c)
        for path in paths:
            release_path(path)
        paths.clear()
        release_context(ctx)
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
    print('PASS: canvas_paths %d assertions' % assertions, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--evidence-json')
    arguments = parser.parse_args()
    verify(arguments.native_directory, arguments.evidence_json)
