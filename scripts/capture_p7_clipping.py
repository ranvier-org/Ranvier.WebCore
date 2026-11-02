"""Capture the unchanged clipping gate in a disposable native-loading process."""
import ctypes
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'tests/abi'))
import background_content_clip_regression as gate

native = Path(sys.argv[1])
work = Path(sys.argv[2])
report = gate.verify(native, 'win-x64')
(work / 'original-report.json').write_text(json.dumps(report, indent=2))
gl = ctypes.WinDLL(str(native / 'libGLESv2.dll'))
gl.glGetString.argtypes = [ctypes.c_uint]
gl.glGetString.restype = ctypes.c_char_p
renderer = gl.glGetString(0x1F01)
assert renderer, 'original gate did not leave a current GPU context'
(work / 'capture-profile.json').write_text(json.dumps({'renderer': renderer.decode()}))
