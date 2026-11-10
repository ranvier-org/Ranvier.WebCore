"""Capture phase evidence; durations are observations, never shared-runner latency assertions."""
import ctypes as C
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe
from snapshot_options import Options, Completion, options
from host_tracing import Event

with SvgProbe(sys.argv[1], 960, 540) as p:
    P, I, U, L = C.c_void_p, C.c_int32, C.c_uint64, C.c_int64
    p.load('<body style="background:linear-gradient(45deg,red,blue)"><h1>Snapshot capture</h1></body>', standalone=False)
    snapshot = p.bind('rv_host_snapshot', I, [P, P, C.POINTER(Options), Completion, P, C.POINTER(U)])
    release = p.bind('rv_resource_release', I, [U])
    drain = p.bind('rv_host_trace_drain', I, [P, C.POINTER(Event), I, C.POINTER(I), C.POINTER(U)])
    p.call('rv_host_trace_enable', [P, I], p.host, 1)
    callback = Completion(lambda *_: None)
    samples = []
    for encoding in (0, 1):
        for _ in range(3):
            value = options(encoding=encoding)
            token = U()
            start = time.perf_counter()
            assert snapshot(p.host, None, C.byref(value), callback, None, C.byref(token)) == 0
            elapsed = time.perf_counter() - start
            assert release(token) == 0
            events, count, dropped = (Event * 256)(), I(), U()
            assert drain(p.host, events, 256, C.byref(count), C.byref(dropped)) == 0 and not dropped.value
            phases = {}
            for event in events[:count.value]:
                phases[event.phase] = phases.get(event.phase, 0) + event.duration_ns
            samples.append({'encoding': encoding, 'ownerSeconds': elapsed, 'phaseNs': phases})
    print(json.dumps(samples), flush=True)
    assert all({6, 7, 9}.issubset(sample['phaseNs']) for sample in samples), 'allocation, raster and pixel-copy phases'
    assert all(8 in sample['phaseNs'] for sample in samples if sample['encoding'] == 1), 'encoding phase'
