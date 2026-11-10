"""Detached pixel encoding on foreign threads, independent of host/document lifetime."""
import concurrent.futures
import ctypes as C
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe
from snapshot_options import png_pixels, jpeg_size

with SvgProbe(sys.argv[1], 8, 8) as p:
    P, I, L = C.c_void_p, C.c_int32, C.c_int64
    encode = p.bind('rv_image_encode_rgba', I, [P, L, I, I, I, I, C.c_double, C.POINTER(P)])
    read = p.bind('rv_encoded_image_bytes', I, [P, P, L, C.POINTER(L)])
    release = p.bind('rv_encoded_image_release', None, [P])
    assert p.bind('rv_abi_has', I, [C.c_char_p])(b'detached-image-encoding-v1') == 1
    pixels = bytes([255, 0, 0, 255, 0, 128, 255, 128] * 16)
    raw = C.create_string_buffer(pixels)
    result = P(1)
    assert encode(None, len(pixels), 8, 4, 0, 1, -1, C.byref(result)) == -1 and not result.value
    assert encode(raw, len(pixels) - 1, 8, 4, 0, 1, -1, C.byref(result)) == -9 and not result.value
    assert encode(raw, len(pixels), 8, 4, 99, 1, -1, C.byref(result)) == -9 and not result.value
    assert encode(raw, len(pixels), 8, 4, 0, 99, -1, C.byref(result)) == -9 and not result.value
    fact = p.bind('rv_host_capability_fact', I, [P, I, C.c_char_p, I, C.POINTER(I)])
    supported = {}
    for encoding, name in ((1, b'image-encoding-png'), (2, b'image-encoding-jpeg'), (3, b'image-encoding-webp')):
        value = I()
        assert fact(p.host, 4, name, 1, C.byref(value)) == 0
        supported[encoding] = value.value == 1
    p.dispose_host()

    def worker(encoding):
        handle = P()
        status = encode(raw, len(pixels), 8, 4, 0, encoding, .8, C.byref(handle))
        if not supported[encoding]:
            assert status == -9 and not handle.value
            return
        assert status == 0
        try:
            length = L()
            assert read(handle, None, 0, C.byref(length)) == -6 and length.value > 0
            output = C.create_string_buffer(length.value)
            assert read(handle, output, len(output), C.byref(length)) == 0
            data = output.raw
            if encoding == 1:
                width, height, decoded = png_pixels(data)
                assert (width, height) == (8, 4)
                assert all(abs(a - b) <= 1 for a, b in zip(decoded, pixels)), 'straight alpha round trip'
            elif encoding == 2:
                assert jpeg_size(data) == (8, 4)
            else:
                assert data[:4] == b'RIFF' and data[8:12] == b'WEBP'
        finally:
            release(handle)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(worker, [1, 2, 3, 1, 2, 3]))
    release(None)
    print('DETACHED_IMAGE_ENCODING=PASS')
