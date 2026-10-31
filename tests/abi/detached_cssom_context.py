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
    references = []
    hosts = []
    assertions = 0
    null_argument, wrong_thread, unsupported, wrong_interface = -1, -2, -9, -11

    class Reference:
        def __init__(self, value, release):
            self.value, self.release = value, release
            references.append(self)

    def bind(name, result, arguments):
        return bind_utf8(library, name, result, arguments)

    def expect(condition, label):
        nonlocal assertions
        assertions += 1
        if not condition:
            raise AssertionError(label)

    def value(item):
        return item.value if isinstance(item, Reference) else item

    def call(name, arguments, *items):
        status = bind(name, integer, arguments)(*(value(item) for item in items))
        expect(status == 0, name + ': status ' + str(status))

    def own(raw, release):
        expect(bool(raw), release + ': non-null retained handle')
        return Reference(raw, release)

    def drop(reference):
        if reference.value:
            bind(reference.release, None, [pointer])(reference.value)
            reference.value = None

    def handle(name, arguments, *items, release):
        result = pointer()
        call(name, arguments + [ctypes.POINTER(pointer)], *items, ctypes.byref(result))
        return own(result.value, release)

    def text(name, arguments, *items):
        buffer, length = ctypes.create_string_buffer(8192), integer()
        call(name, arguments + [pointer, integer, ctypes.POINTER(integer)], *items, buffer, len(buffer), ctypes.byref(length))
        expect(length.value >= 0, name + ': non-null string')
        return buffer.raw[:length.value].decode('utf-8')

    def optional(name, target, release):
        result = pointer()
        call(name, [pointer, ctypes.POINTER(pointer)], target, ctypes.byref(result))
        return Reference(result.value, release)

    def create_host():
        host = bind('rv_host_create', pointer, [integer, integer])(320, 240)
        expect(bool(host), 'host creation')
        hosts.append(host)
        return host

    def destroy_host(host):
        bind('rv_host_destroy', None, [pointer])(host)
        hosts.remove(host)

    def watch_document(host):
        body = own(bind('rv_document_body', pointer, [pointer])(host), 'rv_node_release')
        document = handle('rv_dom_node_get_owner_document', [pointer], body, release='rv_node_release')
        watch = own(bind('rv_node_watch', pointer, [pointer])(document.value), 'rv_watch_release')
        drop(document)
        drop(body)
        return watch

    def rule_list(sheet):
        return handle('rv_dom_css_style_sheet_get_css_rules', [pointer], sheet, release='rv_dom_css_rule_list_release')

    def rule_at(rules, index):
        return handle('rv_dom_css_rule_list_item', [pointer, unsigned], rules, index, release='rv_dom_css_rule_release')

    def descriptors(rule):
        return handle('rv_dom_css_position_try_rule_get_style', [pointer], rule, release='rv_dom_css_style_declaration_release')

    def declaration_text(declaration):
        return text('rv_dom_css_style_declaration_get_css_text', [pointer], declaration)

    def rule_text(rule):
        return text('rv_dom_css_rule_get_css_text', [pointer], rule)

    def top(declaration):
        return text('rv_dom_css_position_try_descriptors_get_top', [pointer], declaration)

    def edit(declaration, top_value, left_value):
        call('rv_dom_css_position_try_descriptors_set_top', [pointer, Utf8], declaration, top_value.encode())
        call('rv_dom_css_style_declaration_set_property', [pointer, Utf8, Utf8, Utf8], declaration, b'left', left_value.encode(), b'')
        expect(top(declaration) == top_value, 'typed detached top edit')
        expect(text('rv_dom_css_position_try_descriptors_get_left', [pointer], declaration) == left_value, 'base detached left edit')
        expect(declaration_text(declaration) == f'top: {top_value}; left: {left_value};', 'complete detached declaration text')

    def sheet_text(sheet):
        rules = rule_list(sheet)
        try:
            length = unsigned()
            call('rv_dom_css_rule_list_get_length', [pointer, ctypes.POINTER(unsigned)], rules, ctypes.byref(length))
            result = []
            for index in range(length.value):
                rule = rule_at(rules, index)
                try:
                    result.append(rule_text(rule))
                finally:
                    drop(rule)
            return result
        finally:
            drop(rules)

    host = create_host()
    try:
        body = own(bind('rv_document_body', pointer, [pointer])(host), 'rv_node_release')
        serial = 0

        def fixture(css):
            nonlocal serial
            serial += 1
            identifier = ('detached-' + str(serial)).encode()
            markup = b'<style id="' + identifier + b'">' + css + b'</style>'
            call('rv_dom_element_set_inner_html', [pointer, Utf8], body, markup)
            style = own(bind('rv_document_get_element_by_id', pointer, [pointer, string])(host, identifier), 'rv_node_release')
            sheet = handle('rv_dom_html_style_element_get_sheet', [pointer], style, release='rv_dom_style_sheet_release')
            return style, sheet

        _, sheet = fixture(b'@position-try --retained {top:3px;left:5px}')
        rules = rule_list(sheet)
        rule = rule_at(rules, 0)
        declaration = descriptors(rule)
        expect(top(declaration) == '3px', 'attached typed descriptor reads')
        call('rv_dom_css_style_sheet_delete_rule', [pointer, unsigned], sheet, 0)
        parent = optional('rv_dom_css_rule_get_parent_style_sheet', rule, 'rv_dom_style_sheet_release')
        expect(not parent.value, 'removed rule parent sheet is null')
        drop(parent)
        repeated = descriptors(rule)
        expect(repeated.value == declaration.value, 'retained descriptor identity after deletion')
        drop(repeated)
        expect(top(declaration) == '3px', 'retained typed descriptor after deletion')
        edit(declaration, '29px', '31px')
        expect(rule_text(rule) == '@position-try --retained { top: 29px; left: 31px; }', 'complete retained rule text')
        call('rv_dom_css_style_declaration_set_css_text', [pointer, Utf8], declaration, b'top:43px;left:47px')
        expect(declaration_text(declaration) == 'top: 43px; left: 47px;', 'base cssText replacement survives detachment')
        expect(top(declaration) == '43px', 'typed read observes base cssText replacement')
        drop(rule)
        edit(declaration, '53px', '59px')
        parent_rule = optional('rv_dom_css_style_declaration_get_parent_rule', declaration, 'rv_dom_css_rule_release')
        expect(not parent_rule.value, 'descriptor survives expired parent rule')
        drop(parent_rule)

        _, sheet = fixture(b'@position-try --late {top:7px;left:11px}')
        rule = rule_at(rule_list(sheet), 0)
        call('rv_dom_css_style_sheet_delete_rule', [pointer, unsigned], sheet, 0)
        late = descriptors(rule)
        expect(top(late) == '7px', 'first descriptor acquisition after deletion')
        edit(late, '61px', '67px')

        _, sheet = fixture(b'@media all {@position-try --early-child {top:13px;left:17px} @position-try --late-child {top:19px;left:23px}}')
        group = rule_at(rule_list(sheet), 0)
        children = handle('rv_dom_css_grouping_rule_get_css_rules', [pointer], group, release='rv_dom_css_rule_list_release')
        early_child = rule_at(children, 0)
        early_style = descriptors(early_child)
        call('rv_dom_css_style_sheet_delete_rule', [pointer, unsigned], sheet, 0)
        edit(early_style, '71px', '73px')
        later_children = handle('rv_dom_css_grouping_rule_get_css_rules', [pointer], group, release='rv_dom_css_rule_list_release')
        expect(later_children.value == children.value, 'detached grouping rule list identity')
        late_child = rule_at(later_children, 1)
        late_style = descriptors(late_child)
        expect(top(late_style) == '19px', 'child first materialized after grouping-rule detachment')
        edit(late_style, '79px', '83px')
        child_parent = optional('rv_dom_css_rule_get_parent_rule', late_child, 'rv_dom_css_rule_release')
        expect(child_parent.value == group.value, 'detached child retains grouping parent identity')
        drop(child_parent)

        _, sheet = fixture(b'@media all {@position-try --all-late {top:89px;left:97px}}')
        group = rule_at(rule_list(sheet), 0)
        call('rv_dom_css_style_sheet_delete_rule', [pointer, unsigned], sheet, 0)
        children = handle('rv_dom_css_grouping_rule_get_css_rules', [pointer], group, release='rv_dom_css_rule_list_release')
        edit(descriptors(rule_at(children, 0)), '101px', '103px')

        style, old_sheet = fixture(b'@position-try --old-sheet {top:107px;left:109px}')
        call('rv_dom_node_set_text_content', [pointer, Utf8], style, b'.replacement {width:1px}')
        old_owner = optional('rv_dom_style_sheet_get_owner_node', old_sheet, 'rv_node_release')
        expect(not old_owner.value, 'text replacement clears old sheet owner node')
        drop(old_owner)
        first_old_rule = rule_at(rule_list(old_sheet), 0)
        old_style = descriptors(first_old_rule)
        expect(top(old_style) == '107px', 'first rule/style acquisition from ownerless retained sheet')
        edit(old_style, '113px', '127px')

        css = b'@position-try --shared {top:11px;left:13px;width:37px} .d21-anchor{anchor-name:--d21-anchor;width:10px;height:10px} .d21-survivor{position:absolute;position-anchor:--d21-anchor;top:anchor(bottom);left:anchor(left);width:220px;height:10px;position-try-fallbacks:--shared}'
        markup = b'<style id="cow-first">' + css + b'</style><style id="cow-survivor">' + css + b'</style><div style="position:relative;width:160px;height:80px;overflow:hidden"><div class="d21-anchor"></div><div id="survivor" class="d21-survivor"></div></div>'
        call('rv_dom_element_set_inner_html', [pointer, Utf8], body, markup)
        find = bind('rv_document_get_element_by_id', pointer, [pointer, string])
        first_node = own(find(host, b'cow-first'), 'rv_node_release')
        survivor_node = own(find(host, b'cow-survivor'), 'rv_node_release')
        probe = own(find(host, b'survivor'), 'rv_node_release')
        first_sheet = handle('rv_dom_html_style_element_get_sheet', [pointer], first_node, release='rv_dom_style_sheet_release')
        survivor_sheet = handle('rv_dom_html_style_element_get_sheet', [pointer], survivor_node, release='rv_dom_style_sheet_release')
        first_rules = rule_list(first_sheet)
        first_rule = rule_at(first_rules, 0)
        retained_style = descriptors(first_rule)
        survivor_rule = rule_at(rule_list(survivor_sheet), 0)
        survivor_style = descriptors(survivor_rule)
        before_sheet, before_style = sheet_text(survivor_sheet), declaration_text(survivor_style)

        def width():
            call('rv_host_update', [pointer], host)
            call('rv_host_update', [pointer], host)
            return text('rv_element_computed_style', [pointer, string], probe, b'width')

        def fallback_layout():
            call('rv_element_set_style', [pointer, string, string, integer], probe, b'position-try-fallbacks', b'none', 0)
            expect(width() == '220px', 'anchored control without fallback overflows at original width')
            call('rv_element_set_style', [pointer, string, string, integer], probe, b'position-try-fallbacks', b'--shared', 0)
            expect(width() == '37px', 'surviving shared fallback produces actual constrained width')

        def edit_copy(top_value, left_value, width_value):
            call('rv_dom_css_position_try_descriptors_set_top', [pointer, Utf8], retained_style, top_value.encode())
            call('rv_dom_css_style_declaration_set_property', [pointer, Utf8, Utf8, Utf8], retained_style, b'left', left_value.encode(), b'')
            call('rv_dom_css_position_try_descriptors_set_width', [pointer, Utf8], retained_style, width_value.encode())
            expect(top(retained_style) == top_value, 'COW typed top edit')
            expect(text('rv_dom_css_position_try_descriptors_get_width', [pointer], retained_style) == width_value, 'COW typed width edit')
            expect(declaration_text(retained_style) == f'top: {top_value}; left: {left_value}; width: {width_value};', 'complete COW descriptor text')

        fallback_layout()
        call('rv_dom_node_set_text_content', [pointer, Utf8], first_node, b'.first-replaced {}')
        call('rv_node_remove_child', [pointer, pointer], body, first_node)
        for released in [first_node, first_sheet, first_rules]:
            drop(released)
        edit_copy('17px', '19px', '71px')
        repeated_style = descriptors(first_rule)
        expect(repeated_style.value == retained_style.value, 'live detached rule reattaches the same descriptor wrapper')
        drop(repeated_style)
        expect(rule_text(first_rule) == '@position-try --shared { top: 17px; left: 19px; width: 71px; }', 'live detached rule observes complete cloned descriptor edits')
        expect(sheet_text(survivor_sheet) == before_sheet, 'live-rule COW preserves complete surviving stylesheet')
        expect(declaration_text(survivor_style) == before_style, 'live-rule COW preserves surviving descriptor text')
        fallback_layout()
        drop(first_rule)
        expired_parent = optional('rv_dom_css_style_declaration_get_parent_rule', retained_style, 'rv_dom_css_rule_release')
        expect(not expired_parent.value, 'descriptor-only COW phase has no surviving parent rule')
        drop(expired_parent)
        edit_copy('23px', '29px', '83px')
        expect(sheet_text(survivor_sheet) == before_sheet, 'descriptor-only COW preserves complete surviving stylesheet')
        expect(declaration_text(survivor_style) == before_style, 'descriptor-only COW preserves surviving descriptor text')
        fallback_layout()

        typed_setter = bind('rv_dom_css_position_try_descriptors_set_top', integer, [pointer, Utf8])
        expect(typed_setter(None, b'1px') == null_argument, 'typed setter rejects null target')
        expect(typed_setter(retained_style.value, None) == null_argument, 'typed setter rejects null value')
        normal_sheet_style, normal_sheet = fixture(b'.normal {color:red}')
        normal_rule = rule_at(rule_list(normal_sheet), 0)
        normal_style = handle('rv_dom_css_style_rule_get_style', [pointer], normal_rule, release='rv_dom_css_style_declaration_release')
        expect(typed_setter(normal_style.value, b'1px') == wrong_interface, 'typed setter rejects another declaration interface')
        thread_results = []
        worker = threading.Thread(target=lambda: thread_results.append(typed_setter(retained_style.value, b'1px')))
        worker.start()
        worker.join()
        expect(thread_results == [wrong_thread], 'typed setter rejects wrong thread')
        expect(top(retained_style) == '23px', 'checked failures preserve retained typed value')

        _, weak_sheet = fixture(b'@position-try --weak-owner {top:139px;left:149px}')
        weak_rule = rule_at(rule_list(weak_sheet), 0)
        weak_style = descriptors(weak_rule)
        expect(top(weak_style) == '139px', 'weak-owner fixture attached baseline')
        get_style = bind('rv_dom_css_position_try_rule_get_style', integer, [pointer, ctypes.POINTER(pointer)])
        get_top = bind('rv_dom_css_position_try_descriptors_get_top', integer, [pointer, pointer, integer, ctypes.POINTER(integer)])
        output, buffer, length = pointer(), ctypes.create_string_buffer(128), integer()
        expect(get_style(None, ctypes.byref(output)) == null_argument, 'rule getter rejects null target')
        expect(get_style(weak_rule.value, None) == null_argument, 'rule getter rejects null output')
        expect(get_style(normal_rule.value, ctypes.byref(output)) == wrong_interface, 'rule getter rejects another rule interface')
        expect(get_top(None, buffer, len(buffer), ctypes.byref(length)) == null_argument, 'descriptor getter rejects null target')
        expect(get_top(weak_style.value, buffer, len(buffer), None) == null_argument, 'descriptor getter rejects null length')
        expect(get_top(normal_style.value, buffer, len(buffer), ctypes.byref(length)) == wrong_interface, 'descriptor getter rejects another declaration interface')
        getter_statuses = []

        def wrong_thread_getters():
            getter_statuses.append(get_style(weak_rule.value, ctypes.byref(output)))
            getter_statuses.append(get_top(weak_style.value, buffer, len(buffer), ctypes.byref(length)))

        worker = threading.Thread(target=wrong_thread_getters)
        worker.start()
        worker.join()
        if output.value:
            own(output.value, 'rv_dom_css_style_declaration_release')
        expect(getter_statuses == [wrong_thread, wrong_thread], 'gated getters reject wrong thread')
        call('rv_dom_css_style_sheet_delete_rule', [pointer, unsigned], weak_sheet, 0)
        first_document_watch = watch_document(host)
        second_host = create_host()
        second_document_watch = watch_document(second_host)
        before_dead = declaration_text(weak_style)
        for reference in references:
            if reference not in [weak_rule, weak_style, first_document_watch, second_document_watch]:
                drop(reference)
        destroy_host(host)
        watch_alive = bind('rv_watch_alive', integer, [pointer])
        collect = bind('rv_collect_garbage', None, [])
        cycle = bind('rv_run_loop_cycle', integer, [integer])
        for _ in range(4):
            if watch_alive(first_document_watch.value) == 0:
                break
            collect()
            expect(cycle(100) >= 0, 'owner-expiry checkpoint runs on owning thread')
        expect(watch_alive(first_document_watch.value) == 0, 'original document actually expires after collection')
        expect(watch_alive(second_document_watch.value) == 1, 'second document remains alive')
        result, buffer, length = pointer(), ctypes.create_string_buffer(128), integer()
        status = get_style(weak_rule.value, ctypes.byref(result))
        if result.value:
            own(result.value, 'rv_dom_css_style_declaration_release')
        expect(status == unsupported, 'expired weak owner rejects gated rule getter: status ' + str(status))
        status = get_top(weak_style.value, buffer, len(buffer), ctypes.byref(length))
        expect(status == unsupported, 'expired weak owner rejects gated descriptor getter')
        expect(typed_setter(weak_style.value, b'151px') == unsupported, 'expired weak owner rejects gated descriptor setter')
        expect(declaration_text(weak_style) == before_dead, 'expired-owner rejection preserves complete declaration')
        call('rv_host_update', [pointer], second_host)
    finally:
        for reference in reversed(references):
            drop(reference)
        for remaining_host in list(reversed(hosts)):
            destroy_host(remaining_host)
        if search:
            search.close()
    print(f'PASS detached CSSOM settings context: {assertions} assertions; handles released; settings toggle not exercised')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    verify(parser.parse_args().native_directory)
