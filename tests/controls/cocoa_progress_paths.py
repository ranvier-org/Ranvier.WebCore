"""Distinguish the default CoreUI painter from the explicitly selected vector painter."""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "abi"))


def blue_columns(pixels, width=300):
    return {x for y in range(20, 40) for x in range(20, 260)
            if (lambda c: c[2] > c[0] + 25 and c[2] > c[1] + 20 and c[3] == 255)(
                pixels[(y * width + x) * 4:(y * width + x) * 4 + 4])}


def vector_reduced_contract(samples, empty, full, width=300):
    center = (30 * width + 140) * 4
    track = empty[center:center + 3]
    opaque = full[center:center + 3]
    channel = max(range(3), key=lambda index: abs(opaque[index] - track[index]))
    delta = opaque[channel] - track[channel]
    uncertainty = 1 / abs(delta) if delta else 1
    alpha = [(pixels[center + channel] - track[channel]) / delta if delta else 0 for pixels in samples]
    columns = blue_columns(full, width)
    checks = [(len(columns) >= 180, 'opaque full-bar geometry control'),
              (abs(delta) >= 128, 'interior opacity endpoints have sufficient channel contrast'),
              (all(blue_columns(pixels, width) == columns for pixels in samples),
               'reduced vector geometry stays full-width while opacity pulses'),
              (all(0.3 - uncertainty <= value <= 0.6 + uncertainty for value in alpha),
               'reduced vector opacity follows the source 0.3 to 0.6 envelope'),
              (len({bytes(pixels[center:center + 3]) for pixels in samples}) > 1,
               'existing reduced vector opacity pulse remains active')]
    return checks, {'opacityEstimates': alpha, 'opacityChannel': channel,
                    'quantizationAlphaUncertainty': uncertainty,
                    'opacityMeasurement': 'Opaque interior, measured empty/full endpoints; one output-channel quantum',
                    'sourceOpacityEnvelope': [0.3, 0.6], 'fullBarColumns': sorted(columns)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', type=Path, required=True)
    parser.add_argument('--abi-source', type=Path, required=True)
    parser.add_argument('--system-helper', type=Path, required=True)
    parser.add_argument('--page-helper', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert sys.platform == 'darwin', 'actual Cocoa runtime required'
    sys.path.insert(0, str(args.abi_source.resolve()))
    from media_queries import Media, MediaPreferences
    from svg_paint_probe import SvgProbe
    from utf8_inputs import Utf8

    native = args.native_directory.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    digest = lambda path: hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()
    before = {p.relative_to(native).as_posix(): digest(p) for p in native.rglob('*') if p.is_file()}
    system = C.CDLL(str(args.system_helper.resolve()))
    system.project2_cocoa_motion_set.argtypes, system.project2_cocoa_motion_set.restype = [C.c_int], C.c_int
    system.project2_cocoa_motion_restore.argtypes, system.project2_cocoa_motion_restore.restype = [], None
    image = C.CDLL(str(args.page_helper.resolve() if args.page_helper else native / 'libRanvierWebCoreHost.dylib'))
    setting = image.project2_progress_form_control_profile
    setting.argtypes, setting.restype = [C.c_void_p, C.c_int32, C.POINTER(C.c_int32)], C.c_int32
    system_motion = image.project2_progress_system_motion
    system_motion.argtypes, system_motion.restype = [C.c_void_p], C.c_int32
    rows, failures = [], []
    assertions = 0

    def check(condition, label):
        nonlocal assertions
        assertions += 1
        if not condition:
            failures.append(label)

    def profile(host, mode):
        current = C.c_int32(-1)
        status = setting(host, mode, C.byref(current))
        check(status == 0, 'private profile call: ' + str((mode, status)))
        return current.value

    try:
        for system_reduced in [False, True]:
            check(system.project2_cocoa_motion_set(int(system_reduced)) == 0, 'process-local system control')
            for vector in [False, True]:
                with SvgProbe(native, 300, 70) as probe:
                    probe.call('rv_host_set_accelerated_compositing', [C.c_void_p, C.c_int32], probe.host, 0)
                    default_profile = profile(probe.host, -1)
                    check(default_profile == 0, 'untouched host retains default legacy styling')
                    probe.load('<!doctype html><style>body{margin:0;background:white}progress{position:absolute;left:20px;top:20px;width:240px;height:20px;accent-color:#007aff}</style><progress id="p"></progress>', standalone=False)
                    check(profile(probe.host, int(vector)) == int(vector), 'explicit per-host painter selection')
                    progress = probe.node('p')
                    if vector:
                        with SvgProbe(native, 20, 20) as untouched:
                            untouched.call('rv_host_set_accelerated_compositing', [C.c_void_p, C.c_int32], untouched.host, 0)
                            check(profile(untouched.host, -1) == 0, 'another host is unaffected')
                    probe.bind('rv_host_set_focused', C.c_int32, [C.c_void_p, C.c_int32])(probe.host, 1)
                    cycle = probe.bind('rv_run_loop_cycle', C.c_int32, [C.c_int32])
                    media = Media(probe)
                    query = media.match_media(probe.host, b'(prefers-reduced-motion: reduce)')
                    check(bool(query), 'actual MediaQueryList')
                    try:
                        for page_mode, page_policy in [(0, 'system'), (1, 'off'), (2, 'on')]:
                            page_reduced = system_reduced if page_mode == 0 else page_mode == 2
                            media.supply(MediaPreferences(size=C.sizeof(MediaPreferences), reduced_motion=page_mode), 'page preference')
                            if page_mode == 0:
                                check(system_motion(probe.host) == 0, 'private explicit System page setting')
                            media.settle()
                            check(media.matches(query) == int(page_reduced), 'page media preference')
                            policy_hashes = []
                            policy_pixels = []
                            for sample in range(3):
                                if sample:
                                    cycle(100)
                                pixels = bytes(probe.paint())
                                columns = set()
                                ink = 0
                                for y in range(20, 40):
                                    for x in range(20, 260):
                                        r, g, b, alpha = pixels[(y * 300 + x) * 4:(y * 300 + x) * 4 + 4]
                                        if (r, g, b) != (255, 255, 255):
                                            ink += 1
                                        if b > r + 25 and b > g + 20 and alpha == 255:
                                            columns.add(x)
                                span = max(columns) - min(columns) + 1 if columns else 0
                                label = f'system-{int(system_reduced)}-vector-{int(vector)}-page-{page_policy}-sample-{sample}'
                                (args.output / (label + '.rgba')).write_bytes(pixels)
                                row = {'label': label, 'systemReduced': system_reduced, 'vectorProfile': vector,
                                       'pageReduced': page_reduced, 'pagePolicy': page_policy,
                                       'privateSystemOverride': page_mode == 0,
                                       'sample': sample, 'blueSpan': span, 'inkPixels': ink,
                                       'pixelSha256': hashlib.sha256(pixels).hexdigest(),
                                       'assertionScope': 'quarter/full vector geometry and motion' if vector else 'fixed visible legacy phase / advancing clock'}
                                rows.append(row)
                                policy_hashes.append(row['pixelSha256'])
                                policy_pixels.append(pixels)
                                check(ink > 100, label + ' painted actual native track')
                                if vector:
                                    check(span >= 180 if page_reduced else 35 <= span <= 90, label + ' explicit vector geometry')
                            if page_reduced:
                                if not vector:
                                    check(len(set(policy_hashes)) == 1, 'resolved legacy reduced motion remains pixel-identical over positive cycles')
                                probe.call('rv_dom_element_set_attribute', [probe.pointer, Utf8, Utf8], progress, b'value', b'0')
                                empty_track = bytes(probe.paint())
                                check(hashlib.sha256(empty_track).hexdigest() != policy_hashes[0], 'reduced phase contains a visible indicator distinct from empty track')
                                empty_label = f'system-{int(system_reduced)}-vector-{int(vector)}-page-{page_policy}-empty-track'
                                (args.output / (empty_label + '.rgba')).write_bytes(empty_track)
                                rows.append({'label': empty_label, 'systemReduced': system_reduced, 'vectorProfile': vector, 'pagePolicy': page_policy, 'determinateEmpty': True, 'pixelSha256': hashlib.sha256(empty_track).hexdigest()})
                                if vector:
                                    probe.call('rv_dom_element_set_attribute', [probe.pointer, Utf8, Utf8], progress, b'value', b'1')
                                    full_bar = bytes(probe.paint())
                                    full_label = empty_label.replace('empty-track', 'full-bar')
                                    (args.output / (full_label + '.rgba')).write_bytes(full_bar)
                                    checks, details = vector_reduced_contract(policy_pixels, empty_track, full_bar)
                                    for condition, label in checks:
                                        check(condition, full_label + ': ' + label)
                                    rows.append({'label': full_label, 'systemReduced': system_reduced,
                                                 'vectorProfile': True, 'pagePolicy': page_policy,
                                                 'determinateFull': True, 'pixelSha256': hashlib.sha256(full_bar).hexdigest(),
                                                 **details})
                                probe.call('rv_dom_element_remove_attribute', [probe.pointer, Utf8], progress, b'value')
                                media.settle()
                            else:
                                check(len(set(policy_hashes)) > 1, 'normal indeterminate painter advances across positive cycles')
                    finally:
                        media.release(query)
                        check(profile(probe.host, default_profile) == default_profile, 'profile restored before teardown')
    finally:
        system.project2_cocoa_motion_restore()
    after = {p.relative_to(native).as_posix(): digest(p) for p in native.rglob('*') if p.is_file()}
    check(before == after, 'native files unchanged')
    report = {'assertions': assertions, 'failures': failures, 'rows': rows,
              'nativeBefore': before, 'nativeAfter': after,
              'scope': 'Default legacy fixed phase and explicit vector stationary opacity pulse; per-page On/Off/System and advancing normal clocks',
              'originalVectorIdentityRed': '41600462117 retained three overstrong vector pixel-identity failures; issue224 explicitly expects a reduced opacity pulse',
              'originalRed': '41504792300 default legacy painter evaluated with vector-only expectations; retained unchanged'}
    (args.output / 'progress-paths.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))
    if failures:
        raise AssertionError(failures)


if __name__ == '__main__':
    main()
