import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np


def json_values(value):
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {key: json_values(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_values(item) for item in value]
    return value


class NumericEvidence:
    def __init__(self, directory):
        self.root = Path(directory)
        self.raw = self.root / 'sampler-grid-raw'
        self.raw.mkdir(exist_ok=True)
        self.report = {'status': 'RUNNING', 'stages': [], 'patterns': []}
        self.arrays = {}

    def save(self, **updates):
        self.report.update(updates)
        destination = self.root / 'sampler-numeric-diagnostic.json'
        temporary = destination.with_suffix('.tmp')
        with temporary.open('w', encoding='utf-8', newline='\n') as stream:
            json.dump(json_values(self.report), stream, indent=2, allow_nan=False)
        os.replace(temporary, destination)

    def pattern(self, bits, taps, ideal):
        self.bits = bits
        source = np.zeros((*taps.shape, 4), dtype=np.uint8)
        source[:, :, 3] = taps * 255
        self.arrays = {'sourceTaps': taps.copy(), 'sourceRgba8': source, 'idealAlpha': ideal.copy()}
        self.current = {'patternBits': bits, 'tapsRowMajorYx': taps.tolist(), 'stages': [],
                        'sourceUpload': {'width': taps.shape[1], 'height': taps.shape[0],
                                         'internalFormat': 'GL_RGBA8', 'format': 'GL_RGBA',
                                         'type': 'GL_UNSIGNED_BYTE'}}
        self.report['patterns'].append(self.current)
        self.flush_raw()

    def flush_raw(self):
        destination = self.raw / f'pattern-{self.bits:02d}.npz'
        temporary = destination.with_suffix('.tmp')
        with temporary.open('wb') as stream:
            np.savez_compressed(stream, **self.arrays)
        os.replace(temporary, destination)
        self.current['raw'] = {'file': str(destination.relative_to(self.root)),
                               'sha256': hashlib.sha256(destination.read_bytes()).hexdigest()}
        self.save()

    def stage(self, name, values, state):
        self.arrays[name + 'Rgba'] = values.copy()
        self.current['stages'].append({'stage': name, 'state': state,
                                      'dtype': str(values.dtype), 'shape': list(values.shape)})
        self.flush_raw()

    def comparison(self, name, reference, actual, error, limit):
        error = np.asarray(error, dtype=np.float64)
        failing = (~np.isfinite(error)) | (error > limit)
        coordinates = np.argwhere(failing)
        finite = np.where(np.isfinite(error), error, np.inf)
        maximum = np.unravel_index(int(np.argmax(finite)), finite.shape)
        positions = [tuple(map(int, maximum)), *[tuple(map(int, row)) for row in coordinates[:31]]]
        positions = list(dict.fromkeys(positions))
        examples = []
        for y, x in positions:
            examples.append({'x': x, 'y': y, 'error': float(error[y, x]),
                             'reference': np.asarray(reference[y, x]).tolist(),
                             'actual': np.asarray(actual[y, x]).tolist(),
                             'idealAlpha': float(self.arrays['idealAlpha'][y, x]),
                             'gridUv': [(x / 256 + .5) / 2, (y / 256 + .5) / 2]})
        summary = {'comparison': name, 'limitUnchanged': limit, 'failures': int(len(coordinates)),
                   'maximumError': float(finite[maximum]), 'samples': examples}
        self.current.setdefault('comparisons', []).append(summary)
        self.arrays[name + 'FailingCoordinatesYx'] = coordinates
        self.flush_raw()
        return summary
