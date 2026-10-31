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
    pointer, integer, unsigned, string = ctypes.c_void_p, ctypes.c_int32, ctypes.c_uint32, ctypes.c_char_p
    retained = []
    assertions = 0

    def bind(name, returns, arguments):
        return bind_utf8(library, name, returns, arguments)

    def expect(condition, label):
        nonlocal assertions
        assertions += 1
        if not condition:
            raise AssertionError(label)

    def call(name, arguments, *values):
        status = bind(name, integer, arguments)(*values)
        expect(status == 0, name + ': status ' + str(status))

    def handle(name, arguments, values, release):
        result = pointer()
        call(name, arguments + [ctypes.POINTER(pointer)], *values, ctypes.byref(result))
        expect(bool(result.value), name + ': non-null handle')
        retained.append((release, result.value))
        return result.value

    def text(name, target):
        buffer, length = ctypes.create_string_buffer(4096), integer()
        call(name, [pointer, pointer, integer, ctypes.POINTER(integer)], target, buffer, len(buffer), ctypes.byref(length))
        expect(length.value >= 0, name + ': non-null text')
        return buffer.raw[:length.value].decode('utf-8')

    host = bind('rv_host_create', pointer, [integer, integer])(320, 240)
    expect(bool(host), 'host creation')
    try:
        body = bind('rv_document_body', pointer, [pointer])(host)
        retained.append(('rv_node_release', body))
        css = b'@keyframes c11-raw { from {width:20px} 25% {width:60px} to {width:100px} }'
        markup = b'<style id="first">' + css + b'</style><style id="copy">' + css + b'</style>'
        markup += b'<style>#probe {width:12px;animation:c11-raw 100s linear -25s 1 normal both paused}</style><div id="probe"></div>'
        call('rv_dom_element_set_inner_html', [pointer, Utf8], body, markup)
        find = bind('rv_document_get_element_by_id', pointer, [pointer, string])
        first, copy, probe = [find(host, name) for name in [b'first', b'copy', b'probe']]
        for node in [first, copy, probe]:
            expect(bool(node), 'fixture element')
            retained.append(('rv_node_release', node))

        def keyframes(style):
            sheet = handle('rv_dom_html_style_element_get_sheet', [pointer], [style], 'rv_dom_style_sheet_release')
            rules = handle('rv_dom_css_style_sheet_get_css_rules', [pointer], [sheet], 'rv_dom_css_rule_list_release')
            return sheet, handle('rv_dom_css_rule_list_item', [pointer, unsigned], [rules, 0], 'rv_dom_css_rule_release')

        sheet, frames = keyframes(first)
        _, copied_frames = keyframes(copy)
        middle = handle('rv_dom_css_keyframes_rule_find_rule', [pointer, Utf8], [frames, b'25%'], 'rv_dom_css_rule_release')
        copied_middle = handle('rv_dom_css_keyframes_rule_find_rule', [pointer, Utf8], [copied_frames, b'25%'], 'rv_dom_css_rule_release')
        declaration = handle('rv_dom_css_keyframe_rule_get_style', [pointer], [middle], 'rv_dom_css_style_declaration_release')
        copied_text = text('rv_dom_css_rule_get_css_text', copied_middle)
        call('rv_node_remove_child', [pointer, pointer], body, copy)

        def width():
            call('rv_host_update', [pointer], host)
            buffer, length = ctypes.create_string_buffer(64), integer()
            call('rv_element_computed_style', [pointer, string, pointer, integer, ctypes.POINTER(integer)],
                 probe, b'width', buffer, len(buffer), ctypes.byref(length))
            return buffer.raw[:length.value].decode('utf-8')

        expect(width() == '60px', 'paused 25% starts at the middle keyframe')
        call('rv_dom_css_keyframe_rule_set_key_text', [pointer, Utf8], middle, b'50%')
        expect(text('rv_dom_css_keyframe_rule_get_key_text', middle) == '50%', 'offset metadata changed')
        actual = width()
        expect(actual == '40px', 'offset edit must invalidate paused animation: expected 40px, got ' + actual)
        expect(text('rv_dom_css_keyframe_rule_get_key_text', copied_middle) == '25%', 'other stylesheet retains original offset')
        call('rv_dom_css_keyframe_rule_set_key_text', [pointer, Utf8], middle, b'invalid')
        expect(text('rv_dom_css_keyframe_rule_get_key_text', middle) == '50%', 'invalid offset is a no-op in pinned WebCore')
        expect(width() == '40px', 'invalid offset preserves animation output')
        call('rv_dom_css_style_declaration_set_property', [pointer, Utf8, Utf8, Utf8], declaration, b'width', b'140px', b'')
        expect(width() == '80px', 'declaration edit changes paused animation')
        expect(text('rv_dom_css_rule_get_css_text', copied_middle) == copied_text, 'other stylesheet retains original declarations')
        call('rv_dom_css_keyframes_rule_append_rule', [pointer, Utf8], frames, b'50% {width:180px}')
        expect(width() == '100px', 'duplicate last offset changes paused animation')
        call('rv_dom_css_keyframes_rule_delete_rule', [pointer, Utf8], frames, b'50%')
        expect(width() == '80px', 'delete duplicate restores earlier offset')
        call('rv_dom_css_keyframes_rule_delete_rule', [pointer, Utf8], frames, b'50%')
        expect(width() == '40px', 'delete final middle offset changes interpolation')
        parent = pointer(42)
        call('rv_dom_css_rule_get_parent_rule', [pointer, ctypes.POINTER(pointer)], middle, ctypes.byref(parent))
        expect(not parent.value, 'deleted keyframe has no parent')
        call('rv_dom_css_keyframe_rule_set_key_text', [pointer, Utf8], middle, b'75%')
        expect(text('rv_dom_css_keyframe_rule_get_key_text', middle) == '75%', 'detached keyframe offset stays editable')
        expect(width() == '40px', 'detached keyframe edit preserves active animation')
        setter = bind('rv_dom_css_keyframe_rule_set_key_text', integer, [pointer, Utf8])
        expect(setter(None, b'25%') == -1, 'null target rejected')
        expect(setter(middle, None) == -1, 'null key text rejected')
        expect(setter(frames, b'25%') == -11, 'wrong interface rejected')
        statuses = []
        worker = threading.Thread(target=lambda: statuses.append(setter(middle, b'25%')))
        worker.start()
        worker.join()
        expect(statuses == [-2], 'wrong thread rejected')
        expect(text('rv_dom_css_keyframe_rule_get_key_text', middle) == '75%', 'failed calls preserve detached offset')
        call('rv_dom_css_keyframes_rule_set_name', [pointer, Utf8], frames, b'c11-renamed')
        expect(width() == '12px', 'renaming keyframes invalidates the old animation name')
        call('rv_element_set_style', [pointer, string, string, integer], probe, b'animation-name', b'c11-renamed', 0)
        expect(width() == '40px', 'new animation name resolves the renamed keyframes')
        call('rv_dom_css_style_sheet_delete_rule', [pointer, unsigned], sheet, 0)
        expect(width() == '12px', 'deleting the complete keyframes rule invalidates its animation')
    finally:
        for release, value in reversed(retained):
            if value:
                bind(release, None, [pointer])(value)
        bind('rv_host_destroy', None, [pointer])(host)
        if search:
            search.close()
    print(f'PASS keyframe rule effects: {assertions} assertions; retained handles released')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    verify(parser.parse_args().native_directory)
