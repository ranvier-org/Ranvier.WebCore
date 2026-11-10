"""Real D3D frame completion, bounded leases, resize and cached input acceptance."""
import ctypes as C
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'abi'))
from svg_paint_probe import SvgProbe
from utf8_inputs import Utf8


def run(directory, helper_path):
    P, I, U = C.c_void_p, C.c_int32, C.c_uint64
    helper = C.CDLL(str(Path(helper_path).resolve()))
    for name, result, params in [
        ('gpu_readback_create', I, [C.POINTER(P)]), ('gpu_readback_destroy', None, [P]),
        ('gpu_readback_rgba', I, [P, P, P, U, C.c_uint32, C.c_uint32]),
        ('native_input_create', I, [P, C.c_uint32, C.c_uint32, I, C.POINTER(P)]),
        ('native_input_publish', I, [P, C.c_float, C.c_float, C.c_float, C.c_float]),
        ('native_input_release', None, [P]), ('native_input_hold', I, [P]), ('native_input_unhold', I, [P]),
        ('native_input_removable', I, [P, C.POINTER(P), C.POINTER(P)]),
        ('native_input_remove', I, [P, P, P]), ('native_input_removal_release', None, [P]),
        ('native_input_device', P, [P])]:
        fn = getattr(helper, name)
        fn.restype, fn.argtypes = result, params
    device = P()
    assert helper.gpu_readback_create(C.byref(device)) == 0
    try:
        with SvgProbe(directory, 64, 64) as p:
            configure = p.bind('rv_host_configure_gpu_pipeline', I, [P, P])
            submit = p.bind('rv_host_submit_gpu_frame', I, [P, U])
            acquire = p.bind('rv_host_try_acquire_completed_gpu_frame', I, [P, C.POINTER(U), C.POINTER(P)])
            release = p.bind('rv_gpu_frame_release', I, [P])
            info = p.bind('rv_gpu_frame_info', I, [P, C.POINTER(P), C.POINTER(I), C.POINTER(I), C.POINTER(I)])
            frames = []

            def take():
                identity, frame = U(999), P(1)
                status = acquire(p.host, C.byref(identity), C.byref(frame))
                if status == 1:
                    p.expect(identity.value == 0 and not frame.value, 'NotReady clears outputs')
                else:
                    p.expect(status == 0 and bool(frame.value), 'completed frame')
                    frames.append(frame)
                return status, identity.value, frame

            def eventually(action):
                deadline = time.monotonic() + 5
                while True:
                    result = action()
                    status = result[0] if isinstance(result, tuple) else result
                    if status != 1:
                        p.expect(status == 0, 'operation succeeds: ' + str(status))
                        return result
                    p.expect(time.monotonic() < deadline, 'bounded readiness retry')
                    time.sleep(0.002)

            def pixels(frame, expected_size):
                texture, width, height, format_ = P(), I(), I(), I()
                p.expect(info(frame, C.byref(texture), C.byref(width), C.byref(height), C.byref(format_)) == 0, 'frame info')
                p.expect((width.value, height.value, format_.value) == (*expected_size, 1), 'physical dimensions and premultiplication')
                data = (C.c_uint8 * (width.value * height.value * 4))()
                p.expect(helper.gpu_readback_rgba(device, texture, data, len(data), width.value, height.value) == 0, 'GPU readback')
                return bytes(data)

            def drop(frame):
                p.expect(release(frame) == 0, 'release lease')
                frames.remove(frame)

            try:
                p.load('<style>html,body{margin:0;background:red}#slot{width:16px;height:16px;will-change:transform}</style><div id="slot"></div>', standalone=False)
                p.call('rv_host_set_accelerated_compositing', [P, I], p.host, 1)
                p.call('rv_host_update', [P], p.host)
                p.expect(configure(p.host, device) == 0, 'configure')
                p.expect(take()[0] == 1, 'empty pipeline')
                wrong = []
                thread = threading.Thread(target=lambda: wrong.append(submit(p.host, 1)))
                thread.start(); thread.join()
                p.expect(wrong == [-2], 'owner thread')
                held = []
                for identity in (1, 2, 3):
                    eventually(lambda: submit(p.host, identity))
                    _, actual, frame = eventually(take)
                    p.expect(actual == identity, 'submission identity')
                    p.expect(pixels(frame, (64, 64))[-4:] == bytes([255, 0, 0, 255]), 'red pixel')
                    held.append(frame)
                started = time.monotonic()
                for size in range(80, 100):
                    p.call('rv_host_resize', [P, I, I], p.host, size, size)
                    p.expect(submit(p.host, 4) == 1, 'held generations cannot grow pool')
                p.expect(time.monotonic() - started < 0.2, 'held consumers cause no positive-time wait')
                drop(held[0])
                p.call('rv_host_resize', [P, I, I], p.host, 80, 60)
                p.call('rv_host_set_device_scale', [P, C.c_float], p.host, 1.5)
                eventually(lambda: submit(p.host, 4))
                _, actual, resized = eventually(take)
                p.expect(actual == 4 and pixels(resized, (120, 90))[-4:] == bytes([255, 0, 0, 255]), 'resized generation')
                p.expect(pixels(held[1], (64, 64))[-4:] == bytes([255, 0, 0, 255]), 'old lease remains unchanged')
                drop(held[1]); drop(held[2]); drop(resized)
                p.expect(submit(p.host, 4) == -9, 'duplicate successful ID rejected')
                texture = P()
                p.expect(helper.native_input_create(device, 16, 16, 1, C.byref(texture)) == 0, 'external texture')
                try:
                    p.call('rv_host_bind_d3d11_texture', [P, P, P], p.host, p.node('slot'), texture)
                    p.expect(submit(p.host, 5) == 1, 'unpublished producer is pre-submit NotReady')
                    p.expect(helper.native_input_publish(texture, 0, 1, 0, 1) == 0, 'publish green')
                    eventually(lambda: submit(p.host, 5))
                    _, _, frame = eventually(take)
                    p.expect(pixels(frame, (120, 90))[:4] == bytes([0, 255, 0, 255]), 'input green')
                    drop(frame)
                    p.expect(helper.native_input_hold(texture) == 0, 'delay external producer')
                    try:
                        p.call('rv_element_set_attribute', [P, C.c_char_p, Utf8], p.node('slot'), b'style', b'transform:translateX(20px)')
                        p.call('rv_host_update', [P], p.host)
                        eventually(lambda: submit(p.host, 6))
                        _, _, frame = eventually(take)
                        image = pixels(frame, (120, 90))
                        offset = (10 * 120 + 40) * 4
                        p.expect(image[offset:offset + 4] == bytes([0, 255, 0, 255]),
                                 'busy producer retains completed cache while DOM moves: ' + str(list(image[offset:offset + 4])))
                        drop(frame)
                    finally:
                        p.expect(helper.native_input_unhold(texture) == 0, 'release delayed producer')
                    p.call('rv_host_bind_d3d11_texture', [P, P, P], p.host, p.node('slot'), None)
                finally:
                    helper.native_input_release(texture)
                removable, removal = P(), P()
                p.expect(helper.native_input_removable(device, C.byref(removable), C.byref(removal)) == 0, 'owned removable device')
                removed_device = helper.native_input_device(removable)
                try:
                    eventually(lambda: configure(p.host, removed_device))
                    eventually(lambda: submit(p.host, 7))
                    _, _, removed_frame = eventually(take)
                    reasons = (I * 4)()
                    p.expect(helper.native_input_remove(removal, removable, reasons) == 0 and reasons[2] < 0 and reasons[3] < 0, 'actual device removal')
                    p.expect(submit(p.host, 8) == -12, 'removed consumer is distinct from congestion')
                    identity, frame = U(999), P(1)
                    p.expect(acquire(p.host, C.byref(identity), C.byref(frame)) == -12 and not frame.value and identity.value == 0, 'device-loss output clearing')
                    p.expect(release(removed_frame) in (0, -5), 'lost frame retirement consumes lease')
                    frames.remove(removed_frame)
                    eventually(lambda: configure(p.host, device))
                finally:
                    helper.gpu_readback_destroy(removed_device)
                    helper.native_input_release(removable)
                    helper.native_input_removal_release(removal)
                eventually(lambda: submit(p.host, 8))
                p.load('<style>html,body{margin:0;background:red}</style>', standalone=False)
                p.call('rv_host_update', [P], p.host)
                p.expect(take()[0] == 1, 'old document completion is never leased')
                eventually(lambda: submit(p.host, 9))
                _, _, retained = eventually(take)
                p.release_all()
                p.dispose_host()
                p.expect(pixels(retained, (120, 90))[-4:] == bytes([255, 0, 0, 255]), 'frame survives host teardown')
                drop(retained)
            finally:
                for frame in frames:
                    release(frame)
            print('GPU pipeline assertions:', p.assertions)
    finally:
        helper.gpu_readback_destroy(device)


if __name__ == '__main__':
    run(sys.argv[1], sys.argv[2])
