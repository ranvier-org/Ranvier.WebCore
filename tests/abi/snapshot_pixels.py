"""Owned native snapshot pixels survive replacement/close and encode on a worker."""
import concurrent.futures
import ctypes as C
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe
from snapshot_options import Options, options, png_pixels
from host_tracing import Event
from utf8_inputs import Utf8

with SvgProbe(sys.argv[1], 64, 48) as p:
    P, I, L, U = C.c_void_p, C.c_int32, C.c_int64, C.c_uint64
    capture = p.bind('rv_host_snapshot_pixels', I, [P, P, C.POINTER(Options), C.POINTER(P), C.POINTER(I), C.POINTER(I)])
    copy = p.bind('rv_snapshot_pixels_copy', I, [P, P, L, C.POINTER(L)])
    encode = p.bind('rv_snapshot_pixels_encode', I, [P, I, C.c_double, C.POINTER(P)])
    release = p.bind('rv_snapshot_pixels_release', None, [P])
    read_encoded = p.bind('rv_encoded_image_bytes', I, [P, P, L, C.POINTER(L)])
    free_encoded = p.bind('rv_encoded_image_release', None, [P])
    drain = p.bind('rv_host_trace_drain', I, [P, C.POINTER(Event), I, C.POINTER(I), C.POINTER(U)])
    assert p.bind('rv_abi_has', I, [C.c_char_p])(b'snapshot-pixels-v1') == 1

    def take(value=None, subject=None):
        result, width, height = P(), I(), I()
        value = value or options()
        assert capture(p.host, subject, C.byref(value), C.byref(result), C.byref(width), C.byref(height)) == 0
        return result, (width.value, height.value)

    def data(handle):
        length = L()
        assert copy(handle, None, 0, C.byref(length)) == -6
        output = C.create_string_buffer(length.value)
        assert copy(handle, output, len(output), C.byref(length)) == 0
        return output.raw

    def phases():
        events, count, lost = (Event * 256)(), I(), U()
        assert drain(p.host, events, 256, C.byref(count), C.byref(lost)) == 0 and not lost.value
        return [event.phase for event in events[:count.value]]

    p.load('<style>html,body{margin:0;background:red}</style><div id="fill" style="position:absolute;inset:0;background:red"></div>', standalone=False)
    p.call('rv_host_trace_enable', [P, I], p.host, 1)
    first, size = take()
    assert size == (64, 48)
    original = data(first)
    assert original[:4] == bytes([255, 0, 0, 255])
    # Layout may invalidate during the first capture. The stable second capture establishes reuse.
    second, _ = take()
    release(second)
    phases()
    third, _ = take()
    assert data(third) == original
    assert not ({6, 7, 9} & set(phases())), 'stable viewport avoids allocation, raster and pixel conversion'
    release(third)
    fill = p.node('fill')
    p.call('rv_dom_element_set_attribute', [P, Utf8, Utf8], fill, b'style', b'position:absolute;inset:0;background:lime')
    changed, _ = take()
    assert data(changed)[:4] == bytes([0, 255, 0, 255]), 'style mutation invalidates cached pixels'
    release(changed)
    p.update()
    phases()
    updated, _ = take()
    assert 7 in phases(), 'rendering update forces a fresh raster'
    release(updated)
    cropped, cropped_size = take(options(crop=1, width=10, height=12, scale=2))
    assert cropped_size == (20, 24)
    release(cropped)
    p.call('rv_host_resize', [P, I, I], p.host, 80, 50)
    p.call('rv_host_set_device_scale', [P, C.c_float], p.host, 2.)
    resized, resized_size = take()
    assert resized_size == (160, 100), 'resize and default DPR invalidate cached dimensions'
    release(resized)
    p.call('rv_host_resize', [P, I, I], p.host, 64, 48)
    p.call('rv_host_set_device_scale', [P, C.c_float], p.host, 1.)
    p.load('<style>html,body{margin:0}</style><div id="alpha" style="position:absolute;left:5px;top:4px;width:20px;height:12px;background:rgba(0,128,255,.5)"></div>', standalone=False)
    alpha, alpha_size = take(subject=p.node('alpha'))
    assert alpha_size == (20, 12)
    assert all(abs(a-b) <= 1 for a, b in zip(data(alpha)[:4], [0, 128, 255, 128]))
    release(alpha)
    cropped, cropped_size = take(options(crop=1, x=2, y=1, width=10, height=8, scale=2), p.node('alpha'))
    assert cropped_size == (20, 16)
    release(cropped)
    p.load('<style>html,body{margin:0}</style><div id="scroll" style="height:48px;overflow:hidden"><div style="height:48px;background:red"></div><div style="height:48px;background:blue"></div></div>', standalone=False)
    unscrolled, _ = take()
    assert data(unscrolled)[:4] == bytes([255, 0, 0, 255])
    release(unscrolled)
    p.call('rv_dom_element_set_scroll_top', [P, I], p.node('scroll'), 48)
    scrolled, _ = take()
    assert data(scrolled)[:4] == bytes([0, 0, 255, 255]), 'scroll invalidates cached pixels'
    release(scrolled)
    p.load('<style>html,body{margin:0;background:blue}</style>', standalone=False)
    changed, _ = take()
    assert data(changed)[:4] == bytes([0, 0, 255, 255])
    assert data(first) == original, 'retained capture is immutable'
    release(changed)
    bad, width, height = P(1), I(), I()
    invalid = options(scale=99)
    assert capture(p.host, None, C.byref(invalid), C.byref(bad), C.byref(width), C.byref(height)) == -9
    assert not bad.value
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        value = options()
        assert pool.submit(capture, p.host, None, C.byref(value), C.byref(bad), C.byref(width), C.byref(height)).result() == -2
    invalid = options(crop=1, width=8192, height=8192, scale=8)
    p.call('rv_host_resize', [P, I, I], p.host, 4096, 4096)
    assert capture(p.host, None, C.byref(invalid), C.byref(bad), C.byref(width), C.byref(height)) == -9
    assert not bad.value
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        assert all(value == original for value in pool.map(lambda _: data(first), range(4)))
    p.dispose_host()

    def worker():
        encoded = P()
        try:
            assert encode(first, 1, -1, C.byref(encoded)) == 0
            length = L()
            assert read_encoded(encoded, None, 0, C.byref(length)) == -6
            output = C.create_string_buffer(length.value)
            assert read_encoded(encoded, output, len(output), C.byref(length)) == 0
            w, h, pixels = png_pixels(output.raw)
            assert (w, h) == size and bytes(pixels) == original
        finally:
            free_encoded(encoded)
            release(first)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(worker).result()
    release(None)
    print('SNAPSHOT_PIXELS=PASS', flush=True)
