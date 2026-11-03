"""Qualify the optional ARM64 provider in an ordinary strict NativeAOT View consumer."""
import argparse
import hashlib
import json
import os
import platform
import re
import select
import shutil
import signal
import subprocess
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

PROFILES = ('present', 'absent', 'no-bus')
RID = 'linux-arm64'
PROVIDER_ID = 'Ranvier.Private.Accessibility.Atspi.ArmQualification'


def validate_result(value, expected_attached):
    expected = dict(windows=3, directHosts=3, expectedAttached=expected_attached, dynamicCodeSupported=False)
    if value != expected:
        raise ValueError(f'Unexpected NativeAOT lifecycle result: {value!r}')


def validate_publish_log(text):
    if re.search(r'warning\s+IL\d+', text, re.I) or 'will always throw because:' in text:
        raise ValueError('NativeAOT publish contains a trimming/AOT or always-throw diagnostic')


def validate_elf(text):
    if 'ELF64' not in text or 'AArch64' not in text or 'libcoreclr' in text.lower():
        raise ValueError('Consumer is not an ARM64 ELF without a dynamic CoreCLR dependency')


def validate_source_claim(manifest, source_revision):
    if not re.fullmatch(r'[0-9a-f]{40}', source_revision) or manifest.get('callerClaimedProviderSourceRevision') != source_revision:
        raise ValueError('Provider source claim does not match the selected producer revision')


def validate_assets(libraries, mode, interop_version, provider_version):
    if mode not in ('normal', 'traced'):
        raise ValueError('Unknown managed trace mode')
    dom = 'Ranvier.Dom' + ('.Traced' if mode == 'traced' else '') + '/0.1.0-alpha.56'
    expected = (dom, 'Ranvier.WebCore/' + interop_version, PROVIDER_ID + '/' + provider_version)
    if not all(name in libraries for name in expected):
        raise ValueError('Published consumer resolved the wrong Core, interop or provider package')
    ids = ('ranvier.dom', 'ranvier.dom.traced', 'ranvier.webcore', PROVIDER_ID.lower())
    selected = [name for name in libraries if name.split('/', 1)[0].lower() in ids]
    if sorted(selected) != sorted(expected):
        raise ValueError('Published consumer contains conflicting Core, interop or provider packages')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run_checked(command, log, cwd=None, env=None, timeout=600):
    with log.open('wb') as output:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise
    text = log.read_text(errors='replace')
    if code:
        raise RuntimeError(f'{command[0]} exited {code}; see {log}\n{text[-5000:]}')
    return text


