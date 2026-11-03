import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests/abi'))
from abi_expectation import expected_environment


def verify(package, gpu=False, evidence=None, expected_abi=63):
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='ranvier-package-api-') as temporary:
        destination = Path(temporary).resolve() / 'native'
        with zipfile.ZipFile(package) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            if type(expected_abi) is not int or expected_abi not in (63, 64):
                raise ValueError('Select supported package ABI63 or ABI64 explicitly.')
            environment = expected_environment(manifest, expected_abi, os.environ)
            rid = manifest['rid']
            if gpu and (rid not in ['win-x64', 'linux-x64', 'linux-arm64', 'osx-arm64'] or manifest.get('flavor') != 'gpu'):
                raise ValueError('Shared-frame acceptance requires a supported GPU package (Windows x64, Linux or macOS arm64)')
            if rid not in ['win-x64', 'win-arm64', 'linux-x64', 'linux-arm64', 'osx-arm64']:
                raise ValueError('Unsupported package runtime: ' + str(rid))
            prefix = f'runtimes/{rid}/native/'
            files = 0
            for entry in archive.infolist():
                if entry.is_dir() or not entry.filename.startswith(prefix):
                    continue
                target = (destination / entry.filename[len(prefix):]).resolve()
                if not target.is_relative_to(destination):
                    raise ValueError('Package native payload escapes its allocated directory')
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as source, target.open('wb') as output:
                    shutil.copyfileobj(source, output)
                files += 1
            if files == 0:
                raise ValueError('Package has no native payload for ' + rid)
        if gpu and rid.startswith('linux-'):
            environment.update(EGL_PLATFORM='surfaceless', LIBGL_ALWAYS_SOFTWARE='1')
            for arguments in [[], ['--context-lifecycle']]:
                subprocess.run([sys.executable, '-I', str(root / 'tests/gpu/linux_egl.py'),
                                str(destination / 'libRanvierWebCoreHost.so'), *arguments], check=True, env=environment)
            subprocess.run([sys.executable, '-I', str(root / 'tests/gpu/linux_view_transition_pixels.py'),
                            '--native-directory', str(destination)], check=True, env=environment)
            subprocess.run([sys.executable, '-I', str(root / 'tests/gpu/compositor_input_linux.py'),
                            '--native-directory', str(destination), '--report', str(destination.parent / 'compositor-input-linux.json')],
                           check=True, env=environment)
        elif gpu and rid == 'osx-arm64':
            subprocess.run([sys.executable, '-I', str(root / 'tests/gpu/mac/qualify_package.py'),
                            '--native-directory', str(destination), '--output', str(evidence or destination.parent / 'mac-gpu')], check=True, env=environment)
        elif gpu:
            sdl = destination.parent / 'sdl'
            subprocess.run([sys.executable, '-I', str(root / 'scripts/sdl_runtime.py'), '--out', str(sdl)], check=True, env=environment)
            subprocess.run([sys.executable, '-I', str(root / 'tests/gpu/run.py'), '--native', str(destination),
                            '--sdl', str(sdl / 'SDL3.dll'), '--teardown', 'all'], check=True, env=environment)
            subprocess.run([sys.executable, '-I', str(root / 'tests/gpu/windows_view_transition_pixels.py'),
                            '--native-directory', str(destination), '--output', str(destination.parent / 'transition-readback')],
                           check=True, env=environment)
            subprocess.run([sys.executable, '-I', str(root / 'tests/gpu/compositor_windows.py'),
                            '--native-directory', str(destination), '--output', str(destination.parent / 'compositor-input')],
                           check=True, env=environment)
        else:
            for name in ['css_supports', 'computed_style', 'fragment_rectangles', 'keyframe_rules', 'counter_style_rules', 'custom_properties', 'typed_style_values', 'style_property_maps', 'declared_style_maps', 'style_map_entries', 'geometry_values', 'matrix_values', 'css_transforms', 'detached_cssom_context']:
                subprocess.run([sys.executable, '-I', str(root / 'tests/abi' / (name + '.py')),
                                '--native-directory', str(destination)], check=True, env=environment)
        subprocess.run([sys.executable, '-I', '-X', 'utf8', str(root / 'tests/abi/mutation_observation.py'),
                        '--native-directory', str(destination)], check=True,
                       env=environment)
        print(f'PASS packaged API probes: {rid}, {files} native/resource files')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--gpu', action='store_true', help='Verify shared frames and lifetimes (D3D11, EGLImage or IOSurface)')
    parser.add_argument('--evidence', type=Path, help='retain the macOS public transport logs and receipts here')
    parser.add_argument('--expected-abi', type=int, choices=[63, 64], default=63)
    args = parser.parse_args()
    verify(args.package, gpu=args.gpu, evidence=args.evidence, expected_abi=args.expected_abi)
