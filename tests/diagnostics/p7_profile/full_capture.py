import base64
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sys
import zlib

root = Path(__file__).parent
sys.path.insert(0, str(root.parents[1] / 'abi'))
from resize_observation import Scene, Native, P, I

directory = Path(sys.argv[1])
output = Path(sys.argv[2])
cases = json.loads((root / 'cases.json').read_text())
native = Native(directory)
rows = []
gl_info = None
for scale in cases['scales']:
    for test in cases['cases']:
        name = test['name']
        print('RV_CASE_BEGIN ' + name + ' scale=' + str(scale), flush=True)
        tag = test.get('element', 'div')
        markup = ('<!doctype html><head><style>' + cases['style'] + test.get('css', '') + '</style></head><body>'
                  + test.get('before', '') + f'<{tag} id="f">' + test.get('inside', '') + f'</{tag}>' + test.get('after', '') + '</body>')
        scene = Scene(native, markup, scale)
        try:
            # The reviewed clipping baselines and shader fingerprint are of CPU-painted layers, composited on the GPU.
            native.ok('rv_host_set_gpu_painting', [P, I], scene.host, 0)
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
            pixels = (ctypes.c_uint8 * (width.value * height.value * 4))()
            native.ok('rv_host_paint_rgba', [P, P, I], scene.host, pixels, len(pixels))
            if os.environ.get('RANVIER_DIAGNOSTIC_TEXTURE_MODEL') and gl_info is None:
                gles = ctypes.WinDLL(str(directory / 'libGLESv2.dll'))
                gles.glGetString.argtypes = [ctypes.c_uint]
                gles.glGetString.restype = ctypes.c_char_p
                version = gles.glGetString(0x1F02)
                if version:
                    gl_info = {name: gles.glGetString(value).decode('utf-8') for name, value in [('version', 0x1F02), ('renderer', 0x1F01), ('vendor', 0x1F00)]}
                    gles.glGetShaderPrecisionFormat.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(I), ctypes.POINTER(I)]
                    for precision_name, value in [('fragmentLowFloat', 0x8DF0), ('fragmentMediumFloat', 0x8DF1), ('fragmentHighFloat', 0x8DF2)]:
                        limits, precision = (I * 2)(), I()
                        gles.glGetShaderPrecisionFormat(0x8B30, value, limits, ctypes.byref(precision))
                        gl_info[precision_name] = {'range': list(limits), 'precision': precision.value}
                    print('RV_GL_INFO ' + json.dumps(gl_info), flush=True)
            raw = bytes(pixels)
            rows.append({'name': name, 'scale': scale, 'width': width.value, 'height': height.value, 'rgbaSha256': hashlib.sha256(raw).hexdigest(),
                         'rgbaZlibBase64': base64.b64encode(zlib.compress(raw)).decode()})
        finally:
            scene.close()
assert len(rows) == 54
output.write_text(json.dumps({'results': rows, 'assertions': native.assertions, 'glInfo': gl_info}, separators=(',', ':')), encoding='utf-8')
print(json.dumps({'cases': len(rows), 'assertions': native.assertions}))
