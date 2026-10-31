"""R07 canvas export and bitmap transport: toBlob/toDataURL bytes through the shared encoders, createImageBitmap from a
canvas, an <img>, ImageData, a Blob and another bitmap with crop, flip and resize, close, the bitmaprenderer context's
transferFromImageBitmap, operation delivery, cancel and release, and explicit errors. Pixels are read back with
getImageData after drawImage. The Chromium oracle is docs/canvas-export-evidence/red-chromium.json."""
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
OK, NULL_ARGUMENT, DOM_EXCEPTION, BUFFER_TOO_SMALL, UNSUPPORTED, WRONG_INTERFACE = 0, -1, -3, -6, -9, -11
TWO_D = 1
RGBA8, PNG, JPEG, WEBP = 0, 1, 2, 3
SOURCE_NODE, SOURCE_BITMAP, SOURCE_IMAGE_DATA, SOURCE_BLOB = 0, 1, 2, 3
SUCCEEDED, DECODE_FAILED, CANCELLED = 0, 2, 3
BITMAP_ARM = 4
CLEAR, RED, LIME, BLUE = [0, 0, 0, 0], [255, 0, 0, 255], [0, 255, 0, 255], [0, 0, 255, 255]
PNG_SIGNATURE = [137, 80, 78, 71, 13, 10, 26, 10]


def png(rows):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    raw = b''.join(b'\0' + bytes(value for pixel in row for value in pixel) for row in rows)
    header = struct.pack('>IIBBBBB', len(rows[0]), len(rows), 8, 6, 0, 0, 0)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')


TILE_URL = 'data:image/png;base64,' + base64.b64encode(png([[RED, LIME], [BLUE, CLEAR]])).decode()
PAGE = ('<!doctype html><style>html,body{margin:0;background:#fff}canvas,img{position:absolute;left:400px;top:0}</style><body>'
        '<canvas id=c width=4 height=2></canvas><canvas id=z width=0 height=2></canvas><canvas id=b width=4 height=2></canvas>'
        '<canvas id=k width=8 height=8></canvas><img id=i src="' + TILE_URL + '"><div id=n></div>')


class Settings(ctypes.Structure):
    _fields_ = [('size', ctypes.c_int32), ('alpha', ctypes.c_int32), ('desynchronized', ctypes.c_int32),
                ('willReadFrequently', ctypes.c_int32), ('colorSpace', ctypes.c_int32), ('colorType', ctypes.c_int32)]


class Options(ctypes.Structure):
    _fields_ = [(name, ctypes.c_int32) for name in ['size', 'crop', 'sx', 'sy', 'sw', 'sh', 'imageOrientation',
                                                     'premultiplyAlpha', 'colorSpaceConversion']] + \
               [('resizeWidth', ctypes.c_uint32), ('resizeHeight', ctypes.c_uint32), ('resizeQuality', ctypes.c_int32)]


class Source(ctypes.Structure):
    _fields_ = [('present', ctypes.c_int32), ('tag', ctypes.c_int32), ('arm0', ctypes.c_void_p), ('arm1', ctypes.c_void_p),
                ('arm2', ctypes.c_void_p), ('arm3', ctypes.c_void_p), ('arm4', ctypes.c_void_p)]


class ByteSpan(ctypes.Structure):
    _fields_ = [('data', ctypes.c_void_p), ('length', ctypes.c_int32)]


class Part(ctypes.Structure):
    _fields_ = [('present', ctypes.c_int32), ('tag', ctypes.c_int32), ('arm0', ByteSpan), ('arm1', ctypes.c_void_p), ('arm2', ByteSpan)]


class Parts(ctypes.Structure):
    _fields_ = [('present', ctypes.c_int32), ('count', ctypes.c_int32), ('items', ctypes.POINTER(Part))]


# red-chromium.json bitmapRenderer.canvas.
CHROMIUM_RENDERER_CANVAS = True


class CanvasUnion(ctypes.Structure):
    _fields_ = [('present', ctypes.c_int32), ('tag', ctypes.c_int32), ('arm0', ctypes.c_void_p)]


