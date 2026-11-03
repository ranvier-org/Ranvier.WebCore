"""Qualify the optional F#/View media consumer with a caller-selected View graph."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def check_package_graphs(artifacts, traced, sha):
    suffix = '.Traced' if traced else ''
    expected = {f'Ranvier.View.WebCore{suffix}/0.1.0-alpha.45'.casefold(),
                f'Ranvier.View.WebCore.Sdl{suffix}/0.1.0-alpha.45'.casefold()}
    families = ['Ranvier.View', 'Ranvier.View.Dom', 'Ranvier.View.WebCore', 'Ranvier.View.WebCore.Sdl']
    opposing = {(name if traced else name + '.Traced').casefold() for name in families}
    graphs = []
    for path in artifacts.rglob('project.assets.json'):
        assets = json.loads(path.read_text(encoding='utf-8'))
        libraries = assets['libraries']
        references = {name for name, value in libraries.items() if value['type'] == 'project'}
        assert references <= {'NativeMedia/1.0.0'}, references
        packages = {name for name, value in libraries.items() if value['type'] == 'package'}
        mixed = {name for name in packages if name.split('/', 1)[0].casefold() in opposing}
        assert not mixed, {'traced': traced, 'opposingViewPackages': sorted(mixed)}
        graphs.append({'path': str(path), 'sha256': sha(path), 'projectReferences': sorted(references),
                       'packageLibraries': sorted(packages)})
    assert graphs and any(expected <= {name.casefold() for name in graph['packageLibraries']}
                          for graph in graphs), expected
    return graphs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-stage', type=Path, required=True)
    graph = parser.add_mutually_exclusive_group(required=True)
    graph.add_argument('--view-root', type=Path)
    graph.add_argument('--package-only', action='store_true')
    parser.add_argument('--traced', action='store_true')
    parser.add_argument('--nuget-config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--dotnet-sdk-driver', type=Path)
    parser.add_argument('--phase', choices=['all', 'build', 'run'], default='all')
    parser.add_argument('--keep-artifacts', action='store_true')
    args = parser.parse_args()
    if os.name != 'nt':
        raise RuntimeError('This qualification uses the optional Windows SDK provider')
    root = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    previous = json.loads((output / 'managed-receipt.json').read_text()) if args.phase == 'run' else None
    work = Path(previous['workDirectory']).resolve() if previous else Path(tempfile.mkdtemp(prefix='managed-', dir=output)).resolve()
    assert work.parent == output and work.is_dir(), 'Expected owned build directory'
    native = args.native_stage.resolve() / 'runtimes/win-x64/native'
    sha = lambda path: hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()
    inputs = [*sorted((root / 'examples/NativeMedia').rglob('*.fs')),
              *sorted((root / 'examples/NativeMedia').rglob('*.fsproj')),
              *sorted((root / 'examples/NativeMedia').glob('*.h')),
              root / 'examples/NativeMedia/WindowsPlaybackBridge.cpp',
              root / 'examples/NativeMedia/build_windows.py',
              *sorted((root / 'tests/media').glob('Managed*')),
              root / 'tests/fixtures/native-media-colors-tone.json',
              root / 'tests/fixtures/native-media-colors-tone.mp4', Path(__file__)]
    before = {path.relative_to(root).as_posix(): sha(path) for path in inputs}
    native_before = {path.relative_to(native).as_posix(): sha(path) for path in native.rglob('*') if path.is_file()}
    assert native_before, 'Missing explicit native stage'
    report = previous or {'sourceBefore': before, 'nativeBefore': native_before, 'commands': [],
              'viewRoot': str(args.view_root.resolve()) if args.view_root else None,
              'packageOnly': args.package_only, 'traced': args.traced,
              'nugetConfigSha256': sha(args.nuget_config.resolve()),
              'scope': 'Optional app-owned Windows provider; no renderer ABI changes'}
    if previous:
        assert previous['buildReady'] and previous['sourceBefore'] == before and previous['nativeBefore'] == native_before
        assert previous.get('packageOnly', False) == args.package_only and previous.get('traced', False) == args.traced
    report['workDirectory'] = str(work)
    if args.dotnet_sdk_driver:
        sdk = args.dotnet_sdk_driver.resolve()
        assert (sdk.parent / 'Sdks').is_dir() and (sdk.parent / 'FSharp/fsc.dll').is_file(), sdk
        selection = work / 'global.json'
        contents = json.dumps({'sdk': {'version': sdk.parent.name, 'rollForward': 'disable'}}, indent=2) + '\n'
        if previous:
            assert selection.read_text(encoding='utf-8') == contents
        else:
            selection.write_text(contents, encoding='utf-8')
        report['sdkSelection'] = {'driver': str(sdk), 'driverSha256': sha(sdk),
                                  'globalJson': str(selection), 'contents': contents, 'sha256': sha(selection)}
    environment = dict(os.environ)
    environment.update(OS='Windows_NT', PROCESSOR_ARCHITECTURE='AMD64',
                       NUGET_PACKAGES=str(work / 'nuget'), NUGET_HTTP_CACHE_PATH=str(work / 'http-cache'),
                       DOTNET_CLI_HOME=str(work / 'dotnet-home'), DOTNET_CLI_TELEMETRY_OPTOUT='1')
    environment['PATH'] = str(native) + os.pathsep + environment.get('PATH', '')

    def run(name, command, timeout=120):
        with (output / (name + '.log')).open('wb') as stream:
            result = subprocess.run(command, cwd=work, env=environment, stdout=stream,
                                    stderr=subprocess.STDOUT, timeout=timeout)
        record = {'name': name, 'argv': command, 'exit': result.returncode,
                  'logSha256': sha(output / (name + '.log'))}
        report['commands'].append(record)
        if result.returncode:
            raise RuntimeError(name + ' failed; see ' + str(output / (name + '.log')))

    try:
        if args.phase != 'run':
            builder_path = root / 'examples/NativeMedia/build_windows.py'
            spec = importlib.util.spec_from_file_location('media_builder', builder_path)
            builder = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(builder)
            provider = work / 'provider'
            builder.build(provider)
            report['provider'] = json.loads((provider / 'build.json').read_text())
            compiler = report['provider']['compiler']
            # Reuse the selected SDK environment for the inspection-only test DLL.
            locator = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Microsoft Visual Studio/Installer/vswhere.exe'
            installation = subprocess.check_output([str(locator), '-latest', '-products', '*', '-requires',
                'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-property', 'installationPath'], text=True).strip()
            setup = Path(installation) / 'VC/Auxiliary/Build/vcvars64.bat'
            script = work / 'environment.cmd'
            script.write_text(f'@call "{setup}" >nul\n@set PATH\n@set INCLUDE\n@set LIB\n', encoding='utf-8', newline='\r\n')
            for line in subprocess.check_output(['cmd', '/d', '/c', str(script)], text=True).splitlines():
                if '=' in line and not line.startswith('='):
                    key, value = line.split('=', 1)
                    environment[key.upper()] = value
            support = work / 'MediaManagedTestSupport.dll'
            run('sdk-support', [compiler, '/nologo', '/std:c++20', '/EHsc', '/W4', '/WX', '/MT', '/utf-8', '/LD',
                '/DWIN32_LEAN_AND_MEAN', '/DNOMINMAX', str(root / 'tests/media/ManagedSupport.cpp'),
                '/Fo:' + str(work) + '/', '/Fe:' + str(support), '/link', '/IMPLIB:' + str(work / 'support.lib'),
                'ole32.lib', 'oleaut32.lib', 'uuid.lib', 'd3d11.lib', 'dxgi.lib', 'runtimeobject.lib',
                'windowsapp.lib', 'shell32.lib', 'user32.lib'])
            dotnet = ['dotnet'] + ([str(args.dotnet_sdk_driver.resolve())] if args.dotnet_sdk_driver else [])
            common = [str(root / 'tests/media/Managed.fsproj'), '-c', 'Release', '-r', 'win-x64', '-m:1', '/nr:false',
                '-v:normal',
                '-p:UseSharedCompilation=false', '--configfile', str(args.nuget_config.resolve()),
                '-p:UseLocalRanvier=false',
                '-p:RanvierWebCoreNativeDir=' + str(args.native_stage.resolve()), '-p:RanvierWebCoreNativeRid=win-x64',
                '-p:NativeMediaDllPath=' + str(provider / 'RanvierNativeMedia.dll'),
                '-p:NativeMediaTestDllPath=' + str(support), '-p:RanvierTrace=' + str(args.traced).lower()]
            if args.view_root:
                common += ['-p:RanvierViewRoot=' + str(args.view_root.resolve()),
                           '-p:UseLocalRanvierWebCore=true', '-p:RanvierWebCoreRoot=' + str(root)]
            else:
                common += ['-p:UseLocalRanvierWebCore=false']
        fixture = str(root / 'tests/fixtures/native-media-colors-tone.mp4')
        for mode in ['jit', 'aot']:
            artifacts = work / mode
            if args.phase != 'run':
                command = dotnet + ['publish' if mode == 'aot' else 'build'] + common + ['--artifacts-path', str(artifacts)]
                if mode == 'aot':
                    command += ['-p:PublishAot=true', '-p:TrimmerSingleWarn=false',
                                '-p:ILLinkTreatWarningsAsErrors=true', '-p:IlcTreatWarningsAsErrors=true']
                run(mode + '-build', command, timeout=540)
                if args.package_only:
                    report[mode + 'PackageGraphs'] = check_package_graphs(artifacts, args.traced, sha)
            directory = artifacts / ('publish' if mode == 'aot' else 'bin') / 'Managed/release_win-x64'
            if args.phase == 'build':
                continue
            application = directory / ('Managed.exe' if mode == 'aot' else 'Managed.dll')
            runtime = [str(application)] if mode == 'aot' else ['dotnet', str(application)]
            run(mode + '-runtime', runtime + [str(native), fixture])
            expected = 'DYNAMIC_CODE_SUPPORTED=' + ('False' if mode == 'aot' else 'True')
            assert expected in (output / (mode + '-runtime.log')).read_text(), expected
            report[mode + 'ApplicationSha256'] = sha(application)
            # A copied directory genuinely lacks the optional provider; no product switch fakes absence.
            absent = work / (mode + '-absent')
            shutil.copytree(directory, absent)
            (absent / 'RanvierNativeMedia.dll').unlink()
            absent_runtime = [str(absent / 'Managed.exe')] if mode == 'aot' else ['dotnet', str(absent / 'Managed.dll')]
            run(mode + '-absent', absent_runtime + ['--unavailable'])
            assert 'MEDIA_MANAGED_UNAVAILABLE_ASSERTIONS=12' in (output / (mode + '-absent.log')).read_text()
        report['buildReady'] = True
        report['passed'] = args.phase != 'build'
    finally:
        report['sourceAfter'] = {path.relative_to(root).as_posix(): sha(path) for path in inputs}
        report['nativeAfter'] = {path.relative_to(native).as_posix(): sha(path) for path in native.rglob('*') if path.is_file()}
        report['unchanged'] = before == report['sourceAfter'] and native_before == report['nativeAfter']
        temporary = output / 'managed-receipt.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        temporary.replace(output / 'managed-receipt.json')
        assert work.parent == output
        if not args.keep_artifacts and (args.phase != 'build' or not report.get('buildReady')):
            shutil.rmtree(work)
        assert report['unchanged'], 'Input mutation during qualification'


if __name__ == '__main__':
    main()
