"""R06 canvas image/pixel operations: ImageData construction, layout and bytes, createImageData, getImageData and
putImageData round trips with dirty rectangles and bounds, drawImage from a canvas, an <img> and an SVG <image>, origin
tainting, and explicit errors. Pixels are read with getImageData, unpremultiplied RGBA; one check reads the host's
software paint. The Chromium oracle is docs/canvas-pixels-evidence/red-chromium.json."""
import argparse
import base64
import ctypes
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe

ABI = 58
OK, NULL_ARGUMENT, DOM_EXCEPTION, UNSUPPORTED, WRONG_INTERFACE = 0, -1, -3, -9, -11
TWO_D = 1
SRGB, DISPLAY_P3 = 0, 1
UNORM8, FLOAT16 = 0, 1
# The arms of the engine's CanvasImageSource, in its order (RV_DOM_UNION_HTML_IMAGE_ELEMENT_OR_SVG_IMAGE_ELEMENT_OR_...).
IMAGE, SVG_IMAGE, CANVAS, BITMAP, STYLE_IMAGE = 1, 2, 3, 4, 5
CLEAR, RED, LIME, BLUE = [0, 0, 0, 0], [255, 0, 0, 255], [0, 255, 0, 255], [0, 0, 255, 255]


def png(rows):
    """An RGBA PNG of rows of [r, g, b, a] pixels."""
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    raw = b''.join(b'\0' + bytes(value for pixel in row for value in pixel) for row in rows)
    header = struct.pack('>IIBBBBB', len(rows[0]), len(rows), 8, 6, 0, 0, 0)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')


TILE = png([[RED, LIME], [BLUE, CLEAR]])
TILE_URL = 'data:image/png;base64,' + base64.b64encode(TILE).decode()
REMOTE = 'https://pixels.test/tile.png'
PAGE = ('<!doctype html><style>html,body{margin:0;background:#fff}canvas{display:block}.away{position:absolute;left:400px;top:0}</style>'
        '<body><canvas id=c width=8 height=8 style="width:8px;height:8px"></canvas>'
        '<canvas id=d class=away width=4 height=4></canvas><canvas id=z class=away width=0 height=4></canvas>'
        '<canvas id=t class=away width=4 height=4></canvas><canvas id=u class=away width=4 height=4></canvas>'
        '<img id=i class=away src="' + TILE_URL + '"><img id=broken class=away src="data:image/png;base64,AAAA"><img id=empty class=away>'
        '<img id=remote class=away src="' + REMOTE + '"><img id=cors class=away crossorigin=anonymous src="' + REMOTE + '?cors">'
        '<svg class=away width=2 height=2><image id=s width=2 height=2 href="' + TILE_URL + '"/></svg><div id=n></div>')


class Layout(ctypes.Structure):
    _fields_ = [('size', ctypes.c_int32), ('width', ctypes.c_uint32), ('height', ctypes.c_uint32), ('colorSpace', ctypes.c_int32),
                ('pixelFormat', ctypes.c_int32), ('bytesPerPixel', ctypes.c_int32), ('rowBytes', ctypes.c_int64), ('byteLength', ctypes.c_int64)]


class DataSettings(ctypes.Structure):
    _fields_ = [('size', ctypes.c_uint32)]


class Source(ctypes.Structure):
    _fields_ = [('present', ctypes.c_int32), ('tag', ctypes.c_int32), ('arm0', ctypes.c_void_p), ('arm1', ctypes.c_void_p),
                ('arm2', ctypes.c_void_p), ('arm3', ctypes.c_void_p), ('arm4', ctypes.c_void_p)]


class Settings(ctypes.Structure):
    _fields_ = [('size', ctypes.c_int32), ('alpha', ctypes.c_int32), ('desynchronized', ctypes.c_int32),
                ('willReadFrequently', ctypes.c_int32), ('colorSpace', ctypes.c_int32), ('colorType', ctypes.c_int32)]


