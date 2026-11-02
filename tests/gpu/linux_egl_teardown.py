"""Exercise reentrant host destruction during a real EGL acquisition."""
import ctypes as C
import sys

runtime = C.CDLL(sys.argv[1])
egl = C.CDLL('libEGL.so.1')
P, I, U = C.c_void_p, C.c_int, C.c_uint

def bind(lib, name, result, *args):
    f = getattr(lib, name)
    f.restype, f.argtypes = result, args
    return f

display = bind(egl, 'eglGetDisplay', P, P)(None)
assert bind(egl, 'eglInitialize', U, P, P, P)(display, None, None)
assert bind(egl, 'eglBindAPI', U, U)(0x30A0)
attrs = (I * 11)(0x3033, 1, 0x3040, 4, 0x3024, 8, 0x3023, 8, 0x3022, 8, 0x3038)
config, count = P(), I()
assert bind(egl, 'eglChooseConfig', U, P, C.POINTER(I), C.POINTER(P), I, C.POINTER(I))(display, attrs, C.byref(config), 1, C.byref(count)) and count.value
context = bind(egl, 'eglCreateContext', P, P, P, P, C.POINTER(I))(display, config, None, (I * 3)(0x3098, 2, 0x3038))
wrong_context = '--wrong-context' in sys.argv
other_context = bind(egl, 'eglCreateContext', P, P, P, P, C.POINTER(I))(display, config, None, (I * 3)(0x3098, 2, 0x3038)) if wrong_context else None
make_current = bind(egl, 'eglMakeCurrent', U, P, P, P, P)
assert context and make_current(display, None, None, context)
assert bind(runtime, 'rv_configure_egl_display', I, P)(display) == 0
create = bind(runtime, 'rv_host_create', P, I, I)
destroy = bind(runtime, 'rv_host_destroy', None, P)
load = bind(runtime, 'rv_host_load_html', I, P, C.c_char_p, I)
mode = bind(runtime, 'rv_host_set_accelerated_compositing', I, P, I)
update = bind(runtime, 'rv_host_update', I, P)
acquire = bind(runtime, 'rv_host_acquire_egl_frame', I, P, C.POINTER(P))
release = bind(runtime, 'rv_gpu_frame_release', I, P)
callback_type = C.CFUNCTYPE(None, P)
set_callback = bind(runtime, 'rv_host_set_frame_callback', I, P, callback_type, P)
host = create(64, 64)
assert host and mode(host, 1) == 0
html = b'<style>@keyframes a{from{transform:translateX(0)}to{transform:translateX(10px)}}div{animation:a 1s infinite;will-change:transform}</style><div>x</div>'
assert load(host, html, len(html)) == 0
armed, calls, callback_context = [False], [], []
frame, image = P(), P()

@callback_type
def on_frame(_):
    if armed[0]:
        calls.append('destroy')
        callback_context.append(bind(egl, 'eglGetCurrentContext', P)())
        if wrong_context:
            width, height, format_ = I(), I(), I()
            info = bind(runtime, 'rv_gpu_frame_info', I, P, C.POINTER(P), C.POINTER(I), C.POINTER(I), C.POINTER(I))
            assert frame and info(frame, C.byref(image), C.byref(width), C.byref(height), C.byref(format_)) == 0
            assert other_context and make_current(display, None, None, other_context)
        destroy(host)

assert set_callback(host, on_frame, None) == 0 and update(host) == 0
armed[0] = True
assert make_current(display, None, None, context)
assert acquire(host, C.byref(frame)) == -10 and not frame
assert calls == ['destroy']
if wrong_context:
    get_proc = bind(egl, 'eglGetProcAddress', P, C.c_char_p)
    destroy_image = C.CFUNCTYPE(U, P, P)(get_proc(b'eglDestroyImageKHR'))
    assert image and not destroy_image(display, image), 'unexposed image must have been destroyed after release failure'
else:
    assert callback_context == [context], 'consumer context must be current before frame delivery and teardown'
    assert bind(egl, 'eglGetCurrentContext', P)() == context
print('EGL reentrant acquisition teardown: PASS')
