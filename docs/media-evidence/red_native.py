"""G01 RED: which media features the native host evaluates, and what they report. usage: red_native.py <tree> <native dir>"""
import ctypes, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / 'tests/abi'))
from svg_paint_probe import SvgProbe
QUERIES = ['(min-width: 300px)', '(width: 320px)', '(height: 240px)', '(orientation: landscape)', '(aspect-ratio: 4/3)',
           '(resolution: 1dppx)', '(resolution: 2dppx)', '(-webkit-device-pixel-ratio: 1)', '(device-width: 320px)', '(color)', '(color: 8)',
           '(color-gamut: srgb)', '(monochrome)', '(inverted-colors: inverted)', '(inverted-colors: none)',
           '(pointer: fine)', '(pointer: coarse)', '(pointer: none)', '(hover: hover)', '(hover: none)',
           '(any-pointer: fine)', '(any-pointer: coarse)', '(any-pointer: none)', '(any-hover: hover)', '(any-hover: none)',
           '(prefers-color-scheme: light)', '(prefers-color-scheme: dark)', '(prefers-reduced-motion: reduce)', '(prefers-reduced-motion: no-preference)',
           '(prefers-contrast: more)', '(prefers-contrast: less)', '(prefers-contrast: no-preference)', '(prefers-contrast: custom)',
           '(forced-colors: active)', '(forced-colors: none)', '(prefers-reduced-transparency: reduce)', '(prefers-reduced-data: reduce)',
           '(dynamic-range: high)', '(dynamic-range: standard)', '(scripting: enabled)', '(scripting: none)', '(update: fast)',
           '(display-mode: browser)', '(overflow-block: scroll)', '(grid: 0)', '(scan: progressive)', '(prefers-dark-interface)', 'print', 'screen',
           '(video-dynamic-range: high)', '(unknown-feature)']
with SvgProbe(sys.argv[2], 320, 240) as p:
    P, I = p.pointer, p.integer
    mm = p.bind('rv_host_match_media', P, [P, ctypes.c_char_p])
    matches = p.bind('rv_media_query_matches', I, [P, ctypes.POINTER(I)])
    media = p.bind('rv_media_query_media', I, [P, P, I, ctypes.POINTER(I)])
    release = p.bind('rv_event_target_release', None, [P])
    p.load('<!doctype html><html><body>x</body></html>', standalone=False)
    p.update()
    def evaluate():
        out = {}
        for q in QUERIES:
            t = mm(p.host, q.encode())
            m, buf, n = I(-1), ctypes.create_string_buffer(256), I()
            matches(t, ctypes.byref(m)); media(t, buf, 256, ctypes.byref(n))
            out[q] = (m.value, buf.raw[:n.value].decode())
            release(t)
        return out
    base = evaluate()
    p.bind('rv_host_resize', I, [P, I, I])(p.host, 200, 400)
    p.bind('rv_host_set_device_scale', I, [P, ctypes.c_float])(p.host, 2.0)
    p.update()
    after = evaluate()
    result = {q: {'matches': base[q][0], 'media': base[q][1], 'after200x400dpr2': after[q][0]} for q in QUERIES}
    print(json.dumps(result, indent=1))