class Span(ctypes.Structure):
    _fields_ = [('data', ctypes.POINTER(ctypes.c_uint8)), ('length', ctypes.c_int32)]


class Style(ctypes.Structure):
    _fields_ = [('present', ctypes.c_int32), ('tag', ctypes.c_int32), ('arm0', Span),
                ('arm1', ctypes.c_void_p), ('arm2', ctypes.c_void_p)]


def source(tag, handle):
    arms = [None] * 5
    arms[tag - 1] = handle
    return Source(1, tag, *arms)


def verify(directory, evidence_json=None):
    directory = Path(directory).resolve()
    before = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
    report = {}
    with SvgProbe(directory, 320, 240) as p:
        P, I, U, I64 = p.pointer, p.integer, p.unsigned, ctypes.c_int64
        expect = p.expect
        expect(p.bind('rv_abi_version', I, [])() == ABI, 'ABI version ' + str(ABI))
        has = p.bind('rv_abi_has', I, [ctypes.c_char_p])
        for feature in ['canvas-context', 'canvas-pixels', 'dom:ImageData', 'dom:ImageBitmap', 'dom:CanvasRenderingContext2D']:
            expect(has(feature.encode()) == 1, 'rv_abi_has ' + feature)
        last_exception = lambda: p.text('rv_last_exception', [I], 0)
        get_context = p.bind('rv_canvas_get_context', I, [P, I, ctypes.POINTER(Settings), ctypes.POINTER(P)])
        release_context = p.bind('rv_dom_canvas_rendering_context2_d_release', None, [P])
        create = p.bind('rv_image_data_create', I, [U, U, ctypes.POINTER(ctypes.c_uint8), I64, I, I, ctypes.POINTER(P)])
        layout_of = p.bind('rv_image_data_layout', I, [P, ctypes.POINTER(Layout)])
        read = p.bind('rv_image_data_read', I, [P, I64, ctypes.POINTER(ctypes.c_uint8), I64])
        write = p.bind('rv_image_data_write', I, [P, I64, ctypes.POINTER(ctypes.c_uint8), I64])
        release_data = p.bind('rv_dom_image_data_release', None, [P])
        retain_data = p.bind('rv_dom_image_data_retain', P, [P])
        width_of = p.bind('rv_dom_image_data_get_width', I, [P, ctypes.POINTER(U)])
        height_of = p.bind('rv_dom_image_data_get_height', I, [P, ctypes.POINTER(U)])
        create_from_context = p.bind('rv_dom_canvas_rendering_context2_d_create_image_data_3', I, [P, I, I, ctypes.POINTER(DataSettings), ctypes.POINTER(P)])
        create_like = p.bind('rv_dom_canvas_rendering_context2_d_create_image_data_1', I, [P, P, ctypes.POINTER(P)])
        get_data = p.bind('rv_dom_canvas_rendering_context2_d_get_image_data', I, [P, I, I, I, I, ctypes.POINTER(DataSettings), ctypes.POINTER(P)])
        put3 = p.bind('rv_dom_canvas_rendering_context2_d_put_image_data_3', I, [P, P, I, I])
        put7 = p.bind('rv_dom_canvas_rendering_context2_d_put_image_data_7', I, [P, P, I, I, I, I, I, I])
        draw3 = p.bind('rv_dom_canvas_rendering_context2_d_draw_image_3', I, [P, ctypes.POINTER(Source), ctypes.c_double, ctypes.c_double])
        draw5 = p.bind('rv_dom_canvas_rendering_context2_d_draw_image_5', I, [P, ctypes.POINTER(Source)] + [ctypes.c_double] * 4)
        draw9 = p.bind('rv_dom_canvas_rendering_context2_d_draw_image_9', I, [P, ctypes.POINTER(Source)] + [ctypes.c_double] * 8)
        fill_rect = p.bind('rv_dom_canvas_rendering_context2_d_fill_rect', I, [P] + [ctypes.c_double] * 4)
        clear_rect = p.bind('rv_dom_canvas_rendering_context2_d_clear_rect', I, [P] + [ctypes.c_double] * 4)
        set_style = p.bind('rv_dom_canvas_rendering_context2_d_set_fill_style', I, [P, ctypes.POINTER(Style)])
        cycle = p.bind('rv_run_loop_cycle', I, [I])
        Handler = ctypes.CFUNCTYPE(None, P, P, ctypes.c_char_p)
        finish = p.bind('rv_resource_load_finish', I, [P, ctypes.c_char_p, I, ctypes.c_char_p])
        requests = []

        def serve(context, load, url):
            requests.append(url.decode())
            finish(load, TILE, len(TILE), b'image/png')
        handler = Handler(serve)
        p.call('rv_host_set_resource_handler', [P, Handler, P], p.host, handler, None)
        contexts, datas = [], []

        def status_is(code, expected, label, name=None):
            expect(code == expected, label + ': status %d, expected %d' % (code, expected))
            if name is not None:
                expect(last_exception() == name, label + ': ' + str(last_exception()) + ', expected ' + name)

        def context(canvas, **fields):
            requested = Settings(ctypes.sizeof(Settings), 1, 0, 0, 0, 0)
            for name, value in fields.items():
                setattr(requested, name, value)
            out = P()
            status_is(get_context(canvas, TWO_D, ctypes.byref(requested), ctypes.byref(out)), OK, 'getContext')
            contexts.append(out.value)
            return out.value

        def keep(handle):
            expect(bool(handle), 'ImageData handle')
            datas.append(handle)
            return handle

        def buffer(values):
            return (ctypes.c_uint8 * max(len(values), 1))(*values)

        def new_data(width, height, values=None, color_space=SRGB, pixel_format=UNORM8, status=OK, name=None):
            out = P(1234)
            data = buffer(values) if values is not None else None
            code = create(width, height, data, len(values) if values is not None else 0, color_space, pixel_format, ctypes.byref(out))
            status_is(code, status, 'rv_image_data_create %dx%d' % (width, height), name)
            if code == OK:
                return keep(out.value)
            expect(out.value is None, 'failed create leaves the result NULL')
            return None

        def layout(data):
            value = Layout(ctypes.sizeof(Layout), 0, 0, -7, -7, -7, -7, -7)
            status_is(layout_of(data, ctypes.byref(value)), OK, 'rv_image_data_layout')
            return {name: getattr(value, name) for name, _ in Layout._fields_[1:]}

        def data_bytes(data):
            length = layout(data)['byteLength']
            out = (ctypes.c_uint8 * length)()
            status_is(read(data, 0, out, length), OK, 'rv_image_data_read')
            return list(out)

        def size_of(data):
            w, h = U(), U()
            status_is(width_of(data, ctypes.byref(w)), OK, 'ImageData.width')
            status_is(height_of(data, ctypes.byref(h)), OK, 'ImageData.height')
            return [w.value, h.value]

        def get(ctx, x, y, w, h, status=OK, name=None):
            out = P()
            code = get_data(ctx, x, y, w, h, None, ctypes.byref(out))
            status_is(code, status, 'getImageData %d,%d,%d,%d' % (x, y, w, h), name)
            if code != OK:
                return None
            data = keep(out.value)
            values = data_bytes(data)
            return values

        def px(ctx, x, y):
            return get(ctx, x, y, 1, 1)

        def set_fill(ctx, text):
            data = text.encode()
            keepalive = (ctypes.c_uint8 * len(data)).from_buffer_copy(data)
            value = Style(1, 1, Span(ctypes.cast(keepalive, ctypes.POINTER(ctypes.c_uint8)), len(data)), None, None)
            status_is(set_style(ctx, ctypes.byref(value)), OK, 'fillStyle ' + text)

        def wait(condition, label, limit=400):
            for _ in range(limit):
                if condition():
                    return
                cycle(5)
            raise AssertionError('timed out: ' + label)

        def complete(img):
            value = I()
            status = p.bind('rv_dom_html_image_element_get_complete', I, [P, ctypes.POINTER(I)])(img, ctypes.byref(value))
            return status == OK and value.value == 1

        p.load(PAGE, standalone=False)
        c, d, z, t, u, i, broken, empty, remote, cors, s, n = (p.node(name) for name in ['c', 'd', 'z', 't', 'u', 'i', 'broken', 'empty', 'remote', 'cors', 's', 'n'])

        # ImageData construction: layout, zeroed pixels, and the constructor's exceptions.
        blank = new_data(2, 3)
        report['construct'] = {'size': size_of(blank), 'layout': layout(blank)}
        expect(report['construct'] == {'size': [2, 3], 'layout': {'width': 2, 'height': 3, 'colorSpace': SRGB, 'pixelFormat': UNORM8,
                                       'bytesPerPixel': 4, 'rowBytes': 8, 'byteLength': 24}}, 'construct: ' + str(report['construct']))
        expect(data_bytes(blank) == [0] * 24, 'a new ImageData is transparent black')
        errors = {}
        for label, args, expected in [('zeroWidth', (0, 2), 'IndexSizeError'), ('zeroHeight', (2, 0), 'IndexSizeError'),
                                      ('notMultipleOf4', (1, 1, [0] * 6), 'InvalidStateError'),
                                      ('notMultipleOfRow', (2, 1, [0] * 12), 'IndexSizeError'),
                                      ('heightMismatch', (2, 3, [0] * 16), 'IndexSizeError'),
                                      ('emptyData', (1, 1, []), 'InvalidStateError')]:
            new_data(*args, status=DOM_EXCEPTION, name=expected)
            errors[label] = expected
        new_data(65536, 65536, status=DOM_EXCEPTION, name='RangeError')
        errors['huge'] = 'RangeError'
        for label, kwargs in [('displayP3', dict(color_space=DISPLAY_P3)), ('float16', dict(pixel_format=FLOAT16)),
                              ('unknownColorSpace', dict(color_space=7)), ('unknownPixelFormat', dict(pixel_format=-1))]:
            new_data(1, 1, status=UNSUPPORTED, **kwargs)
            errors[label] = 'unsupported'
        out = P()
        status_is(create(1, 1, None, 4, SRGB, UNORM8, ctypes.byref(out)), NULL_ARGUMENT, 'NULL bytes with a length')
        status_is(create(1, 1, None, 0, SRGB, UNORM8, None), NULL_ARGUMENT, 'NULL result')
        report['constructErrors'] = errors
        from_data = new_data(1, 2, [1, 2, 3, 4, 5, 6, 7, 8])
        report['constructFromData'] = {'size': size_of(from_data), 'data': data_bytes(from_data)}
        expect(report['constructFromData'] == {'size': [1, 2], 'data': [1, 2, 3, 4, 5, 6, 7, 8]}, 'construct from data')
        short = Layout(ctypes.sizeof(Layout) - 1, 9, 9, 9, 9, 9, 9, 9)
        status_is(layout_of(blank, ctypes.byref(short)), UNSUPPORTED, 'layout with a short size')
        expect((short.width, short.byteLength) == (9, 9), 'a short layout is left unchanged')

        # Byte access: ranges inside the data, and RangeError with nothing copied past the end.
        status_is(write(blank, 4, buffer([9, 8, 7, 6]), 4), OK, 'write inside')
        expect(data_bytes(blank)[:12] == [0, 0, 0, 0, 9, 8, 7, 6, 0, 0, 0, 0], 'write lands at its offset')
        status_is(write(blank, 21, buffer([1, 1, 1, 1]), 4), DOM_EXCEPTION, 'write past the end', 'RangeError')
        expect(data_bytes(blank)[20:] == [0, 0, 0, 0], 'a write past the end writes nothing')
        part = (ctypes.c_uint8 * 4)(5, 5, 5, 5)
        status_is(read(blank, 22, part, 4), DOM_EXCEPTION, 'read past the end', 'RangeError')
        expect(list(part) == [5, 5, 5, 5], 'a read past the end copies nothing')
        status_is(read(blank, -1, part, 1), DOM_EXCEPTION, 'negative offset', 'RangeError')
        status_is(read(blank, 25, None, 0), DOM_EXCEPTION, 'offset past the end', 'RangeError')
        status_is(read(blank, 24, None, 0), OK, 'empty read at the end')
        status_is(write(blank, 0, None, 4), NULL_ARGUMENT, 'NULL bytes with a length')
        status_is(read(blank, 4, part, 4), OK, 'read inside')
        expect(list(part) == [9, 8, 7, 6], 'read returns the written bytes')
        expect(retain_data(blank) == blank, 'retain returns the handle')
        release_data(blank)

        # createImageData on a context.
        ctx = context(c)
        dctx = context(d, willReadFrequently=1)
        out = P()
        status_is(create_from_context(ctx, -3, 2, None, ctypes.byref(out)), OK, 'createImageData(-3, 2)')
        created = keep(out.value)
        report['createImageData'] = {'negative': size_of(created), 'colorSpace': layout(created)['colorSpace']}
        status_is(create_from_context(ctx, 0, 1, None, ctypes.byref(out)), DOM_EXCEPTION, 'createImageData(0, 1)', 'IndexSizeError')
        report['createImageData']['zero'] = 'IndexSizeError'
        settings = DataSettings(ctypes.sizeof(DataSettings))
        status_is(create_from_context(ctx, 1, 1, ctypes.byref(settings), ctypes.byref(out)), OK, 'createImageData with settings')
        keep(out.value)
        status_is(create_like(ctx, from_data, ctypes.byref(out)), OK, 'createImageData(imagedata)')
        like = keep(out.value)
        report['createImageData']['copyOf'] = size_of(like) + [data_bytes(like) == [0] * 8]
        expect(report['createImageData'] == {'negative': [3, 2], 'colorSpace': SRGB, 'zero': 'IndexSizeError', 'copyOf': [1, 2, True]},
               'createImageData: ' + str(report['createImageData']))

        # putImageData and getImageData round trip, outside and negative rectangles.
        pixels = [255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255, 10, 20, 30, 0,
                  255, 255, 255, 128, 0, 0, 0, 255, 200, 100, 50, 255, 1, 2, 3, 255]
        src = new_data(4, 2, pixels)
        status_is(put3(ctx, src, 1, 1), OK, 'putImageData')
        report['roundTrip'] = get(ctx, 1, 1, 4, 2)
        expect(report['roundTrip'] == pixels[:12] + CLEAR + pixels[16:], 'round trip: ' + str(report['roundTrip']))
        report['outside'] = get(ctx, -1, -1, 2, 2)
        expect(report['outside'] == CLEAR * 4, 'outside the canvas reads transparent black')
        report['negativeRect'] = get(ctx, 3, 2, -2, -1)
        expect(report['negativeRect'] == RED + LIME, 'a negative rectangle reads the rectangle it spans')
        get(ctx, 0, 0, 0, 1, DOM_EXCEPTION, 'IndexSizeError')
        get(ctx, 0, 0, 1, 0, DOM_EXCEPTION, 'IndexSizeError')
        report['getErrors'] = {'zeroWidth': 'IndexSizeError', 'zeroHeight': 'IndexSizeError'}
        out = P()
        status_is(get_data(ctx, 0, 0, 1, 1, ctypes.byref(settings), ctypes.byref(out)), OK, 'getImageData with settings')
        report['getColorSpace'] = layout(keep(out.value))['colorSpace']
        expect(report['getColorSpace'] == SRGB, 'getImageData is sRGB')
        # The host paint shows the put pixels over the white page.
        rgba = p.paint()
        report['painted'] = [p.pixel(rgba, 1, 1), p.pixel(rgba, 2, 1), p.pixel(rgba, 4, 1), p.pixel(rgba, 6, 6)]
        expect(report['painted'] == [RED, LIME, [255, 255, 255, 255], [255, 255, 255, 255]], 'paint: ' + str(report['painted']))

        # Dirty rectangles: only the dirty part lands, at dx + dirtyX.
        status_is(clear_rect(ctx, 0, 0, 8, 8), OK, 'clearRect')
        solid = new_data(3, 3, BLUE * 9)
        status_is(put7(ctx, solid, 2, 2, 1, 1, 1, 1), OK, 'putImageData dirty')
        report['dirty'] = {'inside': px(ctx, 3, 3), 'corner': px(ctx, 2, 2)}
        expect(report['dirty'] == {'inside': BLUE, 'corner': CLEAR}, 'dirty: ' + str(report['dirty']))
        status_is(put7(ctx, solid, 4, 4, 2, 2, -2, -2), OK, 'putImageData negative dirty')
        report['dirtyNegative'] = {'at5': px(ctx, 5, 5), 'at6': px(ctx, 6, 6), 'at4': px(ctx, 4, 4)}
        expect(report['dirtyNegative'] == {'at5': BLUE, 'at6': CLEAR, 'at4': BLUE}, 'negative dirty: ' + str(report['dirtyNegative']))
        status_is(put3(ctx, solid, 7, 7), OK, 'putImageData partly outside')
        report['partlyOutsidePixel'] = px(ctx, 7, 7)
        expect(report['partlyOutsidePixel'] == BLUE, 'partly outside lands inside')

        # The willReadFrequently context reads what it draws.
        set_fill(dctx, '#ff0000')
        status_is(fill_rect(dctx, 0, 0, 2, 4), OK, 'fillRect')
        set_fill(dctx, '#0000ff')
        status_is(fill_rect(dctx, 2, 0, 2, 4), OK, 'fillRect')
        report['willReadFrequently'] = get(dctx, 1, 0, 2, 1)
        expect(report['willReadFrequently'] == RED + BLUE, 'willReadFrequently readback')

        # drawImage from a canvas: 3, 5 and 9 arguments.
        canvas_source = source(CANVAS, d)
        status_is(clear_rect(ctx, 0, 0, 8, 8), OK, 'clearRect')
        status_is(draw3(ctx, canvas_source, 0, 0), OK, 'drawImage(canvas, 0, 0)')
        report['drawCanvas'] = {'left': px(ctx, 0, 0), 'right': px(ctx, 3, 0), 'beyond': px(ctx, 5, 0)}
        expect(report['drawCanvas'] == {'left': RED, 'right': BLUE, 'beyond': CLEAR}, 'drawCanvas: ' + str(report['drawCanvas']))
        status_is(clear_rect(ctx, 0, 0, 8, 8), OK, 'clearRect')
        status_is(draw5(ctx, canvas_source, 0, 0, 8, 8), OK, 'drawImage scaled')
        report['drawCanvasScaled'] = {'left': px(ctx, 1, 6), 'right': px(ctx, 6, 6)}
        expect(report['drawCanvasScaled'] == {'left': RED, 'right': BLUE}, 'scaled: ' + str(report['drawCanvasScaled']))
        status_is(clear_rect(ctx, 0, 0, 8, 8), OK, 'clearRect')
        status_is(draw9(ctx, canvas_source, 2, 0, 2, 4, 0, 0, 2, 4), OK, 'drawImage sub-rectangle')
        report['drawCanvasSubRect'] = {'left': px(ctx, 0, 0), 'right': px(ctx, 1, 3), 'beyond': px(ctx, 2, 0)}
        expect(report['drawCanvasSubRect'] == {'left': BLUE, 'right': BLUE, 'beyond': CLEAR}, 'sub-rect: ' + str(report['drawCanvasSubRect']))
        status_is(draw3(ctx, source(CANVAS, z), 0, 0), DOM_EXCEPTION, 'zero-size canvas', 'InvalidStateError')
        status_is(draw9(ctx, canvas_source, 0, 0, 0, 4, 0, 0, 4, 4), OK, 'zero source rectangle')
        status_is(draw3(ctx, canvas_source, float('nan'), 0), OK, 'non-finite drawImage')
        status_is(draw3(ctx, source(IMAGE, empty), 0, 0), OK, 'drawImage of an image without a source')
        report['drawErrors'] = {'zeroSizeCanvas': 'InvalidStateError', 'zeroSourceRect': 'ok', 'nonFinite': 'ok', 'emptyImage': 'ok'}
        status_is(draw3(ctx, source(IMAGE, n), 0, 0), WRONG_INTERFACE, 'a <div> as an image')
        status_is(draw3(ctx, source(CANVAS, i), 0, 0), WRONG_INTERFACE, 'an <img> as a canvas')
        status_is(draw3(ctx, Source(1, BITMAP, None, None, None, None, None), 0, 0), NULL_ARGUMENT, 'a NULL ImageBitmap arm')
        status_is(draw3(ctx, Source(1, 9, None, None, None, None, None), 0, 0), UNSUPPORTED, 'an unknown union tag')

        # drawImage from a decoded <img> and an SVG <image>.
        wait(lambda: complete(i) and complete(broken), 'images decode')
        status_is(clear_rect(ctx, 0, 0, 8, 8), OK, 'clearRect')
        status_is(draw3(ctx, source(IMAGE, i), 0, 0), OK, 'drawImage(img)')
        report['drawImage'] = get(ctx, 0, 0, 2, 2)
        expect(report['drawImage'] == RED + LIME + BLUE + CLEAR, 'drawImage(img): ' + str(report['drawImage']))
        status_is(draw3(ctx, source(IMAGE, broken), 0, 0), DOM_EXCEPTION, 'broken image', 'InvalidStateError')
        report['drawBroken'] = 'InvalidStateError'
        sctx = context(u)
        for _ in range(40):
            cycle(5)
        status_is(draw3(sctx, source(SVG_IMAGE, s), 0, 0), OK, 'drawImage(svg image)')
        report['drawSvgImage'] = get(sctx, 0, 0, 2, 2)
        expect(report['drawSvgImage'] == RED + LIME + BLUE + CLEAR, 'drawImage(svg image): ' + str(report['drawSvgImage']))

        # Origin: an image served from another origin taints the canvas; a CORS-mode load does not.
        wait(lambda: complete(remote) and complete(cors), 'remote images load')
        tctx = context(t)
        status_is(draw3(tctx, source(IMAGE, remote), 0, 0), OK, 'drawImage(cross-origin img)')
        get(tctx, 0, 0, 1, 1, DOM_EXCEPTION, 'SecurityError')
        status_is(clear_rect(ctx, 0, 0, 8, 8), OK, 'clearRect')
        status_is(draw3(ctx, source(IMAGE, cors), 0, 0), OK, 'drawImage(CORS img)')
        report['taint'] = {'crossOrigin': 'SecurityError', 'cors': get(ctx, 0, 0, 1, 1), 'requests': sorted(set(requests))}
        expect(report['taint']['cors'] == RED, 'a CORS image leaves the canvas readable')
        expect(report['taint']['requests'] == [REMOTE, REMOTE + '?cors'], 'requests: ' + str(requests))

        # Lifetime: an ImageData outlives its canvas and the document.
        kept = retain_data(src)
        status_is(p.bind('rv_node_remove', I, [P])(c), OK, 'remove the canvas')
        for handle in contexts:
            release_context(handle)
        contexts.clear()
        p.release_nodes()
        p.load('<!doctype html><body>', standalone=False)
        expect(data_bytes(kept) == pixels, 'ImageData bytes survive the document')
        release_data(kept)
        for handle in reversed(datas):
            release_data(handle)
        datas.clear()
        report['assertions'] = p.assertions

    after = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
    assert before == after, 'the probe changed the native directory'
    if evidence_json:
        Path(evidence_json).write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8')
    print('canvas_pixels: %d assertions PASS' % report['assertions'])
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--evidence-json')
    arguments = parser.parse_args()
    verify(arguments.native_directory, arguments.evidence_json)
