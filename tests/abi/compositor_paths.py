"""The composited paths a browser keeps cheap stay cheap natively, measured with host tracing (RENDERING_UPDATE and
PAINT), and keep their pixels:

- a viewport scroll moves the root layer's pixels and repaints only the strip it exposes, and the scrolled frame equals
  a full repaint of the same position;
- a scroll leaves a composited position:fixed layer's pixels alone: it moves with the viewport, not its content;
- a composited layer that only moves (its transform) is not repainted;
- recoloring one small element repaints that element, not the text around it;
- rv_host_update with nothing invalidated runs no style, layout or paint work.
"""

import ctypes as C
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe, software_gl
from utf8_inputs import Utf8

WIDTH, HEIGHT, SCALE = 960, 600, 2
FRAMES = 20
STYLE_LAYOUT, PAINT, RENDERING_UPDATE = 2, 3, 4
CARD = ('width:200px;height:150px;border-radius:14px;background:#fff;margin:20px;display:inline-block;'
        'vertical-align:top;padding:8px;font:14px sans-serif;'
        'box-shadow:0 6px 18px -8px rgba(0,0,0,.45),0 18px 36px -14px rgba(0,0,0,.35)')
TEXT = 'Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore. ' * 3
CARDS = ''.join(f'<div style="{CARD}">{TEXT}</div>' for _ in range(60))
BOX = 'position:absolute;left:10px;top:10px;width:20px;height:20px;background:{}'
LAYER = f'position:absolute;right:20px;top:60px;width:300px;height:400px;will-change:transform;{CARD}'
FIXED = f'position:fixed;left:40px;top:80px;width:300px;height:400px;will-change:transform;{CARD}'
PAGE = (f'<body style="margin:0;background:#eef">{CARDS}<div id="box" style="{BOX.format("red")}"></div>'
        f'<div id="layer" style="{LAYER}">{TEXT * 4}</div>'
        f'<div id="fixed" style="{FIXED};display:none">{TEXT * 4}</div></body>')
# Hard-edged content, so a scrolled frame and a full repaint compare exactly.
STRIPES = ''.join(f'<div style="height:37px;border-bottom:3px solid rgb({i * 7 % 256},{i * 13 % 256},{i * 29 % 256});'
                  f'font:16px sans-serif">row {i}</div>' for i in range(120))
STRIPES_FIXED = (f'<div style="position:fixed;left:30px;top:50px;width:200px;height:120px;background:#fff;'
                 f'border:3px solid #208;will-change:transform;font:16px sans-serif">fixed {"text " * 20}</div>')


class Event(C.Structure):
    _fields_ = [('phase', C.c_int32), ('source', C.c_int32), ('start_ns', C.c_uint64),
                ('duration_ns', C.c_uint64), ('sequence', C.c_uint64)]


