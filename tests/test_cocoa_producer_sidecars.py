import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class ProducerSidecarAdmission(unittest.TestCase):
    def test_external_controller_uses_clean_producer_sources_and_retains_appkit_failure_inputs(self):
        spec = importlib.util.spec_from_file_location('producer_sidecars', ROOT / 'tests/controls/build_cocoa_sidecars.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            producer, controller, stage, build, webkit, packages = [root / name for name in ['F', 'H', 'stage', 'build', 'webkit', 'packages']]
            for path in [producer, controller, stage, build, webkit, packages]:
                path.mkdir()
            for filename in ['tests/abi/cocoa_timer_contract.cpp', 'tests/controls/cocoa_page_sidecar.cpp',
                             'tests/controls/cocoa_progress_motion.mm', 'tests/controls/cocoa_contrast_scoped_override.mm']:
                path = producer / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('producer-F test source')
            builder = controller / 'tests/abi/build_cocoa_timer_contract.py'
            builder.parent.mkdir(parents=True)
            builder.write_text('controller-H builder')
            header = producer / 'host/RanvierWebCoreAbi.h'
            header.parent.mkdir()
            header.write_text('\n'.join('RV_EXPORT void rv_fixture_' + str(i) + '(void);' for i in range(349)))
            native = stage / 'runtimes/osx-arm64/native'
            native.mkdir(parents=True)
            files = []
            for name in ['libRanvierWebCoreHost.dylib', 'libWebCore.dylib', 'libJavaScriptCore.dylib', 'libWebGPU.dylib']:
                path = native / name
                path.write_bytes(b'not executable')
                files.append(dict(name=name, sha256=module.sha(path)))
            manifest = dict(rid='osx-arm64', flavor='slim', abi=64, source=dict(commit='a' * 40, dirty=False), files=files)
            (stage / 'manifest.json').write_text(json.dumps(manifest))
            with zipfile.ZipFile(packages / 'fixture.nupkg', 'w') as archive:
                archive.writestr('manifest.json', json.dumps(manifest))
                for row in files:
                    archive.write(native / row['name'], 'runtimes/osx-arm64/native/' + row['name'])
            compiler, sdk = root / 'clang', root / 'sdk'
            compiler.write_bytes(b'not executable')
            sdk.mkdir()
            output = root / 'output'
            commands = []

            def check_output(command, **kwargs):
                if command[0] == 'git':
                    return '' if command[1] == 'status' else ('a' if kwargs['cwd'] == producer else 'b') * 40
                return str(sdk if '--show-sdk-path' in command else compiler)

            class Child:
                pid = 123456
                def __init__(self, command, **kwargs):
                    commands.append(command)
                    if kwargs['start_new_session']:
                        raise AssertionError('An outer-owned group must be inherited')
                    self.code = 1 if '-dynamiclib' in command else 0
                    if '--probe-source' in command:
                        probe = Path(command[command.index('--probe-source') + 1])
                        if not probe.is_relative_to(producer):
                            raise AssertionError('Source must come from F')
                        if Path(command[3]) != builder:
                            raise AssertionError('Builder must come from H')
                        target = Path(command[command.index('--output') + 1])
                        target.mkdir()
                        helper = target / 'helper.dylib'
                        helper.write_bytes(b'helper fixture')
                        (target / 'build-receipt.json').write_text(json.dumps(dict(status='compiled', inputsUnchanged=True, runtimeUnchanged=True, helperPath=str(helper))))
                    elif '-M' in command:
                        probe = next(Path(arg) for arg in command if str(arg).endswith('.mm'))
                        Path(command[command.index('-MF') + 1]).write_text('helper: ' + probe.as_posix().replace(' ', '\\ '))
                def wait(self, **kwargs):
                    return self.code
                def poll(self):
                    return self.code

            argv = ['builder', '--producer-root', str(producer), '--stage', str(stage), '--build', str(build),
                    '--webkit-source', str(webkit), '--packages', str(packages), '--output', str(output)]
            with patch.object(module, 'ROOT', controller), patch.object(module.sys, 'argv', argv), \
                    patch.object(module.sys, 'platform', 'darwin'), patch.object(module.platform, 'machine', return_value='arm64'), \
                    patch.object(module.platform, 'mac_ver', return_value=('26.0', (), '')), \
                    patch.object(module.subprocess, 'check_output', side_effect=check_output), \
                    patch.object(module.subprocess, 'Popen', Child), patch.object(os, 'killpg', create=True), \
                    patch.object(module.signal, 'SIGKILL', 9, create=True), \
                    patch.dict(os.environ, {'RANVIER_COCOA_OWNED_GROUP': '1'}):
                with self.assertRaisesRegex(RuntimeError, 'motion-compile'):
                    module.main()
            receipt = json.loads((output / 'producer-sidecars.json').read_text())
            self.assertEqual(receipt['nativeSource'], 'a' * 40)
            self.assertEqual(receipt['controllerSource'], 'b' * 40)
            self.assertTrue(receipt['sourcesUnchanged'] and receipt['nativeUnchanged'])
            self.assertEqual(receipt['status'], 'failed')
            self.assertTrue(all(row['childReaped'] and not row['ownsProcessGroup'] for row in receipt['commands']))
            self.assertTrue(all('processGroupReaped' not in row for row in receipt['commands']))
            capsule = output / receipt['appkitConsumedInputs']['motion']['path']
            self.assertEqual(module.sha(capsule), receipt['appkitConsumedInputs']['motion']['sha256'])
            with zipfile.ZipFile(capsule) as archive:
                probe = producer / 'tests/controls/cocoa_progress_motion.mm'
                self.assertEqual(archive.read('inputs/' + probe.as_posix().lstrip('/')), probe.read_bytes())

    def test_clean_controller_and_producer_identities_are_independent(self):
        spec = importlib.util.spec_from_file_location('producer_sidecars', ROOT / 'tests/controls/build_cocoa_sidecars.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        producer, controller = Path('producer-F'), Path('controller-H')
        with patch.object(module.subprocess, 'check_output', side_effect=['a' * 40, '', 'b' * 40, '']) as call:
            self.assertEqual(module.clean_source(producer), 'a' * 40)
            self.assertEqual(module.clean_source(controller), 'b' * 40)
            self.assertEqual([row.kwargs['cwd'] for row in call.call_args_list], [producer, producer, controller, controller])
        for head, dirty in [('a' * 40, ' M tracked.py'), ('invalid', '')]:
            with patch.object(module.subprocess, 'check_output', side_effect=[head, dirty]):
                with self.assertRaisesRegex(ValueError, 'clean tracked'):
                    module.clean_source(controller)

    def test_package_and_manifest_are_uploaded_before_sidecars(self):
        text = (ROOT / '.github/workflows/build.yml').read_text(encoding='utf-8')
        start = text.index('      - name: Package\n')
        sidecars = text.index('      - name: Build matching macOS CPU test sidecars', start)
        for name in ['package', 'manifest']:
            self.assertLess(text.index('name: ' + name + '-${{ matrix.rid }}-${{ env.FLAVOR }}', start), sidecars)

    def test_package_with_matching_manifest_and_changed_payload_is_rejected(self):
        spec = importlib.util.spec_from_file_location('producer_sidecars', ROOT / 'tests/controls/build_cocoa_sidecars.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / 'native'
            original.write_bytes(b'original')
            manifest = dict(files=[dict(name='library', sha256=module.sha(original))])
            package = root / 'fixture.nupkg'
            with zipfile.ZipFile(package, 'w') as archive:
                archive.writestr('manifest.json', json.dumps(manifest))
                archive.writestr('runtimes/osx-arm64/native/library', b'changed')
            self.assertFalse(module.package_matches(package, manifest))
            with zipfile.ZipFile(package, 'w') as archive:
                archive.writestr('manifest.json', json.dumps(manifest))
                archive.writestr('runtimes/osx-arm64/native/library', b'original')
            self.assertTrue(module.package_matches(package, manifest))
            with warnings.catch_warnings(), zipfile.ZipFile(package, 'a') as archive:
                warnings.simplefilter('ignore', UserWarning)
                archive.writestr('runtimes/osx-arm64/native/library', b'original')
            self.assertFalse(module.package_matches(package, manifest))

    def test_complete_staged_payload_is_required_before_helper_compilation(self):
        path = ROOT / 'tests/controls/build_cocoa_sidecars.py'
        self.assertTrue(path.is_file(), 'The producer must capture its matching helper closure')
        spec = importlib.util.spec_from_file_location('producer_sidecars', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            native = stage / 'runtimes/osx-arm64/native'
            native.mkdir(parents=True)
            files = []
            for name in ['libRanvierWebCoreHost.dylib', 'libWebCore.dylib', 'libJavaScriptCore.dylib', 'libWebGPU.dylib']:
                path = native / name
                path.write_bytes(b'metadata fixture, never loaded')
                files.append(dict(name=name, sha256=module.sha(path)))
            manifest = dict(rid='osx-arm64', flavor='slim', abi=64,
                            source=dict(commit='a' * 40, dirty=False), files=files)
            (stage / 'manifest.json').write_text(json.dumps(manifest))
            _, selected, hashes = module.admit_stage(stage)
            self.assertEqual(selected, native.resolve())
            self.assertEqual(len(hashes), 4)
            (native / 'unrecorded.resource').write_bytes(b'extra')
            with self.assertRaisesRegex(ValueError, 'payload'):
                module.admit_stage(stage)
            (native / 'unrecorded.resource').unlink()
            (native / files[0]['name']).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'payload'):
                module.admit_stage(stage)


if __name__ == '__main__':
    unittest.main()
