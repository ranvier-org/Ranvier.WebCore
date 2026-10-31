"""T06 text segmentation through rv_text_segment.

Replays tests/fixtures/text-segmentation-cases.json at grapheme, word, sentence and line granularity and compares
each result with Chromium's in tests/fixtures/text-segmentation-oracle.json (Intl.Segmenter; Intl.v8BreakIterator for
lines). A difference passes only when tests/fixtures/text-segmentation-qualified.json records it with the runtime's
exact value. Also checks that every word, sentence and line boundary is a grapheme boundary, locale resolution and
RangeErrors, argument and thread errors, and results held past rv_host_destroy.
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
GRANULARITIES = ['grapheme', 'word', 'sentence', 'line']
pointer, integer = ctypes.c_void_p, ctypes.c_int32


class TextSegments(ctypes.Structure):
    _fields_ = [('count', integer), ('starts', ctypes.POINTER(integer)), ('word_like', ctypes.POINTER(integer)), ('locale', ctypes.c_char_p)]


def units(text):
    return text.encode('utf-16-le', 'surrogatepass')


def verify(native_directory, abi, record=None):
    directory = Path(native_directory).resolve()
    filename = {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')
    search = os.add_dll_directory(str(directory)) if sys.platform == 'win32' else None
    library = ctypes.CDLL(str(directory / filename))
    cases = json.loads((FIXTURES / 'text-segmentation-cases.json').read_text(encoding='utf-8'))
    oracle = json.loads((FIXTURES / 'text-segmentation-oracle.json').read_text(encoding='utf-8'))
    qualified_file = json.loads((FIXTURES / 'text-segmentation-qualified.json').read_text(encoding='utf-8'))
    qualified = qualified_file['differences']
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

    segment_raw = bind('rv_text_segment', [integer, ctypes.c_char_p, ctypes.c_char_p, integer, ctypes.POINTER(TextSegments)])
    release = bind('rv_text_segments_release', [ctypes.POINTER(TextSegments)], None)

    def exception():
        buffer, length = ctypes.create_string_buffer(256), integer()
        bind('rv_last_exception', [integer, pointer, integer, ctypes.POINTER(integer)])(0, buffer, 256, ctypes.byref(length))
        return buffer.raw[:max(length.value, 0)].decode('utf-8')

    def segment(granularity, locale, text, keep=False):
        data = units(text)
        result = TextSegments()
        status = segment_raw(GRANULARITIES.index(granularity), None if locale is None else locale.encode(), data or None, len(data) // 2, ctypes.byref(result))
        if status == -3:
            return {'error': exception()}, None
        expect(status == 0, f'{granularity} {locale!r}: status {status}')
        starts = [result.starts[i] for i in range(result.count)]
        expect(not starts or starts[0] == 0, 'first segment starts at 0')
        expect(all(a < b for a, b in zip(starts, starts[1:])), 'segment starts increase')
        ends = starts[1:] + [len(data) // 2]
        pieces = [data[s * 2:e * 2].decode('utf-16-le', 'surrogatepass') for s, e in zip(starts, ends)]
        expect((result.word_like is not None and bool(result.word_like)) == (granularity == 'word' and result.count > 0), 'word_like only for words')
        if granularity == 'word':
            out = [[s, p, bool(result.word_like[i])] for i, (s, p) in enumerate(zip(starts, pieces))]
        else:
            out = [[s, p] for s, p in zip(starts, pieces)]
        locale_name = result.locale.decode('utf-8') if result.locale else None
        if keep:
            return out, (result, locale_name)
        release(ctypes.byref(result))
        expect(result.count == 0 and not result.starts and not result.locale, 'release zeroes the result')
        return out, locale_name

    buffer, length = ctypes.create_string_buffer(64), integer()
    expect(bind('rv_text_segmentation_version', [pointer, integer, ctypes.POINTER(integer)])(buffer, 64, ctypes.byref(length)) == 0, 'version')
    version = buffer.raw[:length.value].decode()
    icu = version.split()[0]
    # Exact results are checked on the ICU they were measured with; another ICU (Linux and macOS use the system's)
    # is checked for the invariants and has its differences printed.
    exact = icu == qualified_file['measuredIcu']

    def compare(key, actual, expected):
        if actual == expected:
            expect(True, key)
            return
        differences[key] = {'native': actual, 'chromium': expected}
        if record is None and exact:
            expect(key in qualified and qualified[key]['native'] == actual, f'{key}: native {json.dumps(actual, ensure_ascii=False)[:300]} != chromium {json.dumps(expected, ensure_ascii=False)[:300]}')

    # Before the first host, the engine is not initialized.
    early = TextSegments()
    expect(segment_raw(0, None, b'a\x00', 1, ctypes.byref(early)) == -2, 'segmentation before the first host')
    expect(bind('rv_abi_version', [], integer)() == abi, f'ABI version {abi}')
    expect(bind('rv_abi_has', [ctypes.c_char_p], integer)(b'text-segmentation') == 1, 'text-segmentation feature')
    host = bind('rv_host_create', [integer, integer], pointer)(320, 240)
    expect(bool(host), 'host creation')
    held = None
    try:
        for index, (locale, text) in enumerate(cases['cases']):
            row = oracle['cases'][index]
            graphemes = None
            for granularity in GRANULARITIES:
                actual, _ = segment(granularity, locale, text)
                if granularity == 'grapheme':
                    graphemes = {s for s, _ in actual} | {len(units(text)) // 2}
                else:
                    expect(all(s in graphemes for s, *_ in actual), f'case {index} {granularity}: every boundary is a grapheme boundary')
                compare(f'cases[{index}].{granularity}', actual, row[granularity])

        resolved = {}
        for index, locale in enumerate(cases['locales']):
            words, name = segment('word', locale, 'a.b c')
            expected = oracle['locales'][index]
            if isinstance(words, dict):
                compare(f'locales[{index}].words', words, expected['words'])
                continue
            compare(f'locales[{index}].words', words, expected['words'])
            resolved[locale] = name
        default_words, default_locale = segment('word', None, 'a.b c')
        empty_words, empty_locale = segment('word', '', 'a.b c')
        expect(default_words == empty_words and default_locale == empty_locale, 'NULL and "" are the root locale')

        # Arguments, granularity and thread.
        result = TextSegments()
        expect(segment_raw(0, None, None, 3, ctypes.byref(result)) == -1, 'NULL text with a length')
        expect(segment_raw(0, None, b'a\x00', -1, ctypes.byref(result)) == -1, 'negative length')
        expect(segment_raw(0, None, b'a\x00', 1, None) == -1, 'NULL result')
        expect(segment_raw(4, None, b'a\x00', 1, ctypes.byref(result)) == -9, 'unknown granularity')
        expect(segment_raw(-1, None, b'a\x00', 1, ctypes.byref(result)) == -9, 'negative granularity')
        lone = units('\ud800x')
        actual, _ = segment('grapheme', 'en', '\ud800x')
        expect(actual == [[0, '\ud800'], [1, 'x']], 'a lone surrogate is its own grapheme')
        statuses = []
        worker = threading.Thread(target=lambda: statuses.append(segment_raw(0, None, b'a\x00', 1, ctypes.byref(TextSegments()))))
        worker.start()
        worker.join()
        expect(statuses == [-2], 'wrong thread')
        held = segment('word', 'th', 'ภาษาไทยไม่มีช่องว่าง', keep=True)
    finally:
        bind('rv_host_destroy', [pointer], None)(host)

    # The engine stays initialized after its hosts are destroyed; a held result stays readable until released.
    words, (result, _) = held
    expect([result.starts[i] for i in range(result.count)] == [w[0] for w in words], 'a held result after host destroy')
    release(ctypes.byref(result))
    after, _ = segment('grapheme', 'en', 'éx')
    expect(after == [[0, 'é'], [2, 'x']], 'segmentation after host destroy')
    release(None)

    if record is not None:
        Path(record).write_text(json.dumps({'version': version, 'differences': differences, 'resolvedLocales': resolved}, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    if not exact:
        print(f'{version}: exact results are measured on {qualified_file["measuredIcu"]}; {len(differences)} differences from Chromium:')
        for key in sorted(differences):
            print('  ' + key)
    print(f'text_segmentation: {assertions} assertions, {len(differences)} qualified differences, {version}')
    return assertions


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--abi', type=int, default=ABI, help='the expected ABI version of a later runtime')
    parser.add_argument('--record-differences', help='write every difference from Chromium instead of failing on unqualified ones')
    arguments = parser.parse_args()
    verify(arguments.native_directory, arguments.abi, arguments.record_differences)
