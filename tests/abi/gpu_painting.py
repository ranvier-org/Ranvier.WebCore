"""Composited frames rasterize layer contents on the GPU by default, so a frame that repaints over blurred box-shadows
no longer pays the CPU blur, and rv_host_set_gpu_painting(0) returns to CPU raster with the same picture."""

import ctypes as C
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe
from utf8_inputs import Utf8

# A dashboard at a high-DPI scale, with the Motion app's card shadows, and a translucent panel that moves across the
# cards in the root layer, so every frame repaints a rectangle over several shadows.
WIDTH, HEIGHT, SCALE = 960, 600, 2
FRAMES = 24
PAINT = 3
CARD = ('position:absolute;width:200px;height:150px;border-radius:14px;background:rgb(255,255,255);'
        'box-shadow:0 6px 18px -8px rgba(0,0,0,0.45),0 18px 36px -14px rgba(0,0,0,0.35)')
CARDS = ''.join(f'<div style="{CARD};left:{24 + 232 * (i % 4)}px;top:{24 + 190 * (i // 4)}px"></div>' for i in range(12))
PANEL = 'position:absolute;left:{}px;top:{}px;width:360px;height:280px;background:rgba(40,90,200,0.3)'
PAGE = ('<body style="margin:0;background:rgb(236,239,244)">' + CARDS +
        '<div style="position:absolute;left:60px;top:70px;width:40px;height:30px;background:rgb(255,0,0)"></div>'
        '<div style="position:absolute;left:780px;top:500px;width:40px;height:30px;background:rgb(0,0,255)"></div>'
        f'<div id="m" style="{PANEL.format(0, 0)}"></div>'
        '<div style="position:absolute;left:940px;top:4px;width:8px;height:8px;will-change:transform"></div></body>')
RED, BLUE = (80, 85), (800, 515)


class Event(C.Structure):
    _fields_ = [('phase', C.c_int32), ('source', C.c_int32), ('start_ns', C.c_uint64),
                ('duration_ns', C.c_uint64), ('sequence', C.c_uint64)]


def run(directory):
    with SvgProbe(directory, WIDTH, HEIGHT) as p:
        P, I = p.pointer, p.integer
        has = p.bind('rv_abi_has', I, [C.c_char_p])
        compositing = p.bind('rv_host_set_accelerated_compositing', I, [P, I])
        set_gpu = p.bind('rv_host_set_gpu_painting', I, [P, I])
        gpu = p.bind('rv_host_gpu_painting', I, [P])
        trace = p.bind('rv_host_trace_enable', I, [P, I])
        drain = p.bind('rv_host_trace_drain', I, [P, C.POINTER(Event), I, C.POINTER(I), C.POINTER(C.c_uint64)])
        update = p.bind('rv_host_update', I, [P])
        paint_rgba = p.bind('rv_host_paint_rgba', I, [P, C.POINTER(C.c_uint8), I])
        p.expect(set_gpu(p.host, 2) == -9, 'an unknown value is rejected')
        p.expect(p.bind('rv_host_set_device_scale', I, [P, C.c_float])(p.host, SCALE) == 0, 'device scale')
        width, height = WIDTH * SCALE, HEIGHT * SCALE
        image = (C.c_uint8 * (width * height * 4))()

        def paint():
            p.expect(update(p.host) >= 0 and paint_rgba(p.host, image, len(image)) == 0, 'paint')
            return bytes(image)

        def color(frame, point):
            x, y = point[0] * SCALE, point[1] * SCALE
            return tuple(frame[(y * width + x) * 4:(y * width + x) * 4 + 3])

        if not has(b'gpu-painting'):
            p.expect(gpu(p.host) == 0 and set_gpu(p.host, 1) == -9 and set_gpu(p.host, 0) == 0,
                     'a runtime without GPU painting paints on the CPU and refuses the setting')
            print('gpu painting: no GPU painting in this runtime; assertions:', p.assertions)
            return
        if compositing(p.host, 1) != 0:
            print('gpu painting: no GL context for compositing; skipped')
            return
        p.load(PAGE, standalone=False)
        if gpu(p.host) != 1:
            # The automatic fallback: without a Skia GL context, composited frames keep painting on the CPU.
            p.expect(color(paint(), RED) == (255, 0, 0), 'the CPU fallback paints the page')
            print('gpu painting: Skia GL context unavailable; CPU fallback verified; assertions:', p.assertions)
            return
        panel = p.node('m')

        def take():
            events, count, dropped = (Event * 256)(), I(-1), C.c_uint64()
            p.expect(drain(p.host, events, 256, C.byref(count), C.byref(dropped)) == 0, 'trace drain')
            return list(events[:count.value])

        def frames():
            """The PAINT phase of FRAMES composited frames, each moving the panel over the shadows."""
            paint()
            take()
            durations = []
            for frame in range(FRAMES):
                x, y = 20 + (frame * 53) % 560, 10 + (frame * 31) % 300
                p.call('rv_element_set_attribute', [P, C.c_char_p, Utf8], panel, b'style', PANEL.format(x, y).encode())
                paint()
                durations += [e.duration_ns / 1e6 for e in take() if e.phase == PAINT]
            return durations

        p.expect(trace(p.host, 1) == 0, 'tracing')
        gpu_ms = frames()
        gpu_frame = paint()
        p.expect(set_gpu(p.host, 0) == 0 and gpu(p.host) == 0, 'GPU painting turns off')
        cpu_ms = frames()
        cpu_frame = paint()
        p.expect(set_gpu(p.host, 1) == 0 and gpu(p.host) == 1, 'GPU painting turns back on')
        p.expect(len(gpu_ms) == FRAMES and len(cpu_ms) == FRAMES, 'one PAINT phase a frame')

        def p95(values):
            return sorted(values)[int(len(values) * 0.95)]
        gpu_median, cpu_median = statistics.median(gpu_ms), statistics.median(cpu_ms)
        print(f'gpu painting: PAINT median {gpu_median:.2f} ms on the GPU, {cpu_median:.2f} ms on the CPU; '
              f'p95 {p95(gpu_ms):.2f} / {p95(cpu_ms):.2f} ms ({width}x{height} device pixels, read back each frame)')
        p.expect(gpu_median < cpu_median * 0.6,
                 f'a GPU-painted frame over blurred shadows pays no CPU blur ({gpu_median:.2f} ms vs {cpu_median:.2f} ms)')

        # Both painters draw the same page: channels in order, rows in order, and the picture agrees but for
        # antialiasing and blur rounding.
        for frame, painter in [(gpu_frame, 'GPU'), (cpu_frame, 'CPU')]:
            p.expect(color(frame, RED) == (255, 0, 0), f'{painter}: red is red')
            p.expect(color(frame, BLUE) == (0, 0, 255), f'{painter}: blue is blue, low on the page')
        difference = sum(abs(a - b) for a, b in zip(gpu_frame, cpu_frame)) / len(gpu_frame)
        p.expect(difference < 1.0, f'GPU and CPU frames agree (mean channel difference {difference:.3f})')
        p.expect(compositing(p.host, 2) == 0, 'compositing returns to when-needed')
        p.release_all()
        print('gpu painting assertions:', p.assertions)


if __name__ == '__main__':
    run(sys.argv[1])
