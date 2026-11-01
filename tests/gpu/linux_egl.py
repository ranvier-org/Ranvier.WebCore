"""Strict native EGLImage transport acceptance; run with LIBGL_ALWAYS_SOFTWARE=1."""
import argparse
import ctypes as C
import json
import threading

parser = argparse.ArgumentParser()
parser.add_argument("runtime")
args = parser.parse_args()
runtime = C.CDLL(args.runtime)
assert hasattr(runtime, "rv_configure_egl_display"), "Linux EGL display configuration is missing"
assert hasattr(runtime, "rv_host_acquire_egl_frame"), "Linux EGL frame transport is missing"

ptr, integer, uint = C.c_void_p, C.c_int, C.c_uint
egl = C.CDLL("libEGL.so.1")
gl = C.CDLL("libGLESv2.so.2")

def bind(library, name, result, *parameters):
    function = getattr(library, name)
    function.restype = result
    function.argtypes = parameters
    return function

get_display = bind(egl, "eglGetDisplay", ptr, ptr)
initialize = bind(egl, "eglInitialize", uint, ptr, ptr, ptr)
choose = bind(egl, "eglChooseConfig", uint, ptr, C.POINTER(integer), C.POINTER(ptr), integer, C.POINTER(integer))
create_context = bind(egl, "eglCreateContext", ptr, ptr, ptr, ptr, C.POINTER(integer))
make_current = bind(egl, "eglMakeCurrent", uint, ptr, ptr, ptr, ptr)
get_proc = bind(egl, "eglGetProcAddress", ptr, C.c_char_p)
display = get_display(None)
assert initialize(display, None, None), "Mesa display initialization failed"
assert bind(egl, "eglBindAPI", uint, uint)(0x30A0)
attrs = (integer * 11)(0x3033, 1, 0x3040, 4, 0x3024, 8, 0x3023, 8, 0x3022, 8, 0x3038)
config, count = ptr(), integer()
assert choose(display, attrs, C.byref(config), 1, C.byref(count)) and count.value
context = create_context(display, config, None, (integer * 3)(0x3098, 2, 0x3038))
assert context and make_current(display, None, None, context)
configure = bind(runtime, "rv_configure_egl_display", integer, ptr)
assert configure(None) == -1
assert configure(display) == 0
create = bind(runtime, "rv_host_create", ptr, integer, integer)
destroy = bind(runtime, "rv_host_destroy", None, ptr)
load = bind(runtime, "rv_host_load_html", integer, ptr, C.c_char_p, integer)
update = bind(runtime, "rv_host_update", integer, ptr)
resize = bind(runtime, "rv_host_resize", integer, ptr, integer, integer)
mode = bind(runtime, "rv_host_set_accelerated_compositing", integer, ptr, integer)
acquire = bind(runtime, "rv_host_acquire_egl_frame", integer, ptr, C.POINTER(ptr))
info = bind(runtime, "rv_gpu_frame_info", integer, ptr, C.POINTER(ptr), C.POINTER(integer), C.POINTER(integer), C.POINTER(integer))
release = bind(runtime, "rv_gpu_frame_release", integer, ptr)
gen_texture = bind(gl, "glGenTextures", None, integer, C.POINTER(uint))
bind_texture = bind(gl, "glBindTexture", None, uint, uint)
gen_fbo = bind(gl, "glGenFramebuffers", None, integer, C.POINTER(uint))
bind_fbo = bind(gl, "glBindFramebuffer", None, uint, uint)
attach = bind(gl, "glFramebufferTexture2D", None, uint, uint, uint, uint, integer)
read = bind(gl, "glReadPixels", None, integer, integer, integer, integer, uint, uint, ptr)
image_target = C.CFUNCTYPE(None, uint, ptr)(get_proc(b"glEGLImageTargetTexture2DOES"))
host = create(80, 60)
assert host
assert configure(display) == -9, "display selection is frozen once a host exists"
assert mode(host, 1) == 0, "strict compositor must be supported"
html = b"<style>html,body{margin:0;background:rgb(17,34,51)}div{width:30px;height:20px;background:rgb(221,17,34);transform:translate3d(7px,9px,0)}</style><div></div>"
assert load(host, html, len(html)) == 0
assert update(host) == 0
assert make_current(display, None, None, context)
frame = ptr()
assert acquire(None, C.byref(frame)) == -1 and not frame
assert acquire(host, None) == -1
assert acquire(host, C.byref(frame)) == 0 and frame
assert bind(egl, "eglGetCurrentContext", ptr)() == context
second = ptr(1)
assert acquire(host, C.byref(second)) == -9 and not second, "outstanding frame must not be overwritten"
image, width, height, format_ = ptr(), integer(), integer(), integer()
assert info(frame, C.byref(image), C.byref(width), C.byref(height), C.byref(format_)) == 0
assert image and (width.value, height.value, format_.value) == (80, 60, 1)
wrong_thread = []
worker = threading.Thread(target=lambda: wrong_thread.append(release(frame)))
worker.start()
worker.join()
assert wrong_thread == [-2]
second_host = create(32, 24)
assert second_host and mode(second_host, 1) == 0
assert load(second_host, html, len(html)) == 0 and update(second_host) == 0
assert make_current(display, None, None, context)
second_frame = ptr()
assert acquire(second_host, C.byref(second_frame)) == 0 and second_frame
assert release(second_frame) == 0
destroy(second_host)
assert make_current(display, None, None, context)
other_context = create_context(display, config, None, (integer * 3)(0x3098, 2, 0x3038))
assert other_context and make_current(display, None, None, other_context)
assert release(frame) == -5, "another context must not release a consumer's outstanding GPU work"
assert make_current(display, None, None, context)
assert resize(host, 96, 72) == 0
destroy(host)
assert make_current(display, None, None, context), "consumer context restored after host destruction"
texture, framebuffer = uint(), uint()
gen_texture(1, C.byref(texture))
bind_texture(0x0DE1, texture)
image_target(0x0DE1, image)
assert bind(gl, "glGetError", uint)() == 0
gen_fbo(1, C.byref(framebuffer))
bind_fbo(0x8D40, framebuffer)
attach(0x8D40, 0x8CE0, 0x0DE1, texture, 0)
assert bind(gl, "glCheckFramebufferStatus", uint, uint)(0x8D40) == 0x8CD5
pixel = (C.c_ubyte * 4)()
read(0, 0, 1, 1, 0x1908, 0x1401, pixel)
assert list(pixel) == [17, 34, 51, 255], list(pixel)
read(10, 12, 1, 1, 0x1908, 0x1401, pixel)
assert list(pixel) == [221, 17, 34, 255], list(pixel)
bind(gl, "glFinish", None)()
bind(gl, "glDeleteFramebuffers", None, integer, C.POINTER(uint))(1, C.byref(framebuffer))
bind(gl, "glDeleteTextures", None, integer, C.POINTER(uint))(1, C.byref(texture))
assert release(frame) == 0
print(json.dumps({"result": "PASS", "transport": "EGLImage", "size": [width.value, height.value], "held_over_resize_and_host_destroy": True}))
