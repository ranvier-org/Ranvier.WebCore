"""T02 font construction and registration: FontFace from bytes (TTF, CFF OTF, WOFF, WOFF2, invalid, empty) and from URL
sources the resource handler serves late, descriptors and their errors, rv_font_face_load/loaded, document.fonts
has/size/add/delete/clear/values with a CSS-connected face, measurement, cancellation, navigation, another host and
destroy."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sys
import threading

AHEM_SHA256 = '63d2abd0041c3e3b4b52ad8d382353b53c51c6785e76ce56ed9dacad2d2e31c4'
FIXTURES = {
    'ahemTtf': 'Tools/TestWebKitAPI/Resources/cocoa/Ahem.ttf',
    'ahemCff': 'Tools/TestWebKitAPI/Resources/cocoa/Ahem-CFF.otf',
    'robotoOtf': 'Source/ThirdParty/skia/modules/canvaskit/tests/assets/Roboto-Regular.otf',
    'robotoWoff': 'Source/ThirdParty/skia/modules/canvaskit/tests/assets/Roboto-Regular.woff',
    'robotoWoff2': 'Source/ThirdParty/skia/modules/canvaskit/tests/assets/Roboto-Regular.woff2',
}
UNLOADED, LOADING, LOADED, ERROR = 0, 1, 2, 3
SUCCEEDED, LOAD_FAILED, DECODE_FAILED, CANCELLED, INVALIDATED = 0, 1, 2, 3, 4
FAMILY = 'Rvé字'


class Utf8Span(ctypes.Structure):
    _fields_ = [('data', ctypes.c_char_p), ('length', ctypes.c_int32)]


class ByteSpan(ctypes.Structure):
    _fields_ = [('data', ctypes.c_char_p), ('length', ctypes.c_int32)]


class Source(ctypes.Structure):
    _fields_ = [('present', ctypes.c_int32), ('tag', ctypes.c_int32), ('arm0', Utf8Span), ('arm1', ByteSpan)]


class StringInput(ctypes.Structure):
    _fields_ = [('present', ctypes.c_int32), ('data', ctypes.c_char_p), ('length', ctypes.c_int32)]


DESCRIPTORS = ['style', 'weight', 'stretch', 'unicode_range', 'feature_settings', 'display', 'size_adjust']


class Descriptors(ctypes.Structure):
    _fields_ = [('size', ctypes.c_uint32)] + [(name, StringInput) for name in DESCRIPTORS]


class Faces(ctypes.Structure):
    _fields_ = [('present', ctypes.c_int32), ('count', ctypes.c_int32), ('items', ctypes.POINTER(ctypes.c_void_p))]


def verify(directory, webkit_source, evidence_json=None):
    directory = Path(directory).resolve()
    before = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
    if sys.platform == 'win32':
        os.add_dll_directory(str(directory))
    filename = {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')
    library = ctypes.CDLL(str(directory / filename))
    P, I, U64, D = ctypes.c_void_p, ctypes.c_int32, ctypes.c_uint64, ctypes.c_double
    assertions = 0
    cases = {}

    def expect(condition, message):
        nonlocal assertions
        assertions += 1
        if not condition:
            raise AssertionError(message)

    def bind(name, result, arguments):
        function = getattr(library, name)
        function.restype, function.argtypes = result, arguments
        return function

    fonts = {name: (Path(webkit_source) / path).read_bytes() for name, path in FIXTURES.items()}
    expect(hashlib.sha256(fonts['ahemTtf']).hexdigest() == AHEM_SHA256, 'Pinned Ahem fixture')
    ahem = fonts['ahemTtf']
    has = bind('rv_abi_has', I, [ctypes.c_char_p])
    features = ['dom:FontFace', 'dom:FontFaceSet', 'dom-constructor:FontFace', 'dom-font-face-set-values', 'font-face-load']
    expect(all(has(f.encode()) == 1 for f in features), 'Features ' + repr({f: has(f.encode()) for f in features}))
    create = bind('rv_host_create', P, [I, I])
    destroy = bind('rv_host_destroy', None, [P])
    load_html_bytes = bind('rv_host_load_html', I, [P, ctypes.c_char_p, ctypes.c_int32])  # utf8 bytes and length (#145)
    load_html = lambda a0, a1: load_html_bytes(a0, a1, -1 if a1 is None else len(a1))  # utf8 length
    host_document = bind('rv_host_document', P, [P])
    by_id_bytes = bind('rv_document_get_element_by_id', P, [P, ctypes.c_char_p, ctypes.c_int32])  # utf8 bytes and length (#145)
    by_id = lambda a0, a1: by_id_bytes(a0, a1, -1 if a1 is None else len(a1))  # utf8 length
    release_node = bind('rv_node_release', None, [P])
    rect = bind('rv_element_rect', I, [P] + [ctypes.POINTER(D)] * 4)
    update = bind('rv_host_update', I, [P])
    cycle = bind('rv_run_loop_cycle', I, [I])
    last_exception = bind('rv_last_exception', I, [I, ctypes.c_char_p, I, ctypes.POINTER(I)])
    Handler = ctypes.CFUNCTYPE(None, P, P, ctypes.c_char_p)
    set_handler = bind('rv_host_set_resource_handler', I, [P, Handler, P])
    finish = bind('rv_resource_load_finish', I, [P, ctypes.c_char_p, I, ctypes.c_char_p])
    fail = bind('rv_resource_load_fail', I, [P])
    Completion = ctypes.CFUNCTYPE(None, P, I, I, I)
    face_load = bind('rv_font_face_load', I, [P, P, Completion, P, ctypes.POINTER(U64)])
    face_loaded = bind('rv_font_face_loaded', I, [P, P, Completion, P, ctypes.POINTER(U64)])
    cancel = bind('rv_resource_cancel', I, [U64])
    release = bind('rv_resource_release', I, [U64])
    face_create = bind('rv_dom_font_face_create', I, [P, ctypes.c_char_p, I, ctypes.POINTER(Source), ctypes.POINTER(Descriptors), ctypes.POINTER(P)])
    face_release = bind('rv_dom_font_face_release', None, [P])
    face_retain = bind('rv_dom_font_face_retain', P, [P])
    retained = []
    face_status = bind('rv_dom_font_face_get_status', I, [P, ctypes.POINTER(I)])
    get_fonts = bind('rv_dom_document_get_fonts', I, [P, ctypes.POINTER(P)])
    target_release = bind('rv_event_target_release', None, [P])
    target_equals = bind('rv_event_target_equals', I, [P, P])
    set_size = bind('rv_dom_font_face_set_get_size', I, [P, ctypes.POINTER(I)])
    set_status = bind('rv_dom_font_face_set_get_status', I, [P, ctypes.POINTER(I)])
    set_has = bind('rv_dom_font_face_set_has', I, [P, P, ctypes.POINTER(I)])
    set_add = bind('rv_dom_font_face_set_add', I, [P, P, ctypes.POINTER(P)])
    set_delete = bind('rv_dom_font_face_set_delete', I, [P, P, ctypes.POINTER(I)])
    set_clear = bind('rv_dom_font_face_set_clear', I, [P])
    set_check = bind('rv_dom_font_face_set_check', I, [P, ctypes.c_char_p, I, ctypes.c_char_p, I, ctypes.POINTER(I)])
    set_values = bind('rv_dom_font_face_set_values', I, [P, ctypes.POINTER(Faces)])
    faces_release = bind('rv_dom_sequence_font_face_release', None, [ctypes.POINTER(Faces)])
    getters, setters = {}, {}
    for name in ['family'] + DESCRIPTORS[:2] + ['stretch', 'unicode_range', 'feature_settings', 'display', 'size_adjust', 'width']:
        getters[name] = bind('rv_dom_font_face_get_' + name, I, [P, ctypes.c_char_p, I, ctypes.POINTER(I)])
        setters[name] = bind('rv_dom_font_face_set_' + name, I, [P, ctypes.c_char_p, I])

    held = {}
    requested = []
    results = []
    state = {'inside': False, 'reentered': False}

    def serve(context, load, url):
        name = url.decode().rsplit('/', 1)[-1]
        requested.append(name)
        held[name] = load
    handler = Handler(serve)

    def complete(context, outcome, width, height):
        if state['inside']:
            state['reentered'] = True
        results.append((context or 0, outcome, width, height))
    completion = Completion(complete)

    def inside(function, *arguments):
        state['inside'] = True
        try:
            return function(*arguments)
        finally:
            state['inside'] = False

    def of(tag):
        return [r[1] for r in results if r[0] == tag]

    # Hang guard: waits count no assertion, so totals do not depend on timing.
    def settle(condition, label, limit=400):
        for _ in range(limit):
            if condition():
                return
            cycle(5)
        raise AssertionError('Timed out: ' + label)

    def drain(turns=10):
        for _ in range(turns):
            cycle(5)

    def exception_name():
        buffer, length = ctypes.create_string_buffer(64), I()
        last_exception(0, buffer, len(buffer), ctypes.byref(length))
        return buffer.raw[:length.value].decode()

    def utf8(value):
        return value.encode('utf-8') if isinstance(value, str) else value

    def string_source(text):
        data = utf8(text)
        return Source(1, 1, Utf8Span(data, len(data)), ByteSpan(None, 0))

    def byte_source(data):
        return Source(1, 2, Utf8Span(None, 0), ByteSpan(data, len(data)))

    def descriptors(**values):
        result = Descriptors()
        result.size = ctypes.sizeof(Descriptors)
        for key, value in values.items():
            data = utf8(value)
            setattr(result, key, StringInput(1, data, len(data)))
        return result

    def new_face(document, family, source, given=None):
        face = P()
        name = utf8(family)
        code = inside(face_create, document, name, len(name), ctypes.byref(source), ctypes.byref(given) if given else None, ctypes.byref(face))
        expect(code == 0 and bool(face.value), 'Construct %r: %d' % (family, code))
        return face.value

    def status_of(face):
        value = I(-1)
        expect(face_status(face, ctypes.byref(value)) == 0, 'FontFace.status')
        return value.value

    def read(face, name):
        buffer, length = ctypes.create_string_buffer(256), I()
        expect(getters[name](face, buffer, len(buffer), ctypes.byref(length)) == 0, 'Get ' + name)
        return buffer.raw[:length.value].decode('utf-8')

    def write(face, name, value):
        data = utf8(value)
        return inside(setters[name], face, data, len(data))

    def start(function, host, face, tag):
        operation = U64(0)
        code = inside(function, host, face, completion, tag, ctypes.byref(operation))
        expect(code == 0 and operation.value != 0 and not of(tag), 'Operation %d starts without a terminal inside the call (%d)' % (tag, code))
        return operation.value

    def size_of(fonts_set):
        value = I(-1)
        expect(set_size(fonts_set, ctypes.byref(value)) == 0, 'FontFaceSet.size')
        return value.value

    def contains(fonts_set, face):
        value = I(-1)
        expect(set_has(fonts_set, face, ctypes.byref(value)) == 0, 'FontFaceSet.has')
        return value.value

    def values_of(fonts_set):
        faces = Faces()
        expect(set_values(fonts_set, ctypes.byref(faces)) == 0 and faces.present == 1, 'FontFaceSet.values')
        # Each handle is retained past the snapshot's release; the probe releases them at the end.
        handles = [face_retain(faces.items[i]) for i in range(faces.count)]
        families = [read(h, 'family') for h in handles]
        faces_release(ctypes.byref(faces))
        retained.extend(handles)
        return handles, families

    def check(fonts_set, value):
        result = I(-1)
        data = utf8(value)
        return inside(set_check, fonts_set, data, len(data), None, 0, ctypes.byref(result)), result.value

    def width(host, element):
        update(host)
        node = by_id(host, element)
        x, y, w, h = D(), D(), D(), D()
        expect(rect(node, ctypes.byref(x), ctypes.byref(y), ctypes.byref(w), ctypes.byref(h)) == 0, 'Measure span')
        release_node(node)
        return w.value

    def page(generation):
        return ('<!DOCTYPE html><style>@font-face{font-family:RvCss;src:url(https://t02.test/css.ttf?' + generation + ')}'
                'span{font:20px monospace;white-space:pre}#a{font-family:RvAdded, monospace}#u{font-family:RvUrl, monospace}'
                '</style><body><span id=a>XXXX</span><span id=u>XXXX</span><span id=f>XXXX</span>').encode('utf-8')

    host = create(400, 100)
    expect(bool(host), 'Host creation')
    expect(set_handler(host, handler, None) == 0, 'Resource handler')
    expect(load_html(host, page('1')) == 0, 'Load page')
    document = host_document(host)
    fonts_set = P()
    expect(get_fonts(document, ctypes.byref(fonts_set)) == 0 and bool(fonts_set.value), 'Document.fonts')
    fonts_set = fonts_set.value
    css_faces, css_families = values_of(fonts_set)
    expect(size_of(fonts_set) == 1 and css_families == ['RvCss'], 'One CSS-connected face: ' + repr(css_families))
    css_face = css_faces[0]
    fallback = width(host, b'a')
    cases['fallbackWidth'] = fallback

    # Byte sources: every face settles at construction; loaded reports the engine's outcome on a later cycle.
    formats = {}
    tag = 100
    byte_cases = dict(fonts, invalid=b'not a font', empty=b'', nul=b'\x00' * 64)
    for name, data in byte_cases.items():
        face = new_face(document, 'RvBytes_' + name, byte_source(data))
        initial = status_of(face)
        operation = start(face_loaded, host, face, tag)
        settle(lambda: of(tag), 'loaded of ' + name)
        formats[name] = {'initial': initial, 'outcome': of(tag)[0], 'status': status_of(face)}
        expect(release(operation) == 0, 'Release ' + name)
        face_release(face)
        tag += 1
    cases['bytes'] = formats
    for name in fonts:
        expect(formats[name] == {'initial': LOADED, 'outcome': SUCCEEDED, 'status': LOADED}, name + ' loads from bytes: ' + repr(formats[name]))
    for name in ['invalid', 'empty', 'nul']:
        expect(formats[name] == {'initial': ERROR, 'outcome': DECODE_FAILED, 'status': ERROR}, name + ' bytes DECODE_FAILED: ' + repr(formats[name]))

    # Descriptors: defaults, values, constructor errors, setter errors and a UTF-8 family with an embedded NUL.
    plain = new_face(document, FAMILY, byte_source(ahem))
    defaults = {name: read(plain, name) for name in getters}
    cases['defaults'] = defaults
    # WebKit serializes unicode-range in lowercase hexadecimal; Chromium writes U+0-10FFFF.
    expect(defaults == {'family': FAMILY, 'style': 'normal', 'weight': 'normal', 'stretch': 'normal', 'unicode_range': 'U+0-10ffff',
                        'feature_settings': 'normal', 'display': 'auto', 'size_adjust': '100%', 'width': 'normal'}, 'Defaults ' + repr(defaults))
    given = new_face(document, 'RvDesc', byte_source(ahem), descriptors(weight='bold', style='italic', stretch='condensed',
                     unicode_range='U+0-7F', feature_settings='"liga" 0', display='swap', size_adjust='90%'))
    values = {name: read(given, name) for name in getters}
    cases['descriptors'] = values
    expect(values == {'family': 'RvDesc', 'style': 'italic', 'weight': 'bold', 'stretch': 'condensed', 'unicode_range': 'U+0-7f',
                      'feature_settings': '"liga" 0', 'display': 'swap', 'size_adjust': '90%', 'width': 'condensed'}, 'Descriptors ' + repr(values))
    expect(status_of(given) == LOADED, 'Face with valid descriptors loads')
    errors = {}
    for key, value in [('weight', 'heavy'), ('style', 'sideways'), ('stretch', 'wide'), ('unicode_range', 'U+ZZ'),
                       ('display', 'later'), ('feature_settings', 'liga'), ('size_adjust', '-5%')]:
        bad = new_face(document, 'RvBad_' + key, byte_source(ahem), descriptors(**{key: value}))
        operation = start(face_loaded, host, bad, tag)
        settle(lambda: of(tag), 'bad ' + key)
        errors[key] = (status_of(bad), of(tag)[0])
        expect(release(operation) == 0, 'Release bad ' + key)
        face_release(bad)
        tag += 1
    cases['descriptorErrors'] = errors
    expect(all(v == (ERROR, DECODE_FAILED) for v in errors.values()), 'Invalid descriptors: SyntaxError as DECODE_FAILED ' + repr(errors))
    setter = {}
    for key, value in [('weight', '300'), ('weight', 'heavy'), ('style', 'oblique 10deg'), ('family', 'Renamed'),
                       ('unicode_range', 'U+20-7E'), ('display', 'later')]:
        code = write(given, key, value)
        setter[key + '=' + value] = (code, exception_name() if code == -3 else '', read(given, key))
    cases['setters'] = setter
    expect(setter['weight=300'] == (0, '', '300') and setter['weight=heavy'] == (-3, 'SyntaxError', '300'), 'Weight setter ' + repr(setter))
    expect(setter['family=Renamed'] == (0, '', 'Renamed') and setter['display=later'] == (-3, 'SyntaxError', 'swap'), 'Family/display setters ' + repr(setter))
    expect(setter['unicode_range=U+20-7E'][0] == 0 and setter['style=oblique 10deg'][0] == 0, 'Range/style setters ' + repr(setter))
    nul_family = b'Rv\x00Nul'
    face = new_face(document, nul_family, byte_source(ahem))
    # The family arrives whole, NUL included, and WebKit serializes it as an escaped CSS string.
    cases['nulFamily'] = read(face, 'family')
    expect(cases['nulFamily'] == '"Rv\\0 Nul"', 'A family keeps its embedded NUL: %r' % cases['nulFamily'])
    face_release(face)
    bad_source = new_face(document, 'RvBadSource', string_source('nonsense('))
    operation = start(face_load, host, bad_source, tag)
    settle(lambda: of(tag), 'bad source')
    cases['badSource'] = (status_of(bad_source), of(tag))
    expect(of(tag) == [DECODE_FAILED] and status_of(bad_source) == ERROR, 'Unparsable src: DECODE_FAILED')
    expect(release(operation) == 0, 'Release bad source')
    face_release(bad_source)
    tag += 1
    url_bad = new_face(document, 'RvUrlBadWeight', string_source('url(https://t02.test/never.ttf)'), descriptors(weight='heavy'))
    operation = start(face_load, host, url_bad, tag)
    settle(lambda: of(tag), 'URL face with a bad descriptor')
    cases['urlBadDescriptor'] = (status_of(url_bad), of(tag))
    expect(of(tag) == [DECODE_FAILED] and status_of(url_bad) == ERROR and 'never.ttf' not in requested,
           'A URL face with an invalid descriptor: SyntaxError as DECODE_FAILED, never fetched')
    expect(release(operation) == 0, 'Release URL bad descriptor')
    face_release(url_bad)
    tag += 1

    # URL sources served late: loaded waits for a load, load starts it, failures report NetworkError as LOAD_FAILED.
    url_face = new_face(document, 'RvUrl', string_source('url(https://t02.test/ahem.ttf)'))
    missing = new_face(document, 'RvMissingUrl', string_source('url(https://t02.test/missing.ttf)'))
    broken = new_face(document, 'RvBrokenUrl', string_source('url(https://t02.test/broken.ttf) format("truetype")'))
    skipped = new_face(document, 'RvSkipped', string_source('url(https://t02.test/eot.eot) format("embedded-opentype"), url(https://t02.test/ahem2.ttf)'))
    expect([status_of(f) for f in [url_face, missing, broken, skipped]] == [UNLOADED] * 4, 'URL faces start unloaded')
    waiting = start(face_loaded, host, url_face, 200)
    drain()
    expect(not of(200) and status_of(url_face) == UNLOADED and 'ahem.ttf' not in requested, 'loaded starts no load')
    loading = start(face_load, host, url_face, 201)
    expect(status_of(url_face) == LOADING, 'load starts the face loading')
    failing = [start(face_load, host, missing, 202), start(face_load, host, broken, 203), start(face_load, host, skipped, 204)]
    settle(lambda: all(n in held for n in ['ahem.ttf', 'missing.ttf', 'broken.ttf', 'ahem2.ttf']), 'URL requests')
    drain()
    expect('eot.eot' not in requested and not of(200) and not of(201), 'Unsupported format skipped; loads wait for the responses')
    expect(finish(held.pop('ahem.ttf'), ahem, len(ahem), b'font/ttf') == 0 and fail(held.pop('missing.ttf')) == 0
           and finish(held.pop('broken.ttf'), b'not a font', 10, b'font/ttf') == 0
           and finish(held.pop('ahem2.ttf'), ahem, len(ahem), b'font/ttf') == 0, 'Serve the URL faces')
    expect(not of(200) and not of(201), 'No terminal inside the resource call')
    settle(lambda: all(of(t) for t in range(200, 205)), 'URL faces settle')
    cases['url'] = {t: of(t) for t in range(200, 205)}
    expect([of(t) for t in range(200, 205)] == [[SUCCEEDED], [SUCCEEDED], [LOAD_FAILED], [LOAD_FAILED], [SUCCEEDED]], 'URL outcomes ' + repr(cases['url']))
    expect([status_of(f) for f in [url_face, missing, broken, skipped]] == [LOADED, ERROR, ERROR, LOADED], 'URL face statuses')
    count = len(requested)
    again = [start(face_load, host, missing, 205), start(face_load, host, url_face, 206)]
    settle(lambda: of(205) and of(206), 'settled faces again')
    expect(of(205) == [LOAD_FAILED] and of(206) == [SUCCEEDED] and len(requested) == count, 'A settled face keeps its outcome and is not fetched again')
    for op in [waiting, loading] + failing + again:
        expect(release(op) == 0 and release(op) == 0, 'Release is idempotent')
    for f in [missing, broken, skipped]:
        face_release(f)

    # Cancellation delivers CANCELLED inside rv_resource_cancel; the later response delivers nothing more.
    held_face = new_face(document, 'RvHeld', string_source('url(https://t02.test/held.ttf)'))
    pending = start(face_load, host, held_face, 300)
    settle(lambda: 'held.ttf' in held, 'held request')
    expect(cancel(pending) == 0 and of(300) == [CANCELLED], 'Cancel delivers CANCELLED')
    expect(finish(held.pop('held.ttf'), ahem, len(ahem), b'font/ttf') == 0, 'Serve after cancel')
    settle(lambda: status_of(held_face) == LOADED, 'held face loads')
    drain()
    expect(of(300) == [CANCELLED] and release(pending) == 0, 'One terminal per operation')

    # Registration: add/has/delete/clear, iteration order, measurement and check with a CSS-connected face present.
    added = new_face(document, 'RvAdded', byte_source(ahem))
    second = new_face(document, 'RvSecond', byte_source(fonts['robotoWoff2']))
    registration = {'widthBefore': width(host, b'a'), 'checkBefore': check(fonts_set, '20px RvAdded')}
    returned = P()
    expect(set_add(fonts_set, added, ctypes.byref(returned)) == 0 and target_equals(returned.value, fonts_set) == 1, 'add returns the set')
    target_release(returned.value)
    for f in [second, added]:
        expect(set_add(fonts_set, f, ctypes.byref(returned)) == 0, 'add')
        target_release(returned.value)
    handles, families = values_of(fonts_set)
    registration['afterAdd'] = families
    expect(families == ['RvCss', 'RvAdded', 'RvSecond'] and handles[1] == added, 'Insertion order, one entry per face: ' + repr(families))
    expect(contains(fonts_set, added) == 1 and contains(fonts_set, css_face) == 1 and contains(fonts_set, url_face) == 0, 'has')
    registration['widthAfterAdd'] = width(host, b'a')
    registration['checkAfterAdd'] = check(fonts_set, '20px RvAdded')
    expect(abs(registration['widthAfterAdd'] - 80.0) <= 1.0 and abs(fallback - 80.0) > 1.0, 'Added face measures with Ahem metrics ' + repr(registration))
    expect(registration['checkAfterAdd'] == (0, 1), 'check true for the added loaded face')
    lazy = new_face(document, 'RvLazy', string_source('url(https://t02.test/lazy.ttf)'))
    expect(set_add(fonts_set, lazy, ctypes.byref(returned)) == 0, 'add an unloaded URL face')
    target_release(returned.value)
    registration['checkLazy'] = check(fonts_set, '20px RvLazy')
    # WebKit's check is true for an unloaded face it does not load; Chromium's is false. Neither starts the load.
    expect(registration['checkLazy'] == (0, 1) and status_of(lazy) == UNLOADED, 'check of an unloaded face starts no load: %r' % (registration['checkLazy'],))
    code = set_add(fonts_set, css_face, ctypes.byref(returned))
    registration['addCss'] = (code, exception_name() if code == -3 else '')
    expect(registration['addCss'] == (0, ''), 'add of a CSS-connected face already in the set is a no-op, as in Chromium ' + repr(registration['addCss']))
    deleted = I(-1)
    expect(set_delete(fonts_set, css_face, ctypes.byref(deleted)) == 0 and deleted.value == 0, 'delete of a CSS-connected face is false')
    expect(set_delete(fonts_set, added, ctypes.byref(deleted)) == 0 and deleted.value == 1, 'delete')
    expect(set_delete(fonts_set, added, ctypes.byref(deleted)) == 0 and deleted.value == 0, 'delete again is false')
    registration['afterDelete'] = values_of(fonts_set)[1]
    registration['widthAfterDelete'] = width(host, b'a')
    expect(registration['afterDelete'] == ['RvCss', 'RvSecond', 'RvLazy'] and abs(registration['widthAfterDelete'] - fallback) <= 0.01,
           'Deleted face leaves layout ' + repr(registration))
    expect(set_add(fonts_set, added, ctypes.byref(returned)) == 0, 'add again')
    target_release(returned.value)
    expect(set_clear(fonts_set) == 0, 'clear')
    registration['afterClear'] = values_of(fonts_set)[1]
    registration['widthAfterClear'] = width(host, b'a')
    expect(registration['afterClear'] == ['RvCss'] and contains(fonts_set, added) == 0 and status_of(added) == LOADED
           and abs(registration['widthAfterClear'] - fallback) <= 0.01, 'clear keeps CSS faces only ' + repr(registration))
    status_value = I(-1)
    expect(set_status(fonts_set, ctypes.byref(status_value)) == 0 and status_value.value in (0, 1), 'FontFaceSet.status')
    cases['registration'] = registration

    # Another host: its faces are WRONG_HOST here; a face of a replaced document is DETACHED.
    other = create(200, 100)
    expect(load_html(other, b'<!DOCTYPE html><body>other') == 0, 'Second host')
    other_document = host_document(other)
    foreign = new_face(other_document, 'RvForeign', byte_source(ahem))
    operation = U64(0)
    expect(face_load(host, foreign, completion, 400, ctypes.byref(operation)) == -12 and operation.value == 0, 'Another host: WRONG_HOST')
    expect(set_add(fonts_set, added, ctypes.byref(returned)) == 0, 'add before navigation')
    target_release(returned.value)
    lingering = new_face(document, 'RvLingering', string_source('url(https://t02.test/linger.ttf)'))
    linger = start(face_load, host, lingering, 401)
    settle(lambda: 'linger.ttf' in held, 'lingering request')
    expect(load_html(host, page('2')) == 0, 'Navigate')
    expect(of(401) == [INVALIDATED], 'Navigation INVALIDATED the pending face operation: ' + repr(of(401)))
    expect(face_load(host, added, completion, 402, ctypes.byref(operation)) == -10 and operation.value == 0, 'Face of a replaced document: DETACHED')
    new_document = host_document(host)
    new_set = P()
    expect(get_fonts(new_document, ctypes.byref(new_set)) == 0, 'New document fonts')
    reload = values_of(new_set.value)[1]
    cases['reload'] = reload
    expect(reload == ['RvCss'] and target_equals(new_set.value, fonts_set) == 0 and status_of(added) == LOADED,
           'The new document holds only its CSS faces; the old face keeps its status ' + repr(reload))
    code = set_add(new_set.value, css_face, ctypes.byref(returned))
    cases['addOldCssFace'] = (code, exception_name() if code == -3 else '')
    expect(cases['addOldCssFace'] == (-3, 'InvalidModificationError'), 'A CSS-connected face outside the set cannot be added ' + repr(cases['addOldCssFace']))
    code = set_add(new_set.value, foreign, ctypes.byref(returned))
    cases['addForeignFace'] = code
    if code == 0:
        target_release(returned.value)
    expect(code == 0 and contains(new_set.value, foreign) == 1, 'The engine accepts a face built in another document ' + repr(code))
    deleted = I(-1)
    expect(set_delete(new_set.value, foreign, ctypes.byref(deleted)) == 0 and deleted.value == 1, 'delete the foreign face')
    for name in list(held):
        fail(held.pop(name))
    drain()
    expect(release(linger) == 0, 'Release after navigation')

    # Argument and thread guards, then destroy.
    expect(face_load(None, url_face, completion, 500, ctypes.byref(operation)) == -1 and face_load(host, None, completion, 500, ctypes.byref(operation)) == -1
           and face_loaded(host, url_face, completion, 500, None) == -1, 'NULL arguments')
    late_face = new_face(new_document, 'RvLate', string_source('url(https://t02.test/late.ttf)'))
    doomed = start(face_load, host, late_face, 501)
    seen = []
    thread = threading.Thread(target=lambda: seen.extend([face_load(host, late_face, completion, 502, ctypes.byref(U64())),
                                                          set_size(new_set.value, ctypes.byref(I()))]))
    thread.start()
    thread.join()
    expect(seen == [-2, -2], 'Wrong thread ' + repr(seen))
    for handle in [new_set.value, fonts_set]:
        target_release(handle)
    destroy(host)
    expect(of(501) == [INVALIDATED], 'Destroy INVALIDATED: ' + repr(of(501)))
    for load_handle in held.values():
        fail(load_handle)
    drain()
    expect(release(doomed) == 0 and status_of(late_face) in (UNLOADED, LOADING, ERROR), 'Release after destroy; a face handle outlives its host')
    for f in [plain, given, url_face, held_face, added, second, lazy, lingering, late_face, foreign]:
        face_release(f)
    for f in retained:
        face_release(f)
    for d in [document, new_document, other_document]:
        release_node(d)
    destroy(other)
    expect(not state['reentered'], 'No completion inside an rv_* call other than cancel and release')
    after = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
    expect(before == after, 'Runtime unchanged')
    summary = dict(assertions=assertions, cases=cases, requested=requested)
    if evidence_json:
        Path(evidence_json).write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print('PASS font construction: %d assertions' % assertions, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--webkit-source', required=True)
    parser.add_argument('--evidence-json')
    arguments = parser.parse_args()
    verify(arguments.native_directory, arguments.webkit_source, arguments.evidence_json)
