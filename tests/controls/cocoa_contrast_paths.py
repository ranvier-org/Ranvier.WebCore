"""Capture page contrast versus process-local system contrast on actual native controls."""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import sys


def crop(pixels, bounds, width=300):
    x, y, w, h = bounds
    return b''.join(pixels[((y + row) * width + x) * 4:((y + row) * width + x + w) * 4]
                    for row in range(h))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-directory', type=Path, required=True)
    parser.add_argument('--abi-source', type=Path, required=True)
    parser.add_argument('--system-helper', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert sys.platform == 'darwin'
    sys.path.insert(0, str(args.abi_source.resolve()))
    from media_queries import Media, MediaPreferences
    from svg_paint_probe import SvgProbe

    args.output.mkdir(parents=True, exist_ok=True)
    native = args.native_directory.resolve()
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    before = {p.name: sha(p) for p in native.iterdir() if p.is_file()}
    helper = C.CDLL(str(args.system_helper.resolve()))
    helper.project2_cocoa_contrast_set.argtypes = [C.c_int]
    helper.project2_cocoa_contrast_set.restype = C.c_int
    helper.project2_cocoa_contrast_calls.argtypes = []
    helper.project2_cocoa_contrast_calls.restype = C.c_uint
    helper.project2_cocoa_contrast_restore.argtypes = []
    helper.project2_cocoa_contrast_restore.restype = C.c_int
    image = C.CDLL(str(native / 'libRanvierWebCoreHost.dylib'))
    profile = image.project2_progress_form_control_profile
    profile.argtypes, profile.restype = [C.c_void_p, C.c_int32, C.POINTER(C.c_int32)], C.c_int32
    rows, failures, captures = [], [], {}
    assertions = 0

    def check(condition, name):
        nonlocal assertions
        assertions += 1
        if not condition:
            failures.append(name)

    boxes = {'checkbox': (15, 15, 40, 40), 'radio': (75, 15, 40, 40),
             'textfield': (15, 75, 240, 40)}
    markup = '''<!doctype html><style>
      body{margin:0;background:white;color:black;color-scheme:light}
      input{position:absolute;margin:0;accent-color:#007aff}
      #c{left:20px;top:20px;width:30px;height:30px}
      #r{left:80px;top:20px;width:30px;height:30px}
      #t{left:20px;top:80px;width:220px;height:30px;font:16px sans-serif}
      </style><input id=c type=checkbox checked><input id=r type=radio checked>
      <input id=t value=Contrast readonly>'''
    try:
        for system_more in [False, True]:
            for page_more in [False, True]:
                check(helper.project2_cocoa_contrast_set(int(system_more)) == 0, 'process-local contrast hook')
                with SvgProbe(native, 300, 140) as probe:
                    current = C.c_int32(-1)
                    check(profile(probe.host, -1, C.byref(current)) == 0 and current.value == 0,
                          'default native appearance remains legacy')
                    probe.load(markup, standalone=False)
                    check(profile(probe.host, 1, C.byref(current)) == 0 and current.value == 1,
                          'explicit per-host vector control path')
                    media = Media(probe)
                    query = media.match_media(probe.host, b'(prefers-contrast: more)')
                    check(bool(query), 'actual contrast media query')
                    try:
                        media.supply(MediaPreferences(size=C.sizeof(MediaPreferences), color_scheme=1,
                                                     contrast=2 if page_more else 1), 'page contrast')
                        media.settle()
                        check(media.matches(query) == int(page_more), 'CSS follows page rather than system')
                        samples = [bytes(probe.paint()), bytes(probe.paint())]
                        check(samples[0] == samples[1], 'static control repeat is byte-identical')
                        calls = helper.project2_cocoa_contrast_calls()
                        check(calls > 0, 'native process-local contrast getter was exercised')
                        label = f'system-{int(system_more)}-page-{int(page_more)}'
                        (args.output / (label + '.rgba')).write_bytes(samples[0])
                        captures[(system_more, page_more)] = samples[0]
                        rows.append({'label': label, 'systemMore': system_more, 'pageMore': page_more,
                                     'cssMore': media.matches(query), 'getterCalls': calls,
                                     'sha256': hashlib.sha256(samples[0]).hexdigest(),
                                     'controlHashes': {name: hashlib.sha256(crop(samples[0], box)).hexdigest()
                                                       for name, box in boxes.items()}})
                    finally:
                        media.release(query)
                        check(profile(probe.host, 0, C.byref(current)) == 0, 'profile restored')
        for page_more in [False, True]:
            for name, bounds in boxes.items():
                left, right = [crop(captures[(system, page_more)], bounds) for system in [False, True]]
                different = sum(left[i:i + 4] != right[i:i + 4] for i in range(0, len(left), 4))
                check(different == 0, f'{name} page-{int(page_more)} ignores contradictory system contrast: {different} pixels')
                rows.append({'control': name, 'pageMore': page_more, 'systemAxisDifferentPixels': different})
        for system_more in [False, True]:
            for name, bounds in boxes.items():
                left, right = [crop(captures[(system_more, page)], bounds) for page in [False, True]]
                different = sum(left[i:i + 4] != right[i:i + 4] for i in range(0, len(left), 4))
                check(different > 0, f'{name} system-{int(system_more)} has a visible page contrast control')
                rows.append({'control': name, 'systemMore': system_more, 'pageAxisDifferentPixels': different})
    finally:
        check(helper.project2_cocoa_contrast_restore() == 0, 'original process getter restored')
        after = {p.name: sha(p) for p in native.iterdir() if p.is_file()}
        check(before == after, 'native inputs unchanged')
        report = {'scope': 'Explicit vector control contrast on retained CPU206, default styling unchanged; no product fix or GPU claim',
                  'assertions': assertions, 'failures': failures, 'rows': rows,
                  'nativeBefore': before, 'nativeAfter': after}
        (args.output / 'contrast-paths.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))
    if failures:
        raise AssertionError(failures)


if __name__ == '__main__':
    main()
