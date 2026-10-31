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

    class Utf8StringInput(ctypes.Structure):
        _fields_ = [('present', integer), ('data', pointer), ('length', integer)]

    class Descriptor(ctypes.Structure):
        _fields_ = [('size', unsigned), ('name', Utf8StringInput), ('syntax', Utf8StringInput),
                    ('inherits', integer), ('initial_value', Utf8StringInput)]

    def bind(name, returns, arguments):
        return bind_utf8(library, name, returns, arguments)

    def expect(condition, label):
        nonlocal assertions
        assertions += 1
        if not condition:
            raise AssertionError(label)

    def definition(name, syntax=None, inherits=False, initial=None):
        result = Descriptor()
        result.size = ctypes.sizeof(result)
        result.inherits = int(inherits)
        result.buffers = []
        for field, value in [('name', name), ('syntax', syntax), ('initial_value', initial)]:
            if value is not None:
                data = value.encode('utf-8') if isinstance(value, str) else value
                buffer = ctypes.create_string_buffer(data)
                result.buffers.append(buffer)
                setattr(result, field, Utf8StringInput(1, ctypes.cast(buffer, pointer), len(data)))
        return result

    register = bind('rv_dom_css_register_property', integer, [pointer, ctypes.POINTER(Descriptor)])
    host = bind('rv_host_create', pointer, [integer, integer])(320, 240)
    expect(bool(host), 'host creation')
    try:
        expect(bind('rv_abi_version', unsigned, [])() == 54, 'Native46 ABI54 registration transport')
        expect(bind('rv_abi_has', integer, [string])(b'dom-css-register-property') == 1, 'registration capability')
        body = bind('rv_document_body', pointer, [pointer])(host)
        retained.append(('rv_node_release', body))
        document = pointer()
        expect(bind('rv_dom_node_get_owner_document', integer, [pointer, ctypes.POINTER(pointer)])(
            body, ctypes.byref(document)) == 0 and bool(document.value), 'document context')
        retained.append(('rv_node_release', document.value))

        def success(value):
            expect(register(document, ctypes.byref(value)) == 0, 'registration ' + repr(value.buffers[0].value))

        def exception_name():
            buffer, length = ctypes.create_string_buffer(256), integer()
            expect(bind('rv_last_exception', integer, [integer, pointer, integer, ctypes.POINTER(integer)])(
                0, buffer, len(buffer), ctypes.byref(length)) == 0, 'exception name retrieval')
            return buffer.raw[:length.value].decode('utf-8')

        def rejected(value, name):
            expect(register(document, ctypes.byref(value)) == -3, 'engine rejects invalid or duplicate registration')
            expect(exception_name() == name, 'exact registration exception ' + name)

        success(definition('--registered-length', '<length>', False, '20px'))
        rejected(definition('--registered-length', '<length>', False, '20px'), 'InvalidModificationError')
        for name, syntax, initial in [('width', '*', None), ('--', '*', None),
                                      ('--bad-grammar', '<not-a-type>', '1'),
                                      ('--missing-initial', '<length>', None),
                                      ('--empty-initial', '<length>', ''),
                                      ('--invalid-initial', '<length>', 'red'),
                                      ('--dependent-initial', '<length>', '1em'),
                                      ('--nul-initial', '<length>', '10px\0junk'),
                                      ('--nul-syntax', '<length>\0junk', '10px')]:
            rejected(definition(name, syntax, False, initial), 'SyntaxError')
        success(definition('--default-universal'))
        success(definition('--unicode-\u03c0', '<length>', False, '23px'))
        success(definition('--inherited-length', '<length>', True, '11px'))
        success(definition('--isolated-length', '<length>', False, '17px'))

        valid = definition('--valid-input', '*', False, None)
        expect(register(None, ctypes.byref(valid)) == -1, 'null context rejected')
        expect(register(body, ctypes.byref(valid)) == -11, 'wrong context interface rejected')
        expect(register(document, None) == -1, 'null dictionary rejected')
        for field, changes in [('name', {'present': 0}), ('name', {'present': 2}),
                               ('name', {'length': -1}), ('name', {'length': 1, 'data': None}),
                               ('syntax', {'present': 2}), ('syntax', {'length': -1}),
                               ('initial_value', {'present': 1, 'length': -1}),
                               ('initial_value', {'present': 1, 'length': 1, 'data': None})]:
            invalid = definition('--valid-input', '*')
            for key, value in changes.items():
                setattr(getattr(invalid, field), key, value)
            expect(register(document, ctypes.byref(invalid)) == -1, 'invalid dictionary span rejected: ' + field + repr(changes))
        invalid_utf8 = definition('--valid-input', '*', False, b'\xff')
        expect(register(document, ctypes.byref(invalid_utf8)) == -1, 'invalid UTF8 rejected')
        incomplete = definition('--valid-input', '*')
        incomplete.size = Descriptor.inherits.offset
        expect(register(document, ctypes.byref(incomplete)) == -1, 'missing required inherits rejected')
        success(valid)
        statuses = []
        threaded = definition('--other-thread')
        worker = threading.Thread(target=lambda: statuses.append(register(document, ctypes.byref(threaded))))
        worker.start()
        worker.join()
        expect(statuses == [-2], 'owning thread enforced')
        success(threaded)

        def call(name, arguments, *values):
            status = bind(name, integer, arguments)(*values)
            expect(status == 0, name + ': status ' + str(status))

        markup = b'''<style id="sheet">
            @property --from-rule { syntax: "<length>"; inherits: false; initial-value: 29px }
            @property --universal-rule { syntax: "*"; inherits: true }
            @keyframes registered-motion { from { --registered-length:20px; --plain-length:20px }
                to { --registered-length:100px; --plain-length:100px } }
            #registered,#plain { animation:registered-motion 100s linear -50s 1 normal both paused }
            #registered {width:var(--registered-length)} #plain {width:var(--plain-length)}
            #parent {--inherited-length:83px;--isolated-length:83px}
            #inherited {width:var(--inherited-length)} #isolated {width:var(--isolated-length)}
            #initial {width:var(--unicode-\xcf\x80)} #rule-value {width:var(--from-rule)}
            #registered-priority {width:var(--registered-length,21px)}
            #plain-priority {width:var(--plain-priority,21px)}
            #registered-cascade {--registered-length:40px!important;--registered-length:80px;width:var(--registered-length)}
            #plain-cascade {--plain-cascade:40px!important;--plain-cascade:80px;width:var(--plain-cascade)}
            </style><div id="registered"></div><div id="plain"></div>
            <div id="parent"><div id="inherited"></div><div id="isolated"></div></div>
            <div id="initial"></div><div id="rule-value"></div>
            <div id="registered-priority"></div><div id="plain-priority"></div>
            <div id="registered-cascade"></div><div id="plain-cascade"></div>'''
        call('rv_dom_element_set_inner_html', [pointer, Utf8], body, markup)
        find = bind('rv_document_get_element_by_id', pointer, [pointer, string])

        def node(name):
            result = find(host, name)
            expect(bool(result), 'fixture element ' + repr(name))
            retained.append(('rv_node_release', result))
            return result

        def width(element):
            call('rv_host_update', [pointer], host)
            buffer, length = ctypes.create_string_buffer(64), integer()
            call('rv_element_computed_style', [pointer, string, pointer, integer, ctypes.POINTER(integer)],
                 element, b'width', buffer, len(buffer), ctypes.byref(length))
            return buffer.raw[:length.value].decode('utf-8')

        for name, expected in [(b'registered', '60px'), (b'plain', '100px'),
                               (b'inherited', '83px'), (b'isolated', '17px'),
                               (b'initial', '23px'), (b'rule-value', '29px')]:
            expect(width(node(name)) == expected, 'actual custom-property effect ' + repr(name))

        def handle(name, arguments, values, release):
            result = pointer()
            call(name, arguments + [ctypes.POINTER(pointer)], *values, ctypes.byref(result))
            expect(bool(result.value), name + ': non-null result')
            retained.append((release, result.value))
            return result.value

        def text(name, target):
            buffer, length = ctypes.create_string_buffer(1024), integer()
            call(name, [pointer, pointer, integer, ctypes.POINTER(integer)], target, buffer, len(buffer), ctypes.byref(length))
            return None if length.value == -1 else buffer.raw[:length.value].decode('utf-8')

        def property_text(style, member, name):
            buffer, length = ctypes.create_string_buffer(1024), integer()
            call('rv_dom_css_style_declaration_get_property_' + member,
                 [pointer, Utf8, pointer, integer, ctypes.POINTER(integer)],
                 style, name, buffer, len(buffer), ctypes.byref(length))
            return buffer.raw[:length.value].decode('utf-8')

        for element_name, property_name, initial in [(b'registered-priority', b'--registered-length', '20px'),
                                                      (b'plain-priority', b'--plain-priority', '21px')]:
            element = node(element_name)
            declaration = handle('rv_dom_html_element_get_style', [pointer], [element], 'rv_dom_css_style_declaration_release')
            def set_value(value, priority):
                call('rv_dom_css_style_declaration_set_property', [pointer, Utf8, Utf8, Utf8],
                     declaration, property_name, value, priority)
            def state(expected_value, expected_priority, expected_width):
                expect(property_text(declaration, 'value', property_name) == expected_value, 'custom specified value')
                expect(property_text(declaration, 'priority', property_name) == expected_priority, 'custom specified priority')
                expect(width(element) == expected_width, 'custom priority actual cascade')
            set_value(b'40px', b'important')
            state('40px', 'important', '40px')
            set_value(b'80px', b'')
            state('80px', '', '80px')
            set_value(b'80px', b'important')
            state('80px', 'important', '80px')
            set_value(b'80px', b'')
            state('80px', '', '80px')
            set_value(b'90px', b'invalid-priority')
            state('80px', '', '80px')
            set_value(b'var()', b'important')
            state('80px', '', '80px')
            set_value(b'', b'')
            state('', '', initial)
        expect(width(node(b'registered-cascade')) == '40px', 'stylesheet parsing retains earlier important registered property')
        expect(width(node(b'plain-cascade')) == '40px', 'stylesheet parsing retains earlier important unregistered property')

        sheet = handle('rv_dom_html_style_element_get_sheet', [pointer], [node(b'sheet')], 'rv_dom_style_sheet_release')
        rules = handle('rv_dom_css_style_sheet_get_css_rules', [pointer], [sheet], 'rv_dom_css_rule_list_release')
        rule = handle('rv_dom_css_rule_list_item', [pointer, unsigned], [rules, 0], 'rv_dom_css_rule_release')
        for member, expected in [('name', '--from-rule'), ('syntax', '<length>'), ('initial_value', '29px')]:
            expect(text('rv_dom_css_property_rule_get_' + member, rule) == expected, 'readonly @property ' + member)
        inherits = integer(42)
        call('rv_dom_css_property_rule_get_inherits', [pointer, ctypes.POINTER(integer)], rule, ctypes.byref(inherits))
        expect(inherits.value == 0, 'readonly @property inherits')
        universal = handle('rv_dom_css_rule_list_item', [pointer, unsigned], [rules, 1], 'rv_dom_css_rule_release')
        expect(text('rv_dom_css_property_rule_get_initial_value', universal) is None, 'absent @property initialValue remains null')
        retained_initial = text('rv_dom_css_rule_get_css_text', rule)
        call('rv_dom_css_style_sheet_delete_rule', [pointer, unsigned], sheet, 0)
        expect(text('rv_dom_css_rule_get_css_text', rule) == retained_initial, 'retained removed @property preserves serialized descriptors')
        expect(text('rv_dom_css_property_rule_get_initial_value', rule) == '29px', 'retained removed @property getter remains readable')
    finally:
        for release, value in reversed(retained):
            if value:
                bind(release, None, [pointer])(value)
        bind('rv_host_destroy', None, [pointer])(host)
        if search:
            search.close()
    print(f'PASS custom property registration: {assertions} assertions; retained handles released')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    verify(parser.parse_args().native_directory)
