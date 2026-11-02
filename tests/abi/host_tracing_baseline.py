"""Measure the uninstrumented settled update baseline for host tracing."""

import json
from pathlib import Path
import statistics
import sys
import time

from svg_paint_probe import SvgProbe

with SvgProbe(sys.argv[1], 64, 64) as p:
    update = p.bind('rv_host_update', p.integer, [p.pointer])
    p.load('<div style="width:10px">trace</div>', standalone=False)
    for _ in range(20):
        assert update(p.host) == 0
    samples = []
    for _ in range(10):
        elapsed = 0
        for _ in range(4):
            start = time.perf_counter_ns()
            for _ in range(100):
                assert update(p.host) == 0
            elapsed += time.perf_counter_ns() - start
        samples.append(elapsed / 400)
    result = {'scenario':'uninstrumented settled rv_host_update, 10 batches of 400 calls',
              'medianNsPerCall':statistics.median(samples), 'samplesNsPerCall':samples}
    print(json.dumps(result, indent=2))
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + '\n')
