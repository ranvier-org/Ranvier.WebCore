"""Independent narrow rectilinear GPU sampling contract for the two promoted clip controls."""
import argparse
import base64
from collections import Counter
import hashlib
import json
import math
from fractions import Fraction
from pathlib import Path
import sys
import zlib

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from precision_budget import complete_budget, coordinate_envelope

ROOT = Path(__file__).parent
SUBTEXEL_ERROR = 0.6 / 256
UNORM_ERROR = 0.6
FILTER_FORMAT_QUANTUM = 1 / 255
IDENTITY = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


def layout_unit(value):
    return math.trunc(value * 64) / 64


def nearest_rect(rect, scale):
    x, y, width, height = map(np.float32, rect)
    return [math.floor(float(np.float32(v * scale)) + 0.5) for v in [x, y, np.float32(x + width), np.float32(y + height)]]


def axis_coverage(coord, start, end):
    return np.clip(coord - start + 1, 0, 1) - np.clip(coord - end + 1, 0, 1)


def axis_interval(bounds, start, end, extent):
    lo, hi = np.clip(bounds[0], 0, extent - 1), np.clip(bounds[1], 0, extent - 1)
    left, right = axis_coverage(lo, start, end), axis_coverage(hi, start, end)
    lower, upper = np.minimum(left, right), np.maximum(left, right)
    for critical in [start - 1, start, end - 1, end]:
        value = axis_coverage(np.full_like(lo, critical), start, end)
        included = (lo <= critical) & (critical <= hi)
        lower = np.where(included, np.minimum(lower, value), lower)
        upper = np.where(included, np.maximum(upper, value), upper)
    return lower, upper


def rect_interval(u, v, rect, size):
    l, t, r, b = rect
    xlo, xhi = axis_interval(u, l, r, size[0])
    ylo, yhi = axis_interval(v, t, b, size[1])
    return xlo * ylo, xhi * yhi


