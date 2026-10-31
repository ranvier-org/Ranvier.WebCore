"""H13: the web-platform-tests URL and URLPattern corpus on the runtime, compared with Chromium.

Runs tests/fixtures/wpt/url (urltestdata.json, setters_tests.json, urlpatterntestdata.json, pinned in
WPT_COMMIT.txt) through the generated exports and records each case's outcome in the same shape as
tests/abi/url_wpt_browser.mjs, which records Chromium's in tests/fixtures/url-wpt-chromium.json. Scores both
engines with the WPT harness rules, then requires every case where the engines disagree to be listed in
tests/fixtures/url-wpt-qualified.json with both outcomes, and every case both engines fail to be listed there too.
"""
import argparse
import ctypes
import json
import os
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from url_values import (COMPONENTS, FIELDS, PatternInit, PatternInput, PatternOptions, PatternResult, Span,  # noqa: E402
                        StringInput, integer, pointer)
from url_wpt_score import score  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
WPT = FIXTURES / 'wpt' / 'url'


class Runtime:
    """The generated URL exports of one host, with UTF-8 length-delimited strings."""

    def __init__(self, directory):
        filename = {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')
        self.search = os.add_dll_directory(str(directory)) if sys.platform == 'win32' else None
        self.library = ctypes.CDLL(str(directory / filename))
        self.keep = []
        self.calls = 0
        self.host = self.bind('rv_host_create', [integer, integer], pointer)(320, 240)
        assert self.host, 'host creation'
        self.body = self.bind('rv_document_body', [pointer], pointer)(self.host)
        document = pointer()
        assert self.bind('rv_dom_node_get_owner_document', [pointer, ctypes.POINTER(pointer)])(self.body, ctypes.byref(document)) == 0
        self.document = document.value
        args = [pointer, pointer, integer, pointer, integer, ctypes.POINTER(pointer)]
        self.create_url = self.bind('rv_dom_domurl_create', args)
        self.release_url = self.bind('rv_dom_domurl_release', [pointer], None)
        self.release_pattern = self.bind('rv_dom_url_pattern_release', [pointer], None)
        self.release_result = self.bind('rv_dom_url_pattern_result_release', [ctypes.POINTER(PatternResult)], None)
        self.create3 = self.bind('rv_dom_url_pattern_create_3', [pointer, ctypes.POINTER(PatternInput), pointer, integer,
                                                                 ctypes.POINTER(PatternOptions), ctypes.POINTER(pointer)])
        self.create2 = self.bind('rv_dom_url_pattern_create_2', [pointer, ctypes.POINTER(PatternInput),
                                                                 ctypes.POINTER(PatternOptions), ctypes.POINTER(pointer)])
        self.test = self.bind('rv_dom_url_pattern_test', [pointer, ctypes.POINTER(PatternInput), pointer, integer, ctypes.POINTER(integer)])
        self.execute = self.bind('rv_dom_url_pattern_exec', [pointer, ctypes.POINTER(PatternInput), pointer, integer,
                                                             ctypes.POINTER(ctypes.POINTER(PatternResult))])

    def close(self):
        self.bind('rv_node_release', [pointer], None)(self.document)
        self.bind('rv_node_release', [pointer], None)(self.body)
        self.bind('rv_host_destroy', [pointer], None)(self.host)
        self.keep.clear()

    def bind(self, name, arguments, result=integer):
        function = getattr(self.library, name)
        function.restype, function.argtypes = result, arguments
        return function

    def span(self, text):
        # A USVString argument replaces a lone surrogate with U+FFFD, as the JavaScript bindings convert it.
        data = text.encode('utf-16-le', 'surrogatepass').decode('utf-16-le', 'replace').encode('utf-8')
        buffer = ctypes.create_string_buffer(data, len(data) + 1)
        self.keep.append(buffer)
        return ctypes.cast(buffer, pointer), len(data)

    def optional(self, text):
        return (None, -1) if text is None else self.span(text)

    def exception(self):
        buffer, length = ctypes.create_string_buffer(256), integer()
        self.bind('rv_last_exception', [integer, pointer, integer, ctypes.POINTER(integer)])(0, buffer, 256, ctypes.byref(length))
        return buffer.raw[:max(length.value, 0)].decode('utf-8')

    def outcome(self, status):
        self.calls += 1
        if status not in (0, -3):
            raise AssertionError(f'status {status}')
        return None if status == 0 else {'error': self.exception()}

    def string(self, name, target):
        function = self.bind(name, [pointer, pointer, integer, ctypes.POINTER(integer)])
        length = integer()
        status = function(target, None, 0, ctypes.byref(length))
        if status == 0 and length.value == -1:
            return None
        assert status in (0, -6), f'{name}: status {status}'
        buffer = ctypes.create_string_buffer(max(length.value, 1))
        assert function(target, buffer, len(buffer), ctypes.byref(length)) == 0, name
        self.calls += 1
        return buffer.raw[:length.value].decode('utf-8', 'surrogatepass')

    def url(self, text, base):
        result = pointer()
        error = self.outcome(self.create_url(self.document, *self.span(text), *self.optional(base), ctypes.byref(result)))
        return error, result.value

    def snapshot(self, url):
        value = {field: self.string(f'rv_dom_domurl_get_{field}', url) for field in FIELDS}
        params = pointer()
        assert self.bind('rv_dom_domurl_get_search_params', [pointer, ctypes.POINTER(pointer)])(url, ctypes.byref(params)) == 0
        value['searchParams'] = self.string('rv_dom_url_search_params_to_string', params.value)
        self.bind('rv_dom_url_search_params_release', [pointer], None)(params.value)
        return value

    def parse_case(self, text, base):
        error, url = self.url(text, base)
        if error:
            return error
        value = self.snapshot(url)
        self.release_url(url)
        return value

    def setter_case(self, href, field, value):
        error, url = self.url(href, None)
        if error:
            return {'base': error}
        status = self.bind(f'rv_dom_domurl_set_{field}', [pointer, pointer, integer])(url, *self.span(value))
        result = {'threw': (self.outcome(status) or {}).get('error'), 'url': self.snapshot(url)}
        self.release_url(url)
        return result

    def pattern_input(self, value):
        if isinstance(value, str):
            return PatternInput(1, 1, Span(*self.span(value)))
        init = PatternInit(ctypes.sizeof(PatternInit))
        for key, text in value.items():
            if key not in COMPONENTS + ['baseURL']:
                continue  # The JavaScript dictionary conversion ignores unknown members.
            data, length = self.span(text)
            setattr(init, 'base_url' if key == 'baseURL' else key, StringInput(1, data, length))
        self.keep.append(init)
        return PatternInput(1, 2, Span(None, 0), ctypes.pointer(init))

    @staticmethod
    def read_span(value, present=True):
        if not present or value.length < 0:
            return None
        return ctypes.string_at(value.data, value.length).decode('utf-8', 'surrogatepass') if value.length else ''

    def read_result(self, result):
        if not result:
            return None
        value = result.contents
        inputs = value.inputs.contents
        out = {'inputs': []}
        for i in range(inputs.count):
            item = inputs.items[i]
            if item.tag == 1:
                out['inputs'].append(self.read_span(item.arm0))
                continue
            init = item.arm1.contents
            out['inputs'].append({('baseURL' if name == 'base_url' else name): self.read_span(Span(getattr(init, name).data, getattr(init, name).length))
                                  for name in COMPONENTS + ['base_url'] if getattr(init, name).present})
        for name in COMPONENTS:
            component = getattr(value, name).contents
            groups = component.groups.contents
            out[name] = {'input': self.read_span(Span(component.input.data, component.input.length), component.input.present),
                         'groups': [[self.read_span(groups.items[i].key),
                                     None if groups.items[i].value.tag == 1 else self.read_span(groups.items[i].value.arm1)]
                                    for i in range(groups.count)]}
        self.release_result(result)
        return out

    def pattern_case(self, entry):
        args = entry['pattern']
        if len(args) == 3 and not (isinstance(args[1], str) and isinstance(args[2], dict)):
            # JavaScript overload resolution: (input, baseURL, options) converts a non-object options argument with a
            # TypeError before the engine runs. The C ABI has no such call.
            return {'ctor': {'error': 'TypeError'}, 'bindingConversion': True}
        source = self.pattern_input(args[0]) if args else None
        base = args[1] if len(args) > 1 and isinstance(args[1], str) else None
        options_value = args[-1] if len(args) > 1 and isinstance(args[-1], dict) else None
        options = PatternOptions(ctypes.sizeof(PatternOptions), int(bool(options_value.get('ignoreCase')))) if options_value else None
        pattern = pointer()
        source_ref = ctypes.byref(source) if source else None
        options_ref = ctypes.byref(options) if options else None
        if base is not None:
            status = self.create3(self.document, source_ref, *self.span(base), options_ref, ctypes.byref(pattern))
        else:
            status = self.create2(self.document, source_ref, options_ref, ctypes.byref(pattern))
        error = self.outcome(status)
        if error:
            return {'ctor': error}
        record = {'ctor': {name: self.string(f'rv_dom_url_pattern_get_{name}', pattern.value) for name in COMPONENTS}}
        if 'inputs' in entry or entry.get('expected_match') is not None:
            inputs = entry.get('inputs', [])
            item = self.pattern_input(inputs[0]) if inputs else None
            item_ref = ctypes.byref(item) if item else None
            input_base = self.optional(inputs[1] if len(inputs) > 1 else None)
            flag = integer()
            record['test'] = self.outcome(self.test(pattern.value, item_ref, *input_base, ctypes.byref(flag))) or bool(flag.value)
            result = ctypes.POINTER(PatternResult)()
            record['exec'] = self.outcome(self.execute(pattern.value, item_ref, *input_base, ctypes.byref(result))) or self.read_result(result)
        self.release_pattern(pattern.value)
        return record


def run(directory):
    runtime = Runtime(directory)
    try:
        urls = [entry for entry in json.loads((WPT / 'urltestdata.json').read_text(encoding='utf-8')) if isinstance(entry, dict)]
        setters = json.loads((WPT / 'setters_tests.json').read_text(encoding='utf-8'))
        patterns = json.loads((WPT / 'urlpatterntestdata.json').read_text(encoding='utf-8'))
        record = {
            'url': [runtime.parse_case(entry['input'], entry.get('base')) for entry in urls],
            'setters': {group: [runtime.setter_case(case['href'], group, case['new_value']) for case in cases]
                        for group, cases in setters.items() if group != 'comment'},
            'urlpattern': [runtime.pattern_case(entry) for entry in patterns],
        }
        statuses = []
        worker = threading.Thread(target=lambda: statuses.append(runtime.create_url(runtime.document, *runtime.span('http://a.test/'), None, -1, ctypes.byref(pointer()))))
        worker.start()
        worker.join()
        assert statuses == [-2], 'wrong thread'
        return record, runtime.calls
    finally:
        runtime.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--write-record', help='also write the runtime outcomes, for evidence and requalification')
    arguments = parser.parse_args()
    native, calls = run(Path(arguments.native_directory).resolve())
    if arguments.write_record:
        Path(arguments.write_record).write_text(json.dumps(native, ensure_ascii=False, indent=0) + '\n', encoding='utf-8')
    chromium = json.loads((FIXTURES / 'url-wpt-chromium.json').read_text(encoding='utf-8'))
    qualified = json.loads((FIXTURES / 'url-wpt-qualified.json').read_text(encoding='utf-8'))
    report = score(WPT, native, chromium)
    unlisted = []
    for key, item in report['disagree'].items():
        listed = qualified['disagree'].get(key)
        if listed is None or listed['native'] != item['native'] or listed['chromium'] != item['chromium']:
            unlisted.append(key)
    for key in report['bothFail']:
        if key not in qualified['bothFail']:
            unlisted.append(key)
    stale = [key for key in qualified['disagree'] if key not in report['disagree']] + \
            [key for key in qualified['bothFail'] if key not in report['bothFail']]
    print(json.dumps(report['counts']))
    print(f'url_wpt: {calls} calls, {len(report["disagree"])} qualified disagreements, {len(report["bothFail"])} both-fail cases')
    if unlisted or stale:
        print('unlisted:', unlisted[:20], 'stale:', stale[:20])
        raise SystemExit(1)


if __name__ == '__main__':
    main()
