"""H13 URL, URLSearchParams and URLPattern through the generated value-object exports.

Replays tests/fixtures/url-cases.json on the runtime and compares each result with Chromium's in
tests/fixtures/url-oracle.json. A difference passes only when tests/fixtures/url-qualified.json records it with the
runtime's exact value. Also checks searchParams identity and liveness, owned results, argument and thread errors,
and handles held past rv_host_destroy.
"""
import argparse
import ctypes
import json
import os
from pathlib import Path
import sys
import threading

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
ABI = 54
COMPONENTS = ['protocol', 'username', 'password', 'hostname', 'port', 'pathname', 'search', 'hash']
FIELDS = ['href', 'origin', 'protocol', 'username', 'password', 'host', 'hostname', 'port', 'pathname', 'search', 'hash']

pointer, integer, unsigned = ctypes.c_void_p, ctypes.c_int32, ctypes.c_uint32


class Span(ctypes.Structure):
    _fields_ = [('data', pointer), ('length', integer)]


class StringInput(ctypes.Structure):
    _fields_ = [('present', integer), ('data', pointer), ('length', integer)]


class PatternInit(ctypes.Structure):
    _fields_ = [('size', unsigned)] + [(name, StringInput) for name in COMPONENTS + ['base_url']]


class PatternOptions(ctypes.Structure):
    _fields_ = [('size', unsigned), ('ignore_case', integer)]


class Strings(ctypes.Structure):
    _fields_ = [('present', integer), ('count', integer), ('items', ctypes.POINTER(Span))]


class StringSequences(ctypes.Structure):
    _fields_ = [('present', integer), ('count', integer), ('items', ctypes.POINTER(Strings))]


class Pair(ctypes.Structure):
    _fields_ = [('present', integer), ('key', Span), ('value', Span)]


class Pairs(ctypes.Structure):
    _fields_ = [('present', integer), ('count', integer), ('items', ctypes.POINTER(Pair))]


class ParamsInit(ctypes.Structure):
    _fields_ = [('present', integer), ('tag', integer), ('arm0', StringSequences), ('arm1', Pairs), ('arm2', Span)]


class PatternInput(ctypes.Structure):
    _fields_ = [('present', integer), ('tag', integer), ('arm0', Span), ('arm1', ctypes.POINTER(PatternInit))]


class PatternInputs(ctypes.Structure):
    _fields_ = [('present', integer), ('count', integer), ('items', ctypes.POINTER(PatternInput))]


class GroupValue(ctypes.Structure):
    _fields_ = [('present', integer), ('tag', integer), ('arm0', integer), ('arm1', Span)]


class Group(ctypes.Structure):
    _fields_ = [('present', integer), ('key', Span), ('value', GroupValue)]


class Groups(ctypes.Structure):
    _fields_ = [('present', integer), ('count', integer), ('items', ctypes.POINTER(Group))]


class ComponentResult(ctypes.Structure):
    _fields_ = [('size', unsigned), ('input', StringInput), ('groups', ctypes.POINTER(Groups))]


class PatternResult(ctypes.Structure):
    _fields_ = [('size', unsigned), ('inputs', ctypes.POINTER(PatternInputs))] + \
               [(name, ctypes.POINTER(ComponentResult)) for name in COMPONENTS]


