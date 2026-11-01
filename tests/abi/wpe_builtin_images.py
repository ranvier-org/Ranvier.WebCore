"""Require embedded WPE images and real broken-image pixels across host lifetimes."""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import Native, P, I, U

NAMES = ('missingImage', 'missingImage@2x', 'missingImage@3x', 'panIcon',
         'textAreaResizeCorner', 'textAreaResizeCorner@2x')
WIDTH, HEIGHT = 96, 64
PAGE = b'''<style>html,body{margin:0;background:white}
img{position:absolute;left:8px;top:8px;width:32px;height:32px}</style>
<img src="data:image/png;base64,AA==">'''


def bind(library, name, result, parameters):
    function = getattr(library, name)
    function.restype, function.argtypes = result, parameters
    return function


def resources(native):
    gio, glib = C.CDLL('libgio-2.0.so.0'), C.CDLL('libglib-2.0.so.0')
    lookup = bind(gio, 'g_resources_lookup_data', P, [C.c_char_p, I, P])
    data = bind(glib, 'g_bytes_get_data', P, [P, P])
    size = bind(glib, 'g_bytes_get_size', C.c_size_t, [P])
    unref = bind(glib, 'g_bytes_unref', None, [P])
    result = {}
    for name in NAMES:
        value = lookup(('/org/webkitwpe/resources/images/' + name).encode(), 0, None)
        native.expect(bool(value), 'embedded WPE image missing: ' + name)
        try:
            content = C.string_at(data(value, None), size(value))
            native.expect(content.startswith(b'\x89PNG\r\n\x1a\n'), name + ' is not a PNG')
            result[name] = {'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
        finally:
            unref(value)
    return result


def gpu_pixels(native, consumer, host, destroy_host):
    consumer.activate()
    frame, texture, framebuffer = P(), U(), U()
    native.ok('rv_host_acquire_egl_frame', [P, P], host, C.byref(frame))
    native.expect(bool(frame.value), 'strict EGL acquisition returned no frame')
    try:
        image, width, height, format_ = P(), I(), I(), I()
        native.ok('rv_gpu_frame_info', [P, P, P, P, P], frame,
                  C.byref(image), C.byref(width), C.byref(height), C.byref(format_))
        native.expect(bool(image.value) and (width.value, height.value, format_.value) == (WIDTH, HEIGHT, 1),
                      'RGBA EGLImage dimensions and format')
        if destroy_host:
            destroy_host()
        consumer.activate()
        bind(consumer.gl, 'glGenTextures', None, [I, P])(1, C.byref(texture))
        bind(consumer.gl, 'glBindTexture', None, [U, U])(0x0DE1, texture)
        consumer.target(0x0DE1, image)
        native.expect(bind(consumer.gl, 'glGetError', U, [])() == 0, 'EGLImage import')
        bind(consumer.gl, 'glGenFramebuffers', None, [I, P])(1, C.byref(framebuffer))
        bind(consumer.gl, 'glBindFramebuffer', None, [U, U])(0x8D40, framebuffer)
        bind(consumer.gl, 'glFramebufferTexture2D', None, [U, U, U, U, I])(0x8D40, 0x8CE0, 0x0DE1, texture, 0)
        native.expect(bind(consumer.gl, 'glCheckFramebufferStatus', U, [U])(0x8D40) == 0x8CD5, 'import framebuffer')
        pixels = (C.c_ubyte * (WIDTH * HEIGHT * 4))()
        bind(consumer.gl, 'glReadPixels', None, [I, I, I, I, U, U, P])(0, 0, WIDTH, HEIGHT, 0x1908, 0x1401, pixels)
        native.expect(bind(consumer.gl, 'glGetError', U, [])() == 0, 'imported pixels')
        return bytes(pixels)
    finally:
        consumer.activate()
        bind(consumer.gl, 'glFinish', None, [])()
        bind(consumer.gl, 'glDeleteFramebuffers', None, [I, P])(1, C.byref(framebuffer))
        bind(consumer.gl, 'glDeleteTextures', None, [I, P])(1, C.byref(texture))
        native.ok('rv_gpu_frame_release', [P], frame)


def run(directory, gpu):
    native = Native(directory)
    embedded = resources(native)
    consumer = None
    if gpu:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'gpu'))
        from linux_view_transition_pixels import Consumer
        consumer = Consumer(native)
    counts = []
    for cycle in range(3):
        host = native.bind('rv_host_create', P, [I, I])(WIDTH, HEIGHT)
        native.expect(bool(host), 'host creation')
        def destroy_current():
            nonlocal host
            value, host = host, None
            native.bind('rv_host_destroy', None, [P])(value)
        try:
            native.ok('rv_host_set_accelerated_compositing', [P, I], host, 1 if gpu else 0)
            for replacement in range(2):
                native.ok('rv_host_load_html', [P, C.c_char_p, I], host, PAGE, len(PAGE))
                for _ in range(10):
                    native.ok('rv_host_update', [P], host)
                    native.call('rv_run_loop_cycle', [I], 1)
                if gpu:
                    raw = gpu_pixels(native, consumer, host, destroy_current if replacement == 1 else None)
                else:
                    pixels = (C.c_ubyte * (WIDTH * HEIGHT * 4))()
                    native.ok('rv_host_paint_rgba', [P, P, I], host, pixels, len(pixels))
                    raw = bytes(pixels)
                nonwhite = sum(raw[(y * WIDTH + x) * 4:(y * WIDTH + x) * 4 + 4] != b'\xff\xff\xff\xff'
                               for y in range(10, 38) for x in range(10, 38))
                native.expect(nonwhite > 0, 'broken-image icon interior is empty')
                counts.append(nonwhite)
        finally:
            if host:
                native.bind('rv_host_destroy', None, [P])(host)
        native.expect(resources(native) == embedded, 'image bundle survives host/document teardown')
    return {'result': 'PASS', 'assertions': native.assertions, 'resources': embedded,
            'host_cycles': 3, 'document_frames': len(counts), 'icon_inner_nonwhite_pixels': counts,
            'transport': 'EGLImage' if gpu else 'CPU paint', 'cpu_paint_api_calls': 0 if gpu else len(counts),
            'held_after_host_destroy': gpu}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--gpu', action='store_true')
    parser.add_argument('--report')
    args = parser.parse_args()
    result = run(args.native_directory, args.gpu)
    if args.report:
        Path(args.report).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)
