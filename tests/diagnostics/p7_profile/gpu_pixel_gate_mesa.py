"""Independent narrow rectilinear GPU sampling contract for the two promoted clip controls."""
import argparse
import base64
from collections import Counter
import hashlib
import json
import math
import sys
from fractions import Fraction
from pathlib import Path
import zlib

import numpy as np

ROOT = Path(__file__).parent
sys.path.insert(0,str(ROOT))

from mesa_filter_model import expectation


def validate(actual, expected):
    low, high, pink, _ = expected
    assert actual.shape == (*low.shape, 4)
    valid = ((actual[:, :, 3] == 255) & (actual[:, :, 1] == actual[:, :, 2])
             & (actual[:, :, 1] >= low) & (actual[:, :, 1] <= high)
             & np.where(pink, actual[:, :, 0] == 255, actual[:, :, 0] == actual[:, :, 1]))
    return valid


def allowed_catalogue(expected):
    low, high, pink, _ = expected
    groups = Counter(zip(pink.flat, low.flat, high.flat))
    return [{'kind': 'red-white' if kind else 'black-white', 'minimum': int(lo), 'maximum': int(hi), 'pixels': int(count),
             'allowedRgba': [[255 if kind else value, value, value, 255] for value in range(int(lo), int(hi) + 1)]}
            for (kind, lo, hi), count in sorted(groups.items())]


def coordinates(expected):
    low, high, pink, _ = expected
    rows = []
    for y in range(low.shape[0]):
        changes = np.where((low[y, 1:] != low[y, :-1]) | (high[y, 1:] != high[y, :-1]) | (pink[y, 1:] != pink[y, :-1]))[0] + 1
        starts, ends = [0, *map(int, changes)], [*map(int, changes), low.shape[1]]
        rows.append([y, [[start, end, int(pink[y, start]), int(low[y, start]), int(high[y, start])] for start, end in zip(starts, ends)]])
    assert sum(end-start for _, runs in rows for start,end,_,_,_ in runs) == low.size
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inputs', type=Path, default=ROOT / 'linux-model-inputs.json')
    parser.add_argument('--capture', type=Path, default=ROOT / 'linux-profile/plain-capture.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'gpu-pixel-gate-mesa.json')
    parser.add_argument('--mutation', choices=['shift', 'erase', 'recolor', 'bleed', 'solid-lsb', 'pink-to-red', 'edge-channel', 'filter-low-bound', 'filter-high-bound'])
    args = parser.parse_args()
    inputs = json.loads(args.inputs.read_text())
    fixture_path = ROOT / 'cases.json'
    assert hashlib.sha256(fixture_path.read_bytes()).hexdigest() == inputs['casesSha256']
    fixture = json.loads(fixture_path.read_text())
    assert fixture['scales'] == [1, 1.5, 2]
    expectations = {scale: expectation(scale, inputs) for scale in (1.5, 2)}
    capture_rows = json.loads(args.capture.read_text())['results']
    capture = {(r['name'], r['scale']): r for r in capture_rows}
    assert len(capture_rows) == len(capture) == 54
    assert set(capture) == {(row['name'], scale) for row in fixture['cases'] for scale in fixture['scales']}
    reports = []
    for scale, expected in expectations.items():
        row = capture[('composited-translate', scale)]
        data = zlib.decompress(base64.b64decode(row['rgbaZlibBase64']))
        assert hashlib.sha256(data).hexdigest() == row['rgbaSha256']
        actual = np.frombuffer(data, np.uint8).reshape(row['height'], row['width'], 4).copy()
        low, high, pink, proof = expected
        red = np.argwhere(pink & (low == 0) & (high == 0))
        y, x = map(int, red[len(red)//2])
        edge = np.argwhere(pink & (low > 5) & (high < 250))
        ey, ex = map(int, edge[len(edge)//2])
        if args.mutation == 'shift':
            moved = np.full_like(actual, 255)
            moved[:, 1:] = actual[:, :-1]
            actual = moved
        elif args.mutation == 'erase': actual[y, x] = [255,255,255,255]
        elif args.mutation == 'recolor': actual[y, x] = [0,255,0,255]
        elif args.mutation == 'bleed': actual[0, 0] = [255,0,0,255]
        elif args.mutation == 'solid-lsb': actual[y, x] = [255,1,1,255]
        elif args.mutation == 'pink-to-red': actual[ey, ex] = [255,0,0,255]
        elif args.mutation in ['filter-low-bound','filter-high-bound']:
            candidates=np.argwhere((low>1)&(high<254))
            by,bx=map(int,candidates[len(candidates)//2])
            value=int(low[by,bx])-1 if args.mutation=='filter-low-bound' else int(high[by,bx])+1
            actual[by,bx]=[255 if pink[by,bx] else value,value,value,255]
        elif args.mutation == 'edge-channel': actual[ey, ex, 2] = (int(actual[ey, ex, 1]) + 1) % 256
        valid = validate(actual, expected)
        bad = np.argwhere(~valid)
        report = {**proof, 'result': 'PASS' if valid.all() else 'FAIL', 'checkedPixels': int(valid.size), 'failures': len(bad),
                  'allFailures': [{'x':int(x),'y':int(y),'actual':actual[y,x].tolist(),'kind':'red-white' if pink[y,x] else 'black-white',
                     'allowedRgba': [[255 if pink[y,x] else value,value,value,255] for value in range(int(low[y,x]),int(high[y,x])+1)]} for y,x in bad],
                  'allowedValueCatalogue': allowed_catalogue(expected)}
        reports.append(report)
        if not args.mutation:
            (args.output.parent / (args.output.stem + '-allowance-' + str(scale) + '.json')).write_text(json.dumps({'format':1,'runFields':['xStart','xEndExclusive','redWhiteKind','minimumGreenBlue','maximumGreenBlue'], 'rows':coordinates(expected)},separators=(',',':')),encoding='utf-8')
    result = {'scope': 'ONLY2 actual promoted GPU controls; original12strict+52unaffectedcomparisons unchanged; original2casepointwiseRED preserved',
              'result':'PASS' if all(row['result']=='PASS' for row in reports) else 'FAIL','mutation':args.mutation,
              'expectedGeneratedBeforeCaptureLoad':True,'pixelGoldenInputs':False,'cases':reports}
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'result':result['result'],'mutation':args.mutation,'checkedPixels':sum(row['checkedPixels'] for row in reports),'failures':sum(row['failures'] for row in reports)}))
    raise SystemExit(0 if result['result']=='PASS' else 1)


if __name__ == '__main__':
    main()
