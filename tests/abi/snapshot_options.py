"""R12 snapshot options against an actual runtime directory. rv_host_snapshot paints the viewport or an element during
the call and delivers an rv_resource_* operation on a later rv_run_loop_cycle, never inside the call. Checks the
image size at each scale (the host's device scale, explicit scales and fractional ones), crops of the viewport and of an
element, RGBA8 pixels against rv_host_paint_rgba and rv_element_snapshot, PNG decoded back to the RGBA8 pixels, JPEG and
WEBP signatures, sizes and the quality rules (out-of-range quality is the encoder default; WEBP at 1 is lossless),
display-p3 against the "snapshot-display-p3" facility, the argument errors, rv_snapshot_result's capacity rules, and
cancel, release, a new document and rv_host_destroy before delivery."""

import argparse
import ctypes
import json
import math
from pathlib import Path
import struct
import sys
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe

OK, NULL_ARGUMENT, PAINT_FAILED, BUFFER_TOO_SMALL, UNSUPPORTED, WRONG_HOST = 0, -1, -5, -6, -9, -12
SUCCEEDED = 0
RGBA8, PNG, JPEG, WEBP = range(4)
SRGB, DISPLAY_P3 = 0, 1
FACILITY, IMPLEMENTED, AVAILABLE = 4, 1, 4
GUARD = 200
PAGE = ('<!doctype html><style>html,body{margin:0;background:#fff}#d{position:absolute;left:5px;top:4px;width:20px;height:10px;'
        'background:rgb(255,0,0)}#g{position:absolute;left:28px;top:4px;width:10px;height:10px;background:rgb(0,128,0)}'
        '#t{position:absolute;left:0;top:16px;width:40px;height:14px;background:linear-gradient(90deg,#00f,#ff0)}'
        '#n{display:none}</style><div id=d></div><div id=g></div><div id=t></div><div id=n></div>')


class Options(ctypes.Structure):
    _fields_ = [('size', ctypes.c_int32), ('color_space', ctypes.c_int32), ('scale', ctypes.c_double), ('crop', ctypes.c_int32),
                ('encoding', ctypes.c_int32), ('x', ctypes.c_double), ('y', ctypes.c_double), ('width', ctypes.c_double),
                ('height', ctypes.c_double), ('quality', ctypes.c_double)]


Completion = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32)


def options(**values):
    result = Options(ctypes.sizeof(Options), SRGB, 0.0, 0, RGBA8, 0, 0, 0, 0, -1.0)
    for key, value in values.items():
        setattr(result, key, value)
    return result


def png_pixels(data):
    """Decodes an 8-bit RGB or RGBA PNG to RGBA rows."""
    assert data[:8] == b'\x89PNG\r\n\x1a\n'
    offset, idat, header = 8, b'', None
    while offset < len(data):
        length, kind = struct.unpack('>I4s', data[offset:offset + 8])
        body = data[offset + 8:offset + 8 + length]
        if kind == b'IHDR':
            header = struct.unpack('>IIBBBBB', body)
        elif kind == b'IDAT':
            idat += body
        offset += 12 + length
    width, height, depth, color, _, _, interlace = header
    assert depth == 8 and color in (2, 6) and interlace == 0, header
    channels = 4 if color == 6 else 3
    raw, stride, rows, previous = zlib.decompress(idat), width * channels, [], bytearray(width * channels)
    for y in range(height):
        kind, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for x in range(stride):
            left = line[x - channels] if x >= channels else 0
            up = previous[x]
            corner = previous[x - channels] if x >= channels else 0
            if kind == 1:
                line[x] = (line[x] + left) & 255
            elif kind == 2:
                line[x] = (line[x] + up) & 255
            elif kind == 3:
                line[x] = (line[x] + (left + up) // 2) & 255
            elif kind == 4:
                p = left + up - corner
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - corner)
                line[x] = (line[x] + (left if pa <= pb and pa <= pc else up if pb <= pc else corner)) & 255
        rows.append(bytes(line))
        previous = line
    if channels == 3:
        rows = [b''.join(row[i:i + 3] + b'\xff' for i in range(0, len(row), 3)) for row in rows]
    return width, height, b''.join(rows)


