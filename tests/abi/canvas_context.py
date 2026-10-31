"""R01 canvas 2D context lifecycle: create and release a 2D context, draw a deterministic surface, context identity and
reset, and explicit failure for context types and settings the engine does not render. Pixels are read from the host's
software paint over a white page, so a transparent canvas pixel reads white. The Chromium oracle is
docs/canvas-evidence/red-chromium.json."""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe

ABI = 55
OK, NULL_ARGUMENT, UNSUPPORTED, WRONG_INTERFACE = 0, -1, -9, -11
NONE, TWO_D, BITMAP_RENDERER, WEBGL, WEBGL2, WEBGPU = range(6)
WHITE = [255, 255, 255, 255]
PAGE = ('<!doctype html><style>html,body{margin:0;background:#fff}canvas{display:block}</style>'
        '<body id=b><canvas id=c width=40 height=20 style="width:40px;height:20px"></canvas>'
        '<canvas id=d></canvas><canvas id=e width=10 height=10></canvas><canvas id=f width=10 height=10></canvas><div id=n></div>')


class Settings(ctypes.Structure):
    _fields_ = [('size', ctypes.c_int32), ('alpha', ctypes.c_int32), ('desynchronized', ctypes.c_int32),
                ('willReadFrequently', ctypes.c_int32), ('colorSpace', ctypes.c_int32), ('colorType', ctypes.c_int32)]


def settings(**fields):
    value = Settings(ctypes.sizeof(Settings), 1, 0, 0, 0, 0)
    for name, field in fields.items():
        setattr(value, name, field)
    return value


class Style(ctypes.Structure):
    _fields_ = [('present', ctypes.c_int32), ('tag', ctypes.c_int32), ('arm0', ctypes.c_char_p),
                ('arm1', ctypes.c_void_p), ('arm2', ctypes.c_void_p)]


