"""Require opaque edge coverage in native-acquired GPU frames at fractional DPR."""
import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--native-directory', required=True, type=Path)
parser.add_argument('--helper-library', type=Path, help='Windows test-only D3D staging helper')
parser.add_argument('--report', required=True, type=Path)
args = parser.parse_args()
P, I, U = C.c_void_p, C.c_int32, C.c_uint32

def bind(library, name, result, *parameters):
    function = getattr(library, name)
    function.restype, function.argtypes = result, parameters
    return function

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

directory = args.native_directory.resolve()
search = os.add_dll_directory(str(directory)) if sys.platform == 'win32' else None
host_path = directory / ('RanvierWebCoreHost.dll' if sys.platform == 'win32' else 'libRanvierWebCoreHost.so')
runtime = C.CDLL(str(host_path))
before = {p.name: sha(p) for p in directory.iterdir() if p.suffix.lower() in ('.dll', '.so')}
create = bind(runtime, 'rv_host_create', P, I, I)
destroy = bind(runtime, 'rv_host_destroy', None, P)
mode = bind(runtime, 'rv_host_set_accelerated_compositing', I, P, I)
load = bind(runtime, 'rv_host_load_html', I, P, C.c_char_p, I)
scale = bind(runtime, 'rv_host_set_device_scale', I, P, C.c_float)
update = bind(runtime, 'rv_host_update', I, P)
info = bind(runtime, 'rv_gpu_frame_info', I, P, C.POINTER(P), C.POINTER(I), C.POINTER(I), C.POINTER(I))
release = bind(runtime, 'rv_gpu_frame_release', I, P)

class D3DConsumer:
    def __init__(self):
        assert args.helper_library, '--helper-library is required on Windows'
        self.library = C.CDLL(str(args.helper_library.resolve()))
        self.device = P()
        assert bind(self.library, 'gpu_readback_create', I, C.POINTER(P))(C.byref(self.device)) == 0 and self.device
        self.acquire_frame = bind(runtime, 'rv_host_acquire_d3d11_frame', I, P, P, C.POINTER(P))
        self.read_pixels = bind(self.library, 'gpu_readback_rgba', I, P, P, P, C.c_uint64, U, U)

    def acquire(self, host):
        frame = P()
        assert self.acquire_frame(host, self.device, C.byref(frame)) == 0 and frame
        return frame

    def read(self, image, width, height):
        pixels = (C.c_ubyte * (width * height * 4))()
        assert self.read_pixels(self.device, image, pixels, len(pixels), width, height) == 0
        return bytes(pixels)

    def close(self):
        bind(self.library, 'gpu_readback_destroy', None, P)(self.device)

class EGLConsumer:
    def __init__(self):
        self.egl, self.gl = C.CDLL('libEGL.so.1'), C.CDLL('libGLESv2.so.2')
        self.display = bind(self.egl, 'eglGetDisplay', P, P)(None)
        assert bind(self.egl, 'eglInitialize', U, P, P, P)(self.display, None, None)
        assert bind(self.egl, 'eglBindAPI', U, U)(0x30A0)
        config, count = P(), I()
        attributes = (I * 11)(0x3033, 1, 0x3040, 4, 0x3024, 8, 0x3023, 8, 0x3022, 8, 0x3038)
        assert bind(self.egl, 'eglChooseConfig', U, P, P, C.POINTER(P), I, C.POINTER(I))(self.display, attributes, C.byref(config), 1, C.byref(count)) and count.value
        self.context = bind(self.egl, 'eglCreateContext', P, P, P, P, P)(self.display, config, None, (I * 3)(0x3098, 2, 0x3038))
        assert self.context
        self.current()
        assert bind(runtime, 'rv_configure_egl_display', I, P)(self.display) == 0
        self.acquire_frame = bind(runtime, 'rv_host_acquire_egl_frame', I, P, C.POINTER(P))
        address = bind(self.egl, 'eglGetProcAddress', P, C.c_char_p)(b'glEGLImageTargetTexture2DOES')
        assert address
        self.image_target = C.CFUNCTYPE(None, U, P)(address)

    def current(self):
        assert bind(self.egl, 'eglMakeCurrent', U, P, P, P, P)(self.display, None, None, self.context)

    def acquire(self, host):
        self.current()
        frame = P()
        assert self.acquire_frame(host, C.byref(frame)) == 0 and frame
        return frame

    def read(self, image, width, height):
        self.current()
        texture, framebuffer = U(), U()
        bind(self.gl, 'glGenTextures', None, I, C.POINTER(U))(1, C.byref(texture))
        bind(self.gl, 'glBindTexture', None, U, U)(0x0DE1, texture)
        self.image_target(0x0DE1, image)
        bind(self.gl, 'glGenFramebuffers', None, I, C.POINTER(U))(1, C.byref(framebuffer))
        try:
            bind(self.gl, 'glBindFramebuffer', None, U, U)(0x8D40, framebuffer)
            bind(self.gl, 'glFramebufferTexture2D', None, U, U, U, U, I)(0x8D40, 0x8CE0, 0x0DE1, texture, 0)
            assert bind(self.gl, 'glCheckFramebufferStatus', U, U)(0x8D40) == 0x8CD5
            pixels = (C.c_ubyte * (width * height * 4))()
            bind(self.gl, 'glReadPixels', None, I, I, I, I, U, U, P)(0, 0, width, height, 0x1908, 0x1401, pixels)
            assert bind(self.gl, 'glGetError', U)() == 0
            bind(self.gl, 'glFinish', None)()
            return bytes(pixels)
        finally:
            bind(self.gl, 'glDeleteFramebuffers', None, I, C.POINTER(U))(1, C.byref(framebuffer))
            bind(self.gl, 'glDeleteTextures', None, I, C.POINTER(U))(1, C.byref(texture))

    def close(self):
        bind(self.egl, 'eglMakeCurrent', U, P, P, P, P)(self.display, None, None, None)
        bind(self.egl, 'eglDestroyContext', U, P, P)(self.display, self.context)
        bind(self.egl, 'eglTerminate', U, P)(self.display)

