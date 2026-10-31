import argparse
import ctypes
import math
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utf8_inputs import Utf8, bind as bind_utf8


def verify(native_directory):
    directory = Path(native_directory).resolve()
    filename = {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')
    search = os.add_dll_directory(str(directory)) if sys.platform == 'win32' else None
    library = ctypes.CDLL(str(directory / filename))
    pointer, integer, unsigned, number, string = ctypes.c_void_p, ctypes.c_int32, ctypes.c_uint32, ctypes.c_double, ctypes.c_char_p
    assertions, failures, fixture_number = 0, [], 0

    class Span(ctypes.Structure):
        _fields_ = [('data', pointer), ('length', integer)]

    class InputValue(ctypes.Structure):
        _fields_ = [('present', integer), ('tag', integer), ('value', pointer), ('text', Span)]

    class InputValues(ctypes.Structure):
        _fields_ = [('present', integer), ('count', integer), ('items', ctypes.POINTER(InputValue))]

    class MaybeValue(ctypes.Structure):
        _fields_ = [('present', integer), ('tag', integer), ('undefined', integer), ('value', pointer)]

    def bind(name, result, arguments):
        return bind_utf8(library, name, result, arguments)

    def expect(condition, label):
        nonlocal assertions
        assertions += 1
        if not condition:
            raise AssertionError(label)

    class Fixture:
        def __init__(self, custom=False, important=False):
            nonlocal fixture_number
            fixture_number += 1
            self.references, self.buffers = [], []
            self.host = bind('rv_host_create', pointer, [integer, integer])(320, 240)
            expect(bool(self.host), 'create declared-map host')
            try:
                self.body = self.own(bind('rv_document_body', pointer, [pointer])(self.host), 'rv_node_release')
                self.document = self.handle('rv_dom_node_get_owner_document', [pointer], self.body, release='rv_node_release')
                width = 'var(--extent)' if custom else '30px'
                priority = '!important' if important else ''
                css = '.probe {width:15px;height:7px;margin:0;--extent:15px}'
                css += f'.probe {{width:{width};height:10px;margin:1px 2px;--extent:30px{priority};--tone:red}}'
                css += '#never-' + str(fixture_number) + ' {color:rgb(1,2,3)}'
                markup = f'<style id="first">{css}</style><style id="copy">{css}</style><div id="item" class="probe"></div>'
                self.call('rv_dom_element_set_inner_html', [pointer, Utf8], self.body, markup.encode('utf-8'))
                self.nodes = {}
                for name in ['first', 'copy', 'item']:
                    raw = bind('rv_document_get_element_by_id', pointer, [pointer, string])(self.host, name.encode('ascii'))
                    self.nodes[name] = self.own(raw, 'rv_node_release')
                self.first = self.declared(self.nodes['first'])
                self.copy = self.declared(self.nodes['copy'])
                self.original = self.sheet_text(self.first)
                self.copied = self.sheet_text(self.copy)
                expect(self.original == self.copied, 'identical stylesheet pair before mutation')
                self.call('rv_node_remove_child', [pointer, pointer], self.body, self.nodes['copy'])
                expect(self.rect()[2:] == (30.0, 10.0), 'active owning rule controls initial geometry')
            except BaseException:
                self.close()
                raise

        def own(self, raw, release):
            expect(bool(raw), release + ': nonnull handle')
            self.references.append([release, raw])
            return raw

        def drop(self, reference):
            if reference[1]:
                bind(reference[0], None, [pointer])(reference[1])
                reference[1] = None

        def close(self):
            for reference in reversed(self.references):
                self.drop(reference)
            if self.host:
                bind('rv_host_destroy', None, [pointer])(self.host)
                self.host = None

        def data(self, value):
            encoded = value.encode('utf-8')
            buffer = ctypes.create_string_buffer(encoded)
            self.buffers.append(buffer)
            return ctypes.cast(buffer, pointer), len(encoded)

        def call(self, name, arguments, *values):
            status = bind(name, integer, arguments)(*values)
            expect(status == 0, name + ': status ' + str(status))

        def handle(self, name, arguments, *values, release):
            result = pointer()
            self.call(name, arguments + [ctypes.POINTER(pointer)], *values, ctypes.byref(result))
            return self.own(result.value, release)

        def text(self, name, target):
            buffer, length = ctypes.create_string_buffer(8192), integer()
            self.call(name, [pointer, pointer, integer, ctypes.POINTER(integer)], target, buffer, len(buffer), ctypes.byref(length))
            expect(length.value >= 0, name + ': nonnull text')
            return buffer.raw[:length.value].decode('utf-8')

        def declared(self, style):
            sheet = self.handle('rv_dom_html_style_element_get_sheet', [pointer], style, release='rv_dom_style_sheet_release')
            rules = self.handle('rv_dom_css_style_sheet_get_css_rules', [pointer], sheet, release='rv_dom_css_rule_list_release')
            rule = self.handle('rv_dom_css_rule_list_item', [pointer, unsigned], rules, 1, release='rv_dom_css_rule_release')
            map_value = self.handle('rv_dom_css_style_rule_get_style_map', [pointer], rule, release='rv_dom_style_property_map_read_only_release')
            declaration = self.handle('rv_dom_css_style_rule_get_style', [pointer], rule, release='rv_dom_css_style_declaration_release')
            return sheet, rules, rule, map_value, declaration

        def sheet_text(self, owner):
            _, rules, _, _, _ = owner
            count = unsigned()
            self.call('rv_dom_css_rule_list_get_length', [pointer, ctypes.POINTER(unsigned)], rules, ctypes.byref(count))
            expect(count.value == 3, 'complete fixture rule count')
            result = []
            for index in range(count.value):
                rule = self.handle('rv_dom_css_rule_list_item', [pointer, unsigned], rules, index, release='rv_dom_css_rule_release')
                result.append(self.text('rv_dom_css_rule_get_css_text', rule))
            return tuple(result)

        def read(self, owner, name):
            result = MaybeValue()
            self.call('rv_dom_style_property_map_read_only_get', [pointer, pointer, pointer, integer, ctypes.POINTER(MaybeValue)],
                      owner[3], self.document, *self.data(name), ctypes.byref(result))
            try:
                expect(result.present == 1 and result.tag in [1, 2], 'declared get has valid result tag')
                if result.tag == 1:
                    expect(result.undefined == 0 and not result.value, 'undefined branch owns no value')
                    return None
                expect(bool(result.value), 'declared typed value is nonnull')
                return self.text('rv_dom_css_style_value_to_string', result.value)
            finally:
                bind('rv_dom_union_undefined_or_css_style_value_release', None, [ctypes.POINTER(MaybeValue)])(ctypes.byref(result))

        def set(self, name, text, typed=False, map_value=None):
            if typed:
                value = self.handle('rv_dom_css_style_value_parse', [pointer, pointer, integer, pointer, integer],
                                    self.document, *self.data(name), *self.data(text), release='rv_dom_css_style_value_release')
                item = InputValue(1, 1, value, Span())
            else:
                item = InputValue(1, 2, None, Span(*self.data(text)))
            items = (InputValue * 1)(item)
            values = InputValues(1, 1, items)
            return bind('rv_dom_style_property_map_set', integer, [pointer, pointer, pointer, integer, ctypes.POINTER(InputValues)])(
                self.first[3] if map_value is None else map_value, self.document, *self.data(name), ctypes.byref(values))

        def delete(self, name):
            self.call('rv_dom_style_property_map_delete', [pointer, pointer, pointer, integer], self.first[3], self.document, *self.data(name))

        def priority(self, owner, name):
            buffer, length = ctypes.create_string_buffer(128), integer()
            self.call('rv_dom_css_style_declaration_get_property_priority', [pointer, Utf8, pointer, integer, ctypes.POINTER(integer)],
                      owner[4], name.encode('utf-8'), buffer, len(buffer), ctypes.byref(length))
            return buffer.raw[:length.value].decode('utf-8')

        def rect(self):
            self.call('rv_host_update', [pointer], self.host)
            result = [number() for _ in range(4)]
            self.call('rv_element_rect', [pointer] + [ctypes.POINTER(number)] * 4, self.nodes['item'], *(ctypes.byref(value) for value in result))
            values = tuple(value.value for value in result)
            expect(all(math.isfinite(value) for value in values), 'declared layout is finite')
            return values

        def unchanged_copy(self):
            expect(self.sheet_text(self.copy) == self.copied, 'complete cache-sharing stylesheet remains unchanged')
            expect(self.read(self.copy, 'height') == '10px', 'copy retains height')
            expect(self.read(self.copy, '--extent') == '30px', 'copy retains custom value')
            expect(self.read(self.copy, 'margin-left') == '2px', 'copy retains margin')

        def invalid_preserves(self):
            before, copied, geometry = self.sheet_text(self.first), self.sheet_text(self.copy), self.rect()
            expect(self.set('width', 'not-a-width') == -3, 'invalid typed-map value raises engine exception')
            buffer, length = ctypes.create_string_buffer(128), integer()
            self.call('rv_last_exception', [integer, pointer, integer, ctypes.POINTER(integer)], 0, buffer, len(buffer), ctypes.byref(length))
            expect(buffer.raw[:length.value] == b'TypeError', 'invalid mutation reports exact TypeError')
            expect(self.sheet_text(self.first) == before, 'invalid mutation preserves complete owning stylesheet')
            expect(self.sheet_text(self.copy) == copied, 'invalid mutation preserves complete copied stylesheet')
            expect(self.rect() == geometry, 'invalid mutation preserves actual layout')

        def identity(self):
            current = self.handle('rv_dom_css_rule_list_item', [pointer, unsigned], self.first[1], 1, release='rv_dom_css_rule_release')
            current_map = self.handle('rv_dom_css_style_rule_get_style_map', [pointer], current, release='rv_dom_style_property_map_read_only_release')
            expect(current == self.first[2], 'COW preserves owning rule wrapper identity')
            expect(current_map == self.first[3], 'COW preserves retained map identity')

    def mutator_case(name):
        fixture = Fixture(custom=name in ['setCustomProperty', 'removeCustomProperty'])
        try:
            initial = fixture.rect()
            fixture.invalid_preserves()
            if name == 'setProperty':
                expect(fixture.set('width', '44px', typed=True) == 0, 'setProperty succeeds')
                expect(fixture.read(fixture.first, 'width') == '44px', 'setProperty edits owning rule after COW')
                expect(fixture.rect()[2:] == (44.0, 10.0), 'setProperty changes actual owning geometry')
            elif name == 'setShorthandProperty':
                expect(fixture.set('margin', '5px 6px') == 0, 'setShorthandProperty succeeds')
                expect(fixture.read(fixture.first, 'margin-left') == '6px', 'shorthand edits owning left margin')
                expect(fixture.read(fixture.first, 'margin-top') == '5px', 'shorthand edits owning top margin')
                changed = fixture.rect()
                expect(abs(changed[0] - initial[0] - 4) < 0.01, 'shorthand changes actual margin offset')
            elif name == 'setCustomProperty':
                expect(fixture.set('--extent', '44px', typed=True) == 0, 'setCustomProperty succeeds')
                expect(fixture.read(fixture.first, '--extent') == '44px', 'custom setter edits owning rule after COW')
                expect(fixture.rect()[2:] == (44.0, 10.0), 'custom setter changes actual var-dependent geometry')
            elif name == 'removeProperty':
                fixture.delete('width')
                expect(fixture.read(fixture.first, 'width') is None, 'removeProperty deletes owning declaration')
                expect(fixture.rect()[2:] == (15.0, 10.0), 'property removal exposes lower-priority width')
            elif name == 'removeCustomProperty':
                fixture.delete('--extent')
                expect(fixture.read(fixture.first, '--extent') is None, 'removeCustomProperty deletes owning declaration')
                expect(fixture.rect()[2:] == (15.0, 10.0), 'custom removal exposes lower-priority var value')
            else:
                fixture.call('rv_dom_style_property_map_clear', [pointer], fixture.first[3])
                size = unsigned(99)
                fixture.call('rv_dom_style_property_map_read_only_get_size', [pointer, ctypes.POINTER(unsigned)], fixture.first[3], ctypes.byref(size))
                expect(size.value == 0, 'clear empties owning map after COW')
                expect(fixture.rect()[2:] == (15.0, 7.0), 'clear exposes lower-priority dimensions')
            changed = fixture.sheet_text(fixture.first)
            expect(changed != fixture.original, name + ': complete owning stylesheet changes')
            expect(changed[0] == fixture.original[0] and changed[2] == fixture.original[2], name + ': unrelated owning rules unchanged')
            fixture.identity()
            fixture.unchanged_copy()
            fixture.invalid_preserves()
        finally:
            fixture.close()

    def priority_case():
        fixture = Fixture(custom=True, important=True)
        try:
            expect(fixture.priority(fixture.first, '--extent') == 'important', 'declared custom property starts important')
            expect(fixture.set('--extent', '44px', typed=True) == 0, 'typed custom map set replaces important declaration')
            actual = fixture.read(fixture.first, '--extent')
            priority = fixture.priority(fixture.first, '--extent')
            expect(actual == '44px', f'typed map set replaces important value: expected44px, actual{actual}, priority{priority}')
            expect(fixture.priority(fixture.first, '--extent') == '', 'typed map set removes old important priority')
            expect(fixture.rect()[2:] == (44.0, 10.0), 'priority removal reaches actual var-dependent geometry')
            fixture.call('rv_dom_css_style_declaration_set_property', [pointer, Utf8, Utf8, Utf8],
                         fixture.first[4], b'--extent', b'44px', b'important')
            expect(fixture.priority(fixture.first, '--extent') == 'important', 'same-value declared control restores important priority')
            geometry = fixture.rect()
            expect(fixture.set('--extent', '44px', typed=True) == 0, 'same-value declared typed assignment succeeds')
            expect(fixture.read(fixture.first, '--extent') == '44px', 'same-value declared assignment preserves value')
            expect(fixture.priority(fixture.first, '--extent') == '', 'same-value declared assignment clears important')
            expect(fixture.rect() == geometry, 'same-value declared assignment preserves actual geometry')
            expect(fixture.priority(fixture.copy, '--extent') == 'important', 'copied declaration keeps important priority')
            fixture.unchanged_copy()
            fixture.invalid_preserves()
        finally:
            fixture.close()

    def inline_priority_case():
        fixture = Fixture(custom=True, important=True)
        try:
            fixture.call('rv_dom_css_style_declaration_set_property', [pointer, Utf8, Utf8, Utf8],
                         fixture.first[4], b'--extent', b'30px', b'')
            expect(fixture.priority(fixture.first, '--extent') == '', 'inline control removes competing stylesheet importance')
            owning_before = fixture.sheet_text(fixture.first)
            target = fixture.nodes['item']
            inline = fixture.handle('rv_dom_html_element_get_attribute_style_map', [pointer], target, release='rv_dom_style_property_map_read_only_release')
            declaration = fixture.handle('rv_dom_html_element_get_style', [pointer], target, release='rv_dom_css_style_declaration_release')
            owner = (None, None, None, inline, declaration)
            fixture.call('rv_element_set_style', [pointer, string, string, integer], target, b'--extent', b'30px', 1)
            expect(fixture.priority(owner, '--extent') == 'important', 'inline custom property starts important')
            expect(fixture.set('--extent', '44px', typed=True, map_value=inline) == 0, 'typed inline custom map assignment succeeds')
            actual = fixture.read(owner, '--extent')
            priority = fixture.priority(owner, '--extent')
            expect(actual == '44px', f'typed inline map replaces important value: expected44px, actual{actual}, priority{priority}')
            expect(fixture.priority(owner, '--extent') == '', 'typed inline map removes old important priority')
            expect(fixture.rect()[2:] == (44.0, 10.0), 'typed inline assignment reaches actual geometry')
            fixture.call('rv_element_set_style', [pointer, string, string, integer], target, b'--extent', b'44px', 1)
            expect(fixture.priority(owner, '--extent') == 'important', 'same-value inline control restores important priority')
            geometry = fixture.rect()
            expect(fixture.set('--extent', '44px', typed=True, map_value=inline) == 0, 'same-value inline typed assignment succeeds')
            expect(fixture.read(owner, '--extent') == '44px', 'same-value inline assignment preserves value')
            expect(fixture.priority(owner, '--extent') == '', 'same-value inline assignment clears important')
            expect(fixture.rect() == geometry, 'same-value inline assignment preserves actual geometry')
            expect(fixture.sheet_text(fixture.first) == owning_before, 'inline assignment leaves complete owning stylesheet unchanged')
            expect(fixture.priority(fixture.copy, '--extent') == 'important', 'inline control preserves copied stylesheet importance')
            fixture.unchanged_copy()
        finally:
            fixture.close()

    def expired_owner_case():
        fixture = Fixture(custom=True)
        try:
            retained_map = fixture.first[3]
            expect(fixture.read(fixture.first, '--extent') == '30px', 'weak-owner map starts with real declarations')
            fixture.call('rv_node_remove_child', [pointer, pointer], fixture.body, fixture.nodes['first'])
            keep = [reference for reference in fixture.references if reference[1] in [retained_map, fixture.document]]
            expect(len(keep) == 2, 'weak-owner case retains only map and document context handles')
            for reference in fixture.references:
                if reference not in keep:
                    fixture.drop(reference)
            size = unsigned(99)
            checkpoints = []
            for _ in range(4):
                checkpoints.append(bind('rv_host_update', integer, [pointer])(fixture.host) == 0)
                bind('rv_collect_garbage', None, [])()
                checkpoints.append(bind('rv_run_loop_cycle', integer, [integer])(100) >= 0)
                checkpoints.append(bind('rv_dom_style_property_map_read_only_get_size', integer, [pointer, ctypes.POINTER(unsigned)])(
                    retained_map, ctypes.byref(size)) == 0)
                if size.value == 0:
                    break
            expect(all(checkpoints), 'weak-owner update/collection checkpoints run successfully on owning thread')
            expect(size.value == 0, 'released declared rule owner expires while map remains retained')
            expect(fixture.read(fixture.first, 'width') is None, 'expired owner get returns undefined')
            for name, value, status in [('width', '44px', -3), ('margin', '5px 6px', -3), ('--extent', '44px', 0)]:
                expect(fixture.set(name, value) == status, 'expired owner setter preserves pinned no-op/error profile: ' + name)
            expect(fixture.read(fixture.first, '--extent') is None, 'expired owner custom setter leaves no declaration')
            fixture.delete('width')
            fixture.delete('--extent')
            fixture.call('rv_dom_style_property_map_clear', [pointer], retained_map)
            fixture.call('rv_dom_style_property_map_read_only_get_size', [pointer, ctypes.POINTER(unsigned)], retained_map, ctypes.byref(size))
            expect(size.value == 0, 'expired owner delete and clear remain safe no-ops')
        finally:
            fixture.close()

    cases = [(name, lambda name=name: mutator_case(name)) for name in [
        'setProperty', 'setShorthandProperty', 'setCustomProperty', 'removeProperty', 'removeCustomProperty', 'clear']]
    cases.append(('custom-important', priority_case))
    cases.append(('inline-custom-important', inline_priority_case))
    cases.append(('expired-weak-owner', expired_owner_case))
    try:
        for name, action in cases:
            try:
                action()
                print('PASS declared COW case: ' + name, flush=True)
            except AssertionError as error:
                failures.append(name + ': ' + str(error))
                print('FAIL declared COW case: ' + failures[-1], flush=True)
    finally:
        if search:
            search.close()
    if failures:
        raise AssertionError('\n'.join(failures))
    if assertions != 2069:
        raise AssertionError(f'Incomplete declared-map acceptance: expected2069 assertions, got{assertions}')
    print(f'PASS declared typed style maps: {assertions} assertions; six fresh-pair mutators; retained handles released', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    verify(parser.parse_args().native_directory)