def expectation(scale, inputs):
    assert scale in (1.5, 2)
    record = next(row for row in inputs['cases'] if row['scale'] == scale)
    assert record['name'] == 'composited-translate' and record['viewportCss'] == [800, 600]
    assert all(inputs['gpu'][key]['precision'] == 23 for key in ['fragmentLowFloat', 'fragmentMediumFloat', 'fragmentHighFloat'])
    assert 'Direct3D11' in inputs['gpu']['renderer']
    snapped_border = float(np.float32(np.floor(np.float32(5 * scale)) / np.float32(scale)))
    border = layout_unit(snapped_border)
    css_size = [100.5 + 2 + 4 + 2 * border, 33.25 + 10 + 6 + 2 * border]
    assert record['resize']['content'] == [100.5, 33.25] and record['resize']['border'] == css_size
    primary_origin = [layout_unit(math.floor(3 * scale) / scale)] * 2
    primary_size = [layout_unit((math.ceil((3 + size) * scale) - math.floor(3 * scale)) / scale) for size in css_size]
    paint_origin = [3 - value for value in primary_origin]
    paint = [*paint_origin, *css_size]
    assert record['paint']['paint'] == paint
    assert record['paint']['ctm'] == [scale, 0, 0, scale, 0, 0]
    precise = [float(np.float32(paint_origin[0] + math.floor(border * scale + .5) / scale + 2)),
               float(np.float32(paint_origin[1] + math.floor(border * scale + .5) / scale + 10)), 100.5, 33.25]
    assert record['paint']['precise'] == precise
    outer = nearest_rect(paint, scale)
    inner = nearest_rect([paint_origin[0] + border, paint_origin[1] + border, css_size[0] - 2 * border, css_size[1] - 2 * border], scale)
    content = nearest_rect(precise, scale)
    quad_size = [float(np.float32(size * scale)) for size in primary_size]
    quad_origin = [(primary_origin[0] + 7.25) * scale, (primary_origin[1] + 11.5) * scale]
    texture_size = [math.ceil(value) for value in quad_size]
    meta = record['promotedTexture']
    assert meta['rect'] == [0, 0, *quad_size] and meta['size'] == meta['allocated'] == texture_size
    assert meta['pattern'] == IDENTITY and meta['opacity'] == [1] and meta['rectilinear'] == [1] and meta['clamp'] == [-1, -1]
    matrix = list(map(float, np.array(meta['matrix'], dtype=np.float32)))
    expected_matrix = IDENTITY.copy()
    expected_matrix[3], expected_matrix[7] = quad_origin
    assert matrix == expected_matrix
    assert all(value * 256 == round(value * 256) for value in [*quad_origin, quad_origin[0] + quad_size[0], quad_origin[1] + quad_size[1]])
    arithmetic_error, arithmetic_proof = complete_budget(inputs, record, quad_origin, quad_size, texture_size)
    width, height = int(800 * scale), int(600 * scale)
    low = np.full((height, width), 255, np.uint8)
    high = low.copy()
    pink = np.zeros((height, width), bool)
    tx, ty = quad_origin
    dw, dh = quad_size
    tw, th = texture_size
    left, top = max(0, math.ceil(tx - .5)), max(0, math.ceil(ty - .5))
    right, bottom = min(width, math.ceil(tx + dw - .5)), min(height, math.ceil(ty + dh - .5))
    u_values = [coordinate_envelope((Fraction(2*x+1,2)-Fraction.from_float(tx))/Fraction.from_float(dw)*tw-Fraction(1,2), arithmetic_error[0]) for x in range(left,right)]
    v_values = [coordinate_envelope((Fraction(2*y+1,2)-Fraction.from_float(ty))/Fraction.from_float(dh)*th-Fraction(1,2), arithmetic_error[1]) for y in range(top,bottom)]
    u_low, v_low = np.meshgrid([value[0] for value in u_values], [value[0] for value in v_values])
    u_high, v_high = np.meshgrid([value[1] for value in u_values], [value[1] for value in v_values])
    u, v = (u_low,u_high), (v_low,v_high)
    outer_lo, outer_hi = rect_interval(u, v, outer, texture_size)
    inner_lo, inner_hi = rect_interval(u, v, inner, texture_size)
    red_lo, red_hi = rect_interval(u, v, content, texture_size)
    black_lo = np.clip(outer_lo - inner_hi, 0, 1)
    black_hi = np.clip(outer_hi - inner_lo, 0, 1)
    assert not np.any((black_hi > 0) & (red_hi > 0)), 'Unexpected mixed red/black filter taps'
    coverage_lo = np.clip(black_lo + red_lo, 0, 1)
    coverage_hi = np.clip(black_hi + red_hi, 0, 1)
    constant = ((coverage_lo == 0) & (coverage_hi == 0)) | ((coverage_lo == 1) & (coverage_hi == 1))
    filter_error = np.where(constant, 0.0, FILTER_FORMAT_QUANTUM)
    lower_float = 255 * (1 - np.clip(coverage_hi + filter_error, 0, 1))
    upper_float = 255 * (1 - np.clip(coverage_lo - filter_error, 0, 1))
    minimum = np.clip(np.ceil(lower_float - UNORM_ERROR), 0, 255).astype(np.uint8)
    maximum = np.clip(np.floor(upper_float + UNORM_ERROR), 0, 255).astype(np.uint8)
    assert np.all(minimum <= maximum)
    low[top:bottom, left:right], high[top:bottom, left:right] = minimum, maximum
    pink[top:bottom, left:right] = red_hi > 0
    proof = {'scale': scale, 'pixels': width * height, 'cssBorderLayoutUnit': border, 'primaryCssOrigin': primary_origin,
             'primaryCssSize': primary_size, 'backingSize': texture_size, 'quad': [*quad_origin, *quad_size],
             'backingOuterRect': outer, 'backingInnerRect': inner, 'backingRedRect': content,
             'backingRedPixels': (content[2] - content[0]) * (content[3] - content[1]),
             'pixelwisePrecision': {'subtexelCoordinateError': SUBTEXEL_ERROR, 'unormConversionError': UNORM_ERROR},
             'float32CompositionProof': arithmetic_proof,
             'separateFilterFormatPolicy': {'maximumNormalizedError':FILTER_FORMAT_QUANTUM,
                 'minimumSourceBits':8,'constantColorExact':True,
                 'kind':'Conservative minimum-format-precision policy inference; not a vendor implementation theorem',
                 'primary':'D3D11.3 7.18.16.2 fixed-format filtering at least source-format precision and 7.18.16.3 min/max/constant invariants',
                 'causalControl':'Separate RGBA32F sampler and RGBA8 blend controls; source-derived binary backing and independent constant UVs'},
             'exactSingleTuplePixels': int(np.count_nonzero(low == high)), 'multipleAllowedTuplePixels': int(np.count_nonzero(low != high))}
    return low, high, pink, proof


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
    parser.add_argument('--inputs', type=Path, default=ROOT / 'gpu-model-inputs-v2.json')
    parser.add_argument('--capture', type=Path, default=ROOT / 'p7-capture.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'gpu-pixel-gate-v3.json')
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
            candidates=np.argwhere((low>1)&(high<254)&(low<high))
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
