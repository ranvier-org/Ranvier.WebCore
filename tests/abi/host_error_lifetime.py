"""Exercise teardown requested by a real resize observer during a rendering update."""
import ctypes as C
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe

def run(directory):
    with SvgProbe(directory, 64, 64) as p:
        P, I = p.pointer, p.integer
        p.load('<div id="x" style="width:10px;height:10px">x</div>', standalone=False)
        node = p.node('x')
        destroy = p.bind('rv_host_destroy', None, [P])
        update = p.bind('rv_host_update', I, [P])
        resize_type = C.CFUNCTYPE(None, P, P, C.c_double, C.c_double)
        calls = []

        @resize_type
        def destroy_during_update(_context, _target, _width, _height):
            calls.append('destroy')
            destroy(p.host)

        observer = p.bind('rv_host_observe_resize', P, [P, resize_type, P])(p.host, destroy_during_update, None)
        p.expect(bool(observer), 'resize observer')
        p.call('rv_observer_observe', [P, P], observer, node)
        result = update(p.host)
        p.host = None
        p.expect(calls == ['destroy'], 'observer requests host destruction')
        p.expect(result == -10, 'update reports deferred destruction')
        p.bind('rv_observer_release', None, [P])(observer)
        p.release_all()
        print('render teardown assertions:', p.assertions)

def acquire_teardown(directory, helper_path):
    with SvgProbe(directory, 64, 64) as p:
        P, I = p.pointer, p.integer
        helper = C.CDLL(helper_path)
        helper.gpu_readback_create.argtypes, helper.gpu_readback_create.restype = [C.POINTER(P)], I
        helper.gpu_readback_destroy.argtypes = [P]
        device, frame = P(), P()
        p.expect(helper.gpu_readback_create(C.byref(device)) == 0, 'D3D consumer device')
        p.load('<style>@keyframes a{from{transform:translateX(0)}to{transform:translateX(10px)}}div{animation:a 1s infinite;will-change:transform}</style><div>x</div>', standalone=False)
        p.call('rv_host_set_accelerated_compositing', [P, I], p.host, 1)
        destroy = p.bind('rv_host_destroy', None, [P])
        callback_type = C.CFUNCTYPE(None, P)
        armed, calls = [False], []

        @callback_type
        def on_frame(_context):
            if armed[0]:
                calls.append('destroy')
                helper.gpu_readback_destroy(device)
                device.value = None
                destroy(p.host)

        p.call('rv_host_set_frame_callback', [P, callback_type, P], p.host, on_frame, None)
        p.call('rv_host_update', [P], p.host)
        armed[0] = True
        result = p.bind('rv_host_acquire_d3d11_frame', I, [P, P, C.POINTER(P)])(p.host, device, C.byref(frame))
        p.host = None
        p.expect(calls == ['destroy'], 'acquisition callback releases device and requests host destruction')
        p.expect(result == -10 and not frame.value, 'acquisition reports deferred destruction without returning a frame')
        print('acquire teardown assertions:', p.assertions)

if __name__ == '__main__':
    if len(sys.argv) > 2:
        acquire_teardown(sys.argv[1], sys.argv[2])
    else:
        run(sys.argv[1])
