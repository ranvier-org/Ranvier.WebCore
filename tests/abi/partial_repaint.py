"""Composited frames repaint only the page's invalidated rectangle, and match a full repaint of the same page."""

import ctypes as C
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe
from utf8_inputs import Utf8

WIDTH, HEIGHT = 200, 120
PAGE = ('<body style="margin:0;background:rgb(255,255,255)">'
        '<div id="a" style="position:absolute;left:10px;top:10px;width:20px;height:20px;background:rgb(255,0,0)"></div>'
        '<div id="b" style="position:absolute;left:150px;top:80px;width:20px;height:20px;background:rgb(0,0,255)"></div>'
        '<div id="c" style="position:absolute;left:100px;top:10px;width:20px;height:20px;background:rgb(0,0,0);'
        'will-change:transform"></div></body>')


def run(directory):
    with SvgProbe(directory, WIDTH, HEIGHT) as p:
        P, I = p.pointer, p.integer
        has = p.bind('rv_abi_has', I, [C.c_char_p])
        compositing = p.bind('rv_host_set_accelerated_compositing', I, [P, I])
        if compositing(p.host, 1) != 0:
            print('partial repaint: no GPU compositing in this runtime; skipped')
            return
        p.expect(has(b'host-tracing') == 1, 'runtime discovery')
        p.load(PAGE, standalone=False)
        a, b = p.node('a'), p.node('b')

        def style(node, value):
            p.call('rv_element_set_attribute', [P, C.c_char_p, Utf8], node, b'style', value.encode())

        def color(image, x, y):
            return tuple(p.pixel(image, x, y)[:3])

        first = p.paint()
        p.expect(color(first, 15, 15) == (255, 0, 0) and color(first, 155, 85) == (0, 0, 255), 'first composite paints the page')

        style(a, 'position:absolute;left:10px;top:10px;width:20px;height:20px;background:rgb(0,128,0)')
        recolored = p.paint()
        p.expect(color(recolored, 15, 15) == (0, 128, 0), 'an invalidated element repaints')
        p.expect(color(recolored, 155, 85) == (0, 0, 255), 'content outside the invalidation keeps its pixels')

        style(a, 'position:absolute;left:60px;top:60px;width:20px;height:20px;background:rgb(0,128,0)')
        moved = p.paint()
        p.expect(color(moved, 15, 15) == (255, 255, 255), 'a moved element leaves no pixels at its old place')
        p.expect(color(moved, 65, 65) == (0, 128, 0), 'a moved element paints at its new place')

        style(b, 'position:absolute;left:150px;top:80px;width:20px;height:20px;background:rgb(255,255,0)')
        partial = p.paint()
        # Equal insets change nothing on the page but invalidate all of it, so the next composite is a full repaint.
        p.call('rv_host_set_obscured_insets', [P, C.c_double, C.c_double, C.c_double, C.c_double], p.host, 0, 0, 0, 0)
        full = p.paint()
        differing = sum(1 for i in range(WIDTH * HEIGHT) if tuple(partial[i * 4:i * 4 + 4]) != tuple(full[i * 4:i * 4 + 4]))
        p.expect(differing == 0, f'a frame of partial repaints equals a full repaint ({differing} pixels differ)')
        p.expect(compositing(p.host, 2) == 0, 'compositing returns to when-needed')
        p.release_all()
        print('partial repaint assertions:', p.assertions)


if __name__ == '__main__':
    run(sys.argv[1])
