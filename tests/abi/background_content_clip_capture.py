"""Capture all physical paint controls through the public native paint API."""
import argparse
import base64
import ctypes
import hashlib
import json
from pathlib import Path
import sys
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
from background_content_clip import FIXTURES, Scene, Native, P, I


def capture_samples(directory, cases):
    native = Native(directory)
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
                native.ok('rv_host_paint_size', [P, ctypes.POINTER(I), ctypes.POINTER(I)], scene.host,
                          ctypes.byref(width), ctypes.byref(height))
                pixels = (ctypes.c_uint8 * (width.value * height.value * 4))()
                native.ok('rv_host_paint_rgba', [P, P, I], scene.host, pixels, len(pixels))
                yield test['name'], scale, width.value, height.value, bytes(pixels)
            finally:
                scene.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    cases_path = FIXTURES / 'background-content-clip-cases.json'
    cases = json.loads(cases_path.read_text())
    results = [dict(name=name, scale=scale, width=width, height=height,
                    rgbaSha256=hashlib.sha256(raw).hexdigest(),
                    rgbaZlibBase64=base64.b64encode(zlib.compress(raw, 6)).decode())
               for name,scale,width,height,raw in capture_samples(args.native_directory, cases)]
    assert len(results) == 54
    args.output.write_text(json.dumps(dict(source=args.source, native_directory=args.native_directory,
                                          casesSha256=hashlib.sha256(cases_path.read_bytes()).hexdigest(),
                                          results=results), separators=(',', ':')) + '\n')
    print('Captured 54 complete RGBA controls; baseline review required')


if __name__ == '__main__':
    main()