def verify(native_directory, record=None):
    directory = Path(native_directory).resolve()
    filename = {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')
    search = os.add_dll_directory(str(directory)) if sys.platform == 'win32' else None
    library = ctypes.CDLL(str(directory / filename))
    cases = json.loads((FIXTURES / 'url-cases.json').read_text(encoding='utf-8'))
    oracle = json.loads((FIXTURES / 'url-oracle.json').read_text(encoding='utf-8'))
    qualified = json.loads((FIXTURES / 'url-qualified.json').read_text(encoding='utf-8'))['differences']
    keep = []  # ctypes buffers that must outlive a call
    assertions = 0
    differences = {}

    def bind(name, arguments, result=integer):
        function = getattr(library, name)
        function.restype, function.argtypes = result, arguments
        return function

    def expect(condition, label):
        nonlocal assertions
        assertions += 1
        if not condition:
            raise AssertionError(label)

    def span(text):
        data = text.encode('utf-8', 'surrogatepass')
        buffer = ctypes.create_string_buffer(data, len(data) + 1)
        keep.append(buffer)
        return ctypes.cast(buffer, pointer), len(data)

    def span_struct(text):
        data, length = span(text)
        return Span(data, length)

    def string_input(text):
        if text is None:
            return StringInput(0, None, 0)
        data, length = span(text)
        return StringInput(1, data, length)

    def read_span(value, present=True):
        if not present or value.length < 0:
            return None
        return ctypes.string_at(value.data, value.length).decode('utf-8', 'surrogatepass') if value.length else ''

    def exception():
        buffer, length = ctypes.create_string_buffer(256), integer()
        bind('rv_last_exception', [integer, pointer, integer, ctypes.POINTER(integer)])(0, buffer, 256, ctypes.byref(length))
        return buffer.raw[:max(length.value, 0)].decode('utf-8')

    def status_error(status, name):
        expect(status in (0, -3), f'{name}: status {status}')
        return None if status == 0 else {'error': exception()}

    def get_string(name, target, *arguments, types=()):
        function = bind(name, [pointer, *types, pointer, integer, ctypes.POINTER(integer)])
        length = integer()
        status = function(target, *arguments, None, 0, ctypes.byref(length))
        if status == 0 and length.value == -1:
            return None
        expect(status in (0, -6, -3), f'{name}: probe status {status}')
        if status == -3:
            return {'error': exception()}
        buffer = ctypes.create_string_buffer(max(length.value, 1))
        status = function(target, *arguments, buffer, len(buffer), ctypes.byref(length))
        expect(status == 0, f'{name}: status {status}')
        return buffer.raw[:length.value].decode('utf-8', 'surrogatepass')

    expect(bind('rv_abi_version', [], integer)() == ABI, f'ABI version {ABI}')
    host = bind('rv_host_create', [integer, integer], pointer)(320, 240)
    expect(bool(host), 'host creation')
    body = bind('rv_document_body', [pointer], pointer)(host)
    document = pointer()
    expect(bind('rv_dom_node_get_owner_document', [pointer, ctypes.POINTER(pointer)])(body, ctypes.byref(document)) == 0, 'document')
    release_node = bind('rv_node_release', [pointer], None)
    release_url = bind('rv_dom_domurl_release', [pointer], None)
    release_params = bind('rv_dom_url_search_params_release', [pointer], None)
    release_pattern = bind('rv_dom_url_pattern_release', [pointer], None)
    release_result = bind('rv_dom_url_pattern_result_release', [ctypes.POINTER(PatternResult)], None)
    release_pairs = bind('rv_dom_sequence_pair_usv_string_and_usv_string_release', [ctypes.POINTER(Pairs)], None)
    release_strings = bind('rv_dom_sequence_usv_string_utf8_release', [ctypes.POINTER(Strings)], None)
    url_args = [pointer, pointer, integer, pointer, integer, ctypes.POINTER(pointer)]
    create_url = bind('rv_dom_domurl_create', url_args)
    parse_url = bind('rv_dom_domurl_parse', url_args)
    can_parse = bind('rv_dom_domurl_can_parse', url_args[:-1] + [ctypes.POINTER(integer)])

    def base_args(base):
        return (None, -1) if base is None else span(base)

    def new_url(text, base=None):
        result = pointer()
        status = create_url(document, *span(text), *base_args(base), ctypes.byref(result))
        error = status_error(status, 'URL constructor')
        return error, result.value

    def snapshot(url):
        return {field: get_string(f'rv_dom_domurl_get_{field}', url) for field in FIELDS}

    def compare(section, index, actual):
        expected = oracle[section][index]
        if actual == expected:
            expect(True, f'{section}[{index}]')
            return
        key = f'{section}[{index}]'
        differences[key] = {'native': actual, 'chromium': expected}
        if record is None:
            expect(key in qualified and qualified[key]['native'] == actual,
                   f'{key}: native {json.dumps(actual)[:400]} != chromium {json.dumps(expected)[:400]}')

    try:
        # URL parsing, relative resolution, URL.parse, URL.canParse and toJSON.
        for index, (text, base) in enumerate(cases['parse']):
            error, url = new_url(text, base)
            parsed, flag = pointer(), integer()
            expect(parse_url(document, *span(text), *base_args(base), ctypes.byref(parsed)) == 0, 'URL.parse status')
            expect(can_parse(document, *span(text), *base_args(base), ctypes.byref(flag)) == 0, 'URL.canParse status')
            actual = {'url': error or snapshot(url), 'canParse': bool(flag.value),
                      'parse': get_string('rv_dom_domurl_get_href', parsed.value) if parsed.value else None,
                      'json': error or get_string('rv_dom_domurl_to_json', url)}
            expect((error is None) == bool(flag.value) == bool(parsed.value), f'parse[{index}]: constructor, parse and canParse agree')
            if url:
                release_url(url)
            if parsed.value:
                release_url(parsed.value)
            compare('parse', index, actual)

        # Setters.
        for index, (href, field, value) in enumerate(cases['setters']):
            error, url = new_url(href)
            expect(error is None, f'setters[{index}]: base URL')
            status = bind(f'rv_dom_domurl_set_{field}', [pointer, pointer, integer])(url, *span(value))
            threw = status_error(status, f'set {field}')
            compare('setters', index, {'threw': threw and threw['error'], 'url': snapshot(url)})
            release_url(url)

        # URLSearchParams.
        create_params = bind('rv_dom_url_search_params_create', [pointer, ctypes.POINTER(ParamsInit), ctypes.POINTER(pointer)])

        def params_init(kind, value):
            init = ParamsInit(1)
            if kind == 'string':
                init.tag, init.arm2 = 3, span_struct(value)
            elif kind == 'record':
                items = (Pair * len(value))(*[Pair(1, span_struct(k), span_struct(v)) for k, v in value])
                keep.append(items)
                init.tag, init.arm1 = 2, Pairs(1, len(value), items)
            else:
                rows = []
                for row in value:
                    strings = (Span * len(row))(*[span_struct(item) for item in row])
                    keep.append(strings)
                    rows.append(Strings(1, len(row), strings))
                items = (Strings * len(rows))(*rows)
                keep.append(items)
                init.tag, init.arm0 = 1, StringSequences(1, len(rows), items)
            return init

        def entries(params):
            result = Pairs()
            expect(bind('rv_dom_url_search_params_entries', [pointer, pointer, ctypes.POINTER(Pairs)])(
                params, document, ctypes.byref(result)) == 0, 'entries status')
            values = [[read_span(result.items[i].key), read_span(result.items[i].value)] for i in range(result.count)]
            release_pairs(ctypes.byref(result))
            expect(result.count == 0 and not result.items, 'entries release clears the container')
            return values

        def optional_value(args):
            return (None, -1) if len(args) < 2 else span(args[1])

        def run(params, op, args):
            if op == 'get':
                return get_string('rv_dom_url_search_params_get', params, *span(args[0]), types=(pointer, integer))
            if op == 'getAll':
                result = Strings()
                expect(bind('rv_dom_url_search_params_get_all', [pointer, pointer, integer, ctypes.POINTER(Strings)])(
                    params, *span(args[0]), ctypes.byref(result)) == 0, 'getAll status')
                values = [read_span(result.items[i]) for i in range(result.count)]
                release_strings(ctypes.byref(result))
                return values
            if op == 'has':
                flag = integer()
                expect(bind('rv_dom_url_search_params_has', [pointer, pointer, integer, pointer, integer, ctypes.POINTER(integer)])(
                    params, *span(args[0]), *optional_value(args), ctypes.byref(flag)) == 0, 'has status')
                return bool(flag.value)
            if op == 'size':
                size = unsigned()
                expect(bind('rv_dom_url_search_params_get_size', [pointer, ctypes.POINTER(unsigned)])(params, ctypes.byref(size)) == 0, 'size')
                return size.value
            if op == 'toString':
                return get_string('rv_dom_url_search_params_to_string', params)
            if op == 'entries':
                return entries(params)
            if op == 'sort':
                expect(bind('rv_dom_url_search_params_sort', [pointer])(params) == 0, 'sort')
            elif op == 'delete':
                expect(bind('rv_dom_url_search_params_delete', [pointer, pointer, integer, pointer, integer])(
                    params, *span(args[0]), *optional_value(args)) == 0, 'delete')
            elif op in ('set', 'append'):
                expect(bind(f'rv_dom_url_search_params_{op}', [pointer, pointer, integer, pointer, integer])(
                    params, *span(args[0]), *span(args[1])) == 0, op)
            else:
                raise ValueError(op)
            return None

        for index, case in enumerate(cases['params']):
            params = pointer()
            init = params_init(*case['init'])
            status = create_params(document, ctypes.byref(init), ctypes.byref(params))
            error = status_error(status, 'URLSearchParams constructor')
            actual = error or {'ops': [run(params.value, op[0], op[1:]) for op in case['ops']]}
            if params.value:
                release_params(params.value)
            compare('params', index, actual)

        # URL.searchParams: one cached object, live in both directions.
        get_params = bind('rv_dom_domurl_get_search_params', [pointer, ctypes.POINTER(pointer)])
        for index, (href, ops) in enumerate(cases['linked']):
            error, url = new_url(href)
            first, second = pointer(), pointer()
            expect(get_params(url, ctypes.byref(first)) == 0 and get_params(url, ctypes.byref(second)) == 0, 'searchParams')
            expect(first.value == second.value, 'searchParams is one cached object')
            actual = []
            for op, *args in ops:
                if op == 'href':
                    actual.append(get_string('rv_dom_domurl_get_href', url))
                elif op == 'search':
                    actual.append(get_string('rv_dom_domurl_get_search', url))
                elif op == 'search=':
                    expect(bind('rv_dom_domurl_set_search', [pointer, pointer, integer])(url, *span(args[0])) == 0, 'set search')
                    actual.append(None)
                else:
                    actual.append(run(first.value, op.removeprefix('searchParams.'), args))
            release_params(first.value)
            release_params(second.value)
            release_url(url)
            compare('linked', index, actual)

        # URLPattern.
        create3 = bind('rv_dom_url_pattern_create_3', [pointer, ctypes.POINTER(PatternInput), pointer, integer,
                                                       ctypes.POINTER(PatternOptions), ctypes.POINTER(pointer)])
        create2 = bind('rv_dom_url_pattern_create_2', [pointer, ctypes.POINTER(PatternInput), ctypes.POINTER(PatternOptions),
                                                       ctypes.POINTER(pointer)])
        test = bind('rv_dom_url_pattern_test', [pointer, ctypes.POINTER(PatternInput), pointer, integer, ctypes.POINTER(integer)])
        execute = bind('rv_dom_url_pattern_exec', [pointer, ctypes.POINTER(PatternInput), pointer, integer,
                                                   ctypes.POINTER(ctypes.POINTER(PatternResult))])

        def pattern_input(kind, value):
            if kind == 'string':
                return PatternInput(1, 1, span_struct(value))
            init = PatternInit(ctypes.sizeof(PatternInit))
            for key, text in value.items():
                setattr(init, 'base_url' if key == 'baseURL' else key, string_input(text))
            keep.append(init)
            return PatternInput(1, 2, Span(None, 0), ctypes.pointer(init))

        def read_input(item):
            if item.tag == 1:
                return read_span(item.arm0)
            init = item.arm1.contents
            expect(init.size == ctypes.sizeof(PatternInit), 'returned init size')
            value = {}
            for name in COMPONENTS + ['base_url']:
                field = getattr(init, name)
                if field.present:
                    value['baseURL' if name == 'base_url' else name] = read_span(Span(field.data, field.length))
            return value

        def read_result(result):
            if not result:
                return None
            value = result.contents
            expect(value.size == ctypes.sizeof(PatternResult), 'returned result size')
            inputs = value.inputs.contents
            out = {'inputs': [read_input(inputs.items[i]) for i in range(inputs.count)]}
            for name in COMPONENTS:
                component = getattr(value, name).contents
                groups = component.groups.contents
                out[name] = {'input': read_span(Span(component.input.data, component.input.length), component.input.present),
                             'groups': [[read_span(groups.items[i].key),
                                         None if groups.items[i].value.tag == 1 else read_span(groups.items[i].value.arm1)]
                                        for i in range(groups.count)]}
            release_result(result)
            return out

        def normalize_groups(value):
            # A JavaScript object lists integer-like keys first; the engine lists groups in pattern order.
            if isinstance(value, dict) and 'inputs' in value:
                for name in COMPONENTS:
                    value[name]['groups'] = sorted(value[name]['groups'], key=lambda pair: pair[0])
            return value

        for index, case in enumerate(cases['patterns']):
            pattern = pointer()
            source = pattern_input(*case['input'])
            options = None
            if 'options' in case:
                options = PatternOptions(ctypes.sizeof(PatternOptions), int(case['options']['ignoreCase']))
            if 'base' in case:
                status = create3(document, ctypes.byref(source), *span(case['base']), options and ctypes.byref(options), ctypes.byref(pattern))
            else:
                status = create2(document, ctypes.byref(source), options and ctypes.byref(options), ctypes.byref(pattern))
            error = status_error(status, 'URLPattern constructor')
            if error:
                compare('patterns', index, error)
                continue
            components = {name: get_string(f'rv_dom_url_pattern_get_{name}', pattern.value) for name in COMPONENTS}
            flag = integer()
            expect(bind('rv_dom_url_pattern_get_has_reg_exp_groups', [pointer, ctypes.POINTER(integer)])(
                pattern.value, ctypes.byref(flag)) == 0, 'hasRegExpGroups')
            components['hasRegExpGroups'] = bool(flag.value)
            tests = []
            for kind, value, base in case['tests']:
                item = pattern_input(kind, value)
                base_value = base_args(base)
                matched = integer()
                status = test(pattern.value, ctypes.byref(item), *base_value, ctypes.byref(matched))
                tested = status_error(status, 'test') or bool(matched.value)
                result = ctypes.POINTER(PatternResult)()
                status = execute(pattern.value, ctypes.byref(item), *base_value, ctypes.byref(result))
                executed = status_error(status, 'exec') or read_result(result)
                tests.append({'test': tested, 'exec': normalize_groups(executed)})
            release_pattern(pattern.value)
            expected = oracle['patterns'][index]
            for item in expected.get('tests', []):
                normalize_groups(item['exec'])
            compare('patterns', index, {'components': components, 'tests': tests})

        # Argument and thread errors.
        url = pointer()
        expect(create_url(None, *span('http://a.test/'), None, -1, ctypes.byref(url)) == -1, 'null receiver')
        expect(create_url(document, None, 3, None, -1, ctypes.byref(url)) == -1, 'null string with a length')
        expect(create_url(document, *span('http://a.test/'), None, -2, ctypes.byref(url)) == -1, 'length below -1')
        expect(create_url(document, None, -1, None, -1, ctypes.byref(url)) == -1, 'required string absent')
        expect(create_url(body, *span('http://a.test/'), None, -1, ctypes.byref(url)) == -11, 'receiver must be a Document')
        expect(execute(None, None, None, -1, None) == -1, 'exec null arguments')
        raw = ctypes.create_string_buffer(b'\xff\xfe', 2)
        expect(create_url(document, ctypes.cast(raw, pointer), 2, None, -1, ctypes.byref(url)) in (0, -1, -3), 'invalid UTF-8 handled')
        if url.value:
            release_url(url.value)
            url = pointer()
        error, held_url = new_url('https://held.test/a?b=c')
        held_params = pointer()
        expect(get_params(held_url, ctypes.byref(held_params)) == 0, 'held searchParams')
        statuses = []
        worker = threading.Thread(target=lambda: statuses.append(create_url(document, *span('http://a.test/'), None, -1, ctypes.byref(url))))
        worker.start()
        worker.join()
        expect(statuses == [-2], 'wrong thread')
        held_pattern = pointer()
        source = pattern_input('init', {'pathname': '/held/:id'})
        expect(create2(document, ctypes.byref(source), None, ctypes.byref(held_pattern)) == 0, 'held pattern')
        held_result = ctypes.POINTER(PatternResult)()
        item = pattern_input('string', 'https://h.test/held/7')
        expect(execute(held_pattern.value, ctypes.byref(item), None, -1, ctypes.byref(held_result)) == 0 and bool(held_result), 'held result')
    finally:
        release_node(document.value)
        release_node(body)
        bind('rv_host_destroy', [pointer], None)(host)

    # Value objects own no document: they keep working, and release cleanly, after the host is destroyed.
    expect(get_string('rv_dom_domurl_get_href', held_url) == 'https://held.test/a?b=c', 'URL after host destroy')
    size = unsigned()
    expect(bind('rv_dom_url_search_params_get_size', [pointer, ctypes.POINTER(unsigned)])(held_params.value, ctypes.byref(size)) == 0
           and size.value == 1, 'searchParams after host destroy')
    expect(get_string('rv_dom_url_pattern_get_pathname', held_pattern.value) == '/held/:id', 'pattern after host destroy')
    expect(read_result(held_result)['pathname']['groups'] == [['id', '7']], 'result read and released after host destroy')
    release_params(held_params.value)
    release_url(held_url)
    release_pattern(held_pattern.value)
    if record is not None:
        Path(record).write_text(json.dumps(differences, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'url_values: {assertions} assertions, {len(differences)} qualified differences')
    return assertions


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--record-differences', help='write every difference from Chromium instead of failing on unqualified ones')
    arguments = parser.parse_args()
    verify(arguments.native_directory, arguments.record_differences)
