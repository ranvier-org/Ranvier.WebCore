import argparse
import ctypes
import hashlib
import json
from pathlib import Path

from resize_observation import Scene, Native, P, I
from snapshot_options import png_pixels

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'


def red_rows(width, height, rgba):
    result = []
    for y in range(height):
        pixels = []
        for x in range(width):
            at = (y * width + x) * 4
            r, g, b, a = rgba[at:at + 4]
            if r > 250 and g < 5 and b < 5 and a > 250:
                pixels.append(x)
        if pixels:
            result.append([y, pixels[0], pixels[-1] + 1, len(pixels)])
    return result


def main():
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--native-directory')
    source.add_argument('--browser-capture', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--oracle', type=Path, default=FIXTURES / 'background-content-clip-oracle.json')
    args = parser.parse_args()
    cases_path = FIXTURES / 'background-content-clip-cases.json'
    cases = json.loads(cases_path.read_text())
    report = {'casesSha256': hashlib.sha256(cases_path.read_bytes()).hexdigest(), 'results': []}
    if args.browser_capture:
        capture = json.loads((args.browser_capture / 'capture.json').read_text())
        report.update(browser=capture['browser'], playwright=capture['playwright'])
        for entry in capture['reports']:
            width, height, rgba = png_pixels((args.browser_capture / entry['png']).read_bytes())
            assert [width, height] == [800 * entry['scale'], 600 * entry['scale']]
            rows = red_rows(width, height, rgba)
            assert rows, f'No red content pixels: {entry["name"]} @{entry["scale"]}'
            report['results'].append({**entry, 'rows': rows})
        assert len(report['results']) == len(cases['scales']) * len(cases['cases'])
        args.report.write_text(json.dumps(report, indent=2) + '\n')
        print(f"Captured {len(report['results'])} Chromium paint controls")
        return
    oracle = json.loads(args.oracle.read_text())
    assert oracle['casesSha256'] == report['casesSha256']
    native = Native(args.native_directory)
    failures = []
    expected = {(entry['name'], entry['scale']): entry for entry in oracle['results']}
    for scale in cases['scales']:
        for test in cases['cases']:
            tag = test.get('element', 'div')
            markup = ('<!doctype html><head><style>' + cases['style'] + test.get('css', '') + '</style></head><body>'
                      + test.get('before', '') + f'<{tag} id="f">' + test.get('inside', '') + f'</{tag}>' + test.get('after', '') + '</body>')
            scene = Scene(native, markup, scale)
            try:
                if 'compositing' in test:
                    native.ok('rv_host_set_accelerated_compositing', [P, I], scene.host, test['compositing'])
                if 'scroll' in test:
                    target, left, top = test['scroll']
                    native.ok('rv_dom_element_set_scroll_left', [P, I], scene.node(target), left)
                    native.ok('rv_dom_element_set_scroll_top', [P, I], scene.node(target), top)
                scene.update()
                scene.update()
                width, height = I(), I()
                native.ok('rv_host_paint_size', [P, ctypes.POINTER(I), ctypes.POINTER(I)], scene.host, ctypes.byref(width), ctypes.byref(height))
                rgba = (ctypes.c_uint8 * (width.value * height.value * 4))()
                native.ok('rv_host_paint_rgba', [P, P, I], scene.host, rgba, len(rgba))
                rows = red_rows(width.value, height.value, bytes(rgba))
                entry = {'name': test['name'], 'scale': scale, 'rows': rows}
                report['results'].append(entry)
                target = expected[(test['name'], scale)]['rows']
                if rows != target:
                    failures.append({'name': test['name'], 'scale': scale, 'nativeRows': rows, 'chromiumRows': target})
                print(f"{test['name']} @{scale}: {'PASS' if rows == target else 'DIFF'}", flush=True)
            finally:
                scene.close()
    report['failures'] = failures
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    assert not failures, f'{len(failures)}/{len(report["results"])} physical paint controls differ; see {args.report}'
    print(f'PASS {len(report["results"])} physical paint controls')


if __name__ == '__main__':
    main()
