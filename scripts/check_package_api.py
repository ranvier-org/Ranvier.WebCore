import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile


def verify(package):
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='ranvier-package-api-') as temporary:
        destination = Path(temporary).resolve()
        with zipfile.ZipFile(package) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            rid = manifest['rid']
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
        for name in ['css_supports', 'computed_style', 'fragment_rectangles', 'keyframe_rules', 'counter_style_rules', 'custom_properties', 'typed_style_values', 'style_property_maps', 'declared_style_maps', 'style_map_entries', 'geometry_values', 'detached_cssom_context']:
            subprocess.run([sys.executable, '-I', str(root / 'tests/abi' / (name + '.py')),
                            '--native-directory', str(destination)], check=True)
        print(f'PASS packaged API probes: {rid}, {files} native/resource files')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', type=Path, required=True)
    verify(parser.parse_args().package)
