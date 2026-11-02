"""Measure enabled and disabled host trace overhead for settled update calls."""

import ctypes as C
import json
from pathlib import Path
import statistics
import sys
import time

from host_tracing import Event
from svg_paint_probe import SvgProbe


def run(directory):
    with SvgProbe(directory, 64, 64) as p:
        P, I = p.pointer, p.integer
        enable = p.bind('rv_host_trace_enable', I, [P, I])
        drain = p.bind('rv_host_trace_drain', I, [P, C.POINTER(Event), I, C.POINTER(I), C.POINTER(C.c_uint64)])
        update = p.bind('rv_host_update', I, [P])
        p.load('<div style="width:10px">trace</div>', standalone=False)
        for _ in range(20):
            assert update(p.host) == 0
        events, count, dropped = (Event * 256)(), I(), C.c_uint64()
        observations = {'disabled': [], 'enabled': []}
        for iteration in range(10):
            for flag in ([0, 1] if iteration % 2 == 0 else [1, 0]):
                assert enable(p.host, flag) == 0
                elapsed = 0
                for _ in range(4):
                    start = time.perf_counter_ns()
                    for _ in range(100):
                        assert update(p.host) == 0
                    elapsed += time.perf_counter_ns() - start
                    assert drain(p.host, events, 256, C.byref(count), C.byref(dropped)) == 0
                    assert dropped.value == 0
                observations['enabled' if flag else 'disabled'].append(elapsed / 400)
        medians = {name: statistics.median(values) for name, values in observations.items()}
        result = {'scenario':'settled rv_host_update, 10 alternating pairs of 400 calls; drain between 100-call batches is excluded',
                  'nsPerCallMedian':medians, 'enabledMinusDisabledNs':medians['enabled']-medians['disabled'],
                  'samplesNsPerCall':observations}
        print(json.dumps(result, indent=2))
        if len(sys.argv) > 2:
            Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    run(sys.argv[1])
