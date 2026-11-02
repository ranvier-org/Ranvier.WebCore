import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import os
import time
import unittest
from unittest import mock
import zipfile


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'recover_preview2_gpu.py'


class RecoveryPackageControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.package = self.root / 'runtime.nupkg'
        self.manifest = self.root / 'manifest.json'
        self.contract_file = self.root / 'contract.json'
        self.receipt = self.root / 'receipt.json'
        self.payload = b'owned test bytes'
        self.model = {
            'source': {'commit': 'a' * 40, 'dirty': False, 'builder': 'ci'},
            'version': '1.2.3-test', 'abi': 60, 'webkit': 'b' * 40,
            'rid': 'win-x64', 'flavor': 'gpu', 'total_bytes': len(self.payload),
            'files': [{'name': 'host.dll', 'bytes': len(self.payload),
                       'sha256': hashlib.sha256(self.payload).hexdigest()}],
        }
        self.contract = {
            'productSource': 'a' * 40, 'testSource': 'c' * 40,
            'version': '1.2.3-test', 'abi': 60, 'webkit': 'b' * 40,
            'rid': 'win-x64', 'flavor': 'gpu',
            'payloadFiles': self.model['files'],
        }
        self.write_package()

    def write_package(self, extra=None, payload=None):
        manifest = json.dumps(self.model).encode()
        self.manifest.write_bytes(manifest)
        with zipfile.ZipFile(self.package, 'w') as archive:
            archive.writestr('manifest.json', manifest)
            archive.writestr('runtimes/win-x64/native/host.dll', self.payload if payload is None else payload)
            archive.writestr('fixture.nuspec', '<package><metadata><id>Fixture.Gpu.win-x64</id><version>1.2.3-test</version><repository commit="' + self.model['source']['commit'] + '" /></metadata></package>')
            if extra:
                archive.writestr(*extra)
        self.contract.update(packageSha256=hashlib.sha256(self.package.read_bytes()).hexdigest(),
                             packageBytes=self.package.stat().st_size,
                             manifestSha256=hashlib.sha256(manifest).hexdigest(),
                             packageId='Fixture.Gpu.win-x64')
        self.contract_file.write_text(json.dumps(self.contract))

    def run_verify(self):
        return subprocess.run([sys.executable, '-B', str(SCRIPT), 'verify', '--package', str(self.package),
                               '--manifest', str(self.manifest), '--contract', str(self.contract_file),
                               '--receipt', str(self.receipt)], capture_output=True, text=True, timeout=15)

    def test_exact_artifact_records_product_and_test_sources_separately(self):
        result = self.run_verify()
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(self.receipt.read_text())
        self.assertEqual(receipt['productSource'], 'a' * 40)
        self.assertEqual(receipt['testSource'], 'c' * 40)
        self.assertEqual(receipt['payloads'], {'host.dll': hashlib.sha256(self.payload).hexdigest()})
        self.assertFalse(receipt['publicationReady'])

    def test_changed_archive_fails_before_receipt(self):
        with self.package.open('ab') as output:
            output.write(b'modified')
        self.assertNotEqual(self.run_verify().returncode, 0)
        self.assertFalse(self.receipt.exists())

    def test_manifest_cannot_relabel_product_source(self):
        self.model['source']['commit'] = 'd' * 40
        self.write_package()
        self.assertNotEqual(self.run_verify().returncode, 0)

    def test_manifest_must_be_clean_ci_product(self):
        for field, value in [('dirty', True), ('builder', 'local')]:
            with self.subTest(field=field):
                self.model['source'] = {'commit': 'a' * 40, 'dirty': False, 'builder': 'ci'}
                self.model['source'][field] = value
                self.write_package()
                self.assertNotEqual(self.run_verify().returncode, 0)

    def test_modified_payload_cannot_hide_behind_a_valid_archive_hash(self):
        self.write_package(payload=b'changed bytes')
        self.assertNotEqual(self.run_verify().returncode, 0)

    def test_extra_native_payload_is_rejected(self):
        self.write_package(extra=('runtimes/win-x64/native/unlisted.dll', b'bad'))
        self.assertNotEqual(self.run_verify().returncode, 0)

    def test_absolute_or_drive_relative_manifest_paths_are_rejected(self):
        for name in ['/escaped.dll', 'C:escaped.dll']:
            with self.subTest(name=name):
                self.model['files'][0]['name'] = name
                self.contract['payloadFiles'] = self.model['files']
                manifest = json.dumps(self.model).encode()
                self.manifest.write_bytes(manifest)
                with zipfile.ZipFile(self.package, 'w') as archive:
                    archive.writestr('manifest.json', manifest)
                    archive.writestr('runtimes/win-x64/native/' + name, self.payload)
                    archive.writestr('fixture.nuspec', '<package><metadata><id>Fixture.Gpu.win-x64</id><version>1.2.3-test</version><repository commit="' + 'a' * 40 + '" /></metadata></package>')
                self.contract.update(packageSha256=hashlib.sha256(self.package.read_bytes()).hexdigest(),
                                     packageBytes=self.package.stat().st_size,
                                     manifestSha256=hashlib.sha256(manifest).hexdigest())
                self.contract_file.write_text(json.dumps(self.contract))
                result = self.run_verify()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Unsafe', result.stderr)

    def test_duplicate_archive_member_is_rejected(self):
        self.write_package(extra=('runtimes/win-x64/native/host.dll', self.payload))
        self.assertNotEqual(self.run_verify().returncode, 0)

    def test_unbound_test_source_cannot_qualify(self):
        self.contract['testSource'] = None
        self.contract_file.write_text(json.dumps(self.contract))
        self.assertNotEqual(self.run_verify().returncode, 0)

    def public_fixture(self):
        cache = self.root / 'public'
        cache.mkdir()
        self.contract['publicPackages'] = []
        for index in range(7):
            name = 'Fixture' + str(index)
            data = ('public artifact ' + str(index)).encode()
            (cache / (name + '.nupkg')).write_bytes(data)
            self.contract['publicPackages'].append({'id': name, 'bytes': len(data),
                                                    'sha256': hashlib.sha256(data).hexdigest()})
        self.contract_file.write_text(json.dumps(self.contract))
        return cache

    def run_public(self, cache):
        return subprocess.run([sys.executable, '-B', str(SCRIPT), 'public', '--cache', str(cache),
                               '--offline', '--contract', str(self.contract_file), '--receipt', str(self.receipt)],
                              capture_output=True, text=True, timeout=15)

    def test_all_seven_public_packages_are_rehashed(self):
        result = self.run_public(self.public_fixture())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(self.receipt.read_text())['publicPackages']), 7)

    def test_changed_public_package_is_rejected(self):
        cache = self.public_fixture()
        (cache / 'Fixture3.nupkg').write_bytes(b'wrong signed package')
        result = self.run_public(cache)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Public package', result.stderr)

    def test_missing_public_package_is_rejected(self):
        cache = self.public_fixture()
        (cache / 'Fixture6.nupkg').unlink()
        result = self.run_public(cache)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Public package', result.stderr)

    def run_catalogue(self, content):
        self.contract.update(catalogueGroups=2, catalogueNames=['First', 'Last'])
        self.contract_file.write_text(json.dumps(self.contract))
        summary = self.root / 'summary.txt'
        summary.write_text(content)
        return subprocess.run([sys.executable, '-B', str(SCRIPT), 'catalogue', '--summary', str(summary),
                               '--contract', str(self.contract_file), '--receipt', str(self.receipt)],
                              capture_output=True, text=True, timeout=15)

    def test_full_catalogue_requires_each_named_group_in_order(self):
        result = self.run_catalogue('PASS 1.0 s First\nPASS 2.0 s Last\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.receipt.read_text())['catalogueGroupsPassed'], 2)

    def test_failed_missing_duplicate_or_reordered_group_cannot_pass(self):
        for summary in ['PASS 1.0 s First\n', 'PASS 1.0 s First\nPASS 2.0 s First\n',
                        'FAIL 1.0 s First\nPASS 2.0 s Last\n', 'PASS 1.0 s Last\nPASS 2.0 s First\n']:
            with self.subTest(summary=summary):
                result = self.run_catalogue(summary)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Catalogue', result.stderr)

    def source_fixture(self):
        tree = self.root / 'test-source'
        tree.mkdir()
        def git(*args):
            return subprocess.check_output(['git', '-C', str(tree), *args], stderr=subprocess.PIPE).decode().strip()
        git('init', '-q')
        (tree / 'host').mkdir()
        (tree / 'host/runtime.cpp').write_text('original product')
        (tree / 'tests/gpu').mkdir(parents=True)
        (tree / 'tests/gpu/NativeFrameAcceptance.cpp').write_text('old fixture')
        (tree / 'tests/gpu/run.py').write_text('old compiler links')
        git('add', '.')
        git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.test', 'commit', '-qm', 'product')
        self.contract['productSource'] = git('rev-parse', 'HEAD')
        (tree / 'tests/gpu/NativeFrameAcceptance.cpp').write_text('real removed consumer')
        (tree / 'tests/gpu/run.py').write_text('link d3d12')
        git('add', '.')
        git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.test', 'commit', '-qm', 'test only')
        self.contract['testSource'] = git('rev-parse', 'HEAD')
        self.contract_file.write_text(json.dumps(self.contract))
        return tree

    def run_source(self, tree):
        return subprocess.run([sys.executable, '-B', str(SCRIPT), 'source', '--test-root', str(tree),
                               '--contract', str(self.contract_file), '--receipt', str(self.receipt)],
                              capture_output=True, text=True, timeout=15)

    def test_test_checkout_preserves_product_and_records_two_fixture_changes(self):
        result = self.run_source(self.source_fixture())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.receipt.read_text())['changedFiles'],
                         ['tests/gpu/NativeFrameAcceptance.cpp', 'tests/gpu/run.py'])

    def test_dirty_or_wrong_test_checkout_is_rejected(self):
        tree = self.source_fixture()
        (tree / 'host/runtime.cpp').write_text('changed product')
        result = self.run_source(tree)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Test checkout', result.stderr)

    def test_bounded_command_preserves_raw_output_and_exit_code(self):
        log = self.root / 'command.log'
        result = subprocess.run([sys.executable, '-B', str(SCRIPT), 'command', '--log', str(log),
                                 '--timeout', '5', '--receipt', str(self.receipt), '--', sys.executable,
                                 '-c', 'import sys;sys.stdout.buffer.write(bytes([0,255,13,10]));sys.exit(23)'],
                                capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertEqual(log.read_bytes(), bytes([0, 255, 13, 10]))
        receipt = json.loads(self.receipt.read_text())
        self.assertEqual(receipt['exit'], 23)
        self.assertTrue(receipt['processEnded'])

    @unittest.skipUnless(os.name == 'nt', 'Windows process tree control')
    def test_timeout_ends_the_owned_parent_and_child(self):
        import ctypes
        pid_file = self.root / 'child.pid'
        script = self.root / 'parent.py'
        script.write_text('import pathlib,subprocess,sys,time\np=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"])\npathlib.Path(sys.argv[1]).write_text(str(p.pid))\ntime.sleep(60)\n')
        started = time.monotonic()
        result = subprocess.run([sys.executable, '-B', str(SCRIPT), 'command', '--log', str(self.root / 'timeout.log'),
                                 '--timeout', '0.7', '--receipt', str(self.receipt), '--', sys.executable,
                                 str(script), str(pid_file)], capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 124, result.stderr)
        self.assertLess(time.monotonic() - started, 12)
        self.assertTrue(json.loads(self.receipt.read_text())['processEnded'])
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x00100000, False, int(pid_file.read_text()))
        if handle:
            try:
                self.assertEqual(kernel.WaitForSingleObject(handle, 1000), 0)
            finally:
                kernel.CloseHandle(handle)

    def qualification_fixture(self, failing_probe=False):
        tree = self.source_fixture()
        subprocess.run(['git', '-C', str(tree), 'checkout', '--detach', self.contract['productSource']], check=True, capture_output=True)
        (tree / 'scripts').mkdir()
        for name in ['smoke.py', 'check_package_api.py']:
            (tree / 'scripts' / name).write_text('print("controlled external runtime fixture")\n')
        (tree / 'scripts/probes.py').write_text('import pathlib,sys\np=pathlib.Path(sys.argv[sys.argv.index("--logs")+1]);p.mkdir(parents=True);(p/"summary.txt").write_text("PASS 1.0 s First\\nPASS 2.0 s Last\\n");(p/"01-first.log").write_text("actual first fixture");(p/"02-last.log").write_text("actual last fixture")\nsys.exit(' + ('7' if failing_probe else '0') + ')\n')
        def commit(message):
            subprocess.run(['git', '-C', str(tree), 'add', '.'], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(tree), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.test',
                            'commit', '-qm', message], check=True, capture_output=True)
            return subprocess.check_output(['git', '-C', str(tree), 'rev-parse', 'HEAD']).decode().strip()
        self.contract['productSource'] = commit('controlled product fixture')
        (tree / 'tests/gpu/NativeFrameAcceptance.cpp').write_text('reviewed fixture')
        (tree / 'tests/gpu/run.py').write_text('reviewed compiler links')
        self.contract['testSource'] = commit('reviewed test-only fixture')
        self.model['source']['commit'] = self.contract['productSource']
        self.write_package()
        public = self.public_fixture()
        payloads = {}
        for item in self.contract['publicPackages']:
            lower = item['id'].lower()
            payloads[f'https://api.nuget.org/v3-flatcontainer/{lower}/1.2.3-test/{lower}.1.2.3-test.nupkg'] = (public / (item['id'] + '.nupkg')).read_bytes()
        self.contract['fonts'] = []
        for index in range(5):
            path = f'Tools/Fonts/font{index}.ttf'
            data = ('font ' + str(index)).encode()
            payloads['https://raw.githubusercontent.com/WebKit/WebKit/' + 'b' * 40 + '/' + path] = data
            self.contract['fonts'].append({'path': path, 'sha256': hashlib.sha256(data).hexdigest()})
        self.contract.update(package='runtime.nupkg', catalogueNames=['First', 'Last'], catalogueGroups=2)
        orchestrator = self.root / 'orchestrator'
        (orchestrator / 'scripts').mkdir(parents=True)
        copied = orchestrator / 'scripts/recover_preview2_gpu.py'
        copied.write_bytes(SCRIPT.read_bytes())
        subprocess.run(['git', '-C', str(orchestrator), 'init', '-q'], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(orchestrator), 'add', '.'], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(orchestrator), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.test',
                        'commit', '-qm', 'orchestrator'], check=True, capture_output=True)
        orchestrator_sha = subprocess.check_output(['git', '-C', str(orchestrator), 'rev-parse', 'HEAD']).decode().strip()
        spec = importlib.util.spec_from_file_location('recovery_fixture', copied)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        def fetch(url, destination, expected_sha, maximum_bytes):
            data = payloads[url]
            if hashlib.sha256(data).hexdigest() != expected_sha or len(data) > maximum_bytes:
                raise ValueError('Controlled remote content mismatch')
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        return module, tree, orchestrator_sha, fetch

    def test_ready_requires_three_actual_commands_catalogue_public_bytes_and_clean_sources(self):
        module, tree, orchestrator_sha, fetch = self.qualification_fixture()
        with mock.patch.object(module, 'download', side_effect=fetch), mock.patch.dict(os.environ, {'GITHUB_SHA': orchestrator_sha}):
            try:
                receipt = module.qualify(self.package, self.manifest, tree, self.root / 'work', self.root / 'evidence', self.contract)
            except Exception as error:
                self.fail('Qualification did not execute its complete proof: ' + str(error))
        self.assertTrue(receipt['publicationReady'])
        self.assertEqual([step['name'] for step in receipt['steps']], ['smoke', 'packed-gpu', 'full-catalogue'])
        self.assertTrue(all(step['exit'] == 0 and step['processEnded'] for step in receipt['steps']))
        self.assertEqual(receipt['catalogue']['catalogueGroupsPassed'], 2)
        self.assertEqual(len(receipt['publicCohortAfter']['publicPackages']), 7)
        self.assertEqual((self.root / 'work/export/runtime.nupkg').read_bytes(), self.package.read_bytes())
        self.contract_file.write_text(json.dumps(self.contract))
        command = [sys.executable, '-B', str(SCRIPT), 'publication', '--export', str(self.root / 'work/export'),
                   '--evidence', str(self.root / 'evidence'), '--contract', str(self.contract_file),
                   '--receipt', str(self.receipt)]
        checked = subprocess.run(command, capture_output=True, text=True,
                                 env=dict(os.environ, GITHUB_SHA=orchestrator_sha), timeout=15)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        (self.root / 'evidence/smoke.log').write_bytes(b'changed after qualification')
        checked = subprocess.run(command, capture_output=True, text=True,
                                 env=dict(os.environ, GITHUB_SHA=orchestrator_sha), timeout=15)
        self.assertNotEqual(checked.returncode, 0)
        self.assertIn('Proof file', checked.stderr)

    def test_failed_actual_probe_preserves_partial_evidence_without_exporting(self):
        module, tree, orchestrator_sha, fetch = self.qualification_fixture(failing_probe=True)
        with mock.patch.object(module, 'download', side_effect=fetch), mock.patch.dict(os.environ, {'GITHUB_SHA': orchestrator_sha}):
            with self.assertRaisesRegex(ValueError, 'Recovery proof failed: full-catalogue'):
                module.qualify(self.package, self.manifest, tree, self.root / 'work', self.root / 'evidence', self.contract)
        receipt = json.loads((self.root / 'evidence/qualification.json').read_text())
        self.assertFalse(receipt['publicationReady'])
        self.assertEqual(receipt['steps'][-1]['exit'], 7)
        self.assertTrue((self.root / 'evidence/full-catalogue.log').is_file())
        self.assertFalse((self.root / 'work/export').exists())


if __name__ == '__main__':
    unittest.main()
