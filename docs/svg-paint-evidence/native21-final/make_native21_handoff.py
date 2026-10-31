import hashlib, json, shutil, subprocess, sys, zipfile
from pathlib import Path

repo = Path('C:/wk/native-svg-paint')
frozen = repo / 'artifacts/native21-0032-frozen'
receipt = json.loads((frozen / 'runtime-receipt.json').read_text())
runtime = frozen / 'runtimes/win-x64/native'
out = repo / 'artifacts/native21-handoff'
assert not out.exists(), 'Hand off into a new directory'
version = json.loads((repo / 'pins.json').read_text())['package']['version']
assert version == '0.1.0-preview.21'
head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
dirty = subprocess.run(['git', 'status', '--porcelain'], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
assert not dirty, dirty


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


canonical = out / 'canonical'
canonical.mkdir(parents=True)
for name in ['gen/Ranvier.Dom.fs', 'gen/dom-api.json', 'gen/dom.json', 'gen/dom-report.txt', 'host/RanvierWebCoreAbi.h', 'host/RanvierWebCoreDom.h']:
    shutil.copyfile(repo / name, canonical / Path(name).name)
stage = out / 'package-stage'
native = stage / 'runtimes/win-x64/native'
files = []
for entry in receipt['shippingFiles']:
    target = native / entry['name']
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(runtime / entry['name'], target)
    assert digest(target) == entry['sha256'], entry['name']
    files.append(dict(name=entry['name'], bytes=entry['bytes'], sha256=entry['sha256']))
assert len(files) == 24
(stage / 'include').mkdir()
for name in ['RanvierWebCoreAbi.h', 'RanvierWebCoreDom.h']:
    shutil.copyfile(repo / 'host' / name, stage / 'include' / name)
commit = json.loads((repo / 'pins.json').read_text())['webkit']['commit']
manifest = dict(flavor='slim', rid='win-x64', version=version, webkit=commit, abi=29,
                source=dict(commit=head, dirty=False, builder='private-owned-relink'), total_bytes=sum(f['bytes'] for f in files), files=files)
(stage / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
(stage / 'buildTransitive.targets').write_text((repo / 'packaging/buildTransitive.targets').read_text().replace('@RID@', 'win-x64'))
packages = out / 'packages'
run = lambda command: subprocess.run(['rtk', 'proxy', *command], cwd='C:/Users/shaya/RiderProjects/Ranvier', check=True)
run(['dotnet', 'pack', str(repo / 'packaging/Ranvier.WebCore.Native.csproj'), '-c', 'Release', '--nologo', '-o', str(packages),
     '-p:PackageId=Ranvier.WebCore.Native.win-x64', f'-p:PackageVersion={version}', f'-p:StageDir={stage.as_posix()}/',
     '-p:RuntimeId=win-x64', f'-p:WebKitCommit={commit}'])
run(['dotnet', 'pack', str(repo / 'src/Ranvier.WebCore/Ranvier.WebCore.fsproj'), '-c', 'Release', '--nologo', '-o', str(packages),
     f'-p:PackageVersion={version}'])
result = {'nativeVersion': version, 'abiVersion': 29, 'sourceHead': head, 'buildHead': receipt['buildHead'],
          'runtimeReceipt': str(frozen / 'runtime-receipt.json'), 'runtimeReceiptSha256': digest(frozen / 'runtime-receipt.json'),
          'canonical': {p.name: digest(p) for p in sorted(canonical.iterdir())},
          'counts': {'interfaces': 248, 'functions': 2455, 'roots': 50, 'dictionaries': 22, 'stubs': 0},
          'sourcePatches': '0000-0032 (0028-0032 from this producer); H05 patch excluded', 'shippingFiles': files, 'packages': {}}
for package in sorted(packages.glob('*.nupkg')):
    entry = {'sha256': digest(package)}
    with zipfile.ZipFile(package) as archive:
        names = archive.namelist()
        dll = next((n for n in names if n.endswith('Ranvier.WebCore.dll')), None)
        if dll:
            entry['assemblySha256'] = hashlib.sha256(archive.read(dll)).hexdigest()
        native_entries = [n for n in names if n.startswith('runtimes/win-x64/native/')]
        if native_entries:
            entry['shippingFileCount'] = len(native_entries)
            for f in files:
                assert hashlib.sha256(archive.read('runtimes/win-x64/native/' + f['name'])).hexdigest() == f['sha256'], f['name']
    result['packages'][package.name] = entry
(out / 'handoff-receipt.json').write_text(json.dumps(result, indent=2) + '\n')
print('HANDOFF', out, digest(out / 'handoff-receipt.json'), json.dumps(result['packages']), flush=True)
