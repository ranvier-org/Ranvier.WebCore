import ctypes
import argparse
import hashlib
import json
from pathlib import Path
import sys

root = Path(__file__).parent
parser = argparse.ArgumentParser()
parser.add_argument('--native-directory', type=Path)
parser.add_argument('--output', type=Path)
args = parser.parse_args()
output = args.output.resolve() if args.output else root
output.mkdir(parents=True, exist_ok=True)
stage = args.native_directory.resolve() if args.native_directory else root / 'precision-runtime' / 'runtimes' / 'win-x64' / 'native'
assert stage.is_dir(), 'caller must stage the verified official package first'
def hashes():
    return {p.relative_to(stage).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in stage.rglob('*') if p.is_file()}
before = hashes()
sys.path.insert(0, str(root / 'helpers'))
from resize_observation import Native, Scene, P, I
native = Native(stage)
scene = Scene(native, '<!doctype html><style>body{margin:0}div{width:100.5px;height:33.25px;transform:translate3d(7.25px,11.5px,0);will-change:transform;background:red}</style><div></div>', 1.5)
try:
    scene.update()
    scene.update()
    rgba = (ctypes.c_ubyte * (1200*900*4))()
    native.ok('rv_host_paint_rgba', [P, P, I], scene.host, rgba, len(rgba))
    gles = ctypes.WinDLL(str(stage / 'libGLESv2.dll'))
    gles.glGetString.argtypes = [ctypes.c_uint]
    gles.glGetString.restype = ctypes.c_char_p
    gles.glGetIntegerv.argtypes = [ctypes.c_uint, ctypes.POINTER(I)]
    gles.glGetShaderPrecisionFormat.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(I), ctypes.POINTER(I)]
    results = {}
    for shader_name, shader in [('vertex',0x8B31),('fragment',0x8B30)]:
        results[shader_name] = {}
        for precision_name, precision in [('low',0x8DF0),('medium',0x8DF1),('high',0x8DF2)]:
            limits, bits = (I*2)(), I()
            gles.glGetShaderPrecisionFormat(shader, precision, limits, ctypes.byref(bits))
            results[shader_name][precision_name] = {'range':list(limits),'fractionBits':bits.value}
    renderer = gles.glGetString(0x1F01).decode()
    vendor = gles.glGetString(0x1F00).decode()
    version = gles.glGetString(0x1F02).decode()
    subpixel = I()
    gles.glGetIntegerv(0x0D50, ctypes.byref(subpixel))
finally:
    scene.close()
assert hashes() == before
receipt = {'shaderPrecision':results,'renderer':renderer,'vendor':vendor,'version':version,'subpixelBits':subpixel.value,
           'runtime':before,'nativeUnchanged':True,'assertions':native.assertions,
           'purpose':'Actual vertex+fragment precision only; no new renderer build or repeated54-case gate'}
(output / 'vertex-fragment-precision.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
assert all(value['fractionBits'] == 23 for shader in results.values() for value in shader.values())
print(json.dumps({'vertex':results['vertex'],'fragment':results['fragment'],'runtimeUnchanged':True}))
