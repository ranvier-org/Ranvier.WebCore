"""A layout inside an SVG root that joins a wider layout repaints what changed, not the grid item around it."""

import ctypes as C
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe
from utf8_inputs import Utf8

WIDTH, HEIGHT = 400, 300
# The chart of a dashboard card: a grid item holding an SVG and an absolutely positioned tooltip over it.
PAGE = ('<body style="margin:0;background:rgb(255,255,255)">'
        '<div style="display:grid;grid-template-columns:1fr;height:300px">'
        '<div id="card" style="position:relative;background:rgb(240,240,240);border-radius:8px">'
        '<svg id="chart" width="360" height="200" style="display:block;overflow:hidden">'
        '<rect width="360" height="200" fill="rgb(200,220,255)"/>'
        '<circle id="dot" cx="40" cy="100" r="6" fill="rgb(255,0,0)"/>'
        '</svg>'
        '<div id="tip" style="position:absolute;left:40px;top:20px;width:40px;height:20px;background:rgb(0,0,0)"></div>'
        '</div></div></body>')
TIP = 'position:absolute;left:{}px;top:20px;width:40px;height:20px;background:rgb(0,0,0)'


def run(directory):
    with SvgProbe(directory, WIDTH, HEIGHT) as p:
        P, I = p.pointer, p.integer
        compositing = p.bind('rv_host_set_accelerated_compositing', I, [P, I])
        composited = compositing(p.host, 1) == 0
        dirty_rect = p.bind('rv_host_dirty_rect', I, [P, C.POINTER(C.c_int32), C.POINTER(C.c_int32), C.POINTER(C.c_int32), C.POINTER(C.c_int32)])
        p.load(PAGE, standalone=False)
        dot, tip = p.node('dot'), p.node('tip')

        def attribute(node, name, value):
            p.call('rv_element_set_attribute', [P, C.c_char_p, Utf8], node, name, value.encode())

        def color(image, x, y):
            return tuple(p.pixel(image, x, y)[:3])

        def dirty():
            x, y, width, height = C.c_int32(), C.c_int32(), C.c_int32(), C.c_int32()
            status = dirty_rect(p.host, C.byref(x), C.byref(y), C.byref(width), C.byref(height))
            return (x.value, y.value, width.value, height.value) if status == 1 else None

        first = p.paint()
        p.expect(color(first, 40, 100) == (255, 0, 0) and color(first, 60, 30) == (0, 0, 0), 'the first paint shows the dot and the tooltip')
        p.expect(dirty() is None, 'a paint leaves nothing invalidated')

        # The dot's move is a layout inside the SVG root, a layout boundary; the tooltip's is a layout of the card's
        # out-of-flow box. Together they are one layout from the top.
        for step, left in enumerate([80, 120, 160], 1):
            attribute(dot, b'cx', str(left))
            attribute(tip, b'style', TIP.format(left))
            p.update()
            area = dirty()
            p.expect(area is not None, f'move {step} invalidates')
            x, y, width, height = area
            p.expect(width * height <= 140 * 110, f'move {step} invalidates the moved content, not the card ({area})')
            moved = p.paint()
            p.expect(color(moved, left, 100) == (255, 0, 0), f'move {step} paints the dot at its new place')
            p.expect(color(moved, left - 40, 100) == (200, 220, 255), f'move {step} leaves no dot at its old place')
            p.expect(color(moved, left + 20, 30) == (0, 0, 0), f'move {step} paints the tooltip at its new place')
            p.expect(color(moved, left - 30, 30) == (200, 220, 255), f'move {step} leaves no tooltip at its old place')

        # A change of the boundary's own size is still a layout of everything around it.
        chart = p.node('chart')
        attribute(chart, b'height', '100')
        resized = p.paint()
        p.expect(color(resized, 300, 150) == (240, 240, 240), 'a resized SVG root lets the card show below it')

        attribute(dot, b'cx', '200')
        attribute(tip, b'style', TIP.format(200))
        partial = p.paint()
        # Equal insets change nothing on the page but invalidate all of it, so the next paint is a full repaint.
        p.call('rv_host_set_obscured_insets', [P, C.c_double, C.c_double, C.c_double, C.c_double], p.host, 0, 0, 0, 0)
        full = p.paint()
        differing = sum(1 for i in range(WIDTH * HEIGHT) if tuple(partial[i * 4:i * 4 + 4]) != tuple(full[i * 4:i * 4 + 4]))
        p.expect(differing == 0, f'the partial repaints equal a full repaint ({differing} pixels differ)')
        if composited:
            p.expect(compositing(p.host, 2) == 0, 'compositing returns to when-needed')
        p.release_all()
        print('boundary repaint assertions:', p.assertions)


if __name__ == '__main__':
    run(sys.argv[1])