assert sys.platform in ('win32', 'linux'), 'This fixture qualifies D3D11 and EGL transports'
consumer = D3DConsumer() if sys.platform == 'win32' else EGLConsumer()
pages = {
    'root': '<style>html,body{margin:0;background:lime}</style>',
    'edge-button': '<div><button style="position:absolute;left:100px;top:100px;width:100px;height:100px;border:0;background:red"></button></div><div><button style="position:absolute;right:0;bottom:0;width:40px;height:40px;border:0;background:lime"></button></div>',
    'offset-layer': '<div style="position:absolute;left:7px;top:9px;right:0;bottom:0;background:lime;transform:translate3d(0,0,0)"></div>',
}
rows, failures = [], []
try:
    for css_width, css_height in ((399, 282), (2051, 1029)):
        for name, html in pages.items():
            for dpr in (1, 1.25, 1.5, 2):
                host, frame = create(css_width, css_height), P()
                assert host
                try:
                    assert mode(host, 1) == 0
                    encoded = html.encode('utf-8')
                    assert load(host, encoded, len(encoded)) == 0
                    assert scale(host, dpr) == 0 and update(host) == 0
                    frame = consumer.acquire(host)
                    image, width, height, format_ = P(), I(), I(), I()
                    assert info(frame, C.byref(image), C.byref(width), C.byref(height), C.byref(format_)) == 0
                    assert image and (width.value, height.value, format_.value) == (int(css_width*dpr), int(css_height*dpr), 1)
                    data = consumer.read(image, width.value, height.value)
                    points = [(width.value-2, height.value-2), (width.value-1, height.value-2), (width.value-2, height.value-1), (width.value-1, height.value-1)]
                    pixels = [list(data[(y*width.value+x)*4:(y*width.value+x)*4+4]) for x,y in points]
                    row = dict(page=name, htmlSha256=hashlib.sha256(encoded).hexdigest(), css=[css_width,css_height], dpr=dpr, frame=[width.value,height.value], points=points, pixels=pixels)
                    rows.append(row)
                    if any(pixel != [0,255,0,255] for pixel in pixels):
                        failures.append(row)
                finally:
                    if frame:
                        assert release(frame) == 0
                    destroy(host)
finally:
    consumer.close()
    after = {p.name: sha(p) for p in directory.iterdir() if p.suffix.lower() in ('.dll', '.so')}
    assert before == after
    args.report.write_text(json.dumps(dict(rows=rows, failures=failures, runtime=before, sourceSha256=sha(Path(__file__)), cpuPaintCalls=0), indent=2))
assert not failures, f'{len(failures)} native GPU fractional coverage cases failed; see {args.report}'
print(f'PASS {len(rows)} GPU edge cases, {len(rows)*4} exact RGBA samples')
