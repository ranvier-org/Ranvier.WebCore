import argparse
import ctypes
import os
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utf8_inputs import Utf8, bind as bind_utf8


def verify(native_directory):
    directory = Path(native_directory).resolve()
    filename = {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')
    search = os.add_dll_directory(str(directory)) if sys.platform == 'win32' else None
    library = ctypes.CDLL(str(directory / filename))
    pointer, integer, single = ctypes.c_void_p, ctypes.c_int32, ctypes.c_float
    retained, watches = [], []
    assertions = 0

    def bind(name, result, arguments):
        return bind_utf8(library, name, result, arguments)

    def expect(condition, label):
        nonlocal assertions
        assertions += 1
        if not condition:
            raise AssertionError(label)

    def call(name, arguments, *values):
        status = bind(name, integer, arguments)(*values)
        expect(status == 0, name + ': status ' + str(status))

    def handle(name, arguments, values, release='rv_node_release'):
        result = pointer()
        call(name, arguments + [ctypes.POINTER(pointer)], *values, ctypes.byref(result))
        expect(bool(result.value), name + ': nonnull')
        retained.append((release, result.value))
        return result.value

    def text(name, arguments, *values):
        buffer, length = ctypes.create_string_buffer(8192), integer()
        call(name, arguments + [pointer, integer, ctypes.POINTER(integer)], *values, buffer, len(buffer), ctypes.byref(length))
        return None if length.value < 0 else buffer.value.decode()

    def document():
        result = bind('rv_host_document', pointer, [pointer])(host)
        expect(bool(result), 'actual frame document')
        retained.append(('rv_node_release', result))
        return result

    def node(identifier):
        result = bind('rv_document_get_element_by_id', pointer, [pointer, ctypes.c_char_p])(host, identifier.encode())
        expect(bool(result), 'find ' + identifier)
        retained.append(('rv_node_release', result))
        return result

    load_svg = bind('rv_host_load_svg', integer, [pointer, ctypes.c_char_p])
    host = bind('rv_host_create', pointer, [integer, integer])(200, 120)
    expect(bool(host), 'SVG document host')
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" id="svg-root" width="200" height="120" viewBox="0 0 200 120">
<rect id="guard" x="10" y="10" width="20" height="20" fill="red"/>
<text id="unicode" x="10" y="50">λ &amp; XML</text>
<script><![CDATA[document.getElementById('guard').setAttribute('x','999');]]></script>
<foreignObject x="60" y="10" width="100" height="60"><div xmlns="http://www.w3.org/1999/xhtml" id="foreign">safe<script>document.getElementById('guard').setAttribute('x','888');</script></div></foreignObject>
</svg>'''.encode()
    try:
        expect(bind('rv_abi_has', integer, [ctypes.c_char_p])(b'svg-document') == 1, 'SVG document MIME capability')
        expect(load_svg(None, svg) == -1, 'null SVG host rejected')
        expect(load_svg(host, None) == -1, 'null SVG markup rejected')
        call('rv_host_load_svg', [pointer, ctypes.c_char_p], host, svg)
        first_document, root, guard = document(), node('svg-root'), node('guard')
        expect(text('rv_dom_document_get_content_type', [pointer], first_document) == 'image/svg+xml', 'actual SVG document MIME')
        expect(text('rv_dom_element_get_namespace_uri', [pointer], root) == 'http://www.w3.org/2000/svg', 'actual SVG root namespace')
        expect(text('rv_dom_node_get_text_content', [pointer], node('unicode')) == 'λ & XML', 'UTF-8 and XML entity parsing')
        expect(text('rv_dom_element_get_namespace_uri', [pointer], node('foreign')) == 'http://www.w3.org/1999/xhtml', 'foreignObject HTML namespace')
        expect(bind('rv_run_loop_cycle', integer, [integer])(20) >= 0, 'SVG document event queue')
        expect(bind('rv_host_update', integer, [pointer])(host) >= 0, 'SVG document rendering update')
        pixels = (ctypes.c_uint8 * (200 * 120 * 4))()
        call('rv_host_paint_rgba', [pointer, pointer, integer], host, pixels, len(pixels))
        close_pixel = list(pixels[(15 * 200 + 15) * 4:(15 * 200 + 15) * 4 + 4])
        expect(close_pixel == [255, 0, 0, 255], 'actual standalone SVG rendered content')
        expect(text('rv_dom_element_get_attribute', [pointer, Utf8], guard, b'x') == '10', 'SVG and foreignObject scripts stay disabled')
        expect(bind('rv_host_scripts_enabled', integer, [pointer])(host) == 0, 'SVG document scripts disabled')
        expect(bind('rv_host_vm_entry_disallowed', integer, [pointer])(host) == 1, 'SVG document VM-entry guard retained')
        errors = []
        def worker():
            errors.append(load_svg(host, svg))
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        expect(errors == [-2], 'wrong-thread SVG load rejected')
        expect(document() == first_document, 'rejected load preserves document identity')
        length = handle('rv_dom_svg_rect_element_get_x', [pointer], [guard], 'rv_dom_svg_animated_length_release')
        base = handle('rv_dom_svg_animated_length_get_base_val', [pointer], [length], 'rv_dom_svg_length_release')
        translate = handle('rv_dom_svgsvg_element_get_current_translate', [pointer], [root], 'rv_dom_svg_point_release')
        for target in [first_document, root, guard]:
            watch = bind('rv_node_watch', pointer, [pointer])(target)
            expect(bool(watch), 'SVG transition weak owner watch')
            watches.append(watch)
        call('rv_host_load_html', [pointer, ctypes.c_char_p], host, b'<div id="html">HTML after SVG</div>')
        html_document = document()
        expect(text('rv_dom_document_get_content_type', [pointer], html_document) == 'text/html', 'HTML MIME path preserved after SVG')
        expect(text('rv_dom_node_get_text_content', [pointer], node('html')) == 'HTML after SVG', 'HTML parser path preserved')
        current = single()
        call('rv_dom_svg_length_get_value', [pointer, ctypes.POINTER(single)], base, ctypes.byref(current))
        expect(current.value == 10, 'retained SVG value survives document replacement')
        call('rv_host_load_svg', [pointer, ctypes.c_char_p], host, svg)
        expect(document() != first_document, 'SVG reload produces a new document')
        expect(text('rv_dom_element_get_attribute', [pointer, Utf8], node('guard'), b'x') == '10', 'SVG after HTML uses XML parser again')
        for release, value in list(reversed(retained)):
            if release == 'rv_node_release':
                bind(release, None, [pointer])(value)
                retained.remove((release, value))
        expect(bind('rv_run_loop_cycle', integer, [integer])(100) >= 0, 'old document disposal events')
        bind('rv_release_memory', None, [])()
        bind('rv_collect_garbage', None, [])()
        for watch in watches:
            expect(bind('rv_watch_alive', integer, [pointer])(watch) == 0, 'replaced SVG document/root/target expires while value retained')
        call('rv_dom_svg_length_get_value', [pointer, ctypes.POINTER(single)], base, ctypes.byref(current))
        expect(current.value == 10, 'detached SVG value remains readable after owner collection')
        call('rv_dom_svg_point_set_x', [pointer, single], translate, 71)
        call('rv_dom_svg_point_set_y', [pointer, single], translate, 83)
        call('rv_dom_svg_point_get_x', [pointer, ctypes.POINTER(single)], translate, ctypes.byref(current))
        expect(current.value == 71, 'survivor currentTranslate remains mutable after root/document collection')
        call('rv_host_load_svg', [pointer, ctypes.c_char_p], host, b'<svg xmlns="http://www.w3.org/2000/svg"><g></svg>')
        malformed_document = document()
        malformed_root = handle('rv_dom_document_get_document_element', [pointer], [malformed_document])
        expect(text('rv_dom_document_get_content_type', [pointer], malformed_document) == 'image/svg+xml', 'malformed XML keeps SVG MIME')
        expect(text('rv_dom_node_get_node_name', [pointer], malformed_root) == 'html', 'engine XML parser produces its actual error document')
        expect('Opening and ending tag mismatch' in text('rv_dom_node_get_text_content', [pointer], malformed_root), 'malformed XML exposes actual engine parser error')
        expect(bind('rv_host_scripts_enabled', integer, [pointer])(host) == 0 and bind('rv_host_vm_entry_disallowed', integer, [pointer])(host) == 1, 'parser-error document preserves script and VM guards')
        call('rv_host_load_html', [pointer, ctypes.c_char_p], host, b'<div id="recovered">recovered after XML error</div>')
        expect(text('rv_dom_node_get_text_content', [pointer], node('recovered')) == 'recovered after XML error', 'HTML load recovers after XML parser error')
    finally:
        for release, value in reversed(retained):
            bind(release, None, [pointer])(value)
        bind('rv_host_destroy', None, [pointer])(host)
        for watch in watches:
            bind('rv_watch_release', None, [pointer])(watch)
        if search:
            search.close()
    print(f'PASS SVG documents: {assertions} assertions', flush=True)
    return assertions


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    verify(parser.parse_args().native_directory)
