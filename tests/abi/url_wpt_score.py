"""Scores recorded URL and URLPattern outcomes with the web-platform-tests harness rules.

url-constructor.any.js, url-setters.any.js and urlpattern.any.js (WPT_COMMIT.txt) define the rules reproduced here.
"""
import json
from pathlib import Path

URL_FIELDS = ['href', 'origin', 'protocol', 'username', 'password', 'host', 'hostname', 'port', 'pathname', 'search', 'hash']
COMPONENTS = ['protocol', 'username', 'password', 'hostname', 'port', 'pathname', 'search', 'hash']
EARLIER = {'protocol': [], 'hostname': ['protocol'], 'port': ['protocol', 'hostname'], 'username': [], 'password': [],
           'pathname': ['protocol', 'hostname', 'port'], 'search': ['protocol', 'hostname', 'port', 'pathname'],
           'hash': ['protocol', 'hostname', 'port', 'pathname', 'search']}


def url_passes(entry, outcome):
    if entry.get('failure'):
        return isinstance(outcome, dict) and outcome.get('error') == 'TypeError'
    if 'error' in outcome:
        return False
    keys = [key for key in URL_FIELDS + ['searchParams'] if key in entry]
    return all(outcome.get(key) == entry[key] for key in keys)


def setter_passes(case, outcome):
    if 'base' in outcome:
        return False
    return all(outcome['url'].get(key) == value for key, value in case['expected'].items())


def expected_component(entry, component, base):
    expected = (entry.get('expected_obj') or {}).get(component) if isinstance(entry.get('expected_obj'), dict) else None
    if expected is not None:
        return expected
    pattern = entry['pattern']
    first = pattern[0] if pattern else None
    if component in entry.get('exactly_empty_components', []):
        return ''
    if isinstance(first, dict) and first.get(component):
        return first[component]
    if isinstance(first, dict) and any(first.get(earlier) is not None for earlier in EARLIER[component]):
        return '*'  # A component after a specified one is not inherited from baseURL.
    if base is not None and component not in ('username', 'password'):
        value = base[component]
        if component == 'protocol':
            return value[:-1]
        if component in ('search', 'hash'):
            return value[1:]
        return value
    return '*'


def groups(value):
    return {key: item for key, item in value}


def pattern_passes(entry, outcome, base):
    if entry.get('expected_obj') == 'error':
        return outcome['ctor'].get('error') == 'TypeError'
    if 'error' in outcome['ctor']:
        return False
    for component in COMPONENTS:
        if outcome['ctor'][component] != expected_component(entry, component, base):
            return False
    match = entry.get('expected_match')
    if match == 'error':
        return outcome.get('test', {}) == {'error': 'TypeError'} and outcome.get('exec', {}) == {'error': 'TypeError'}
    if 'test' not in outcome:
        return True
    if isinstance(outcome['test'], dict) or outcome['test'] != (match is not None):  # JavaScript truthiness: {} is true
        return False
    result = outcome['exec']
    if not isinstance(match, dict):
        return result is None
    if not isinstance(result, dict) or 'error' in result:
        return False
    inputs = match.get('inputs', entry.get('inputs', []))
    if len(result['inputs']) != len(inputs):
        return False
    for actual, expected in zip(result['inputs'], inputs):
        if isinstance(actual, str) or isinstance(expected, str):
            if actual != expected:
                return False
        elif any(actual.get(component) != expected.get(component) for component in COMPONENTS):
            return False
    for component in COMPONENTS:
        expected = match.get(component)
        if not expected:
            expected = {'input': '', 'groups': {} if component in entry.get('exactly_empty_components', []) else {'0': ''}}
        if result[component]['input'] != expected['input'] or groups(result[component]['groups']) != expected['groups']:
            return False
    return True


def normalized(outcome):
    """The outcome with group order removed: a JavaScript object lists integer-like keys first."""
    text = json.dumps(outcome, sort_keys=True, ensure_ascii=False)
    value = json.loads(text)
    if isinstance(value, dict) and isinstance(value.get('exec'), dict) and 'inputs' in value['exec']:
        for component in COMPONENTS:
            value['exec'][component]['groups'] = sorted(value['exec'][component]['groups'])
    return value


def score(wpt, native, chromium):
    wpt = Path(wpt)
    urls = [entry for entry in json.loads((wpt / 'urltestdata.json').read_text(encoding='utf-8')) if isinstance(entry, dict)]
    setters = json.loads((wpt / 'setters_tests.json').read_text(encoding='utf-8'))
    patterns = json.loads((wpt / 'urlpatterntestdata.json').read_text(encoding='utf-8'))
    bases = chromium['patternBases']
    counts = {name: {'cases': 0, 'native': 0, 'chromium': 0} for name in ['urltestdata', 'setters_tests', 'urlpatterntestdata']}
    disagree, both_fail = {}, []

    def judge(file, key, native_outcome, chromium_outcome, passes):
        native_pass, chromium_pass = passes(native_outcome), passes(chromium_outcome)
        counts[file]['cases'] += 1
        counts[file]['native'] += native_pass
        counts[file]['chromium'] += chromium_pass
        if native_pass != chromium_pass or normalized(native_outcome) != normalized(chromium_outcome):
            disagree[key] = {'native': native_outcome, 'chromium': chromium_outcome,
                             'nativePasses': native_pass, 'chromiumPasses': chromium_pass}
        if not native_pass and not chromium_pass:
            both_fail.append(key)

    for index, entry in enumerate(urls):
        judge('urltestdata', f'url[{index}]', native['url'][index], chromium['url'][index], lambda o, e=entry: url_passes(e, o))
    for group, cases in setters.items():
        if group == 'comment':
            continue
        for index, case in enumerate(cases):
            judge('setters_tests', f'setters.{group}[{index}]', native['setters'][group][index], chromium['setters'][group][index],
                  lambda o, c=case: setter_passes(c, o))
    for index, entry in enumerate(patterns):
        judge('urlpatterntestdata', f'urlpattern[{index}]', native['urlpattern'][index], chromium['urlpattern'][index],
              lambda o, e=entry, b=bases[index]: pattern_passes(e, o, b))
    return {'counts': counts, 'disagree': disagree, 'bothFail': both_fail}
