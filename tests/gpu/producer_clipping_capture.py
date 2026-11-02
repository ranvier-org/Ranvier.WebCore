"""Capture the original comparator and actual current context in an owned process."""
import argparse
import ctypes
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests/abi'))
import background_content_clip_regression as gate
from form_collections import ABI


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory',type=Path,required=True)
    parser.add_argument('--rid',choices=['win-x64','linux-x64'],required=True)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--profile',type=Path,required=True)
    args = parser.parse_args()
    report = gate.verify(args.native_directory,args.rid,expected_abi=ABI,retain_all_raw=True)
    args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    gl = ctypes.WinDLL(str(args.native_directory/'libGLESv2.dll')) if args.rid == 'win-x64' else ctypes.CDLL('libGLESv2.so.2')
    gl.glGetString.argtypes,gl.glGetString.restype = [ctypes.c_uint],ctypes.c_char_p
    values = {}
    for name,token in [('renderer',0x1F01),('version',0x1F02),('vendor',0x1F00)]:
        value = gl.glGetString(token)
        assert value, 'No current host GPU context: '+name
        values[name] = value.decode()
    args.profile.write_text(json.dumps(values,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'originalResult':report['result'],'cases':len(report['results']),
                      'strictMasks':report['strictContentMaskKeys'],'originalFailures':len(report['failures'])}))


if __name__ == '__main__': main()