class Span(ctypes.Structure):
    _fields_ = [('data', ctypes.POINTER(ctypes.c_uint8)), ('length', ctypes.c_int32)]


class Style(ctypes.Structure):
    _fields_ = [('present', ctypes.c_int32), ('tag', ctypes.c_int32), ('arm0', Span), ('arm1', ctypes.c_void_p), ('arm2', ctypes.c_void_p)]


def options(**fields):
    value = Options(ctypes.sizeof(Options), 0, 0, 0, 0, 0, 0, 2, 1, 0, 0, 1)
    for name, field in fields.items():
        setattr(value, name, field)
    return value


def verify(directory, evidence_json=None):
    directory = Path(directory).resolve()
    before = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
    report = {}
    with SvgProbe(directory, 320, 240) as p:
        P, I, U, I64 = p.pointer, p.integer, p.unsigned, ctypes.c_int64
        expect = p.expect
        expect(p.bind('rv_abi_version', I, [])() == ABI, 'ABI version ' + str(ABI))
        has = p.bind('rv_abi_has', I, [ctypes.c_char_p])
        for feature in ['canvas-export', 'image-bitmaps', 'canvas-pixels', 'dom:ImageBitmap', 'dom:ImageBitmapRenderingContext']:
            expect(has(feature.encode()) == 1, 'rv_abi_has ' + feature)
        last_exception = lambda: p.text('rv_last_exception', [I], 0)
        get_context = p.bind('rv_canvas_get_context', I, [P, I, ctypes.POINTER(Settings), ctypes.POINTER(P)])
        release_context = p.bind('rv_dom_canvas_rendering_context2_d_release', None, [P])
        encode = p.bind('rv_canvas_encode', I, [P, I, ctypes.c_double, ctypes.POINTER(ctypes.c_uint8), I64, ctypes.POINTER(I64)])
        data_url = p.bind('rv_canvas_to_data_url', I, [P, I, ctypes.c_double, ctypes.c_char_p, I, ctypes.POINTER(I)])
        to_blob = p.bind('rv_canvas_to_blob', I, [P, I, ctypes.c_double, ctypes.POINTER(P)])
        bitmap_context = p.bind('rv_canvas_get_bitmap_context', I, [P, ctypes.POINTER(P)])
        release_bitmap_context = p.bind('rv_dom_image_bitmap_rendering_context_release', None, [P])
        context_canvas = p.bind('rv_dom_image_bitmap_rendering_context_get_canvas', I, [P, ctypes.POINTER(CanvasUnion)])
        release_canvas_union = p.bind('rv_dom_union_html_canvas_element_release', None, [ctypes.POINTER(CanvasUnion)])
        transfer = p.bind('rv_dom_image_bitmap_rendering_context_transfer_from_image_bitmap', I, [P, P])
        Completion = ctypes.CFUNCTYPE(None, P, I, I, I)
        create = p.bind('rv_image_bitmap_create', I, [P, I, P, ctypes.POINTER(Options), Completion, P, ctypes.POINTER(ctypes.c_uint64)])
        result = p.bind('rv_image_bitmap_result', I, [ctypes.c_uint64, ctypes.POINTER(P)])
        error = p.bind('rv_image_bitmap_error', I, [ctypes.c_uint64, ctypes.c_char_p, I, ctypes.POINTER(I)])
        cancel = p.bind('rv_resource_cancel', I, [ctypes.c_uint64])
        release_operation = p.bind('rv_resource_release', I, [ctypes.c_uint64])
        bitmap_width = p.bind('rv_dom_image_bitmap_get_width', I, [P, ctypes.POINTER(U)])
        bitmap_height = p.bind('rv_dom_image_bitmap_get_height', I, [P, ctypes.POINTER(U)])
        close = p.bind('rv_dom_image_bitmap_close', I, [P])
        release_bitmap = p.bind('rv_dom_image_bitmap_release', None, [P])
        release_blob = p.bind('rv_dom_blob_release', None, [P])
        read_blob = p.bind('rv_blob_read_bytes', I, [P, ctypes.POINTER(ctypes.c_uint8), I64, ctypes.POINTER(I64)])
        draw3 = p.bind('rv_dom_canvas_rendering_context2_d_draw_image_3', I, [P, ctypes.POINTER(Source), ctypes.c_double, ctypes.c_double])
        clear_rect = p.bind('rv_dom_canvas_rendering_context2_d_clear_rect', I, [P] + [ctypes.c_double] * 4)
        fill_rect = p.bind('rv_dom_canvas_rendering_context2_d_fill_rect', I, [P] + [ctypes.c_double] * 4)
        set_style = p.bind('rv_dom_canvas_rendering_context2_d_set_fill_style', I, [P, ctypes.POINTER(Style)])
        get_data = p.bind('rv_dom_canvas_rendering_context2_d_get_image_data', I, [P, I, I, I, I, P, ctypes.POINTER(P)])
        data_layout_length = p.bind('rv_image_data_read', I, [P, I64, ctypes.POINTER(ctypes.c_uint8), I64])
        release_data = p.bind('rv_dom_image_data_release', None, [P])
        create_data = p.bind('rv_image_data_create', I, [U, U, ctypes.POINTER(ctypes.c_uint8), I64, I, I, ctypes.POINTER(P)])
        cycle = p.bind('rv_run_loop_cycle', I, [I])
        contexts, bitmaps = [], []
        outcomes = {}
        calls = {'inside': False, 'reentered': False}

        def complete(context, outcome, width, height):
            if calls['inside']:
                calls['reentered'] = True
            outcomes[context] = (outcome, width, height)
        completion = Completion(complete)

        def status_is(code, expected, label, name=None):
            expect(code == expected, label + ': status %d, expected %d' % (code, expected))
            if name is not None:
                expect(last_exception() == name, label + ': ' + str(last_exception()) + ', expected ' + name)

        def context(canvas):
            requested = Settings(ctypes.sizeof(Settings), 1, 0, 0, 0, 0)
            out = P()
            status_is(get_context(canvas, TWO_D, ctypes.byref(requested), ctypes.byref(out)), OK, 'getContext')
            contexts.append(out.value)
            return out.value

        def set_fill(ctx, text):
            data = text.encode()
            keepalive = (ctypes.c_uint8 * len(data)).from_buffer_copy(data)
            value = Style(1, 1, Span(ctypes.cast(keepalive, ctypes.POINTER(ctypes.c_uint8)), len(data)), None, None)
            status_is(set_style(ctx, ctypes.byref(value)), OK, 'fillStyle ' + text)

        def pixels(ctx, x, y, w, h):
            out = P()
            status_is(get_data(ctx, x, y, w, h, None, ctypes.byref(out)), OK, 'getImageData')
            values = (ctypes.c_uint8 * (w * h * 4))()
            status_is(data_layout_length(out.value, 0, values, len(values)), OK, 'ImageData read')
            release_data(out.value)
            return list(values)

        def encoded(canvas, encoding, quality=float('nan'), status=OK, name=None):
            length = I64(-1)
            code = encode(canvas, encoding, quality, None, 0, ctypes.byref(length))
            if status != OK:
                status_is(code, status, 'rv_canvas_encode %d' % encoding, name)
                return None
            if length.value == 0:
                status_is(code, OK, 'rv_canvas_encode of no bitmap')
                return b''
            status_is(code, BUFFER_TOO_SMALL, 'rv_canvas_encode size query')
            out = (ctypes.c_uint8 * length.value)()
            again = I64(-1)
            status_is(encode(canvas, encoding, quality, out, len(out), ctypes.byref(again)), OK, 'rv_canvas_encode')
            expect(again.value == length.value, 'rv_canvas_encode length is stable')
            return bytes(out)

        def url_of(canvas, encoding, quality=float('nan')):
            length = I()
            status_is(data_url(canvas, encoding, quality, None, 0, ctypes.byref(length)), BUFFER_TOO_SMALL, 'toDataURL size query')
            out = ctypes.create_string_buffer(length.value)
            status_is(data_url(canvas, encoding, quality, out, length.value, ctypes.byref(length)), OK, 'toDataURL')
            return out.raw[:length.value].decode('ascii')

        def size(bitmap):
            w, h = U(), U()
            status_is(bitmap_width(bitmap, ctypes.byref(w)), OK, 'ImageBitmap.width')
            status_is(bitmap_height(bitmap, ctypes.byref(h)), OK, 'ImageBitmap.height')
            return [w.value, h.value]

        def start(kind, source, requested=None, tag=None, status=OK):
            operation = ctypes.c_uint64(0)
            calls['inside'] = True
            code = create(p.host, kind, source, ctypes.byref(requested) if requested is not None else None, completion, tag, ctypes.byref(operation))
            calls['inside'] = False
            status_is(code, status, 'rv_image_bitmap_create')
            expect(not calls['reentered'], 'no completion inside rv_image_bitmap_create')
            if code == OK:
                expect(tag not in outcomes, 'the completion waits for the run loop')
            return operation.value

        def settle(tag, limit=400):
            for _ in range(limit):
                if tag in outcomes:
                    return outcomes[tag]
                cycle(5)
            raise AssertionError('timed out waiting for bitmap ' + str(tag))

        def bitmap_of(kind, source, requested=None, tag=1):
            operation = start(kind, source, requested, tag)
            outcome = settle(tag)
            expect(outcome[0] == SUCCEEDED, 'bitmap %d succeeded: %s' % (tag, str(outcome)))
            out = P()
            status_is(result(operation, ctypes.byref(out)), OK, 'rv_image_bitmap_result')
            status_is(release_operation(operation), OK, 'rv_resource_release')
            bitmaps.append(out.value)
            expect(size(out.value) == list(outcome[1:]), 'the completion reports the bitmap size')
            return out.value

        def failure_of(kind, source, requested, tag):
            operation = start(kind, source, requested, tag)
            outcome = settle(tag)
            expect(outcome == (DECODE_FAILED, 0, 0), 'bitmap %d failed: %s' % (tag, str(outcome)))
            name = ctypes.create_string_buffer(64)
            length = I()
            status_is(error(operation, name, len(name), ctypes.byref(length)), OK, 'rv_image_bitmap_error')
            out = P(1234)
            status_is(result(operation, ctypes.byref(out)), UNSUPPORTED, 'no result for a failed bitmap')
            status_is(release_operation(operation), OK, 'rv_resource_release')
            return name.value.decode()

        def drawn(bitmap, w, h):
            status_is(clear_rect(kctx, 0, 0, 8, 8), OK, 'clearRect')
            status_is(draw3(kctx, ctypes.byref(Source(1, BITMAP_ARM, None, None, None, bitmap, None)), 0, 0), OK, 'drawImage(bitmap)')
            return pixels(kctx, 0, 0, w, h)

        p.load(PAGE, standalone=False)
        c, z, b, k, i, n = (p.node(name) for name in 'czbkin')
        ctx = context(c)
        kctx = context(k)
        set_fill(ctx, '#ff0000')
        status_is(fill_rect(ctx, 0, 0, 2, 2), OK, 'fillRect')
        set_fill(ctx, '#0000ff')
        status_is(fill_rect(ctx, 2, 0, 2, 2), OK, 'fillRect')
        expected = (RED * 2 + BLUE * 2) * 2

        # Encoded bytes, data URLs and Blobs.
        png_bytes = encoded(c, PNG)
        expect(list(png_bytes[:8]) == PNG_SIGNATURE, 'PNG signature')
        expect(encoded(c, PNG) == png_bytes, 'PNG encoding is deterministic')
        jpeg_bytes = encoded(c, JPEG, 0.9)
        expect(list(jpeg_bytes[:3]) == [255, 216, 255], 'JPEG signature')
        # WEBP depends on the flavor's encoders: either it encodes a RIFF/WEBP image or it is unsupported.
        probe_length = I64(-1)
        webp_status = encode(c, WEBP, float('nan'), None, 0, ctypes.byref(probe_length))
        expect(webp_status in (BUFFER_TOO_SMALL, UNSUPPORTED), 'WEBP is encoded or unsupported: ' + str(webp_status))
        if webp_status == BUFFER_TOO_SMALL:
            webp_bytes = encoded(c, WEBP)
            expect(webp_bytes[:4] == b'RIFF' and webp_bytes[8:12] == b'WEBP', 'WEBP signature')
            expect(url_of(c, WEBP)[:23] == 'data:image/webp;base64,', 'WEBP data URL')
        report['webpEncoded'] = webp_status == BUFFER_TOO_SMALL
        for encoding in [RGBA8, 7, -1]:
            encoded(c, encoding, status=UNSUPPORTED)
        encoded(n, PNG, status=WRONG_INTERFACE)
        status_is(encode(c, PNG, 0, None, 0, None), NULL_ARGUMENT, 'NULL length')
        expect(encoded(z, PNG) == b'', 'a zero-size canvas encodes nothing')
        url = url_of(c, PNG)
        report['toDataURL'] = {'prefix': url[:22], 'jpegPrefix': url_of(c, JPEG, 0.9)[:23], 'zeroSize': url_of(z, PNG)}
        expect(report['toDataURL'] == {'prefix': 'data:image/png;base64,', 'jpegPrefix': 'data:image/jpeg;base64,', 'zeroSize': 'data:,'},
               'toDataURL: ' + str(report['toDataURL']))
        expect(base64.b64decode(url[22:]) == png_bytes, 'the data URL holds the PNG bytes')
        short = ctypes.create_string_buffer(b'#' * 16)
        length = I()
        status_is(data_url(c, PNG, 0, short, 10, ctypes.byref(length)), BUFFER_TOO_SMALL, 'toDataURL into 10 bytes')
        expect(length.value == len(url) and short.raw[:16] == b'#' * 16, 'a short buffer is untouched')
        status_is(data_url(c, RGBA8, 0, None, 0, ctypes.byref(length)), UNSUPPORTED, 'RGBA8 data URL')
        blob = P()
        status_is(to_blob(c, PNG, 0, ctypes.byref(blob)), OK, 'toBlob')
        blob_bytes = (ctypes.c_uint8 * len(png_bytes))()
        blob_length = I64()
        status_is(read_blob(blob.value, blob_bytes, len(blob_bytes), ctypes.byref(blob_length)), OK, 'Blob bytes')
        expect(bytes(blob_bytes) == png_bytes, 'the Blob holds the PNG bytes')
        report['blobType'] = p.text('rv_dom_blob_get_type', [P], blob.value)
        expect(report['blobType'] == 'image/png', 'Blob type')
        none = P(1234)
        status_is(to_blob(z, PNG, 0, ctypes.byref(none)), OK, 'toBlob of a zero-size canvas')
        expect(none.value is None, 'a zero-size canvas has no Blob')

        # createImageBitmap from each source kind.
        whole = bitmap_of(SOURCE_NODE, c, tag=1)
        report['bitmap'] = size(whole)
        report['decodedBlob'] = drawn(bitmap_of(SOURCE_BLOB, blob.value, tag=2), 4, 2)
        expect(report['decodedBlob'] == expected, 'a decoded toBlob Blob draws the canvas: ' + str(report['decodedBlob']))
        report['wholePixels'] = drawn(whole, 4, 2)
        expect(report['wholePixels'] == expected, 'drawImage(bitmap) draws the canvas')
        crop = bitmap_of(SOURCE_NODE, c, options(crop=1, sx=1, sy=0, sw=2, sh=2), tag=3)
        report['crop'] = {'size': size(crop), 'pixels': drawn(crop, 2, 1)}
        expect(report['crop'] == {'size': [2, 2], 'pixels': RED + BLUE}, 'crop: ' + str(report['crop']))
        negative = bitmap_of(SOURCE_NODE, c, options(crop=1, sx=3, sy=2, sw=-2, sh=-2), tag=4)
        expect(drawn(negative, 2, 1) == RED + BLUE, 'a negative crop spans the same rectangle')
        column = (ctypes.c_uint8 * 8)(*(RED + BLUE))
        data = P()
        status_is(create_data(1, 2, column, 8, 0, 0, ctypes.byref(data)), OK, 'ImageData')
        flipped = bitmap_of(SOURCE_IMAGE_DATA, data.value, options(imageOrientation=1), tag=5)
        report['flipY'] = drawn(flipped, 1, 2)
        expect(report['flipY'] == BLUE + RED, 'flipY: ' + str(report['flipY']))
        resized = bitmap_of(SOURCE_NODE, c, options(resizeWidth=8, resizeHeight=4, resizeQuality=0), tag=6)
        report['resized'] = size(resized)
        expect(report['resized'] == [8, 4], 'resize')
        expect(drawn(resized, 8, 1) == RED * 4 + BLUE * 4, 'a pixelated resize keeps the halves')
        wait_for = lambda: p.bind('rv_dom_html_image_element_get_complete', I, [P, ctypes.POINTER(I)])
        state = I()
        for _ in range(400):
            if wait_for()(i, ctypes.byref(state)) == OK and state.value == 1:
                break
            cycle(5)
        image = bitmap_of(SOURCE_NODE, i, tag=7)
        report['fromImage'] = {'size': size(image), 'pixels': drawn(image, 2, 2)}
        expect(report['fromImage'] == {'size': [2, 2], 'pixels': RED + LIME + BLUE + CLEAR}, 'from <img>: ' + str(report['fromImage']))
        copy = bitmap_of(SOURCE_BITMAP, whole, tag=8)
        expect(size(copy) == [4, 2], 'a bitmap of a bitmap')
        release_data(data.value)

        # Failures arrive through the completion with their DOMException name.
        report['errors'] = {
            'zeroCrop': failure_of(SOURCE_NODE, c, options(crop=1, sw=0, sh=2), 20),
            'zeroCanvas': failure_of(SOURCE_NODE, z, None, 21),
        }
        junk = ctypes.create_string_buffer(b'', 3)
        part = Part(1, 1, ByteSpan(ctypes.cast(junk, P), 3), None, ByteSpan(None, 0))
        parts = Parts(1, 1, ctypes.pointer(part))
        junk_blob = P()
        document = p.bind('rv_host_document', P, [P])(p.host)
        p.retained.append(('rv_node_release', document))
        p.call('rv_dom_blob_create', [P, ctypes.POINTER(Parts), P, ctypes.POINTER(P)], document, ctypes.byref(parts), None, ctypes.byref(junk_blob))
        report['errors']['badBlob'] = failure_of(SOURCE_BLOB, junk_blob.value, None, 23)
        closing = bitmap_of(SOURCE_NODE, c, tag=9)
        status_is(close(closing), OK, 'close')
        report['closed'] = size(closing)
        expect(report['closed'] == [0, 0], 'a closed bitmap is 0x0')
        report['errors']['closedSource'] = failure_of(SOURCE_BITMAP, closing, None, 22)
        status_is(draw3(kctx, ctypes.byref(Source(1, BITMAP_ARM, None, None, None, closing, None)), 0, 0), DOM_EXCEPTION,
                  'drawImage(closed bitmap)', 'InvalidStateError')
        report['errors']['drawClosed'] = 'InvalidStateError'
        expect(report['errors'] == {'zeroCrop': 'RangeError', 'zeroCanvas': 'InvalidStateError', 'badBlob': 'InvalidStateError', 'closedSource': 'InvalidStateError',
                                    'drawClosed': 'InvalidStateError'}, 'errors: ' + str(report['errors']))
        release_blob(junk_blob.value)
        start(SOURCE_NODE, n, None, 30, status=UNSUPPORTED)
        start(9, c, None, 31, status=UNSUPPORTED)
        start(SOURCE_NODE, c, options(size=ctypes.sizeof(Options) - 4), 32, status=UNSUPPORTED)
        start(SOURCE_NODE, c, options(imageOrientation=3), 33, status=UNSUPPORTED)
        start(SOURCE_NODE, c, options(crop=2), 34, status=UNSUPPORTED)
        status_is(create(p.host, SOURCE_NODE, None, None, completion, None, ctypes.byref(ctypes.c_uint64())), NULL_ARGUMENT, 'NULL source')

        # Cancel delivers CANCELLED during the call; a released operation has no result.
        pending = start(SOURCE_BLOB, blob.value, None, 40)
        status_is(cancel(pending), OK, 'rv_resource_cancel')
        expect(outcomes.get(40) == (CANCELLED, 0, 0), 'cancel delivers CANCELLED: ' + str(outcomes.get(40)))
        status_is(release_operation(pending), OK, 'release after cancel')
        out = P(1234)
        status_is(result(pending, ctypes.byref(out)), UNSUPPORTED, 'a released operation has no result')

        # The bitmaprenderer context takes a bitmap's pixels and detaches it.
        bctx = P()
        status_is(bitmap_context(b, ctypes.byref(bctx)), OK, 'getContext(bitmaprenderer)')
        again = P()
        status_is(bitmap_context(b, ctypes.byref(again)), OK, 'second bitmaprenderer request')
        expect(again.value == bctx.value, 'the same bitmaprenderer context')
        release_bitmap_context(again.value)
        other = P(1234)
        status_is(get_context(b, TWO_D, None, ctypes.byref(other)), OK, '2D on a bitmaprenderer canvas')
        expect(other.value is None, 'a bitmaprenderer canvas has no 2D context')
        status_is(bitmap_context(c, ctypes.byref(other)), OK, 'bitmaprenderer on a 2D canvas')
        expect(other.value is None, 'a 2D canvas has no bitmaprenderer context')
        status_is(bitmap_context(n, ctypes.byref(other)), WRONG_INTERFACE, 'bitmaprenderer on a <div>')
        owner = CanvasUnion()
        status_is(context_canvas(bctx.value, ctypes.byref(owner)), OK, 'ImageBitmapRenderingContext.canvas')
        report['rendererCanvas'] = owner.present == 1 and owner.tag == 1 and owner.arm0 == b
        # Chromium: red-chromium.json bitmapRenderer.canvas is true (bctx.canvas === the canvas).
        expect(report['rendererCanvas'] == CHROMIUM_RENDERER_CANVAS, 'the context names its canvas, as in Chromium')
        release_canvas_union(ctypes.byref(owner))
        moving = bitmap_of(SOURCE_NODE, c, tag=10)
        status_is(transfer(bctx.value, moving), OK, 'transferFromImageBitmap')
        report['transfer'] = {'sourceAfter': size(moving), 'canvasData': url_of(b, PNG) == url}
        expect(report['transfer'] == {'sourceAfter': [0, 0], 'canvasData': True}, 'transfer: ' + str(report['transfer']))
        status_is(transfer(bctx.value, moving), DOM_EXCEPTION, 'transfer of a detached bitmap', 'InvalidStateError')
        report['transferClosed'] = 'InvalidStateError'
        status_is(transfer(bctx.value, None), OK, 'transferFromImageBitmap(null)')
        dimension = U()
        p.call('rv_dom_html_canvas_element_get_width', [P, ctypes.POINTER(U)], b, ctypes.byref(dimension))
        expect(dimension.value == 4, 'a null transfer keeps the canvas size')
        release_bitmap_context(bctx.value)

        # Lifetime: a bitmap outlives its source canvas and the document.
        kept = p.bind('rv_dom_image_bitmap_retain', P, [P])(copy)
        for handle in contexts:
            release_context(handle)
        contexts.clear()
        release_blob(blob.value)
        p.release_nodes()
        p.load('<!doctype html><body>', standalone=False)
        expect(size(kept) == [4, 2], 'an ImageBitmap outlives its document')
        release_bitmap(kept)
        for handle in bitmaps:
            release_bitmap(handle)
        bitmaps.clear()
        report['assertions'] = p.assertions

    after = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
    assert before == after, 'the probe changed the native directory'
    if evidence_json:
        Path(evidence_json).write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8')
    print('canvas_export: %d assertions PASS' % report['assertions'])
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--evidence-json')
    arguments = parser.parse_args()
    verify(arguments.native_directory, arguments.evidence_json)
