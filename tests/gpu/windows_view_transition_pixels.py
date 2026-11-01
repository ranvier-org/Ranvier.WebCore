"""A11 snapshot pixels read from the acquired D3D11 frame, without host CPU painting."""
import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import linux_view_transition_pixels as scenario


def build_helper(output, compiler_environment=None):
    output.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    if compiler_environment or not shutil.which('cl'):
        if not compiler_environment:
            vswhere = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Microsoft Visual Studio/Installer/vswhere.exe'
            installation = subprocess.check_output([
                str(vswhere), '-latest', '-products', '*', '-requires',
                'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-property', 'installationPath'], text=True).strip()
            if not installation:
                raise RuntimeError('Visual Studio C++ tools are required for D3D readback')
            compiler_environment = Path(installation) / 'VC/Auxiliary/Build/vcvars64.bat'
        script = output / 'compiler-environment.cmd'
        script.write_text(f'@call "{compiler_environment}" >nul\n@set PATH\n@set INCLUDE\n@set LIB\n', newline='\r\n')
        for line in subprocess.check_output(['cmd', '/d', '/c', str(script)], text=True).splitlines():
            if '=' in line and not line.startswith('='):
                key, value = line.split('=', 1)
                environment[key.upper()] = value
    compiler = shutil.which('cl', path=environment.get('PATH'))
    if not compiler:
        raise RuntimeError('Selected compiler environment did not provide cl.exe')
    sources = Path(__file__).parent
    test = output / 'D3DFrameReadbackTests.exe'
    subprocess.run([compiler, '/nologo', '/std:c++20', '/EHsc', '/W4', '/WX', '/MT',
                    str(sources / 'D3DFrameReadback.cpp'), str(sources / 'D3DFrameReadbackTests.cpp'),
                    f'/Fe:{test}', f'/Fo:{output}/', '/link', 'd3d11.lib', 'dxgi.lib'],
                   cwd=output, env=environment, check=True)
    subprocess.run([str(test)], cwd=output, check=True, timeout=30)
    library = output / 'D3DFrameReadback.dll'
    subprocess.run([compiler, '/nologo', '/std:c++20', '/EHsc', '/W4', '/WX', '/LD', '/MT',
                    str(Path(__file__).with_name('D3DFrameReadback.cpp')), f'/Fe:{library}', f'/Fo:{output}/',
                    '/link', 'd3d11.lib', 'dxgi.lib'], cwd=output, env=environment, check=True)
    return library


class Consumer:
    transport = 'D3D11'
    helper = None
    live = []

    def __init__(self, native):
        self.n = native
        self.device = C.c_void_p()
        assert self.helper.gpu_readback_create(C.byref(self.device)) == 0 and self.device.value, 'hardware D3D11 device'
        self.frames = 0
        self.live.append(self)

    def close(self):
        if self.device.value:
            self.helper.gpu_readback_destroy(self.device)
            self.device = C.c_void_p()

    def pixels(self, host, label):
        P, I = C.c_void_p, C.c_int32
        self.n.ok('rv_host_update', [P], host)
        frame = P()
        self.n.ok('rv_host_acquire_d3d11_frame', [P, P, C.POINTER(P)], host, self.device, C.byref(frame))
        assert frame.value, 'strict D3D acquire returned no frame'
        try:
            texture, width, height, format_ = P(), I(), I(), I()
            self.n.ok('rv_gpu_frame_info', [P, P, P, P, P], frame,
                      C.byref(texture), C.byref(width), C.byref(height), C.byref(format_))
            assert texture.value and (width.value, height.value, format_.value) == (96, 64, 1)
            pixels = (C.c_ubyte * (96 * 64 * 4))()
            status = self.helper.gpu_readback_rgba(self.device, texture, pixels, len(pixels), 96, 64)
            assert status == 0, f'D3D staging readback HRESULT={status & 0xffffffff:08x}'
            output = bytes(pixels)
            sample_at = lambda x, y: list(output[(y * 96 + x) * 4:(y * 96 + x) * 4 + 4])
            sample = {'label': label, 'box': sample_at(20, 20), 'background': sample_at(80, 50),
                      'sha256': hashlib.sha256(output).hexdigest()}
            self.frames += 1
            print(json.dumps(sample), flush=True)
            return sample
        finally:
            self.n.ok('rv_gpu_frame_release', [P], frame)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--compiler-environment', type=Path)
    parser.add_argument('--repeats', type=int, default=1)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error('--repeats must be positive')
    library = build_helper(args.output.resolve(), args.compiler_environment)
    Consumer.helper = C.CDLL(str(library))
    Consumer.helper.gpu_readback_create.argtypes = [C.POINTER(C.c_void_p)]
    Consumer.helper.gpu_readback_create.restype = C.c_int32
    Consumer.helper.gpu_readback_destroy.argtypes = [C.c_void_p]
    Consumer.helper.gpu_readback_destroy.restype = None
    Consumer.helper.gpu_readback_rgba.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p, C.c_uint64, C.c_uint32, C.c_uint32]
    Consumer.helper.gpu_readback_rgba.restype = C.c_int32
    for index in range(args.repeats):
        try:
            scenario.run(args.native_directory, consumer_type=Consumer)
            assert Consumer.live[-1].frames == 9
            print(f'PASS D3D11 transition snapshot repeat={index + 1}', flush=True)
        finally:
            for consumer in Consumer.live:
                consumer.close()
            Consumer.live.clear()


if __name__ == '__main__':
    main()
