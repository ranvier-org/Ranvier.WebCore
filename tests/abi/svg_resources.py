import argparse
import ctypes
import json
from pathlib import Path
import struct
import sys
import threading
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe
from utf8_inputs import Utf8, Span, span

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
XHTML = 'http://www.w3.org/1999/xhtml'
SVG = 'http://www.w3.org/2000/svg'
WHITE, RED, LIME, BLUE, BLACK = [255, 255, 255, 255], [255, 0, 0, 255], [0, 255, 0, 255], [0, 0, 255, 255], [0, 0, 0, 255]


def png(width, height, rgb):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    rows = b''.join(b'\x00' + bytes(rgb) * width for _ in range(height))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b'')


IMAGES = {'blue.png': png(1, 1, (0, 0, 255)), 'green.png': png(1, 1, (0, 255, 0)), 'red.png': png(1, 1, (255, 0, 0)), 'broken.png': b'not a png'}
Handler = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p)


def verify(native_directory):
    with SvgProbe(native_directory, 400, 300) as p:
        oracle = json.loads((FIXTURES / 'svg-resources-oracle.json').read_text())
        requests, held, threads = [], {}, []
        finish = p.bind('rv_resource_load_finish', p.integer, [p.pointer, ctypes.c_char_p, p.integer, ctypes.c_char_p])
        fail = p.bind('rv_resource_load_fail', p.integer, [p.pointer])
        main_thread = threading.get_ident()

        def serve(context, load, url):
            url = url.decode()
            requests.append(url)
            threads.append(threading.get_ident())
            name = url.rsplit('/', 1)[-1]
            if name.startswith('slow'):
                held[name] = load
            elif name in IMAGES:
                p.expect(finish(load, IMAGES[name], len(IMAGES[name]), b'image/png') == 0, 'resource completion ' + name)
            else:
                p.expect(fail(load) == 0, 'resource network failure ' + name)

        handler = Handler(serve)
        p.call('rv_host_set_resource_handler', [p.pointer, Handler, p.pointer], p.host, handler, None)
        p.load((FIXTURES / 'svg-resources.svg').read_bytes())

        def settle():
            for _ in range(5):
                p.expect(p.bind('rv_run_loop_cycle', p.integer, [p.integer])(20) >= 0, 'resource event cycle')
            return p.paint()

        names = ['root', 'title', 'desc', 'metadata', 'style', 'defs', 'symbol', 'green', 'useSymbol', 'useRect', 'group', 'styled',
                 'switch', 'langRect', 'foreign', 'html', 'link', 'image', 'script']
        n = {name: p.node(name) for name in names}
        pixels = settle()
        p.expect(threads and all(thread == main_thread for thread in threads), 'resource handler runs on the owning host thread')
        p.expect(requests == ['https://fixture.test/blue.png'], 'only the image requests a resource; disabled script loads nothing: ' + str(requests))
        expected = oracle['pixels']
        for phase in ['initial']:
            for x, y, rgba in expected[phase]:
                p.expect(p.pixel(pixels, x, y) == rgba, phase + ' paint at ' + str((x, y)) + ': ' + str(p.pixel(pixels, x, y)))
        p.expect(p.attribute(n['root'], 'data-ran') is None, 'native SVG script stays inert')

        document = p.object('rv_dom_node_get_owner_document', [p.pointer], [n['root']], 'node')
        root_element = p.object('rv_dom_document_get_root_element', [p.pointer], [document], 'node')
        p.expect(root_element == n['root'], 'Document.rootElement is the actual SVG root')
        p.expect(p.object('rv_dom_svg_element_get_owner_svg_element', [p.pointer], [n['styled']], 'node') == n['root'], 'ownerSVGElement')
        p.expect(p.object('rv_dom_svg_element_get_viewport_element', [p.pointer], [n['styled']], 'node') == n['root'], 'viewportElement')
        p.expect(p.object('rv_dom_svg_element_get_owner_svg_element', [p.pointer], [n['root']], 'node', nullable=True) is None, 'outermost ownerSVGElement is null')

        for name, local in [('title', 'title'), ('desc', 'desc'), ('metadata', 'metadata'), ('defs', 'defs'), ('group', 'g'), ('switch', 'switch')]:
            p.expect(p.text('rv_dom_element_get_local_name', [p.pointer], n[name]) == local, 'genuine SVG content element ' + local)
            p.expect(p.text('rv_dom_element_get_namespace_uri', [p.pointer], n[name]) == SVG, 'SVG namespace ' + local)
        p.expect(p.text('rv_dom_node_get_text_content', [p.pointer], n['title']) == 'Resources', 'title text')
        p.expect(p.text('rv_dom_node_get_text_content', [p.pointer], n['desc']) == 'S11 reuse, content and resource fixture', 'desc text')
        p.expect(p.text('rv_dom_node_get_text_content', [p.pointer], n['metadata']) == 'm', 'metadata foreign content')
        p.expect(p.text('rv_dom_element_get_namespace_uri', [p.pointer], n['html']) == XHTML, 'foreignObject keeps genuine HTML child')

        def animated_string(function, target):
            value = p.object(function, [p.pointer], [target], 'svg_animated_string')
            p.expect(p.object(function, [p.pointer], [target], 'svg_animated_string') == value, 'live animated string identity ' + function)
            return value

        def base(value):
            return p.text('rv_dom_svg_animated_string_get_base_val', [p.pointer], value)

        def set_base(value, text):
            p.call('rv_dom_svg_animated_string_set_base_val', [p.pointer, Utf8], value, text.encode())

        def string(kind, target, field):
            return p.text('rv_dom_' + kind + '_get_' + field, [p.pointer], target)

        def set_string(kind, target, field, value):
            p.call('rv_dom_' + kind + '_set_' + field, [p.pointer, Utf8], target, None if value is None else value.encode())

        state = {}
        # SVGAElement reflection
        link_target = animated_string('rv_dom_svga_element_get_target', n['link'])
        link_href = animated_string('rv_dom_svga_element_get_href', n['link'])
        state['a'] = dict(target=base(link_target), href=base(link_href), hreflang=string('svga_element', n['link'], 'hreflang'),
                          rel=string('svga_element', n['link'], 'rel'), type=string('svga_element', n['link'], 'type'))
        rel_list = p.object('rv_dom_svga_element_get_rel_list', [p.pointer], [n['link']], 'dom_token_list')
        state['a']['relListLength'] = p.read('dom_token_list', rel_list, 'length', p.unsigned)
        contains = ctypes.c_int32()
        p.call('rv_dom_dom_token_list_contains', [p.pointer, Utf8, ctypes.POINTER(ctypes.c_int32)], rel_list, b'next', ctypes.byref(contains))
        state['a']['relListContainsNext'] = bool(contains.value)
        set_base(link_target, '_self')
        set_string('svga_element', n['link'], 'hreflang', 'fr')
        set_string('svga_element', n['link'], 'type', 'image/svg+xml')
        class Strings(ctypes.Structure):
            _fields_ = [('present', ctypes.c_int32), ('count', ctypes.c_int32), ('items', ctypes.POINTER(Span))]
        tokens = (Span * 1)(span('help'))
        p.call('rv_dom_dom_token_list_add', [p.pointer, ctypes.POINTER(Strings)], rel_list, ctypes.byref(Strings(1, 1, tokens)))
        state['a'].update(changedTarget=p.attribute(n['link'], 'target'), changedHreflang=p.attribute(n['link'], 'hreflang'),
                          changedType=p.attribute(n['link'], 'type'), changedRel=string('svga_element', n['link'], 'rel'))
        set_base(link_href, 'https://fixture.test/other')
        state['a']['changedHref'] = p.attribute(n['link'], 'href')
        p.expect(requests == ['https://fixture.test/blue.png'], 'link href edits do not navigate or load')

        # SVGScriptElement inert reflection
        script_href = animated_string('rv_dom_svg_script_element_get_href', n['script'])
        flag = ctypes.c_int32()
        p.call('rv_dom_svg_script_element_get_async', [p.pointer, ctypes.POINTER(ctypes.c_int32)], n['script'], ctypes.byref(flag))
        state['script'] = dict(type=string('svg_script_element', n['script'], 'type'), href=base(script_href), async_=bool(flag.value))
        set_string('svg_script_element', n['script'], 'type', 'module')
        p.call('rv_dom_svg_script_element_set_async', [p.pointer, ctypes.c_int32], n['script'], 0)
        p.call('rv_dom_svg_script_element_get_async', [p.pointer, ctypes.POINTER(ctypes.c_int32)], n['script'], ctypes.byref(flag))
        set_base(script_href, 'https://fixture.test/script.js')
        state['script'].update(changedType=p.attribute(n['script'], 'type'), changedAsync=bool(flag.value), changedHref=p.attribute(n['script'], 'href'))
        settle()
        p.expect('https://fixture.test/script.js' not in requests and p.attribute(n['root'], 'data-ran') is None, 'edited SVG script stays disabled')

        # SVGStyleElement / LinkStyle
        state['style'] = dict(type=string('svg_style_element', n['style'], 'type'), media=string('svg_style_element', n['style'], 'media'),
                              title=string('svg_style_element', n['style'], 'title'))
        sheet = p.object('rv_dom_svg_style_element_get_sheet', [p.pointer], [n['style']], 'style_sheet')
        p.expect(bool(sheet), 'LinkStyle.sheet is the actual sheet')
        p.call('rv_dom_svg_style_element_set_disabled', [p.pointer, ctypes.c_int32], n['style'], 1)
        disabled = p.pixel(p.paint(), 110, 10)
        p.call('rv_dom_svg_style_element_set_disabled', [p.pointer, ctypes.c_int32], n['style'], 0)
        set_string('svg_style_element', n['style'], 'media', 'print')
        media = p.pixel(p.paint(), 110, 10)
        set_string('svg_style_element', n['style'], 'media', 'all')
        set_string('svg_style_element', n['style'], 'title', 'renamed')
        state['style'].update(disabledPaint=disabled, printMediaPaint=media, restoredPaint=p.pixel(p.paint(), 110, 10), changedTitle=p.attribute(n['style'], 'title'))

        # SVGImageElement
        image_href = animated_string('rv_dom_svg_image_element_get_href', n['image'])
        state['image'] = dict(crossOrigin=string('svg_image_element', n['image'], 'cross_origin'), href=base(image_href))
        set_string('svg_image_element', n['image'], 'cross_origin', 'anonymous')
        state['image']['anonymous'] = string('svg_image_element', n['image'], 'cross_origin')
        set_string('svg_image_element', n['image'], 'cross_origin', 'bogus')
        state['image']['invalidKeyword'] = string('svg_image_element', n['image'], 'cross_origin')
        set_string('svg_image_element', n['image'], 'cross_origin', None)
        state['image']['cleared'] = string('svg_image_element', n['image'], 'cross_origin')
        image_lengths = {}
        for field in ['x', 'y', 'width', 'height']:
            image_lengths[field] = p.length('svg_image_element', n['image'], field)[1]
        state['image']['geometry'] = [p.read('svg_length', image_lengths[field], 'value') for field in ['x', 'y', 'width', 'height']]
        aspect_animated = p.object('rv_dom_svg_image_element_get_preserve_aspect_ratio', [p.pointer], [n['image']], 'svg_animated_preserve_aspect_ratio')
        aspect = p.property('svg_animated_preserve_aspect_ratio', aspect_animated, 'base_val', 'svg_preserve_aspect_ratio')
        aspect_readonly = p.property('svg_animated_preserve_aspect_ratio', aspect_animated, 'anim_val', 'svg_preserve_aspect_ratio')
        state['image']['align'] = p.read('svg_preserve_aspect_ratio', aspect, 'align', p.short)
        p.exception('rv_dom_svg_preserve_aspect_ratio_set_align', [p.pointer, p.short], [aspect_readonly, 6], 'NoModificationAllowedError')
        state['image']['readonlyAlign'] = 'NoModificationAllowedError'
        p.call('rv_dom_svg_preserve_aspect_ratio_set_align', [p.pointer, p.short], aspect, 6)
        meet = p.paint()
        state['image']['meetPaint'] = [p.pixel(meet, 2, 110), p.pixel(meet, 20, 110)]
        p.call('rv_dom_svg_preserve_aspect_ratio_set_align', [p.pointer, p.short], aspect, 1)
        p.set_length(image_lengths['x'], 10)
        moved = p.paint()
        state['image']['movedPaint'] = [p.pixel(moved, 5, 110), p.pixel(moved, 45, 110)]
        p.set_length(image_lengths['x'], 0)

        set_base(image_href, 'https://fixture.test/missing.png')
        failed = settle()
        state['image']['networkErrorPaint'] = p.pixel(failed, 20, 110)
        set_base(image_href, 'https://fixture.test/broken.png')
        broken = settle()
        state['image']['brokenBytesPaint'] = p.pixel(broken, 20, 110)
        set_base(image_href, 'https://fixture.test/green.png')
        state['image']['greenPaint'] = p.pixel(settle(), 20, 110)

        set_base(image_href, 'https://fixture.test/slow-red.png')
        pending = settle()
        p.expect('slow-red.png' in held, 'held image load stays pending')
        state['image']['pendingPaint'] = p.pixel(pending, 20, 110)
        set_base(image_href, 'https://fixture.test/blue.png')
        state['image']['replacementPaint'] = p.pixel(settle(), 20, 110)
        stale = held.pop('slow-red.png')
        p.expect(finish(stale, IMAGES['red.png'], len(IMAGES['red.png']), b'image/png') == 0, 'stale generation completes exactly once after replacement')
        state['image']['staleCompletionPaint'] = p.pixel(settle(), 20, 110)

        set_base(image_href, 'https://fixture.test/slow-late.png')
        settle()
        p.expect('slow-late.png' in held, 'second held load is pending')
        p.call('rv_node_remove', [p.pointer], n['image'])
        late = held.pop('slow-late.png')
        p.expect(finish(late, IMAGES['red.png'], len(IMAGES['red.png']), b'image/png') == 0, 'late completion after owner removal is accepted once')
        state['image']['removedLatePaint'] = p.pixel(settle(), 20, 110)
        p.expect(not held, 'every resource load reached exactly one terminal completion')
        p.expect(not hasattr(p.library, 'rv_dom_svg_image_element_decode'), 'native SVGImageElement.decode is not bound (H05 blocker)')

        # SVGUseElement and symbol reuse
        use_lengths = {field: p.length('svg_use_element', n['useRect'], field)[1] for field in ['x', 'y', 'width', 'height']}
        symbol_width = p.length('svg_use_element', n['useSymbol'], 'width')[1]
        use_href = animated_string('rv_dom_svg_use_element_get_href', n['useRect'])
        state['use'] = dict(href=base(use_href), geometry=[p.read('svg_length', use_lengths[field], 'value') for field in ['x', 'y', 'width', 'height']])
        p.set_length(use_lengths['x'], 60)
        moved = p.paint()
        state['use']['movedPaint'] = [p.pixel(moved, 55, 10), p.pixel(moved, 75, 10)]
        p.call('rv_dom_element_set_attribute', [p.pointer, Utf8, Utf8], n['green'], b'fill', b'black')
        state['use']['targetEditPaint'] = p.pixel(p.paint(), 75, 10)
        set_base(use_href, '#blueTarget')
        state['use']['hrefPaint'] = p.pixel(p.paint(), 75, 10)
        p.set_length(symbol_width, 20)
        symbol = p.paint()
        state['use']['symbolWidthPaint'] = [p.pixel(symbol, 10, 30), p.pixel(symbol, 30, 30)]
        view_box = p.property('svg_animated_rect', p.object('rv_dom_svg_symbol_element_get_view_box', [p.pointer], [n['symbol']], 'svg_animated_rect'), 'base_val', 'svg_rect')
        p.call('rv_dom_svg_rect_set_width', [p.pointer, p.single], view_box, 20)
        state['use']['symbolViewBoxPaint'] = [p.pixel(p.paint(), 5, 30), p.pixel(p.paint(), 15, 30)]

        # SVGSwitchElement conditional processing through SVGTests
        languages = p.object('rv_dom_svg_graphics_element_get_system_language', [p.pointer], [n['langRect']], 'svg_string_list')
        p.call('rv_dom_svg_string_list_clear', [p.pointer], languages)
        state['switch'] = dict(clearedPaint=p.pixel(p.paint(), 160, 10), attribute=p.attribute(n['langRect'], 'systemLanguage'))

        # SVGForeignObjectElement
        foreign = {field: p.length('svg_foreign_object_element', n['foreign'], field)[1] for field in ['x', 'y', 'width', 'height']}
        state['foreignObject'] = dict(geometry=[p.read('svg_length', foreign[field], 'value') for field in ['x', 'y', 'width', 'height']])
        p.set_length(foreign['width'], 5)
        clipped = p.paint()
        state['foreignObject']['clippedPaint'] = [p.pixel(clipped, 202, 10), p.pixel(clipped, 220, 10)]
        p.set_length(foreign['y'], 30)
        state['foreignObject']['movedPaint'] = [p.pixel(p.paint(), 202, 10), p.pixel(p.paint(), 202, 40)]

        # A qualification is one native value, or a value per sys.platform family where ports differ; "browser" marks
        # a platform whose native value equals the measured browser value.
        family = 'windows' if sys.platform == 'win32' else 'macos' if sys.platform == 'darwin' else 'linux'
        qualifications = {}
        for key, native_only in oracle.get('nativeQualifications', {}).items():
            value = native_only[family] if isinstance(native_only, dict) else native_only
            if value != 'browser':
                qualifications[key] = value
        for key, want in oracle['state'].items():
            got = json.loads(json.dumps(state[key]))
            for field, value in want.items():
                if key + '.' + field in qualifications:
                    continue
                p.expect(got.get(field) == value, key + '.' + field + ' matches measured browser: native ' + repr(got.get(field)) + ' browser ' + repr(value))
        for key, native_only in qualifications.items():
            section, field = key.split('.')
            p.expect(state[section][field] == native_only, 'retained native qualification ' + key + ' (' + family + '): ' + repr(state[section][field]))

        for function, target in [('rv_dom_svg_use_element_get_x', n['useRect']), ('rv_dom_svg_image_element_get_x', n['image']), ('rv_dom_svg_foreign_object_element_get_x', n['foreign']),
                                 ('rv_dom_svga_element_get_target', n['link']), ('rv_dom_svg_script_element_get_href', n['script'])]:
            untouched = p.pointer(123)
            getter = p.bind(function, p.integer, [p.pointer, ctypes.POINTER(p.pointer)])
            p.expect(getter(n['group'], ctypes.byref(untouched)) == -11 and untouched.value == 123, 'subtype rejection preserves output ' + function)
            p.expect(getter(None, ctypes.byref(untouched)) == -1 and untouched.value == 123, 'null rejection preserves output ' + function)
            statuses = []
            worker = threading.Thread(target=lambda: statuses.append(getter(target, ctypes.byref(untouched))))
            worker.start()
            worker.join()
            p.expect(statuses == [-2] and untouched.value == 123, 'off-thread rejection preserves output ' + function)
        buffer, length = ctypes.create_string_buffer(b'#', 1), ctypes.c_int32(77)
        status = p.bind('rv_dom_svga_element_get_hreflang', p.integer, [p.pointer, p.pointer, p.integer, ctypes.POINTER(ctypes.c_int32)])(n['link'], buffer, 1, ctypes.byref(length))
        p.expect(status == -6 and length.value == 2 and buffer.raw == b'#', 'undersized string buffer reports the UTF-8 length and stays untouched: ' + str((status, length.value)))

        kept = link_href
        for owner in [n['root'], n['image'], n['useRect'], n['link'], n['script']]:
            p.watch(owner)
        p.call('rv_host_set_resource_handler', [p.pointer, Handler, p.pointer], p.host, Handler(), None)
        for release, value in list(reversed(p.retained)):
            if value != kept:
                p.bind(release, None, [p.pointer])(value)
                p.retained.remove((release, value))
        p.dispose_host()
        p.collect()
        p.expect_expired()
        set_base(kept, 'https://fixture.test/after')
        p.expect(base(kept) == 'https://fixture.test/after', 'retained animated href stays safely mutable after owner collection')
        print('SVG_RESOURCES_STATE ' + json.dumps(state, sort_keys=True), flush=True)
        print(f'PASS SVG resources: {p.assertions} assertions', flush=True)
        return p.assertions


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    verify(parser.parse_args().native_directory)
