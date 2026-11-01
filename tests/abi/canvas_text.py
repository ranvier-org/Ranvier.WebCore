"""R05 canvas text: font, textAlign, textBaseline, direction, letterSpacing and wordSpacing, fillText and strokeText with
maxWidth, and measureText's TextMetrics, asserted as values and as representative pixels. The page loads WebKit's pinned
Ahem fixture as the @font-face family RvAhem from a data: URL, and the probe waits for it through rv_fonts_load (T01)
before measuring or drawing. Pixels are read from the host's software paint over a white page, each sampled at least
2px from a glyph edge. Tolerances: advance widths, font bounding boxes and baselines are exact for Ahem; actual bounding
boxes are within 1px, since Chromium inflates glyph bounds by 1px. Engine differences from Chromium, asserted as the
engine's values: the hanging baseline is the font ascent (Chromium: 0.8 of the ascent), the hanging textBaseline aligns
like top, and an inherited direction reads back resolved (Chromium: "inherit"). The Chromium oracle is docs/canvas-text-evidence/red-chromium.json."""
import argparse
import base64
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
OK, NULL_ARGUMENT, UNSUPPORTED = 0, -1, -9
TWO_D = 1
SUCCEEDED = 0
AHEM_SHA256 = '63d2abd0041c3e3b4b52ad8d382353b53c51c6785e76ce56ed9dacad2d2e31c4'
WHITE, RED, GREEN = [255, 255, 255, 255], [255, 0, 0, 255], [0, 255, 0, 255]
HEADER = Path(__file__).resolve().parents[2] / 'host/RanvierWebCoreDom.h'
METRICS = ['width', 'actual_bounding_box_left', 'actual_bounding_box_right', 'font_bounding_box_ascent', 'font_bounding_box_descent',
           'actual_bounding_box_ascent', 'actual_bounding_box_descent', 'em_height_ascent', 'em_height_descent', 'hanging_baseline',
           'alphabetic_baseline', 'ideographic_baseline']
ACTUAL = {'actual_bounding_box_left', 'actual_bounding_box_right', 'actual_bounding_box_ascent', 'actual_bounding_box_descent'}


def header_constants(prefix):
    text = HEADER.read_text(encoding='utf-8')
    return {name.removeprefix(prefix): int(value) for name, value in re.findall(r'(' + prefix + r'\w+) = (\d+)', text)}


ALIGN = header_constants('RV_DOM_CANVAS_TEXT_ALIGN_')
BASELINE = header_constants('RV_DOM_CANVAS_TEXT_BASELINE_')
DIRECTION = header_constants('RV_DOM_CANVAS_DIRECTION_')


def page(webkit_source):
    font = (Path(webkit_source) / 'Tools/TestWebKitAPI/Resources/cocoa/Ahem.ttf').read_bytes()
    assert hashlib.sha256(font).hexdigest() == AHEM_SHA256, 'Pinned Ahem fixture'
    return ('<!doctype html><style>@font-face{font-family:RvAhem;src:url(data:font/ttf;base64,' + base64.b64encode(font).decode() + ')}'
            'html,body{margin:0;background:#fff}canvas{display:block}#c,#r{width:120px;height:60px}</style>'
            '<body><canvas id=c width=120 height=60></canvas><canvas id=r dir=rtl width=120 height=60></canvas>')


def ahem(width, ascent=16.0, descent=4.0, shift=0.0, left=0.0, right=None):
    """The metrics of 20px Ahem text of the given advance whose ink spans [ascent, descent] around the alphabetic baseline,
    measured against a baseline moved down by shift."""
    return {'width': width, 'actual_bounding_box_left': left, 'actual_bounding_box_right': width - left if right is None else right,
            'font_bounding_box_ascent': 16.0 - shift, 'font_bounding_box_descent': 4.0 + shift,
            'actual_bounding_box_ascent': ascent - shift if ascent else 0.0, 'actual_bounding_box_descent': descent + shift if descent or ascent else 0.0,
            'em_height_ascent': 16.0 - shift, 'em_height_descent': 4.0 + shift, 'hanging_baseline': 16.0 - shift,
            'alphabetic_baseline': -shift, 'ideographic_baseline': -4.0 - shift}


