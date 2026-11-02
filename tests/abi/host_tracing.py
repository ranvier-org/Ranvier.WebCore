"""Exercise the host-owned trace buffer against an actual native runtime directory."""

import ctypes as C
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe
from utf8_inputs import Utf8


class Event(C.Structure):
    _fields_ = [('phase', C.c_int32), ('source', C.c_int32), ('start_ns', C.c_uint64),
                ('duration_ns', C.c_uint64), ('sequence', C.c_uint64)]


def run(directory, gpu_helper=None):
    with SvgProbe(directory, 64, 64) as p:
        P, I = p.pointer, p.integer
        enable = p.bind('rv_host_trace_enable', I, [P, I])
        drain = p.bind('rv_host_trace_drain', I, [P, C.POINTER(Event), I, C.POINTER(I), C.POINTER(C.c_uint64)])
        has = p.bind('rv_abi_has', I, [C.c_char_p])
        update = p.bind('rv_host_update', I, [P])
        paint = p.bind('rv_host_paint_rgba', I, [P, C.POINTER(C.c_uint8), I])
        image = (C.c_uint8 * (64 * 64 * 4))()
        p.expect(has(b'host-tracing') == 1, 'feature discovery')

        def take(capacity=256):
            events, count, dropped = (Event * capacity)(), I(-1), C.c_uint64()
            p.expect(drain(p.host, events, capacity, C.byref(count), C.byref(dropped)) == 0, 'drain succeeds')
            return list(events[:count.value]), dropped.value

        p.load('<div id="x" style="width:10px">a</div>', standalone=False)
        p.expect(update(p.host) == 0 and paint(p.host, image, len(image)) == 0, 'disabled frame')
        events, dropped = take()
        p.expect(not events and dropped == 0, 'disabled by default')
        p.expect(enable(p.host, 1) == 0, 'enable')
        node = p.node('x')
        p.call('rv_element_set_attribute', [P, C.c_char_p, Utf8], node, b'style', b'width:30px')
        p.expect(update(p.host) == 0 and paint(p.host, image, len(image)) == 0, 'traced frame')
        events, dropped = take()
        p.expect(dropped == 0 and len(events) >= 3, 'bounded event sequence')
        p.expect({1, 2, 3, 4}.issubset({e.phase for e in events}), 'invalidation, page update, style-layout and paint phases')
        p.expect(all(e.source == 1 and e.start_ns > 0 for e in events), 'native host monotonic provenance')
        p.expect(all(a.sequence < b.sequence for a, b in zip(events, events[1:])), 'event sequence increases')
        style = next(e for e in events if e.phase == 2)
        painted = next(e for e in events if e.phase == 3)
        p.expect(style.start_ns + style.duration_ns <= painted.start_ns, 'style/layout preparation precedes painting')
        if gpu_helper:
            helper = C.CDLL(gpu_helper)
            helper.gpu_readback_create.argtypes, helper.gpu_readback_create.restype = [C.POINTER(P)], I
            helper.gpu_readback_destroy.argtypes, helper.gpu_readback_destroy.restype = [P], None
            device, frame = P(), P()
            p.expect(helper.gpu_readback_create(C.byref(device)) == 0 and device.value, 'D3D device')
            try:
                p.call('rv_host_set_accelerated_compositing', [P, I], p.host, 1)
                p.call('rv_element_set_attribute', [P, C.c_char_p, Utf8], node, b'style', b'width:30px;will-change:transform;transform:translateZ(0)')
                p.expect(update(p.host) == 0, 'GPU rendering update')
                acquire = p.bind('rv_host_acquire_d3d11_frame', I, [P, P, C.POINTER(P)])
                result = acquire(p.host, device, C.byref(frame))
                p.expect(result == 0 and frame.value, 'real GPU frame: status ' + str(result))
                gpu_events, gpu_dropped = take()
                p.expect(gpu_dropped == 0 and {2, 3}.issubset({e.phase for e in gpu_events}), 'GPU style/layout and paint traced')
                p.call('rv_gpu_frame_release', [P], frame)
                frame = P()
                p.call('rv_host_set_accelerated_compositing', [P, I], p.host, 0)
            finally:
                if frame.value:
                    p.call('rv_gpu_frame_release', [P], frame)
                helper.gpu_readback_destroy(device)
        invalid_count, invalid_dropped = I(123), C.c_uint64(456)
        p.expect(drain(p.host, None, -1, C.byref(invalid_count), C.byref(invalid_dropped)) == -9, 'invalid capacity rejected')
        p.expect((invalid_count.value, invalid_dropped.value) == (123, 456), 'invalid drain preserves outputs')
        p.expect(enable(p.host, 2) == -9, 'invalid enable rejected')
        wrong = []
        worker = threading.Thread(target=lambda: wrong.append(enable(p.host, 0)))
        worker.start(); worker.join()
        p.expect(wrong == [-2], 'wrong-thread rejected')
        calls = []
        resize_type = C.CFUNCTYPE(None, P, P, C.c_double, C.c_double)

        @resize_type
        def restart_trace(_context, _target, _width, _height):
            calls.append((enable(p.host, 0), enable(p.host, 1)))

        observe = p.bind('rv_host_observe_resize', P, [P, resize_type, P])
        observer = observe(p.host, restart_trace, None)
        p.expect(bool(observer), 'resize observer')
        try:
            p.call('rv_observer_observe', [P, P], observer, node)
            p.expect(update(p.host) == 0, 'update with trace restart in callback')
            p.expect(calls == [(0, 0)], 'trace can stop and restart in an observer callback')
            restarted, _ = take()
            p.expect(not any(e.phase == 4 for e in restarted), 'old update span is not appended to restarted buffer')
        finally:
            p.bind('rv_observer_release', None, [P])(observer)
        for _ in range(300):
            p.expect(update(p.host) == 0, 'overflow update')
        events, dropped = take()
        p.expect(len(events) == 256 and dropped > 0, 'fixed capacity reports dropped events')
        p.expect(update(p.host) == 0 and update(p.host) == 0, 'prepare partial drain')
        first, _ = take(1)
        rest, _ = take()
        p.expect(len(first) == 1 and len(rest) >= 1 and first[0].sequence < rest[0].sequence, 'partial drain preserves FIFO')
        p.expect(enable(p.host, 0) == 0, 'disable')
        p.expect(update(p.host) == 0, 'disabled update')
        events, dropped = take()
        p.expect(not events and dropped == 0, 'disable clears and stops collection')
        p.release_all()
        stale = p.host
        p.dispose_host()
        p.expect(enable(stale, 1) == -10, 'destroyed host rejected')
        print('host tracing assertions:', p.assertions)


if __name__ == '__main__':
    run(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
