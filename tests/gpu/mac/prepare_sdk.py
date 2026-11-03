"""Stage the presenter SDK from its exact package and SDL source pins."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.request
import zipfile

PACKAGE_VERSION = '2026.1002.1'
PACKAGE_SHA256 = 'c5450151ffb6abf479d9cf6d36f331ff53ae3fbd4c6335f4ca86e6e104963568'
SDL_COMMIT = 'ea7a2dabfd1ab6b0a5720568ffd207f5825e47f1'
DYLIB_MEMBER = 'runtimes/osx-arm64/native/libSDL3.dylib'
DYLIB_SHA256 = 'ed551fb95c4d17a15c2973d3608740bf1a84ab7910c4fbc71f51002eac5963a5'
MAX_PACKAGE_BYTES = 128 * 1024 * 1024


def extract_library(package, destination):
    if hashlib.sha256(package.read_bytes()).hexdigest() != PACKAGE_SHA256:
        raise ValueError('The presenter package differs from its reviewed pin.')
    with zipfile.ZipFile(package) as archive:
        data = archive.read(DYLIB_MEMBER)
    if hashlib.sha256(data).hexdigest() != DYLIB_SHA256:
        raise ValueError('The presenter dylib differs from its reviewed pin.')
    destination.write_bytes(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True, type=Path)
    args = parser.parse_args()
    root = args.directory.resolve()
    root.mkdir(parents=True, exist_ok=False)
    library = root / 'lib'
    library.mkdir()
    package = root / 'presenter.nupkg'
    url = f'https://api.nuget.org/v3-flatcontainer/ppy.sdl3-cs/{PACKAGE_VERSION}/ppy.sdl3-cs.{PACKAGE_VERSION}.nupkg'
    request = urllib.request.Request(url, headers={'User-Agent': 'Ranvier private Mac GPU qualification'})
    with urllib.request.urlopen(request, timeout=120) as response, package.open('wb') as output:
        downloaded = 0
        while chunk := response.read(1024 * 1024):
            downloaded += len(chunk)
            if downloaded > MAX_PACKAGE_BYTES:
                raise ValueError('The presenter package exceeds its download limit.')
            output.write(chunk)
    dylib = library / 'libSDL3.dylib'
    extract_library(package, dylib)
    source = root / 'source'
    subprocess.run(['git', 'init', str(source)], check=True, capture_output=True)
    subprocess.run(['git', '-C', str(source), 'remote', 'add', 'origin', 'https://github.com/libsdl-org/SDL.git'], check=True)
    subprocess.run(['git', '-C', str(source), 'fetch', '--depth=1', 'origin', SDL_COMMIT], check=True)
    subprocess.run(['git', '-C', str(source), 'checkout', '--detach', 'FETCH_HEAD'], check=True)
    actual = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != SDL_COMMIT:
        raise ValueError('SDL headers differ from the pinned source commit.')
    install_name = subprocess.check_output(['otool', '-D', str(dylib)], text=True).splitlines()[1].strip()
    if install_name.startswith('@rpath/'):
        alias = library / install_name[len('@rpath/'):]
    else:
        alias = library / Path(install_name).name
    if not alias.resolve().is_relative_to(library.resolve()):
        raise ValueError('The presenter install name escapes the private library directory.')
    if alias != dylib:
        alias.parent.mkdir(parents=True, exist_ok=True)
        alias.symlink_to(os.path.relpath(dylib, alias.parent))
    pkgconfig = library / 'pkgconfig'
    pkgconfig.mkdir()
    (pkgconfig / 'sdl3.pc').write_text(
        f'prefix={root}\nlibdir=${{prefix}}/lib\nincludedir=${{prefix}}/source/include\n\n'
        'Name: sdl3\nDescription: Exact Ranvier private presenter SDK\nVersion: 3.5.0\n'
        'Libs: -L${libdir} -lSDL3 -Wl,-rpath,${libdir}\nCflags: -I${includedir}\n', encoding='utf-8')
    receipt = {'packageVersion': PACKAGE_VERSION, 'packageSha256': PACKAGE_SHA256,
               'sdlCommit': actual, 'dylibSha256': hashlib.sha256(dylib.read_bytes()).hexdigest(),
               'installName': install_name, 'privateAlias': str(alias), 'directory': str(root)}
    (root / 'sdk-receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