def verify(directory, webkit_source, evidence_json=None):
    directory = Path(directory).resolve()
    before = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
    report = {}
    with SvgProbe(directory, 320, 240) as p:
        P, I, D, U64 = p.pointer, p.integer, ctypes.c_double, ctypes.c_uint64
        expect = p.expect
        expect(p.bind('rv_abi_version', I, [])() == ABI, 'ABI version ' + str(ABI))
        has = p.bind('rv_abi_has', I, [ctypes.c_char_p])
        expect(has(b'dom:TextMetrics') == 1 and has(b'font-load') == 1, 'rv_abi_has dom:TextMetrics and font-load')
        expect(ALIGN == {'START': 0, 'END': 1, 'LEFT': 2, 'RIGHT': 3, 'CENTER': 4} and len(BASELINE) == 6 and DIRECTION == {'LTR': 0, 'RTL': 1, 'INHERIT': 2},
               'enumeration constants: %s %s %s' % (ALIGN, BASELINE, DIRECTION))
        C = 'rv_dom_canvas_rendering_context2_d_'
        # The pinned engine has no fontKerning, fontStretch, fontVariantCaps or textRendering: they are Unsupported.
        unsupported = [C + verb + name for verb in ['get_', 'set_'] for name in ['font_kerning', 'font_stretch', 'font_variant_caps', 'text_rendering']]
        expect(not [name for name in unsupported if hasattr(p.library, name)], 'no export for the unsupported text attributes')

        def fn(name, arguments, prefix=C):
            return p.bind(prefix + name, I, arguments)

        get_context = p.bind('rv_canvas_get_context', I, [P, I, P, ctypes.POINTER(P)])
        strings = {name: fn('set_' + name, [P, Utf8]) for name in ['font', 'letter_spacing', 'word_spacing']}
        indices = {name: (fn('get_' + name, [P, ctypes.POINTER(I)]), fn('set_' + name, [P, I])) for name in ['text_align', 'text_baseline', 'direction']}
        fill_text = fn('fill_text', [P, Utf8, D, D, ctypes.POINTER(D)])
        stroke_text = fn('stroke_text', [P, Utf8, D, D, ctypes.POINTER(D)])
        measure = fn('measure_text', [P, Utf8, ctypes.POINTER(P)])
        getters = {name: p.bind('rv_dom_text_metrics_get_' + name, I, [P, ctypes.POINTER(D)]) for name in METRICS}
        release_metrics = p.bind('rv_dom_text_metrics_release', None, [P])
        retain_metrics = p.bind('rv_dom_text_metrics_retain', P, [P])
        clear_rect = fn('clear_rect', [P] + [D] * 4)
        set_line_width = fn('set_line_width', [P, D])
        save, restore, reset = fn('save', [P]), fn('restore', [P]), fn('reset', [P])

        def ok(status, label):
            expect(status == OK, label + ': status ' + str(status))

        def text(target, name):
            return p.text(C + 'get_' + name, [P], target)

        def index(target, name):
            value = I(-1)
            ok(indices[name][0](target, ctypes.byref(value)), name)
            return value.value

        def styles(target):
            return {'font': text(target, 'font'), 'textAlign': index(target, 'text_align'), 'textBaseline': index(target, 'text_baseline'),
                    'direction': index(target, 'direction'), 'letterSpacing': text(target, 'letter_spacing'), 'wordSpacing': text(target, 'word_spacing')}

        def read(metrics):
            values = {}
            for name in METRICS:
                value = D(math.nan)
                ok(getters[name](metrics, ctypes.byref(value)), 'TextMetrics.' + name)
                values[name] = value.value
            return values

        def measured(target, value):
            handle = P()
            ok(measure(target, value, ctypes.byref(handle)), 'measureText ' + repr(value))
            expect(bool(handle.value), 'measureText returns a TextMetrics')
            values = read(handle.value)
            release_metrics(handle.value)
            return values

        # HarfBuzz returns 16.16 fixed-point advances, so a measured width can be short by 2^-16 px per glyph.
        WIDTH_TOLERANCE = 2 ** -14

        def matches(actual, expected, label):
            def within(name):
                tolerance = 1.0 if name in ACTUAL else WIDTH_TOLERANCE
                return abs(actual[name] - expected[name]) <= tolerance
            expect(all(within(name) for name in METRICS), label + ': ' + json.dumps(actual) + ' expected ' + json.dumps(expected))

        def max_width(value):
            return None if value is None else ctypes.byref(D(value))

        def pixels(*points):
            rgba = p.paint()
            return [p.pixel(rgba, x, y) for x, y in points]

        # R04's union style setter: present, tag 1 (string), a UTF-8 span.
        class Span(ctypes.Structure):
            _fields_ = [('data', ctypes.POINTER(ctypes.c_uint8)), ('length', ctypes.c_int32)]

        class StyleUnion(ctypes.Structure):
            _fields_ = [('present', ctypes.c_int32), ('tag', ctypes.c_int32), ('arm0', Span), ('arm1', ctypes.c_void_p), ('arm2', ctypes.c_void_p)]
        set_styles = {kind: fn('set_' + kind + '_style', [P, ctypes.POINTER(StyleUnion)]) for kind in ['fill', 'stroke']}

        def set_style(target, kind, colour):
            data = colour.encode()
            buffer = (ctypes.c_uint8 * len(data)).from_buffer_copy(data)
            return set_styles[kind](target, ctypes.byref(StyleUnion(1, 1, Span(ctypes.cast(buffer, ctypes.POINTER(ctypes.c_uint8)), len(data)), None, None)))

        p.load(page(webkit_source), standalone=False)
        c, r = p.node('c'), p.node('r')
        handle = P()
        ok(get_context(c, TWO_D, None, ctypes.byref(handle)), 'getContext 2d')
        ctx = handle.value
        ok(get_context(r, TWO_D, None, ctypes.byref(handle)), 'getContext 2d on the rtl canvas')
        rtl = handle.value

        # 1. Defaults, then readiness of the Ahem face through T01, never by sleeping.
        report['defaults'] = styles(ctx)
        expect(report['defaults'] == {'font': '10px sans-serif', 'textAlign': ALIGN['START'], 'textBaseline': BASELINE['ALPHABETIC'],
                                      'direction': DIRECTION['LTR'], 'letterSpacing': '0px', 'wordSpacing': '0px'}, 'defaults: ' + str(report['defaults']))
        Completion = ctypes.CFUNCTYPE(None, P, I, I, I)
        results = []
        completion = Completion(lambda context, outcome, width, height: results.append((outcome, width)))
        load = p.bind('rv_fonts_load', I, [P, Utf8, ctypes.c_char_p, I, Completion, P, ctypes.POINTER(U64)])
        cycle = p.bind('rv_run_loop_cycle', I, [I])
        release_operation = p.bind('rv_resource_release', I, [U64])
        operation = U64(0)
        ok(load(p.host, '20px RvAhem', None, 0, completion, None, ctypes.byref(operation)), 'rv_fonts_load 20px RvAhem')
        expect(results == [], 'no font completion inside rv_fonts_load')
        # Hang guard: the wait counts no assertion.
        for _ in range(400):
            if results:
                break
            cycle(5)
        else:
            raise AssertionError('Timed out waiting for the Ahem face')
        expect(results == [(SUCCEEDED, 1)], 'the Ahem face loads: ' + str(results))
        release_operation(operation)

        # 2. Setters and their validation.
        ok(strings['font'](ctx, '20px RvAhem'), 'font')
        report['font'] = text(ctx, 'font')
        ok(strings['font'](ctx, 'bogus'), 'invalid font')
        report['fontKept'] = text(ctx, 'font')
        ok(strings['font'](ctx, 'italic bold 20px/30px RvAhem'), 'font shorthand')
        report['fontShorthand'] = text(ctx, 'font')
        ok(strings['font'](ctx, '1em RvAhem'), 'font in em')
        report['fontEm'] = text(ctx, 'font')
        ok(indices['text_align'][1](ctx, ALIGN['CENTER']), 'textAlign center')
        expect(indices['text_align'][1](ctx, 5) == UNSUPPORTED and indices['text_align'][1](ctx, -1) == UNSUPPORTED, 'unknown textAlign index')
        expect(indices['text_baseline'][1](ctx, 6) == UNSUPPORTED and indices['direction'][1](ctx, 3) == UNSUPPORTED, 'unknown baseline and direction indices')
        ok(indices['text_baseline'][1](ctx, BASELINE['TOP']), 'textBaseline top')
        ok(indices['direction'][1](ctx, DIRECTION['RTL']), 'direction rtl')
        ok(strings['letter_spacing'](ctx, '2px'), 'letterSpacing')
        ok(strings['letter_spacing'](ctx, 'wide'), 'invalid letterSpacing')
        report['letterSpacingKept'] = text(ctx, 'letter_spacing')
        ok(strings['letter_spacing'](ctx, '0.5em'), 'letterSpacing em')
        report['letterSpacingEm'] = text(ctx, 'letter_spacing')
        ok(strings['word_spacing'](ctx, '3px'), 'wordSpacing')
        ok(strings['word_spacing'](ctx, '3'), 'unitless wordSpacing')
        report['set'] = styles(ctx)
        expect(report['font'] == '20px RvAhem' and report['fontKept'] == '20px RvAhem' and report['fontShorthand'] == 'italic bold 20px RvAhem'
               and report['fontEm'] == '16px RvAhem', 'font serialisation: ' + str([report[k] for k in ['font', 'fontKept', 'fontShorthand', 'fontEm']]))
        expect(report['letterSpacingKept'] == '2px' and report['letterSpacingEm'] == '0.5em', 'letterSpacing: ' + str([report['letterSpacingKept'], report['letterSpacingEm']]))
        expect(report['set'] == {'font': '16px RvAhem', 'textAlign': ALIGN['CENTER'], 'textBaseline': BASELINE['TOP'], 'direction': DIRECTION['RTL'],
                                 'letterSpacing': '0.5em', 'wordSpacing': '3px'}, 'set styles: ' + str(report['set']))
        ok(reset(ctx), 'reset')
        report['afterReset'] = styles(ctx)
        expect(report['afterReset'] == report['defaults'], 'reset restores the text defaults: ' + str(report['afterReset']))
        ok(save(ctx), 'save')
        ok(strings['font'](ctx, '20px RvAhem'), 'font inside save')
        ok(indices['text_align'][1](ctx, ALIGN['END']), 'textAlign inside save')
        ok(restore(ctx), 'restore')
        expect(text(ctx, 'font') == '10px sans-serif' and index(ctx, 'text_align') == ALIGN['START'], 'restore restores font and textAlign')

        # 3. Metrics of 20px Ahem: every glyph of 'X' fills the em box, 'p' its descent, 'É' its ascent.
        ok(strings['font'](ctx, '20px RvAhem'), 'font 20px RvAhem')
        report['measureX'] = measured(ctx, 'XXX')
        matches(report['measureX'], ahem(60), 'XXX')
        report['measureP'] = measured(ctx, 'p')
        matches(report['measureP'], ahem(20, ascent=0.0, descent=4.0), 'p')
        report['measureE'] = measured(ctx, 'É')
        matches(report['measureE'], ahem(20, ascent=16.0, descent=0.0), 'É')
        report['measureEmpty'] = measured(ctx, '')
        expect(report['measureEmpty']['width'] == 0 and report['measureEmpty']['font_bounding_box_ascent'] == 16, 'empty text: ' + str(report['measureEmpty']))
        report['measureSpace'] = measured(ctx, 'X X')
        matches(report['measureSpace'], ahem(60), 'X X')
        for name, left in [('START', 0), ('END', 40), ('LEFT', 0), ('RIGHT', 40), ('CENTER', 20)]:
            ok(indices['text_align'][1](ctx, ALIGN[name]), 'textAlign ' + name)
            report['align_' + name] = measured(ctx, 'XX')
            matches(report['align_' + name], ahem(40, left=float(left), right=40.0 - left), 'align ' + name)
        ok(indices['text_align'][1](ctx, ALIGN['START']), 'textAlign start')
        for name, shift in [('TOP', 16.0), ('HANGING', 16.0), ('MIDDLE', 6.0), ('ALPHABETIC', 0.0), ('IDEOGRAPHIC', -4.0), ('BOTTOM', -4.0)]:
            ok(indices['text_baseline'][1](ctx, BASELINE[name]), 'textBaseline ' + name)
            report['baseline_' + name] = measured(ctx, 'X')
            matches(report['baseline_' + name], ahem(20, shift=shift), 'baseline ' + name)
        ok(indices['text_baseline'][1](ctx, BASELINE['ALPHABETIC']), 'textBaseline alphabetic')
        ok(strings['letter_spacing'](ctx, '5px'), 'letterSpacing 5px')
        report['letterSpaced'] = measured(ctx, 'XXX')
        # WebKit's ink bounds include the trailing letter spacing (Chromium: 70).
        matches(report['letterSpaced'], ahem(75), 'letter spaced')
        ok(strings['letter_spacing'](ctx, '0px'), 'letterSpacing 0px')
        ok(strings['word_spacing'](ctx, '7px'), 'wordSpacing 7px')
        report['wordSpaced'] = measured(ctx, 'X X')
        matches(report['wordSpaced'], ahem(67), 'word spaced')
        ok(strings['word_spacing'](ctx, '0px'), 'wordSpacing 0px')
        ok(indices['direction'][1](ctx, DIRECTION['RTL']), 'direction rtl')
        report['rtlStart'] = measured(ctx, 'XX')
        matches(report['rtlStart'], ahem(40, left=40.0, right=0.0), 'rtl start')
        ok(indices['direction'][1](ctx, DIRECTION['INHERIT']), 'direction inherit')
        ok(strings['font'](rtl, '20px RvAhem'), 'font on the rtl canvas')
        report['inheritRtl'] = measured(rtl, 'XX')
        # WebKit reads an inherited direction back resolved, where Chromium reads "inherit".
        expect(index(rtl, 'direction') == DIRECTION['RTL'], 'an inherited direction reads back resolved on the rtl canvas')
        matches(report['inheritRtl'], ahem(40, left=40.0, right=0.0), 'inherited rtl')

        # A TextMetrics outlives a retain/release pair and the context's later state changes.
        handle = P()
        ok(measure(ctx, 'XX', ctypes.byref(handle)), 'measureText kept')
        kept = handle.value
        expect(retain_metrics(kept) == kept, 'rv_dom_text_metrics_retain returns its argument')
        release_metrics(kept)
        ok(strings['font'](ctx, '40px RvAhem'), 'font 40px')
        expect(abs(read(kept)['width'] - 40) <= WIDTH_TOLERANCE, 'a TextMetrics is a snapshot: later font changes keep its width')
        ok(strings['font'](ctx, '20px RvAhem'), 'font 20px again')

        # 4. Pixels, sampled at least 2px from a glyph edge.
        ok(set_style(ctx, 'fill', '#ff0000'), 'fillStyle red')
        ok(fill_text(ctx, 'X', 10, 30, None), 'fillText X')
        report['fill'] = pixels((20, 22), (20, 16), (20, 32), (20, 11), (20, 37), (7, 22), (33, 22))
        expect(report['fill'] == [RED] * 3 + [WHITE] * 4, 'fillText at an alphabetic baseline: ' + str(report['fill']))
        ok(clear_rect(ctx, 0, 0, 120, 60), 'clearRect')
        ok(fill_text(ctx, 'XXXX', 0, 30, max_width(40)), 'fillText maxWidth 40')
        report['maxWidth'] = pixels((37, 22), (43, 22), (70, 22))
        expect(report['maxWidth'] == [RED, WHITE, WHITE], 'maxWidth compresses the run: ' + str(report['maxWidth']))
        ok(clear_rect(ctx, 0, 0, 120, 60), 'clearRect')
        for value in [0, -1, math.nan]:
            ok(fill_text(ctx, 'XX', 0, 30, max_width(value)), 'fillText maxWidth %r' % value)
        ok(fill_text(ctx, '', 0, 30, None), 'fillText empty')
        ok(fill_text(ctx, 'X', math.nan, 30, None), 'fillText NaN x')
        report['nothingDrawn'] = pixels((10, 22), (30, 22))
        expect(report['nothingDrawn'] == [WHITE, WHITE], 'non-positive or NaN maxWidth, empty text and NaN x draw nothing: ' + str(report['nothingDrawn']))
        ok(indices['text_align'][1](ctx, ALIGN['CENTER']), 'textAlign center')
        ok(indices['text_baseline'][1](ctx, BASELINE['MIDDLE']), 'textBaseline middle')
        ok(fill_text(ctx, 'X', 60, 30, None), 'centred fillText')
        report['centered'] = pixels((60, 30), (52, 30), (47, 30), (68, 30), (73, 30), (60, 22), (60, 17), (60, 38), (60, 43))
        expect(report['centered'] == [RED, RED, WHITE, RED, WHITE, RED, WHITE, RED, WHITE], 'centre/middle: ' + str(report['centered']))
        ok(clear_rect(ctx, 0, 0, 120, 60), 'clearRect')
        ok(indices['text_align'][1](ctx, ALIGN['START']), 'textAlign start')
        ok(indices['text_baseline'][1](ctx, BASELINE['ALPHABETIC']), 'textBaseline alphabetic')
        ok(indices['direction'][1](ctx, DIRECTION['RTL']), 'direction rtl')
        ok(fill_text(ctx, 'X', 100, 30, None), 'rtl fillText')
        report['rtlFill'] = pixels((90, 22), (103, 22), (77, 22))
        expect(report['rtlFill'] == [RED, WHITE, WHITE], 'rtl start draws leftwards: ' + str(report['rtlFill']))
        ok(indices['direction'][1](ctx, DIRECTION['INHERIT']), 'direction inherit')
        ok(clear_rect(ctx, 0, 0, 120, 60), 'clearRect')
        ok(set_line_width(ctx, 2), 'lineWidth 2')
        ok(set_style(ctx, 'stroke', '#0000ff'), 'strokeStyle blue')
        ok(stroke_text(ctx, 'X', 10, 30, None), 'strokeText')
        report['stroke'] = pixels((10, 22), (20, 22), (6, 22), (30, 22))
        blue = [report['stroke'][0], report['stroke'][3]]
        expect(all(b >= 200 and r <= 80 and g <= 80 for r, g, b, _ in blue) and report['stroke'][1:3] == [WHITE, WHITE],
               'strokeText outlines the glyph and leaves it hollow: ' + str(report['stroke']))
        ok(clear_rect(ctx, 0, 0, 120, 60), 'clearRect')
        ok(strings['letter_spacing'](ctx, '10px'), 'letterSpacing 10px')
        ok(fill_text(ctx, 'XX', 0, 30, None), 'letter-spaced fillText')
        report['letterSpacedFill'] = pixels((10, 22), (25, 22), (40, 22), (55, 22))
        expect(report['letterSpacedFill'] == [RED, WHITE, RED, WHITE], 'letterSpacing separates the glyphs: ' + str(report['letterSpacedFill']))
        ok(set_style(rtl, 'fill', '#00ff00'), 'fillStyle green on the rtl canvas')
        ok(fill_text(rtl, 'X', 100, 30, None), 'inherited rtl fillText')
        report['inheritRtlFill'] = pixels((90, 82), (103, 82), (77, 82))
        expect(report['inheritRtlFill'] == [GREEN, WHITE, WHITE], 'direction inherit follows the canvas dir=rtl: ' + str(report['inheritRtlFill']))
        expect(fill_text(None, 'X', 0, 0, None) == NULL_ARGUMENT and measure(ctx, 'X', None) == NULL_ARGUMENT
               and getters['width'](None, ctypes.byref(D())) == NULL_ARGUMENT, 'NULL arguments')

        # 5. Teardown: a TextMetrics handle stays readable after its context, canvas and host are gone.
        canvas_watch = p.watch(c)
        p.bind(C + 'release', None, [P])(ctx)
        p.bind(C + 'release', None, [P])(rtl)
        p.release_all()
        p.dispose_host()
        p.collect()
        expect(p.bind('rv_watch_alive', I, [P])(canvas_watch) == 0, 'the canvas expires after host destruction')
        report['keptAfterHost'] = read(kept)
        matches(report['keptAfterHost'], ahem(40), 'TextMetrics after host destruction')
        release_metrics(kept)
        report['assertions'] = p.assertions
        assertions = p.assertions
    after = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
    if before != after:
        raise AssertionError('runtime changed')
    if evidence_json:
        Path(evidence_json).write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8')
    print('PASS: canvas_text %d assertions' % assertions, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--webkit-source', default='C:/wk/src')
    parser.add_argument('--evidence-json')
    arguments = parser.parse_args()
    verify(arguments.native_directory, arguments.webkit_source, arguments.evidence_json)
