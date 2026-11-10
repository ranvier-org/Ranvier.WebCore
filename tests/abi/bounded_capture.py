"""Reject oversized opt-in captures before buffer allocation or rasterization."""
import ctypes as C
import sys
from svg_paint_probe import SvgProbe
from snapshot_options import Options, Completion, options
from host_tracing import Event

with SvgProbe(sys.argv[1], 4096, 4096) as p:
    P, I, U = C.c_void_p, C.c_int32, C.c_uint64
    snapshot = p.bind('rv_host_snapshot_bounded', I, [P, P, C.POINTER(Options), Completion, P, C.POINTER(U)])
    release = p.bind('rv_resource_release', I, [U])
    drain = p.bind('rv_host_trace_drain', I, [P, C.POINTER(Event), I, C.POINTER(I), C.POINTER(U)])
    p.load('<div id="large" style="position:absolute;width:9000px;height:2px;background:red"></div>', standalone=False)
    element = p.node('large')
    p.call('rv_host_trace_enable', [P, I], p.host, 1)
    callback = Completion(lambda *_: None)

    def phases():
        events, count, dropped = (Event * 256)(), I(), U()
        assert drain(p.host, events, 256, C.byref(count), C.byref(dropped)) == 0 and not dropped.value
        return {event.phase for event in events[:count.value]}

    for subject, value in [(None, options(scale=2)), (element, options()),
                           (element, options(crop=1, width=8193, height=1)),
                           (None, options(scale=1.0001))]:
        token = U(123)
        assert snapshot(p.host, subject, C.byref(value), callback, None, C.byref(token)) == -9
        assert token.value == 123
        assert not ({6, 7, 9} & phases()), 'no allocation, raster or pixel copies before rejection'

    # Bounds apply after crop, with the explicit scale overriding the host DPR.
    for subject, value in [(None, options(crop=1, width=4, height=3, scale=2)),
                           (element, options(crop=1, width=8192, height=1)),
                           (element, options(crop=1, width=64, height=1, scale=.25))]:
        token = U()
        assert snapshot(p.host, subject, C.byref(value), callback, None, C.byref(token)) == 0
        assert release(token) == 0
        assert {6, 7, 9}.issubset(phases())
    p.call('rv_host_set_device_scale', [P, C.c_float], p.host, 2.0)
    token = U(123)
    value = options()
    assert snapshot(p.host, None, C.byref(value), callback, None, C.byref(token)) == -9
    assert not ({6, 7, 9} & phases())
    print('BOUNDED_CAPTURE=PASS', flush=True)
