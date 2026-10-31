import ctypes, sys
from pathlib import Path
sys.path.insert(0, 'tests/abi')
from svg_paint_probe import SvgProbe
markup = '''<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300" id="root"><defs><symbol id="symbol" viewBox="0 0 10 10" preserveAspectRatio="none"><rect width="10" height="10" fill="red"/></symbol></defs><use id="u" href="#symbol" width="20" height="40"/></svg>'''
for mode in ['typed', 'attribute', 'typed-then-other-edit']:
    with SvgProbe(sys.argv[1], 400, 300) as p:
        p.load(markup); s = p.node('symbol'); p.paint()
        if mode == 'attribute':
            p.call('rv_dom_element_set_attribute', [p.pointer, ctypes.c_char_p, ctypes.c_char_p], s, b'viewBox', b'0 0 20 10')
        else:
            vb = p.property('svg_animated_rect', p.object('rv_dom_svg_symbol_element_get_view_box', [p.pointer], [s], 'svg_animated_rect'), 'base_val', 'svg_rect')
            p.call('rv_dom_svg_rect_set_width', [p.pointer, p.single], vb, 20)
            if mode == 'typed-then-other-edit':
                p.call('rv_dom_element_set_attribute', [p.pointer, ctypes.c_char_p, ctypes.c_char_p], p.node('u'), b'x', b'0.0')
        px = p.paint()
        print(mode, p.attribute(s, 'viewBox'), p.pixel(px, 5, 30), p.pixel(px, 15, 30), flush=True)