def config_file(path, feed):
    root = ET.Element('configuration')
    sources = ET.SubElement(root, 'packageSources')
    ET.SubElement(sources, 'clear')
    ET.SubElement(sources, 'add', key='private', value=str(feed))
    ET.SubElement(sources, 'add', key='nuget', value='https://api.nuget.org/v3/index.json')
    mappings = ET.SubElement(root, 'packageSourceMapping')
    private = ET.SubElement(mappings, 'packageSource', key='private')
    for pattern in ('Ranvier.WebCore', PROVIDER_ID):
        ET.SubElement(private, 'package', pattern=pattern)
    public = ET.SubElement(mappings, 'packageSource', key='nuget')
    ET.SubElement(public, 'package', pattern='*')
    path.write_bytes(ET.tostring(root))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--view', type=Path, required=True)
    parser.add_argument('--native-source', type=Path, required=True)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--source-revision', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--display', help='Existing X display for a local harness control; CI omits this option')
    args = parser.parse_args()
    if platform.machine().lower() not in ('aarch64', 'arm64'):
        raise RuntimeError('This qualification must execute on an ARM64 runner')
    args.output.mkdir(parents=True, exist_ok=False)
    work = args.output.resolve()
    native = args.native.resolve()
    package = args.package.resolve()
    with zipfile.ZipFile(package) as archive:
        manifest = json.loads(archive.read('provider-manifest.json'))
        validate_source_claim(manifest, args.source_revision)
        if manifest['rid'] != RID or manifest['id'] != PROVIDER_ID or manifest['hostSha256'] != sha(native):
            raise ValueError('The private provider package does not match this ARM64 host')
        for name, expected in manifest['payloads'].items():
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise ValueError('Provider package payload hash mismatch: ' + name)
    feed = work / 'feed'
    feed.mkdir()
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', manifest['id']) or not re.fullmatch(r'[A-Za-z0-9_.-]+', manifest['version']):
        raise ValueError('Invalid provider package identity')
    shutil.copy2(package, feed / (manifest['id'] + '.' + manifest['version'] + '.nupkg'))
    interop_version = '0.0.0-arm64.' + os.environ.get('GITHUB_RUN_ID', '1')
    run_checked(['dotnet', 'pack', str(args.native_source / 'src/Ranvier.WebCore/Ranvier.WebCore.fsproj'),
                 '-c', 'Release', '-m:1', '/nr:false', '-p:Version=' + interop_version,
                 '-p:NuGetAudit=false', '-o', str(feed)], work / 'interop-pack.log', timeout=300)
    interop = feed / ('Ranvier.WebCore.' + interop_version + '.nupkg')
    if not interop.is_file():
        raise RuntimeError('The exact-source managed interop package was not produced')
    config = work / 'NuGet.Config'
    config_file(config, feed)
    stage = work / 'native-stage/runtimes' / RID / 'native'
    stage.mkdir(parents=True)
    shutil.copy2(native, stage / native.name)
    if sha(stage / native.name) != manifest['hostSha256']:
        raise ValueError('Staged native host hash changed')
    cache = work / 'cache'
    projects = {}
    asset_graphs = {}
    for mode in ('normal', 'traced'):
        output = work / ('publish-' + mode)
        command = ['dotnet', 'publish', str(args.view / 'tests/AccessibilityAot/AccessibilityAot.fsproj'),
                   '-c', 'Release', '-r', RID, '-m:1', '/nr:false', '-v:minimal',
                   '-p:RanvierTrace=' + str(mode == 'traced').lower(), '-p:AccessibilityStyleTrial=true',
                   '-p:AccessibilityAtspiPackageId=' + PROVIDER_ID,
                   '-p:AccessibilityAtspiPackageVersion=' + manifest['version'],
                   '-p:RanvierWebCoreNativeVersion=' + interop_version,
                   '-p:RanvierWebCoreNativeDir=' + str(work / 'native-stage'),
                   '-p:RanvierWebCoreNativeRid=' + RID, '-p:RestoreConfigFile=' + str(config),
                   '-p:RestorePackagesPath=' + str(cache), '-p:NuGetAudit=false',
                   '-p:UseSharedCompilation=false', '-p:IlcTreatWarningsAsErrors=true',
                   '-p:ILLinkTreatWarningsAsErrors=true', '-p:TrimmerSingleWarn=false',
                   '-p:PublishAot=true', '--artifacts-path', str(work / ('artifacts-' + mode)), '-o', str(output)]
        log = run_checked(command, work / ('publish-' + mode + '.log'), cwd=args.view)
        validate_publish_log(log)
        assets = work / ('artifacts-' + mode) / 'obj/AccessibilityAot/project.assets.json'
        graph = json.loads(assets.read_text())['libraries']
        validate_assets(graph, mode, interop_version, manifest['version'])
        asset_graphs[mode] = {'path': str(assets), 'sha256': sha(assets)}
        binary = output / 'AccessibilityAot'
        validate_elf(subprocess.check_output(['readelf', '-h', '-d', str(binary)], text=True))
        for name, expected in [('libRanvierWebCoreHost.so', manifest['hostSha256']),
                               ('libRanvierWebCoreAtspi.so', manifest['providerSha256'])]:
            if sha(output / name) != expected:
                raise ValueError('Published native asset mismatch: ' + name)
        projects[mode] = output

    children = []
    streams = []
    receipt = {'architecture': platform.machine(), 'rid': RID, 'sourceRevision': args.source_revision,
               'sourceProvenance': manifest['sourceProvenance'], 'hostSha256': sha(native),
               'providerSha256': manifest['providerSha256'], 'packageSha256': sha(package),
               'interopSha256': sha(interop), 'interopVersion': interop_version,
               'assetGraphs': asset_graphs, 'runs': []}
    environment = dict(os.environ, SDL_VIDEODRIVER='x11', EGL_PLATFORM='surfaceless', LIBGL_ALWAYS_SOFTWARE='1')
    environment.pop('LD_LIBRARY_PATH', None)

    def spawn(command, log, env=None, pass_fds=(), cwd=None):
        output = log.open('wb')
        streams.append(output)
        child = subprocess.Popen(command, env=env or environment, cwd=cwd, stdout=output, stderr=subprocess.STDOUT,
                                 pass_fds=pass_fds, start_new_session=True)
        children.append(child)
        receipt.setdefault('processes', []).append({'pid': child.pid, 'stat': Path(f'/proc/{child.pid}/stat').read_text(),
                                                   'command': command})
        return child

    try:
        if args.display:
            if not re.fullmatch(r':[0-9]+', args.display):
                raise ValueError('An existing local display must have the form :N')
            display = args.display[1:]
            socket = Path('/tmp/.X11-unix/X' + display)
            before = socket.stat()
            receipt['existingDisplaySocketBefore'] = [before.st_ino, before.st_mode, before.st_mtime_ns]
        else:
            display_read, display_write = os.pipe()
            spawn(['Xvfb', '-displayfd', str(display_write), '-screen', '0', '1024x768x24', '-nolisten', 'tcp'],
                  work / 'xvfb.log', pass_fds=(display_write,))
            os.close(display_write)
            if not select.select([display_read], [], [], 10)[0]:
                raise RuntimeError('Private Xvfb did not allocate a display')
            display = os.read(display_read, 64).decode().strip()
            os.close(display_read)
            if not display.isdigit():
                raise RuntimeError('Invalid private Xvfb display')
        environment['DISPLAY'] = ':' + display
        bus = subprocess.Popen(['dbus-daemon', '--session', '--nofork', '--print-address=1'],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
        children.append(bus)
        receipt.setdefault('processes', []).append({'pid': bus.pid, 'stat': Path(f'/proc/{bus.pid}/stat').read_text(),
                                                   'command': ['dbus-daemon', '--session', '--nofork']})
        if not select.select([bus.stdout], [], [], 10)[0]:
            raise RuntimeError('Private session bus did not start')
        address = bus.stdout.readline().decode().strip()
        environment.update(DBUS_SESSION_BUS_ADDRESS=address, AT_SPI_BUS_ADDRESS=address)
        registry = spawn(['/usr/libexec/at-spi2-registryd'], work / 'registry.log')
        deadline = time.monotonic() + 10
        while True:
            probe = subprocess.run(['gdbus', 'call', '--address', address, '--dest', 'org.freedesktop.DBus',
                                    '--object-path', '/org/freedesktop/DBus', '--method',
                                    'org.freedesktop.DBus.NameHasOwner', 'org.a11y.atspi.Registry'],
                                   capture_output=True, text=True, timeout=3)
            if probe.returncode == 0 and 'true' in probe.stdout.lower():
                break
            if registry.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError('Private accessibility registry did not own its bus name')
            time.sleep(0.05)
        for mode, published in projects.items():
            for profile in PROFILES:
                directory = published
                if profile == 'absent':
                    directory = work / ('publish-' + mode + '-absent')
                    shutil.copytree(published, directory, ignore=shutil.ignore_patterns('libRanvierWebCoreAtspi.so'))
                    if (directory / 'libRanvierWebCoreAtspi.so').exists():
                        raise RuntimeError('Provider-absent control still has a module')
                app_env = environment.copy()
                if profile == 'no-bus':
                    missing = 'unix:path=' + str(work / 'no-such-accessibility-bus')
                    app_env.update(AT_SPI_BUS_ADDRESS=missing, DBUS_SESSION_BUS_ADDRESS=missing)
                expected_attached = profile == 'present'
                command = [str(directory / 'AccessibilityAot')] + (['--expect-attached'] if expected_attached else [])
                log = work / (mode + '-' + profile + '.log')
                native_names = ['libRanvierWebCoreHost.so', 'libSDL3.so']
                if profile != 'absent':
                    native_names.append('libRanvierWebCoreAtspi.so')
                before = {name: sha(directory / name) for name in native_names}
                app = spawn(command, log, env=app_env, cwd=directory)
                try:
                    code = app.wait(timeout=60)
                except subprocess.TimeoutExpired:
                    os.killpg(app.pid, signal.SIGKILL)
                    app.wait()
                    raise
                if code:
                    raise RuntimeError(f'NativeAOT consumer exited {code}; see {log}')
                text = log.read_text(errors='replace')
                value = next(json.loads(line) for line in text.splitlines() if line.startswith('{'))
                validate_result(value, expected_attached)
                maps = {line.split()[-1] for line in text.splitlines() if line.startswith('native-map ')}
                expected_maps = {str(directory / 'libRanvierWebCoreHost.so')}
                if profile != 'absent':
                    expected_maps.add(str(directory / 'libRanvierWebCoreAtspi.so'))
                if maps != expected_maps:
                    raise ValueError(f'Unexpected loaded native assets: {maps!r}')
                after = {name: sha(directory / name) for name in native_names}
                if before != after:
                    raise ValueError('A native asset changed during the managed consumer run')
                receipt['runs'].append({'mode': mode, 'profile': profile, 'result': value,
                                        'binarySha256': sha(directory / 'AccessibilityAot'),
                                        'hostSha256': sha(directory / 'libRanvierWebCoreHost.so'),
                                        'nativeBefore': before, 'nativeAfter': after,
                                        'nonBmpStyle': expected_attached,
                                        'maps': sorted(maps), 'logSha256': sha(log)})
        if len(receipt['runs']) != 6:
            raise RuntimeError('All normal/traced provider profiles are required')
    finally:
        for child in reversed(children):
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=5)
        for stream in streams:
            stream.close()
        if 'bus' in locals():
            bus.stdout.close()
        receipt['allOwnedProcessesExited'] = all(child.poll() is not None for child in children)
        if args.display:
            after = socket.stat()
            receipt['existingDisplaySocketAfter'] = [after.st_ino, after.st_mode, after.st_mtime_ns]
            if receipt['existingDisplaySocketBefore'] != receipt['existingDisplaySocketAfter']:
                raise RuntimeError('The existing display socket changed during the control')
        (work / 'managed-aot-receipt.json').write_text(json.dumps(receipt, indent=2))
    if not receipt['allOwnedProcessesExited']:
        raise RuntimeError('Owned ARM64 test processes remain alive')
    print('PASS ARM64 managed strict AOT provider profiles')


if __name__ == '__main__':
    main()