def verify(directory, evidence_json=None):
    directory = Path(directory).resolve()
    before = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
    report = {}
    with SvgProbe(directory, 320, 240) as p:
        P, I, U = p.pointer, p.integer, p.unsigned
        expect = p.expect
        expect(p.bind('rv_abi_version', I, [])() == ABI, 'ABI version ' + str(ABI))
        has = p.bind('rv_abi_has', I, [ctypes.c_char_p])
        for feature in ['canvas-context', 'dom:HTMLCanvasElement', 'dom:CanvasRenderingContext2D', 'dom:CanvasGradient', 'dom:CanvasPattern']:
            expect(has(feature.encode()) == 1, 'rv_abi_has ' + feature)
        get_context = p.bind('rv_canvas_get_context', I, [P, I, ctypes.POINTER(Settings), ctypes.POINTER(P)])
        attributes = p.bind('rv_canvas_context_2d_attributes', I, [P, ctypes.POINTER(Settings)])
        release_context = p.bind('rv_dom_canvas_rendering_context2_d_release', None, [P])
        retain_context = p.bind('rv_dom_canvas_rendering_context2_d_retain', P, [P])
        get_canvas = p.bind('rv_dom_canvas_rendering_context2_d_get_canvas', I, [P, ctypes.POINTER(P)])
        get_style = p.bind('rv_dom_canvas_rendering_context2_d_get_fill_style', I, [P, ctypes.POINTER(Style)])
        set_style = p.bind('rv_dom_canvas_rendering_context2_d_set_fill_style', I, [P, ctypes.POINTER(Style)])
        release_style = p.bind('rv_dom_union_dom_string_or_canvas_gradient_or_canvas_pattern_release', None, [ctypes.POINTER(Style)])
        fill_rect = p.bind('rv_dom_canvas_rendering_context2_d_fill_rect', I, [P] + [ctypes.c_double] * 4)
        clear_rect = p.bind('rv_dom_canvas_rendering_context2_d_clear_rect', I, [P] + [ctypes.c_double] * 4)
        node_release = p.bind('rv_node_release', None, [P])
        contexts = []

        def context(canvas, kind=TWO_D, requested=None, status=OK):
            out = P(1234)
            code = get_context(canvas, kind, ctypes.byref(requested) if requested is not None else None, ctypes.byref(out))
            expect(code == status, 'rv_canvas_get_context status %d, expected %d' % (code, status))
            if out.value:
                contexts.append(out.value)
            return out.value

        def dimension(canvas, name):
            value = U()
            p.call('rv_dom_html_canvas_element_get_' + name, [P, ctypes.POINTER(U)], canvas, ctypes.byref(value))
            return value.value

        def set_dimension(canvas, name, value):
            p.call('rv_dom_html_canvas_element_set_' + name, [P, U], canvas, value)

        def fill_style(ctx):
            value = Style()
            expect(get_style(ctx, ctypes.byref(value)) == OK, 'fillStyle getter')
            expect(value.present == 1 and value.tag == 1, 'fillStyle is a string')
            text = value.arm0.decode()
            release_style(ctypes.byref(value))
            return text

        def set_fill(ctx, text):
            value = Style(1, 1, text.encode(), None, None)
            expect(set_style(ctx, ctypes.byref(value)) == OK, 'fillStyle setter ' + text)

        def read_attributes(ctx):
            value = Settings(ctypes.sizeof(Settings), -7, -7, -7, -7, -7)
            expect(attributes(ctx, ctypes.byref(value)) == OK, 'getContextAttributes')
            return {name: getattr(value, name) for name, _ in Settings._fields_[1:]}

        def pixels(*points):
            rgba = p.paint()
            return [p.pixel(rgba, x, y) for x, y in points]

        def near(actual, expected, label, tolerance=1):
            expect(all(abs(a - b) <= tolerance for a, b in zip(actual, expected)), label + ': ' + str(actual))

        p.load(PAGE, standalone=False)
        c, d, e, f, n, b = (p.node(name) for name in 'cdefnb')

        # Defaults and the generated dimensions.
        report['defaults'] = [dimension(d, 'width'), dimension(d, 'height')]
        expect(report['defaults'] == [300, 150], 'default canvas size 300x150')
        expect(dimension(c, 'width') == 40 and dimension(c, 'height') == 20, 'canvas size from attributes')
        width = U()
        expect(p.bind('rv_dom_html_canvas_element_get_width', I, [P, ctypes.POINTER(U)])(n, ctypes.byref(width)) == WRONG_INTERFACE,
               'width getter rejects a <div>')

        # Creation, identity and the canvas back-reference.
        out = P(1234)
        expect(get_context(n, TWO_D, None, ctypes.byref(out)) == WRONG_INTERFACE and out.value is None, 'getContext rejects a <div>')
        expect(get_context(None, TWO_D, None, ctypes.byref(out)) == NULL_ARGUMENT, 'getContext rejects a NULL canvas')
        expect(get_context(c, TWO_D, None, None) == NULL_ARGUMENT, 'getContext rejects a NULL output')
        ctx = context(c)
        expect(bool(ctx), '2D context created')
        again = context(c)
        expect(again == ctx, 'getContext returns the same context')
        ignored = context(c, requested=settings(willReadFrequently=1))
        expect(ignored == ctx and read_attributes(ctx)['willReadFrequently'] == 0, 'later settings are ignored')
        expect(context(c, requested=settings(alpha=0), status=UNSUPPORTED) is None, 'unsupported settings fail on an existing context')
        back = P()
        expect(get_canvas(ctx, ctypes.byref(back)) == OK and back.value == c, 'context.canvas is the canvas')
        node_release(back.value)
        expect(retain_context(ctx) == ctx, 'retain returns the context')
        release_context(ctx)

        # Explicit failure for other context types, with and without an existing context.
        for kind in [BITMAP_RENDERER, WEBGL, WEBGL2, WEBGPU, NONE, 99, -1]:
            expect(context(c, kind, status=UNSUPPORTED) is None, 'type %d is unsupported on a 2D canvas' % kind)
        for kind in [WEBGL, WEBGL2, WEBGPU, BITMAP_RENDERER, 42]:
            expect(context(e, kind, status=UNSUPPORTED) is None, 'type %d is unsupported on a fresh canvas' % kind)
        expect(bool(context(e)), 'an unsupported request leaves the canvas free for 2D')

        # Settings: what the engine honours, and explicit failure for what it does not.
        report['attributes'] = read_attributes(ctx)
        expect(report['attributes'] == {'alpha': 1, 'desynchronized': 0, 'willReadFrequently': 0, 'colorSpace': 0, 'colorType': 0},
               'default context attributes')
        for label, request in [('alpha 0', settings(alpha=0)), ('display-p3', settings(colorSpace=1)), ('float16', settings(colorType=1)),
                               ('flag 2', settings(desynchronized=2)), ('colour space 9', settings(colorSpace=9)),
                               ('size', Settings(ctypes.sizeof(Settings) - 4, 1, 0, 0, 0, 0))]:
            expect(context(f, requested=request, status=UNSUPPORTED) is None, 'unsupported setting ' + label)
        willing = context(d, requested=settings(willReadFrequently=1, desynchronized=1))
        report['requestedAttributes'] = read_attributes(willing)
        expect(report['requestedAttributes'] == {'alpha': 1, 'desynchronized': 1, 'willReadFrequently': 1, 'colorSpace': 0, 'colorType': 0},
               'requested attributes are applied')
        expect(bool(context(f)), 'unsupported settings leave the canvas free for 2D')
        small = Settings(ctypes.sizeof(Settings) - 4, 9, 9, 9, 9, 9)
        expect(attributes(ctx, ctypes.byref(small)) == UNSUPPORTED and small.alpha == 9, 'attributes reject a small struct')
        expect(attributes(ctx, None) == NULL_ARGUMENT, 'attributes reject NULL')

        # fillStyle serialisation as Chromium reports it.
        report['fillStyle'] = {'initial': fill_style(ctx)}
        expect(report['fillStyle']['initial'] == '#000000', 'initial fillStyle')
        for given, expected in [('#ff0000', '#ff0000'), ('not a colour', '#ff0000'), ('rgba(0, 0, 255, 0.5)', 'rgba(0, 0, 255, 0.5)'), ('lime', '#00ff00')]:
            set_fill(ctx, given)
            report['fillStyle'][given] = fill_style(ctx)
            expect(report['fillStyle'][given] == expected, 'fillStyle %r serialises as %r' % (given, expected))

        # A deterministic surface.
        expect(pixels((5, 5))[0] == WHITE, 'a fresh canvas is transparent')
        set_fill(ctx, '#ff0000')
        p.call('rv_dom_canvas_rendering_context2_d_fill_rect', [P] + [ctypes.c_double] * 4, ctx, 0, 0, 20, 20)
        set_fill(ctx, 'rgb(0, 0, 255)')
        p.call('rv_dom_canvas_rendering_context2_d_fill_rect', [P] + [ctypes.c_double] * 4, ctx, 20, 0, 20, 20)
        report['drawn'] = pixels((5, 5), (30, 5), (45, 5))
        expect(report['drawn'] == [[255, 0, 0, 255], [0, 0, 255, 255], WHITE], 'filled rectangles paint exactly')
        p.call('rv_dom_canvas_rendering_context2_d_clear_rect', [P] + [ctypes.c_double] * 4, ctx, 5, 5, 4, 4)
        report['cleared'] = pixels((6, 6), (10, 10))
        expect(report['cleared'] == [WHITE, [255, 0, 0, 255]], 'clearRect clears exactly its rectangle')
        expect(fill_rect(ctx, float('nan'), 0, 5, 5) == OK and fill_rect(ctx, 0, 0, float('inf'), 5) == OK, 'non-finite fillRect is accepted')
        expect(pixels((6, 6))[0] == WHITE, 'non-finite fillRect draws nothing')
        set_fill(ctx, 'rgba(0, 255, 0, 0.5)')
        expect(fill_rect(ctx, 0, 10, 40, 10) == OK, 'half-alpha fill')
        report['halfAlpha'] = pixels((5, 15), (30, 15))
        near(report['halfAlpha'][0], [127, 128, 0, 255], 'half-alpha green over red')
        near(report['halfAlpha'][1], [0, 128, 127, 255], 'half-alpha green over blue')
        expect(fill_rect(None, 0, 0, 1, 1) == NULL_ARGUMENT and clear_rect(None, 0, 0, 1, 1) == NULL_ARGUMENT, 'rect calls reject NULL')

        # Reset: assigning a dimension clears the bitmap and the drawing state, and keeps the context.
        set_fill(ctx, '#123456')
        set_dimension(c, 'width', dimension(c, 'width'))
        expect(pixels((5, 5))[0] == WHITE and fill_style(ctx) == '#000000', 'same-width assignment resets bitmap and state')
        expect(context(c) == ctx, 'reset keeps the context')
        set_fill(ctx, '#00ff00')
        fill_rect(ctx, 0, 0, 40, 20)
        expect(pixels((5, 5))[0] == [0, 255, 0, 255], 'draw after reset')
        set_dimension(c, 'height', 30)
        expect(pixels((5, 5))[0] == WHITE and fill_style(ctx) == '#000000' and dimension(c, 'height') == 30, 'height assignment resets')
        set_dimension(c, 'width', 4294967295)
        report['hugeWidth'] = dimension(c, 'width')
        expect(report['hugeWidth'] == 300, 'width above 2^31-1 falls back to 300')
        set_dimension(c, 'width', 0)
        expect(dimension(c, 'width') == 0 and read_attributes(ctx)['alpha'] == 1, 'zero width keeps the context')
        set_dimension(c, 'width', 40)
        set_dimension(c, 'height', 20)

        # A removed canvas keeps drawing; reinserted, it paints what was drawn.
        p.call('rv_node_remove', [P], c)
        set_fill(ctx, '#ff00ff')
        expect(fill_rect(ctx, 0, 0, 10, 10) == OK and context(c) == ctx, 'a detached canvas keeps its context and draws')
        p.call('rv_node_insert_before', [P, P, P], b, c, d)
        expect(pixels((1, 1))[0] == [255, 0, 255, 255], 'a reinserted canvas paints its detached drawing')

        # Ownership: a context keeps its canvas alive after every node handle is released.
        document = p.bind('rv_host_document', P, [P])(p.host)
        expect(bool(document), 'host document')
        p.retained.append(('rv_node_release', document))
        created = P()
        p.call('rv_dom_document_create_element', [P, ctypes.c_char_p, I, P, ctypes.POINTER(P)], document, b'canvas', 6, None, ctypes.byref(created))
        orphan_watch = p.watch(created.value)
        orphan = context(created.value)
        expect(bool(orphan), 'a never-attached canvas has a 2D context')
        node_release(created.value)
        p.collect()
        expect(p.bind('rv_watch_alive', I, [P])(orphan_watch) == 1, 'the context keeps its canvas alive')
        back = P()
        expect(get_canvas(orphan, ctypes.byref(back)) == OK and bool(back.value), 'canvas of a context that owns it')
        expect(dimension(back.value, 'width') == 300, 'the kept canvas is usable')
        node_release(back.value)
        contexts.remove(orphan)
        release_context(orphan)
        p.collect()
        expect(p.bind('rv_watch_alive', I, [P])(orphan_watch) == 0, 'releasing the last context reference frees the canvas')

        canvas_watch = p.watch(c)
        for handle in contexts:
            release_context(handle)
        contexts.clear()
        p.release_all()
        p.dispose_host()
        p.collect()
        expect(p.bind('rv_watch_alive', I, [P])(canvas_watch) == 0, 'the document canvas expires after host destruction')
        report['assertions'] = p.assertions
        assertions = p.assertions
    after = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
    if before != after:
        raise AssertionError('runtime changed')
    if evidence_json:
        Path(evidence_json).write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8')
    print('PASS: canvas_context %d assertions' % assertions, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--evidence-json')
    arguments = parser.parse_args()
    verify(arguments.native_directory, arguments.evidence_json)
