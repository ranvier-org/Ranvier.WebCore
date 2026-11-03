"""Compare same-scene CPU/GPU glyph masks without an antialiasing golden."""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def bmp(path):
    data = Path(path).read_bytes()
    if data[:2] != b'BM':
        raise ValueError('Not BMP')
    offset = struct.unpack_from('<I', data, 10)[0]
    width, signed_height = struct.unpack_from('<ii', data, 18)
    bits = struct.unpack_from('<H', data, 28)[0]
    compression = struct.unpack_from('<I', data, 30)[0]
    if width <= 0 or not signed_height or bits not in [24, 32] or compression not in [0, 3]:
        raise ValueError('Unsupported captured BMP layout')
    height = abs(signed_height)
    stride = ((width * bits + 31) // 32) * 4
    if offset + stride * height > len(data):
        raise ValueError('Truncated BMP')
    masks = struct.unpack_from('<III', data, 54) if compression == 3 else (0xff0000, 0xff00, 0xff)
    def channel(value, mask):
        shift = (mask & -mask).bit_length() - 1
        return ((value & mask) >> shift) * 255 // (mask >> shift)
    pixels = []
    for y in range(height):
        row = y if signed_height < 0 else height - 1 - y
        for x in range(width):
            value = int.from_bytes(data[offset + row * stride + x * (bits // 8):
                                        offset + row * stride + (x + 1) * (bits // 8)], 'little')
            pixels.append(tuple(channel(value, mask) for mask in masks))
    return width, height, pixels


def ink_mask(image, bounds):
    width, height, pixels = image
    x, y, w, h = bounds
    if not (0 <= x < x + w <= width and 0 <= y < y + h <= height):
        raise ValueError('Glyph bounds outside capture')
    points = {(col, row) for row in range(y, y + h) for col in range(x, x + w)
              if max(pixels[row * width + col]) < 80}
    if not points:
        raise ValueError('Missing dark glyph')
    left, top = min(p[0] for p in points), min(p[1] for p in points)
    right, bottom = max(p[0] for p in points), max(p[1] for p in points)
    return {'bounds': [left, top, right + 1, bottom + 1],
            'width': right - left + 1, 'height': bottom - top + 1,
            'points': {(col - left, row - top) for col, row in points}}


def overlap(left, right):
    return len(left & right) / len(left | right)


def compare(cpu, gpu, bounds, f_shape=False):
    a, b = ink_mask(cpu, bounds), ink_mask(gpu, bounds)
    upright = overlap(a['points'], b['points'])
    flipped = {(x, a['height'] - 1 - y) for x, y in a['points']}
    reflected = overlap(flipped, b['points'])
    result = {'cpuBounds': a['bounds'], 'gpuBounds': b['bounds'],
              'cpuInk': len(a['points']), 'gpuInk': len(b['points']),
              'sameDimensions': (a['width'], a['height']) == (b['width'], b['height']),
              'uprightMaskIoU': upright, 'verticalReflectionMaskIoU': reflected,
              'closerToVerticalReflection': reflected > upright,
              'interpretation': 'Orientation diagnostic, not a widened pixel or antialiasing acceptance tolerance'}
    if f_shape:
        def mass(mask):
            third = max(1, mask['height'] // 3)
            top = sum(y < third for _, y in mask['points'])
            bottom = sum(y >= mask['height'] - third for _, y in mask['points'])
            return {'topThirdInk': top, 'bottomThirdInk': bottom, 'topHeavyF': top > bottom}
        result.update(cpuF=mass(a), gpuF=mass(b))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--captures', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = {'scope': 'Same runtime and DOM, CPU-off versus GPU; independent asymmetric F/top-bottom controls', 'rows': []}
    for label, scale, rect, f_shape in [('original-1', 1, (40, 125, 110, 35), False),
            ('asymmetric-10', 1, (40, 40, 120, 100), True),
            ('asymmetric-15', 1.5, (40, 40, 120, 100), True),
            ('asymmetric-20', 2, (40, 40, 120, 100), True)]:
        paths = [args.captures / (label + '-' + kind + '.bmp') for kind in ['cpu', 'gpu']]
        images = [bmp(path) for path in paths]
        bounds = tuple(int(value * scale) for value in rect)
        report['rows'].append({'label': label, 'scale': scale,
            'hashes': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},
            **compare(*images, bounds, f_shape=f_shape)})
        if f_shape:
            samples = {}
            for kind, image in zip(['cpu', 'gpu'], images):
                width, _, pixels = image
                top = pixels[int(44 * scale) * width + int(45 * scale)]
                bottom = pixels[int(136 * scale) * width + int(45 * scale)]
                samples[kind] = {'top': top, 'bottom': bottom,
                                 'redTopBlueBottom': top == (255, 0, 0) and bottom == (0, 0, 255)}
            report['rows'][-1]['asymmetricLayerStripes'] = samples
    report['copyPrimitive'] = {}
    expected_rows = [0xffff0000] * 4 + [0xff0000ff] * 4
    for mode in ['identity', 'flipped']:
        path = args.captures / ('cg-copy-' + mode + '.bgra')
        data = path.read_bytes()
        if len(data) != 8 * 8 * 4:
            raise ValueError('Wrong CG primitive output size')
        rows = [struct.unpack_from('<I', data, y * 8 * 4)[0] for y in range(8)]
        report['copyPrimitive'][mode] = {'firstPixelEachRow': [hex(value) for value in rows],
            'preservesSourceRows': rows == expected_rows,
            'reflectsSourceRows': rows == list(reversed(expected_rows)),
            'sha256': hashlib.sha256(data).hexdigest()}
    report['inversionObserved'] = any(row['closerToVerticalReflection'] for row in report['rows'])
    report['cpuOrientationSuspect'] = any(not row['cpuF']['topHeavyF'] for row in report['rows'] if 'cpuF' in row)
    report['gpuOrientationSuspect'] = any(not row['gpuF']['topHeavyF'] or
        not row['asymmetricLayerStripes']['gpu']['redTopBlueBottom'] for row in report['rows'] if 'gpuF' in row)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    return int(report['inversionObserved'] or report['cpuOrientationSuspect'] or report['gpuOrientationSuspect'])


if __name__ == '__main__':
    raise SystemExit(main())