def run(directory):
    with SvgProbe(directory, WIDTH, HEIGHT) as p:
        P, I = p.pointer, p.integer
        if p.bind('rv_host_set_accelerated_compositing', I, [P, I])(p.host, 1) != 0:
            print('compositor paths: no GPU compositing in this runtime; skipped')
            return
        p.expect(p.bind('rv_host_set_device_scale', I, [P, C.c_float])(p.host, SCALE) == 0, 'device scale')
        set_gpu = p.bind('rv_host_set_gpu_painting', I, [P, I])
        # macOS composites without Skia, so its layers paint on the CPU alone.
        gpu_painting = p.bind('rv_abi_has', I, [C.c_char_p])(b'gpu-painting') == 1
        p.expect(p.bind('rv_host_trace_enable', I, [P, I])(p.host, 1) == 0, 'tracing')
        drain = p.bind('rv_host_trace_drain', I, [P, C.POINTER(Event), I, C.POINTER(I), C.POINTER(C.c_uint64)])
        update = p.bind('rv_host_update', I, [P])
        paint_rgba = p.bind('rv_host_paint_rgba', I, [P, C.POINTER(C.c_uint8), I])
        scroll_to = p.bind('rv_host_scroll_to', I, [P, I, I])
        insets = p.bind('rv_host_set_obscured_insets', I, [P, C.c_double, C.c_double, C.c_double, C.c_double])
        image = (C.c_uint8 * (WIDTH * SCALE * HEIGHT * SCALE * 4))()

        def phases():
            events, count, dropped = (Event * 256)(), I(-1), C.c_uint64()
            p.expect(drain(p.host, events, 256, C.byref(count), C.byref(dropped)) == 0, 'trace drain')
            return {phase: sum(e.duration_ns for e in events[:count.value] if e.phase == phase) / 1e6
                    for phase in (STYLE_LAYOUT, PAINT, RENDERING_UPDATE)}

        def frame(change=None):
            if change:
                change()
            p.expect(update(p.host) >= 0 and paint_rgba(p.host, image, len(image)) == 0, 'frame')
            return phases()

        def median(change, phase, frames=FRAMES):
            for _ in range(3):
                frame(change)
            return statistics.median(frame(change)[phase] for _ in range(frames))

        def style(node, value):
            p.call('rv_element_set_attribute', [P, C.c_char_p, Utf8], node, b'style', value.encode())

        def full_repaint():
            # Equal insets change nothing on the page but invalidate all of it.
            p.expect(insets(p.host, 0, 0, 0, 0) == 0, 'invalidate the whole viewport')

        report = {}
        for gpu in (0, 1) if gpu_painting else (0,):
            painter = 'GPU' if gpu else 'CPU'
            p.expect(set_gpu(p.host, gpu) == 0, f'{painter} painting')
            p.load(PAGE, standalone=False)
            box, layer, fixed = p.node('box'), p.node('layer'), p.node('fixed')
            frame()
            frame()
            idle = median(None, PAINT)
            p.expect(median(None, RENDERING_UPDATE) < 0.5 and median(None, STYLE_LAYOUT) < 0.5,
                     f'{painter}: an update with nothing invalidated runs no style or layout work')
            full = median(full_repaint, PAINT, 8)
            software = software_gl(directory)
            position = [0]

            def scroll():
                position[0] += 3
                scroll_to(p.host, 0, position[0])
            scrolled = median(scroll, PAINT)
            style(fixed, FIXED)
            frame()
            frame()
            scrolled_fixed = median(scroll, PAINT)
            style(fixed, FIXED + ';display:none')
            scroll_to(p.host, 0, 0)
            frame()
            colors = iter(['red', 'blue'] * FRAMES * 2)
            recolored = median(lambda: style(box, BOX.format(next(colors))), PAINT)
            offsets = iter(range(1, FRAMES * 4))
            moved = median(lambda: style(layer, LAYER + f';transform:translateX(-{next(offsets) % 40}px)'), PAINT)
            report[painter] = dict(idle=idle, full=full, scroll=scrolled, recolor=recolored, move=moved)
            print(f'compositor paths, {painter} painting: PAINT median idle {idle:.2f} ms, full repaint {full:.2f} ms, '
                  f'3px scroll {scrolled:.2f} ms, with a fixed layer {scrolled_fixed:.2f} ms, '
                  f'one element recolored {recolored:.2f} ms, layer moved {moved:.2f} ms')
            # A software renderer spends milliseconds drawing one more layer, which these limits would count as paint.
            if not software:
                p.expect(moved < idle + 0.5, f'{painter}: a layer that only moves is not repainted ({moved:.2f} ms)')
                p.expect(scrolled_fixed < scrolled + 0.5,
                         f'{painter}: a scroll does not repaint a composited fixed layer ({scrolled_fixed:.2f} ms '
                         f'against {scrolled:.2f} ms without it)')
        # The CPU painter shows raster cost undiluted by the GPU painter's fixed per-frame costs, so it carries the
        # ratios; on the GPU painter both stay below a full repaint.
        cpu = report['CPU']
        cpu_raster = cpu['full'] - cpu['idle']
        p.expect(cpu['recolor'] < cpu['idle'] + cpu_raster * 0.1,
                 f'one recolored element repaints itself, not the page ({cpu["recolor"]:.2f} ms)')
        p.expect(cpu['scroll'] < cpu['idle'] + cpu_raster * 0.3,
                 f'a 3px scroll repaints the strip it exposes, not the viewport ({cpu["scroll"]:.2f} ms against '
                 f'{cpu["full"]:.2f} ms for a full repaint)')
        if gpu_painting:
            gpu = report['GPU']
            p.expect(gpu['scroll'] < gpu['full'] and gpu['recolor'] < gpu['full'],
                     'GPU painting: a scroll and a recolor cost less than a full repaint')

        # A frame built by moving pixels equals a full repaint at the same position, on both painters and at a
        # fractional scale, where a move of a whole number of CSS pixels is not a whole number of device pixels.
        for gpu, scale in [(0, SCALE), (1, SCALE), (1, 1.5)] if gpu_painting else [(0, SCALE), (0, 1.5)]:
            p.expect(set_gpu(p.host, gpu) == 0, 'painter')
            p.expect(p.bind('rv_host_set_device_scale', I, [P, C.c_float])(p.host, scale) == 0, 'scale')
            size = int(WIDTH * scale) * int(HEIGHT * scale) * 4
            pixels = (C.c_uint8 * size)()
            p.load(f'<body style="margin:0;background:white">{STRIPES}{STRIPES_FIXED}</body>', standalone=False)

            def take():
                p.expect(update(p.host) >= 0 and paint_rgba(p.host, pixels, size) == 0, 'paint')
                return bytes(pixels)
            take()
            for y in [3, 6, 9, 50, 47, 300, 301, 0]:
                scroll_to(p.host, 0, y)
                scrolled = take()
                full_repaint()
                repainted = take()
                differing = sum(1 for i in range(0, size, 4) if scrolled[i:i + 4] != repainted[i:i + 4])
                p.expect(differing == 0, f'painter {gpu} scale {scale}: the frame scrolled to {y} equals a full '
                                         f'repaint ({differing} pixels differ)')
        phases()
        p.release_all()
        print('compositor paths assertions:', p.assertions)


if __name__ == '__main__':
    run(sys.argv[1])
