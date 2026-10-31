"""Segments the RED cases with the runtime's own ICU (icuuc77.dll next to WebCore.dll) and compares with Chromium."""
import ctypes
import json
import os
import sys

runtime, cases_path, chromium_path, out_path = sys.argv[1:5]
os.add_dll_directory(runtime)
icu = ctypes.CDLL(os.path.join(runtime, 'icuuc77.dll'))
i32 = ctypes.c_int32
open_ = icu.ubrk_open_77
open_.restype = ctypes.c_void_p
open_.argtypes = [i32, ctypes.c_char_p, ctypes.c_wchar_p, i32, ctypes.POINTER(i32)]
for name in ['ubrk_first_77', 'ubrk_next_77', 'ubrk_getRuleStatus_77']:
    getattr(icu, name).restype = i32
    getattr(icu, name).argtypes = [ctypes.c_void_p]
icu.ubrk_close_77.argtypes = [ctypes.c_void_p]
KIND = {'grapheme': 0, 'word': 1, 'line': 2, 'sentence': 3}
version = (ctypes.c_uint8 * 4)()
icu.u_getVersion_77.argtypes = [ctypes.c_void_p]
icu.u_getVersion_77(version)


def utf16_units(text):
    return len(text.encode('utf-16-le')) // 2


def segment(locale, granularity, text):
    status = i32(0)
    buffer = ctypes.create_unicode_buffer(text, utf16_units(text) + 1)  # wchar_t is UTF-16 on Windows
    length = utf16_units(text)
    iterator = open_(KIND[granularity], locale.encode(), buffer, length, ctypes.byref(status))
    if status.value > 0:
        raise RuntimeError(f'ubrk_open {granularity} {locale}: {status.value}')
    units = text.encode('utf-16-le')
    out = []
    start = icu.ubrk_first_77(iterator)
    while True:
        end = icu.ubrk_next_77(iterator)
        if end == -1:
            break
        piece = units[start * 2:end * 2].decode('utf-16-le')
        if granularity == 'word':
            rule = icu.ubrk_getRuleStatus_77(iterator)
            out.append([start, piece, not (0 <= rule < 100)])
        else:
            out.append([start, piece])
        start = end
    icu.ubrk_close_77(iterator)
    return out


cases = json.load(open(cases_path, encoding='utf-8'))['cases']
chromium = json.load(open(chromium_path, encoding='utf-8'))
result = {'icuVersion': '.'.join(map(str, version)), 'cases': []}
agree = {k: 0 for k in ['grapheme', 'word', 'sentence', 'line']}
differences = []
for index, (locale, text) in enumerate(cases):
    row = {'locale': locale, 'text': text}
    for granularity in ['grapheme', 'word', 'sentence', 'line']:
        row[granularity] = segment(locale, granularity, text)
        expected = chromium['cases'][index].get(granularity)
        if expected is None:
            continue
        if row[granularity] == expected:
            agree[granularity] += 1
        else:
            differences.append({'case': index, 'locale': locale, 'granularity': granularity, 'icu': row[granularity], 'chromium': expected})
    result['cases'].append(row)
result['agreement'] = {k: f'{v}/{len(cases)}' for k, v in agree.items()}
result['differences'] = differences
json.dump(result, open(out_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('ICU', result['icuVersion'], result['agreement'], len(differences), 'differences')
for d in differences[:8]:
    print(d['case'], d['locale'], d['granularity'])
