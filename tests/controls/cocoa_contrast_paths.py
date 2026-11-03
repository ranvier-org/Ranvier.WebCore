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


def contrast_policy_results(captures, boxes, vector):
    checks, rows = [], []
    for page in [False, True]:
        for name, bounds in boxes.items():
            left, right = [crop(captures[(system, page)], bounds) for system in [False, True]]
            changed = sum(left[i:i + 4] != right[i:i + 4] for i in range(0, len(left), 4))
            if vector:
                checks.append((changed == 0, f'{name} page-{int(page)} ignores contradictory system contrast: {changed} pixels'))
            rows.append({'control': name, 'pageMore': page, 'systemAxisDifferentPixels': changed})
    for system in [False, True]:
        for name, bounds in boxes.items():
            left, right = [crop(captures[(system, page)], bounds) for page in [False, True]]
            changed = sum(left[i:i + 4] != right[i:i + 4] for i in range(0, len(left), 4))
            if vector:
                checks.append((changed > 0, f'{name} system-{int(system)} has a visible page contrast control'))
                expected = crop(captures[(system, system)], bounds)
                actual = crop(captures[(system, None)], bounds)
                checks.append((actual == expected, f'{name} System follows system-{int(system)} resolved policy'))
            rows.append({'control': name, 'systemMore': system, 'pageAxisDifferentPixels': changed})
    return checks, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-directory', type=Path, required=True)
    parser.add_argument('--abi-source', type=Path, required=True)
    parser.add_argument('--system-helper', type=Path, required=True)
    parser.add_argument('--page-helper', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--legacy-only', action='store_true')
    parser.add_argument('--legacy-reference', type=Path)
    parser.add_argument('--first-system-more', action='store_true')
    parser.add_argument('--trace-getters', action='store_true')
    parser.add_argument('--scoped-helper', action='store_true')
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
    helper.project2_cocoa_contrast_reset_calls.argtypes = []
    helper.project2_cocoa_contrast_reset_calls.restype = C.c_int
    helper.project2_cocoa_contrast_restore.argtypes = []
    helper.project2_cocoa_contrast_restore.restype = C.c_int
    if args.scoped_helper:
        helper.project2_cocoa_contrast_platform_calls.argtypes = []
        helper.project2_cocoa_contrast_platform_calls.restype = C.c_uint
        helper.project2_cocoa_contrast_platform_value.argtypes = []
        helper.project2_cocoa_contrast_platform_value.restype = C.c_int
    image = C.CDLL(str(args.page_helper.resolve() if args.page_helper else native / 'libRanvierWebCoreHost.dylib'))
    profile = image.project2_progress_form_control_profile
    profile.argtypes, profile.restype = [C.c_void_p, C.c_int32, C.POINTER(C.c_int32)], C.c_int32
    system_contrast = image.project2_progress_system_contrast
    system_contrast.argtypes, system_contrast.restype = [C.c_void_p], C.c_int32
    rows, failures, captures, unknown_controls = [], [], {}, []
    assertions = 0

    def check(condition, name):
        nonlocal assertions
        assertions += 1
        if not condition:
            failures.append(name)

    boxes = {'checkbox': (15, 15, 40, 40), 'radio': (75, 15, 40, 40),
             'textfield': (15, 75, 240, 40)}
    if args.legacy_only:
        boxes['switch'] = (135, 15, 70, 40)
    markup = '''<!doctype html><style>
      body{margin:0;background:white;color:black;color-scheme:light}
      input{position:absolute;margin:0;accent-color:#007aff}
      #c{left:20px;top:20px;width:30px;height:30px}
      #r{left:80px;top:20px;width:30px;height:30px}
      #s{left:140px;top:20px;width:51px;height:26px}
      #t{left:20px;top:80px;width:220px;height:30px;font:16px sans-serif}
      </style><input id=c type=checkbox checked><input id=r type=radio checked>
      <input id=s type=checkbox switch checked><input id=t value=Contrast readonly>'''
    try:
        if args.scoped_helper:
            original = helper.project2_cocoa_contrast_platform_value()
            check(original in [0, 1], 'original platform contrast is available')
            for forced in [0, 1]:
                check(helper.project2_cocoa_contrast_set(forced) == 0, 'unknown-caller hook installation')
                observed = helper.project2_cocoa_contrast_platform_value()
                control = dict(forced=forced, original=original, observed=observed,
                               themeCalls=helper.project2_cocoa_contrast_calls(),
                               platformCalls=helper.project2_cocoa_contrast_platform_calls())
                unknown_controls.append(control)
                check(observed == original and control['themeCalls'] == 0 and control['platformCalls'] > 0,
                      'unattributed caller forwards original platform preference')
            check(helper.project2_cocoa_contrast_restore() == 0, 'unknown-caller hook restored')
            check(helper.project2_cocoa_contrast_platform_value() == original, 'original platform preference preserved')
        for system_more in ([True, False] if args.first_system_more else [False, True]):
            for page_more in [False, True, None]:
                check(helper.project2_cocoa_contrast_set(int(system_more)) == 0, 'process-local contrast hook')
                def phase(name):
                    if args.trace_getters:
                        print('CONTRAST_PHASE=' + json.dumps({'phase': name, 'systemMore': system_more,
                            'pageMore': page_more, 'calls': helper.project2_cocoa_contrast_calls(),
                            'platformCalls': helper.project2_cocoa_contrast_platform_calls() if args.scoped_helper else None}), flush=True)
                phase('before-host')
                with SvgProbe(native, 300, 140) as probe:
                    probe.call('rv_host_set_accelerated_compositing', [C.c_void_p, C.c_int32], probe.host, 0)
                    current = C.c_int32(-1)
                    check(profile(probe.host, -1, C.byref(current)) == 0 and current.value == 0,
                          'default native appearance remains legacy')
                    probe.load(markup, standalone=False)
                    selected = int(not args.legacy_only)
                    check(profile(probe.host, selected, C.byref(current)) == 0 and current.value == selected,
                          'explicit per-host profile selection')
                    media = Media(probe)
                    query = media.match_media(probe.host, b'(prefers-contrast: more)')
                    check(bool(query), 'actual contrast media query')
                    try:
                        check(helper.project2_cocoa_contrast_reset_calls() == 0,
                              'exclude prior host/default-profile getter queries')
                        phase('before-page-preference')
                        media.supply(MediaPreferences(size=C.sizeof(MediaPreferences), color_scheme=1,
                                                     contrast=0 if page_more is None else 2 if page_more else 1), 'page contrast')
                        if page_more is None:
                            check(system_contrast(probe.host) == 0, 'private explicit System contrast policy')
                        media.settle()
                        phase('after-page-settle')
                        effective_more = system_more if page_more is None else page_more
                        check(media.matches(query) == int(effective_more), 'CSS follows resolved page policy')
                        phase('before-first-paint')
                        samples = [bytes(probe.paint())]
                        phase('after-first-paint')
                        samples.append(bytes(probe.paint()))
                        phase('after-second-paint')
                        check(samples[0] == samples[1], 'static control repeat is byte-identical')
                        calls = helper.project2_cocoa_contrast_calls()
                        if not args.legacy_only:
                            check(calls > 0 if page_more is None else calls == 0,
                                  'System exercises getter; explicit page policy avoids singleton')
                        page_label = 'system' if page_more is None else str(int(page_more))
                        label = f'system-{int(system_more)}-page-{page_label}'
                        (args.output / (label + '.rgba')).write_bytes(samples[0])
                        captures[(system_more, page_more)] = samples[0]
                        rows.append({'label': label, 'systemMore': system_more, 'pageMore': page_more,
                                     'vectorProfile': not args.legacy_only,
                                     'cssMore': media.matches(query), 'getterCalls': calls,
                                     'platformCalls': helper.project2_cocoa_contrast_platform_calls() if args.scoped_helper else None,
                                     'sha256': hashlib.sha256(samples[0]).hexdigest(),
                                     'controlHashes': {name: hashlib.sha256(crop(samples[0], box)).hexdigest()
                                                       for name, box in boxes.items()}})
                    finally:
                        media.release(query)
                        check(profile(probe.host, 0, C.byref(current)) == 0, 'profile restored')
        checks, policy_rows = contrast_policy_results(captures, boxes, not args.legacy_only)
        for condition, name in checks:
            check(condition, name)
        rows.extend(policy_rows)
        if args.legacy_reference:
            assert args.legacy_only, 'legacy byte reference requires untouched default profile'
            reference = json.loads(args.legacy_reference.read_text())
            old_rows = {row['label']: row for row in reference['rows'] if 'label' in row}
            for row in rows:
                if 'label' in row:
                    previous = old_rows.get(row['label'])
                    row['legacyReferenceComparison'] = {
                        'scope': 'Measured before/after; 0072 intentionally changes page-contrast leaks. No blanket byte-identity claim.',
                        'samePolicyAligned': row['pageMore'] == row['systemMore'],
                        'referencePresent': previous is not None,
                        'controlHashesEqual': previous is not None and row['controlHashes'] == previous['controlHashes']}

    finally:
        check(helper.project2_cocoa_contrast_restore() == 0, 'original process getter restored')
        after = {p.name: sha(p) for p in native.iterdir() if p.is_file()}
        check(before == after, 'native inputs unchanged')
        report = {'scope': 'Default legacy capture/reference; no pixel contrast behavior claim' if args.legacy_only else
                  'Post0072 vector page/system contrast; original strict pixel assertions plus System control; no GPU claim',
                  'assertions': assertions, 'failures': failures, 'rows': rows,
                  'scopedHelper': args.scoped_helper, 'unknownCallerControls': unknown_controls,
                  'nativeBefore': before, 'nativeAfter': after}
        (args.output / 'contrast-paths.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))
    if failures:
        raise AssertionError(failures)


if __name__ == '__main__':
    main()
