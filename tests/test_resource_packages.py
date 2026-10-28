"""Restore five RID packages and verify resource paths in a standalone consumer."""

import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile


ROOT = Path(__file__).resolve().parents[1]
VERSION = '1.0.0-resource-test'
RIDS = ['win-x64', 'win-arm64', 'osx-arm64', 'linux-x64', 'linux-arm64']
ICONS = ['missingImage.png', 'missingImage@2x.png', 'missingImage@3x.png',
         'panIcon.png', 'textAreaResizeCorner.png', 'textAreaResizeCorner@2x.png']


def package(feed, name, files, dependencies=''):
    with zipfile.ZipFile(feed / f'{name}.{VERSION}.nupkg', 'w') as archive:
        archive.writestr(f'{name}.nuspec', f'''<?xml version="1.0"?>
<package><metadata><id>{name}</id><version>{VERSION}</version><authors>fixture</authors>
<description>Resource contract fixture</description>{dependencies}</metadata></package>''')
        for path, contents in files.items():
            archive.writestr(path, contents)


def run(work):
    (work / 'global.json').write_text(json.dumps({'sdk': {
        'version': '10.0.100', 'rollForward': 'latestFeature', 'allowPrerelease': False}}))
    feed = work / 'feed'
    feed.mkdir()
    target = (ROOT / 'packaging/buildTransitive.targets').read_text()
    for rid in RIDS:
        name = f'Ranvier.WebCore.Native.{rid}'
        files = {f'buildTransitive/{name}.targets': target.replace('@RID@', rid),
                 'lib/net10.0/_._': b'', f'runtimes/{rid}/native/fixture.dll': rid.encode()}
        if rid.startswith('win-'):
            files.update({f'runtimes/{rid}/native/WebKit.resources/icons/{icon}': f'{rid}:{icon}'.encode()
                          for icon in ICONS})
            files[f'runtimes/{rid}/native/WebKit.resources/icons/nested/probe.png'] = f'{rid}:nested'.encode()
        package(feed, name, files)
    meta = ET.parse(ROOT / 'packaging/Ranvier.WebCore.Native.Meta.csproj')
    dependencies = [item.get('Include') for item in meta.findall('.//PackageReference')]
    assert set(dependencies) == {f'Ranvier.WebCore.Native.{rid}' for rid in RIDS}
    references = ''.join(f'<dependency id="{name}" version="[{VERSION}]" />' for name in dependencies)
    package(feed, 'Ranvier.WebCore.Native', {'lib/net10.0/_._': b''},
            f'<dependencies><group targetFramework="net10.0">{references}</group></dependencies>')
    (work / 'NuGet.Config').write_text(f'''<configuration><packageSources><clear />
<add key="fixture" value="{feed.as_posix()}" /></packageSources></configuration>''')
    project = work / 'Consumer.csproj'
    project.write_text(f'''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>
<RuntimeIdentifier>win-x64</RuntimeIdentifier><SelfContained>false</SelfContained><UseAppHost>false</UseAppHost>
<RestorePackagesPath>{(work / 'cache').as_posix()}</RestorePackagesPath>
</PropertyGroup><ItemGroup><PackageReference Include="Ranvier.WebCore.Native" Version="{VERSION}" />
</ItemGroup></Project>''')
    (work / 'Program.cs').write_text('System.Console.WriteLine("resource fixture");')

    def command(*arguments):
        result = subprocess.run(['dotnet', *map(str, arguments)], cwd=work,
                                capture_output=True, text=True)
        with (work / 'commands.log').open('a', encoding='utf-8') as log:
            log.write('dotnet ' + ' '.join(map(str, arguments)) + '\n' + result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)

    for runtime in ['win-x64', 'win-arm64']:
        expected = {f'WebKit.resources/icons/{name}': f'{runtime}:{name}'.encode() for name in ICONS}
        expected['WebKit.resources/icons/nested/probe.png'] = f'{runtime}:nested'.encode()
        command('restore', project, f'-p:RuntimeIdentifier={runtime}', '--configfile', work / 'NuGet.Config', '--nologo')
        assets = json.loads((work / 'obj/project.assets.json').read_text())
        assert all(f'Ranvier.WebCore.Native.{rid}/{VERSION}' in assets['libraries'] for rid in RIDS)
        for action, destination in [('build', 'jit'), ('publish', 'publish')]:
            output = work / runtime / destination
            command(action, project, f'-p:RuntimeIdentifier={runtime}', '--no-restore', '-c', 'Release', '--nologo', '-o', output)
            for relative, contents in expected.items():
                path = output / relative
                assert path.is_file(), f'{action}: missing {relative}; files={list(output.glob("*.png"))}'
                assert path.read_bytes() == contents, f'{action}: wrong RID bytes for {relative}'
            assert (output / 'fixture.dll').read_bytes() == runtime.encode(), f'{action}: wrong native DLL selection'
    print('MULTI_RID_PACKAGE_RESOURCES PASS: five-package restore, both Windows RIDs, JIT/publish canonical paths and exact bytes')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path)
    args = parser.parse_args()
    if args.work:
        args.work.mkdir(parents=True, exist_ok=False)
        run(args.work.resolve())
    else:
        with tempfile.TemporaryDirectory(prefix='ranvier-resource-packages-') as temporary:
            run(Path(temporary))