def jpeg_size(data):
    assert data[:2] == b'\xff\xd8'
    offset = 2
    while offset < len(data):
        marker, length = data[offset + 1], struct.unpack('>H', data[offset + 2:offset + 4])[0]
        if marker in (0xc0, 0xc1, 0xc2):
            height, width = struct.unpack('>HH', data[offset + 5:offset + 9])
            return width, height
        offset += 2 + length
    raise AssertionError('no SOF marker')


def verify(native_directory):
    report = {'sizes': {}, 'encodings': {}, 'facilities': {}}
    with SvgProbe(native_directory, 40, 30) as p:
        P, I, U64, I64 = p.pointer, p.integer, ctypes.c_uint64, ctypes.c_int64
        expect = p.expect
        expect(p.bind('rv_abi_has', I, [ctypes.c_char_p])(b'snapshot-options') == 1, 'snapshot-options advertised')
        snapshot = p.bind('rv_host_snapshot', I, [P, P, ctypes.POINTER(Options), Completion, P, ctypes.POINTER(U64)])
        result = p.bind('rv_snapshot_result', I, [U64, ctypes.c_char_p, I64, ctypes.POINTER(I64)])
        cancel = p.bind('rv_resource_cancel', I, [U64])
        release = p.bind('rv_resource_release', I, [U64])
        cycle = p.bind('rv_run_loop_cycle', I, [I])
        fact = p.bind('rv_host_capability_fact', I, [P, I, ctypes.c_char_p, I, ctypes.POINTER(I)])
        set_scale = p.bind('rv_host_set_device_scale', I, [P, ctypes.c_float])
        paint = p.bind('rv_host_paint_rgba', I, [P, ctypes.c_char_p, I])
        element_snapshot = p.bind('rv_element_snapshot', I, [P, ctypes.c_char_p, I, ctypes.POINTER(I), ctypes.POINTER(I)])
        host_create = p.bind('rv_host_create', P, [I, I])
        host_destroy = p.bind('rv_host_destroy', None, [P])
        load_html = p.bind('rv_host_load_html', I, [P, ctypes.c_char_p])
        by_id = p.bind('rv_document_get_element_by_id', P, [P, ctypes.c_char_p])
        release_node = p.bind('rv_node_release', None, [P])
        p.load(PAGE, standalone=False)
        d, g, n = p.node('d'), p.node('g'), p.node('n')
        deliveries = {}

        def on_complete(context, outcome, width, height):
            deliveries.setdefault(context, []).append((outcome, width, height))

        completion = Completion(on_complete)
        counter = [0]

        def facility(name):
            row = []
            for dimension in (IMPLEMENTED, AVAILABLE):
                value = I(99)
                expect(fact(p.host, FACILITY, name.encode(), dimension, ctypes.byref(value)) == OK, name + ' fact')
                row.append(value.value)
            expect(row[0] in (0, 1) and (name == 'snapshot-options' or row[0] == row[1]), name + ' implemented equals available')
            return row[0]

        for name in ['snapshot-options', 'snapshot-display-p3', 'image-encoding-png', 'image-encoding-jpeg', 'image-encoding-webp']:
            report['facilities'][name] = facility(name)
        expect(report['facilities']['snapshot-options'] == 1, 'snapshot-options implemented')

        def drain(context):
            # A hang guard: the loop raises and counts nothing.
            for _ in range(GUARD):
                if context in deliveries:
                    return
                cycle(1)
            raise AssertionError('no delivery for context ' + str(context))

        def read(token):
            length = I64(-1)
            expect(result(token, None, 0, ctypes.byref(length)) == BUFFER_TOO_SMALL and length.value > 0, 'result size query')
            short = ctypes.create_string_buffer(b'\x07' * 4, 4)
            again = I64(-1)
            expect(result(token, short, 1, ctypes.byref(again)) == BUFFER_TOO_SMALL and again.value == length.value
                   and short.raw == b'\x07' * 4, 'short capacity leaves the buffer untouched')
            buffer = ctypes.create_string_buffer(length.value)
            expect(result(token, buffer, length.value, ctypes.byref(again)) == OK and again.value == length.value, 'result copy')
            return buffer.raw

        def take(element, label, **values):
            counter[0] += 1
            context = counter[0]
            token = U64(0xdead)
            option = options(**values)
            status = snapshot(p.host, element, ctypes.byref(option), completion, context, ctypes.byref(token))
            expect(status == OK, label + ': status ' + str(status))
            expect(context not in deliveries, label + ': not delivered inside the call')
            length = I64(-1)
            expect(result(token, None, 0, ctypes.byref(length)) == UNSUPPORTED and length.value == -1, label + ': no result before delivery')
            drain(context)
            expect(len(deliveries[context]) == 1 and deliveries[context][0][0] == SUCCEEDED, label + ': one SUCCEEDED')
            _, width, height = deliveries[context][0]
            data = read(token)
            expect(release(token) == OK, label + ': release')
            expect(result(token, None, 0, ctypes.byref(length)) == UNSUPPORTED, label + ': no result after release')
            return width, height, data

        def failure(element, expected, label, host=None, **values):
            token = U64(0xdead)
            option = options(**values)
            status = snapshot(host or p.host, element, ctypes.byref(option), completion, 999, ctypes.byref(token))
            expect(status == expected and token.value == 0xdead, label + ': status ' + str(status))

        def solid(data, rgba, label):
            expect(len(data) % 4 == 0 and data == bytes(rgba) * (len(data) // 4), label + ': solid ' + str(list(data[:4])))

        # Sizes at each scale; the host's device scale is used for 0.
        for device in [1.0, 2.0, 1.5]:
            expect(set_scale(p.host, device) == OK, 'device scale ' + str(device))
            for scale in [0.0, 1.0, 2.0, 0.5, 1.5, 0.25, 8.0]:
                effective = device if scale == 0 else scale
                width, height, data = take(d, 'element at ' + str(scale) + ' on ' + str(device), scale=scale)
                expect((width, height) == (math.floor(20 * effective), math.floor(10 * effective)), 'element size ' + str((width, height)))
                expect(len(data) == width * height * 4, 'RGBA8 length')
                # Layout snaps boxes to the host's device pixels, so a scale other than the device scale, or a box
                # origin between device pixels, partly covers the edge pixels.
                if effective == device and (5 * device).is_integer() and (4 * device).is_integer():
                    solid(data, (255, 0, 0, 255), 'element pixels at ' + str(effective))
                else:
                    # The box's origin falls between device pixels: its edge pixels are partly covered.
                    # The snapped box moves by at most half a host device pixel from the CSS pixel bounds.
                    margin = math.ceil(0.5 * effective / device) + 1
                    interior = b''.join(data[(row * width + margin) * 4:(row * width + width - margin) * 4]
                                        for row in range(margin, height - margin))
                    solid(interior, (255, 0, 0, 255), 'element interior pixels at ' + str(effective))
                report['sizes'][str(device) + '/' + str(scale)] = [width, height]
            # The default scale matches rv_element_snapshot and rv_host_paint_rgba exactly.
            w, h = I(), I()
            element_snapshot(d, None, 0, ctypes.byref(w), ctypes.byref(h))
            legacy = ctypes.create_string_buffer(w.value * h.value * 4)
            expect(element_snapshot(d, legacy, len(legacy), ctypes.byref(w), ctypes.byref(h)) == OK, 'rv_element_snapshot')
            width, height, data = take(d, 'element default on ' + str(device))
            expect((width, height) == (w.value, h.value) and data == legacy.raw, 'element snapshot equals rv_element_snapshot')
            pw, ph = math.floor(40 * device), math.floor(30 * device)
            frame = ctypes.create_string_buffer(pw * ph * 4)
            expect(paint(p.host, frame, len(frame)) == OK, 'rv_host_paint_rgba')
            width, height, data = take(None, 'viewport default on ' + str(device))
            expect((width, height) == (pw, ph) and data == frame.raw, 'viewport snapshot equals rv_host_paint_rgba')
        expect(set_scale(p.host, 1.0) == OK, 'device scale 1')

        # Crops, in CSS pixels from the subject's top left, expanded to whole pixels and clipped to the subject.
        width, height, data = take(None, 'viewport crop', crop=1, x=28, y=4, width=10, height=10)
        expect((width, height) == (10, 10), 'viewport crop size')
        solid(data, (0, 128, 0, 255), 'viewport crop pixels')
        width, height, data = take(None, 'viewport crop at 2', crop=1, x=28, y=4, width=10, height=10, scale=2.0)
        expect((width, height) == (20, 20), 'viewport crop size at 2')
        solid(data, (0, 128, 0, 255), 'viewport crop pixels at 2')
        width, height, data = take(d, 'element crop', crop=1, x=5, y=2, width=10, height=5)
        expect((width, height) == (10, 5), 'element crop size')
        solid(data, (255, 0, 0, 255), 'element crop pixels')
        width, height, _ = take(d, 'fractional crop', crop=1, x=0.5, y=0.5, width=3.2, height=2.2)
        expect((width, height) == (4, 3), 'fractional crop expands to whole pixels ' + str((width, height)))
        width, height, _ = take(d, 'overhanging crop', crop=1, x=15, y=5, width=50, height=50)
        expect((width, height) == (5, 5), 'crop clipped to the element ' + str((width, height)))
        width, height, data = take(None, 'viewport white', crop=1, x=0, y=0, width=4, height=3)
        solid(data, (255, 255, 255, 255), 'viewport background')

        # Encodings: PNG decodes back to the RGBA8 image; JPEG and WEBP carry their signatures and sizes.
        _, _, rgba = take(None, 'viewport RGBA8')
        if report['facilities']['image-encoding-png']:
            width, height, data = take(None, 'viewport PNG', encoding=PNG)
            expect(png_pixels(data) == (40, 30, rgba) and (width, height) == (40, 30), 'PNG decodes to the RGBA8 snapshot')
            width, height, data = take(d, 'element PNG at 2', encoding=PNG, scale=2.0)
            expect(png_pixels(data)[:2] == (40, 20) and (width, height) == (40, 20), 'element PNG size')
            report['encodings']['png'] = len(data)
        else:
            failure(None, UNSUPPORTED, 'PNG without an encoder', encoding=PNG)
        if report['facilities']['image-encoding-jpeg']:
            sizes = {}
            for quality in [0.05, 0.5, 1.0, -1.0, 2.0, float('nan')]:
                width, height, data = take(None, 'JPEG quality ' + str(quality), encoding=JPEG, quality=quality)
                expect(jpeg_size(data) == (40, 30) == (width, height), 'JPEG size')
                sizes[str(quality)] = data
            expect(len(sizes['0.05']) < len(sizes['1.0']), 'JPEG quality changes the size')
            expect(sizes['-1.0'] == sizes['2.0'] == sizes['nan'], 'out-of-range quality is the encoder default')
            width, height, data = take(None, 'PNG ignores quality', encoding=PNG, quality=0.1)
            expect(png_pixels(data)[2] == rgba, 'PNG ignores quality')
            report['encodings']['jpeg'] = {k: len(v) for k, v in sizes.items()}
        else:
            failure(None, UNSUPPORTED, 'JPEG without an encoder', encoding=JPEG)
        if report['facilities']['image-encoding-webp']:
            width, height, lossless = take(None, 'WEBP quality 1', encoding=WEBP, quality=1.0)
            _, _, lossy = take(None, 'WEBP quality 0.5', encoding=WEBP, quality=0.5)
            for data, chunk in [(lossless, b'VP8L'), (lossy, b'VP8 ')]:
                chunks, offset = [], 12
                while offset + 8 <= len(data):
                    size = struct.unpack('<I', data[offset + 4:offset + 8])[0]
                    chunks.append(data[offset:offset + 4])
                    offset += 8 + size + (size & 1)
                expect(data[:4] == b'RIFF' and data[8:12] == b'WEBP' and chunk in chunks
                       and not ({b'VP8L', b'VP8 '} - {chunk}) & set(chunks), 'WEBP ' + chunk.decode() + ' ' + str(chunks))
            expect((width, height) == (40, 30), 'WEBP size')
            report['encodings']['webp'] = {'lossless': len(lossless), 'lossy': len(lossy)}
        else:
            failure(None, UNSUPPORTED, 'WEBP without an encoder', encoding=WEBP)

        # display-p3 follows its facility; without it there is no substitute.
        if report['facilities']['snapshot-display-p3']:
            width, height, data = take(d, 'display-p3', color_space=DISPLAY_P3)
            expect((width, height) == (20, 10) and len(data) == 800, 'display-p3 snapshot')
        else:
            failure(d, UNSUPPORTED, 'display-p3 without the color space', color_space=DISPLAY_P3)

        # Argument errors write no operation.
        token = U64(0xdead)
        good = options()
        expect(snapshot(None, None, ctypes.byref(good), completion, None, ctypes.byref(token)) == NULL_ARGUMENT, 'null host')
        expect(snapshot(p.host, None, None, completion, None, ctypes.byref(token)) == NULL_ARGUMENT, 'null options')
        expect(snapshot(p.host, None, ctypes.byref(good), Completion(), None, ctypes.byref(token)) == NULL_ARGUMENT, 'null completion')
        expect(snapshot(p.host, None, ctypes.byref(good), completion, None, None) == NULL_ARGUMENT, 'null operation')
        expect(token.value == 0xdead, 'no operation after null arguments')
        for label, values in [('size', {'size': 32}), ('scale 0.2', {'scale': 0.2}), ('scale 9', {'scale': 9.0}),
                              ('scale NaN', {'scale': float('nan')}), ('scale -1', {'scale': -1.0}), ('crop 2', {'crop': 2}),
                              ('crop width 0', {'crop': 1, 'width': 0, 'height': 5}), ('crop height -1', {'crop': 1, 'width': 5, 'height': -1}),
                              ('crop x NaN', {'crop': 1, 'x': float('nan'), 'width': 5, 'height': 5}),
                              ('crop outside', {'crop': 1, 'x': 100, 'y': 0, 'width': 5, 'height': 5}),
                              ('encoding 4', {'encoding': 4}), ('encoding -1', {'encoding': -1}), ('color space 2', {'color_space': 2})]:
            failure(d, UNSUPPORTED, label, **values)
        failure(n, PAINT_FAILED, 'element without a box')
        second = host_create(20, 20)
        expect(bool(second) and load_html(second, b'<!doctype html><div id=x style="width:5px;height:5px;background:red"></div>') == OK, 'second host')
        other = by_id(second, b'x')
        expect(bool(other), 'second host element')
        failure(other, WRONG_HOST, 'element of another host')
        failure(d, WRONG_HOST, 'element of the first host on the second', host=second)

        # Lifecycle before delivery: the snapshot is reached in the call and kept.
        def pending(host, element, context):
            token = U64()
            option = options()
            expect(snapshot(host, element, ctypes.byref(option), completion, context, ctypes.byref(token)) == OK, 'pending snapshot')
            expect(context not in deliveries, 'pending snapshot not delivered inside the call')
            return token

        token = pending(p.host, d, 1001)
        expect(cancel(token) == OK and deliveries.get(1001) == [(SUCCEEDED, 20, 10)], 'cancel delivers the reached snapshot')
        expect(len(read(token)) == 800, 'result after cancel')
        cycle(1)
        expect(release(token) == OK and release(token) == OK and len(deliveries[1001]) == 1, 'one delivery after cancel')
        token = pending(p.host, None, 1002)
        expect(release(token) == OK and deliveries.get(1002) == [(SUCCEEDED, 40, 30)], 'release delivers the reached snapshot')
        length = I64(-1)
        expect(result(token, None, 0, ctypes.byref(length)) == UNSUPPORTED, 'no result after release')
        token = pending(second, other, 1003)
        expect(load_html(second, b'<!doctype html><body>next') == OK and 1003 not in deliveries, 'not delivered inside a new document')
        drain(1003)
        expect(deliveries[1003] == [(SUCCEEDED, 5, 5)] and len(read(token)) == 100, 'a new document keeps the snapshot')
        release(token)
        release_node(other)
        token = pending(second, None, 1004)
        host_destroy(second)
        expect(1004 not in deliveries, 'not delivered inside rv_host_destroy')
        drain(1004)
        expect(deliveries[1004] == [(SUCCEEDED, 20, 20)] and len(read(token)) == 1600, 'rv_host_destroy keeps the snapshot')
        release(token)
        report['assertions'] = p.assertions
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--report')
    args = parser.parse_args()
    report = verify(args.native_directory)
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=1), encoding='utf-8')
    print('PASS snapshot_options: ' + str(report['assertions']) + ' assertions; facilities ' + json.dumps(report['facilities']), flush=True)


if __name__ == '__main__':
    main()
