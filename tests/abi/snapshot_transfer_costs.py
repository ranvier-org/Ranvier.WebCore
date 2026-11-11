"""Owner and completion latency for equal PNG output, including the worker drain."""
import concurrent.futures
import ctypes as C
import json
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe
from snapshot_options import Options, Completion, options

results = []
for width, height in ((800, 600), (1600, 1200)):
    with SvgProbe(sys.argv[1], width, height) as p, concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        P, I, U = C.c_void_p, C.c_int32, C.c_uint64
        legacy = p.bind('rv_host_snapshot_bounded', I, [P, P, C.POINTER(Options), Completion, P, C.POINTER(U)])
        free_resource = p.bind('rv_resource_release', I, [U])
        capture = p.bind('rv_host_snapshot_pixels', I, [P, P, C.POINTER(Options), C.POINTER(P), C.POINTER(I), C.POINTER(I)])
        encode = p.bind('rv_snapshot_pixels_encode', I, [P, I, C.c_double, C.POINTER(P)])
        release = p.bind('rv_snapshot_pixels_release', None, [P])
        free_encoded = p.bind('rv_encoded_image_release', None, [P])
        callback = Completion(lambda *_: None)
        p.load('<body style="background:linear-gradient(45deg,red,blue)"><h1>Snapshot transfer</h1></body>', standalone=False)

        def worker(handle):
            encoded = P()
            try:
                assert encode(handle, 1, -1, C.byref(encoded)) == 0
            finally:
                free_encoded(encoded)
                release(handle)

        for mode in ('legacy', 'native-cold', 'native-reuse'):
            samples = []
            for iteration in range(12):
                if mode != 'native-reuse':
                    p.update()
                started = time.perf_counter()
                if mode == 'legacy':
                    value, token = options(encoding=1), U()
                    assert legacy(p.host, None, C.byref(value), callback, None, C.byref(token)) == 0
                    captured = time.perf_counter()
                    assert free_resource(token) == 0
                else:
                    value, handle, w, h = options(), P(), I(), I()
                    assert capture(p.host, None, C.byref(value), C.byref(handle), C.byref(w), C.byref(h)) == 0
                    assert (w.value, h.value) == (width, height)
                    captured = time.perf_counter()
                    pool.submit(worker, handle).result(timeout=30)
                completed = time.perf_counter()
                if iteration >= 2:
                    samples.append({'ownerMs': (captured-started)*1000, 'completionMs': (completed-started)*1000})
            results.append({'width': width, 'height': height, 'mode': mode, 'samples': samples,
                            'ownerMedianMs': statistics.median(x['ownerMs'] for x in samples),
                            'completionMedianMs': statistics.median(x['completionMs'] for x in samples)})
print('SNAPSHOT_TRANSFER_COSTS=' + json.dumps(results), flush=True)
