"""Hermetic public Cocoa admission/command controls; synthetic files never load as libraries."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('public_cocoa', ROOT / 'tests/controls/public_cocoa_contracts.py')
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)


class PublicCocoaControls(unittest.TestCase):
    def test_library_names_match_inspected_public_and_private_packages(self):
        fixture = json.loads((ROOT / 'tests/fixtures/cocoa-native-library-closure.json').read_text())
        self.assertEqual(subject.MAC_BASE_LIBRARIES, set(fixture['publicSlim']['libraries']))
        self.assertEqual(subject.MAC_BASE_LIBRARIES | {'libEGL.dylib', 'libGLESv2.dylib'},
                         set(fixture['privateGpu']['libraries']))
        self.assertNotIn('libWTF.dylib', subject.MAC_BASE_LIBRARIES)

    def policy(self):
        return dict(schemaVersion=1, armed=True, controllerSource='b' * 40,
                    native=dict(id='Ranvier.WebCore.Native.Gpu.osx-arm64', version='test-only-fixture', source='a' * 40,
                                packageSha256='1' * 64, auditSha256='2' * 64, abi=64, declarations=349),
                    interopPackageSha256='3' * 64, headerSha256='4' * 64, sidecarManifestSha256='5' * 64)

    def test_checked_in_policy_cannot_execute(self):
        with self.assertRaisesRegex(ValueError, 'unarmed'):
            subject.policy_admission(json.loads((ROOT / 'tests/controls/public_cocoa_policy.json').read_text()))

    def test_explicit_cohort_requires_all_independent_pins(self):
        subject.policy_admission(self.policy())
        for change in [dict(abi=63), dict(abi=65), dict(declarations=347), dict(source=None), dict(packageSha256=None)]:
            policy = self.policy()
            policy['native'].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                subject.policy_admission(policy)

    def test_package_requires_complete_exact_clean_cohort(self):
        with tempfile.TemporaryDirectory() as folder:
            package = Path(folder) / 'synthetic-not-runnable.nupkg'
            policy = self.policy()
            names = ['libRanvierWebCoreHost.dylib', 'libWebCore.dylib', 'libJavaScriptCore.dylib',
                     'libWebGPU.dylib', 'libEGL.dylib', 'libGLESv2.dylib']
            payload = b'synthetic metadata control; never loaded'
            manifest = dict(rid='osx-arm64', flavor='gpu', version=policy['native']['version'], abi=64,
                            source=dict(commit=policy['native']['source'], dirty=False),
                            total_bytes=len(names) * len(payload),
                            files=[dict(name=name, bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest()) for name in names])

            def save(value):
                with zipfile.ZipFile(package, 'w') as archive:
                    archive.writestr('fixture.nuspec', '<package><metadata><id>' + policy['native']['id'] + '</id><version>'
                                     + policy['native']['version'] + '</version></metadata></package>')
                    archive.writestr('manifest.json', json.dumps(value))
                    for name in names:
                        archive.writestr('runtimes/osx-arm64/native/' + name, payload)
                policy['native']['packageSha256'] = subject.sha(package)

            save(manifest)
            subject.validate_package(policy, package)
            for change in [dict(abi=63), dict(source=dict(commit='c' * 40, dirty=False)), dict(rid='win-x64'),
                           dict(files=manifest['files'][:-1])]:
                save(manifest | change)
                with self.subTest(change=change), self.assertRaises(ValueError):
                    subject.validate_package(policy, package)

    def test_sidecar_requires_exact_supported_abi_and_preserved_native_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            helpers = {}
            for name in ['timer', 'page', 'motion', 'contrast']:
                path = root / name
                path.write_bytes(b'synthetic-not-a-library')
                helpers[name] = dict(path=name, sha256=subject.sha(path))
            policy = self.policy()
            manifest = dict(files=[dict(name='native.fixture', sha256='a' * 64)])
            data = dict(schemaVersion=1, boundary='public-Host-unchanged-sidecars-v1', abi=64, declarations=349,
                        nativeSource=policy['native']['source'], nativePackageSha256=policy['native']['packageSha256'],
                        nativeBefore={'native.fixture': 'a' * 64}, nativeAfter={'native.fixture': 'a' * 64},
                        hostReplaced=False, headerReconstruction=False, engineCompilation=False,
                        producerConfigurationSha256='b' * 64, consumedInputsArchiveSha256='c' * 64,
                        compilerSha256='d' * 64, compileCommandsSha256='e' * 64,
                        strictLink=True, sourceEquivalenceReviewed=True, helpers=helpers)
            path = root / 'sidecars.json'
            path.write_text(json.dumps(data))
            policy['sidecarManifestSha256'] = subject.sha(path)
            subject.validate_sidecars(policy, manifest, path)
            for change in [dict(abi=65), dict(declarations=347), dict(hostReplaced=True), dict(headerReconstruction=True)]:
                path.write_text(json.dumps(data | change))
                policy['sidecarManifestSha256'] = subject.sha(path)
                with self.subTest(change=change), self.assertRaises(ValueError):
                    subject.validate_sidecars(policy, manifest, path)

    def test_independent_commands_preserve_counts_orders_and_fresh_owner_probe(self):
        helpers = {key: Path('/owned/' + key) for key in ['timer', 'page', 'motion', 'contrast']}
        rows = subject.commands(Path('/owned/native'), helpers, Path('/owned/output'))
        self.assertEqual([name for name, _ in rows], ['timers-eight', 'timer-fairness-0.01', 'timer-fairness-0.1',
                         'timer-fairness-1', 'motion-135', 'contrast-default-83', 'contrast-reverse-83',
                         'contrast-paired-order', 'fresh-owner-branch'])
        commands = dict(rows)
        self.assertIn('--page-helper', commands['motion-135'])
        self.assertIn('--scoped-helper', commands['contrast-default-83'])
        self.assertIn('--first-system-more', commands['contrast-reverse-83'])
        self.assertIn('run', commands['fresh-owner-branch'])
        self.assertFalse(any('--owner-assertion-proof' in row for _, row in rows))

    def test_retained_motion_and_contrast_assertions_are_unchanged(self):
        fixture = json.loads((ROOT / 'tests/fixtures/public-cocoa-retained-assertions.json').read_text())
        for name, record in fixture['files'].items():
            source = (ROOT / name).read_text()
            source = source.replace("    parser.add_argument('--page-helper', type=Path)\n", '')
            source = source.replace("args.page_helper.resolve() if args.page_helper else native / 'libRanvierWebCoreHost.dylib'",
                                    "native / 'libRanvierWebCoreHost.dylib'")
            options = {'show_empty': True} if sys.version_info >= (3, 13) else {}
            actual = hashlib.sha256(ast.dump(ast.parse(source), **options).encode()).hexdigest()
            self.assertEqual(actual, record['astSha256'], name)

    def test_one_child_failure_does_not_hide_the_next_independent_group(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            failed, passed = root / 'failed.py', root / 'passed.py'
            failed.write_text('raise SystemExit(3)')
            passed.write_text('print("INDEPENDENT_GROUP_EXECUTED")')
            with patch.object(subject, 'resident_tree_bytes', return_value=0):
                results = subject.run_groups([('failed', [sys.executable, '-I', str(failed)]),
                                              ('passed', [sys.executable, '-I', str(passed)])], root, dict(__import__('os').environ))
            self.assertEqual([row['exit'] for row in results], [3, 0])
            self.assertTrue(all(row['childrenReaped'] for row in results))
            self.assertIn('INDEPENDENT_GROUP_EXECUTED', (root / 'passed.log').read_text())


if __name__ == '__main__':
    unittest.main()
