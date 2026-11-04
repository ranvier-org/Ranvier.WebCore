"""Metadata controls only; synthetic payloads are never loaded as native libraries."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile
import json
import hashlib

ROOT = Path(__file__).resolve().parents[1]


class Preview12Recovery(unittest.TestCase):
    def subject(self):
        path = ROOT / 'scripts/recover_preview12_linux_gpu.py'
        self.assertTrue(path.exists(), 'Recovery must validate the original immutable producer bytes')
        spec = importlib.util.spec_from_file_location('recovery12', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def allocated_metadata(self, subject):
        policy = json.loads((ROOT / 'docs/preview12-linux-gpu-recovery.json').read_text())
        policy.update(armed=True, controllerSource='a' * 40, producerRun=42)
        for record in policy['rids'].values():
            for name in ['packageSha256', 'summarySha256', 'failureLogSha256']:
                record[name] = 'b' * 64
            for name in ['packageArtifact', 'probeArtifact']:
                record[name].update(id=43, sha256='c' * 64)
        return policy

    def test_unallocated_policy_cannot_qualify_or_export(self):
        subject = self.subject()
        for phase in ['qualify', 'export']:
            with self.subTest(phase=phase), self.assertRaisesRegex(ValueError, 'unarmed'):
                subject.admit_policy(dict(schemaVersion=1, armed=False), phase)

    def test_metadata_allocation_does_not_enable_publication(self):
        subject = self.subject()
        policy = self.allocated_metadata(subject)
        subject.admit_policy(policy, 'qualify')
        with self.assertRaisesRegex(ValueError, 'disabled'):
            subject.admit_policy(policy, 'export')

    def test_different_product_source_cannot_reuse_this_recovery(self):
        subject = self.subject()
        policy = self.allocated_metadata(subject)
        policy['productSource'] = 'd' * 40
        with self.assertRaisesRegex(ValueError, 'source/version'):
            subject.admit_policy(policy, 'qualify')

    def test_original_unrelated_failure_is_never_promoted_by_the_abi_test_fix(self):
        subject = self.subject()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'logs.zip'
            data = b'linux_view_transition_pixels.py\nassert value == 63\nAssertionError\n'
            expected = [dict(name='Other native contract'), dict(name=subject.FAILED_GROUP)]
            record = dict(failureLogSha256=hashlib.sha256(data).hexdigest())

            def save(first):
                summary = (first + '\nFAIL 0.1 s  ' + subject.FAILED_GROUP + '  (exit code 1), 02-failed.log\n').encode()
                with zipfile.ZipFile(path, 'w') as archive:
                    archive.writestr('summary.txt', summary)
                    archive.writestr('02-failed.log', data)
                record['summarySha256'] = hashlib.sha256(summary).hexdigest()

            save('PASS 0.1 s  Other native contract')
            subject.verify_summary(path, record, expected)
            save('FAIL 0.1 s  Other native contract  (exit code 1), 01-unrelated.log')
            with self.assertRaisesRegex(ValueError, 'Unexpected'):
                subject.verify_summary(path, record, expected)

    def test_pinned_growth_failure_is_retained_only_with_its_exact_log(self):
        subject = self.subject()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'logs.zip'
            guard = b'linux_view_transition_pixels.py\nassert value == 63\nAssertionError\n'
            growth = b'tests/abi/web_animations.py\nAssertionError: memory flat across rounds: [1, 1, 2]\n'
            expected = [dict(name=subject.GROWTH_GROUP), dict(name=subject.FAILED_GROUP)]
            summary = ('FAIL 0.6 s  ' + subject.GROWTH_GROUP + '  (exit code 1), 01-growth.log\n'
                       'FAIL 0.1 s  ' + subject.FAILED_GROUP + '  (exit code 1), 02-failed.log\n').encode()

            def save(log):
                with zipfile.ZipFile(path, 'w') as archive:
                    archive.writestr('summary.txt', summary)
                    archive.writestr('01-growth.log', log)
                    archive.writestr('02-failed.log', guard)

            record = dict(failureLogSha256=hashlib.sha256(guard).hexdigest(),
                          summarySha256=hashlib.sha256(summary).hexdigest())
            save(growth)
            with self.assertRaisesRegex(ValueError, 'Unexpected'):
                subject.verify_summary(path, record, expected)
            record['growthFailureLogSha256'] = hashlib.sha256(growth).hexdigest()
            self.assertEqual(subject.verify_summary(path, record, expected), [subject.GROWTH_GROUP])
            other = b'tests/abi/web_animations.py\nAssertionError: rendered pixel mismatch\n'
            record['growthFailureLogSha256'] = hashlib.sha256(other).hexdigest()
            save(other)
            with self.assertRaisesRegex(ValueError, 'growth'):
                subject.verify_summary(path, record, expected)

    def test_growth_failure_pin_is_optional_but_exact(self):
        subject = self.subject()
        policy = self.allocated_metadata(subject)
        policy['rids']['linux-x64']['growthFailureLogSha256'] = 'not-a-digest'
        with self.assertRaisesRegex(ValueError, 'growth'):
            subject.admit_policy(policy, 'qualify')
        policy['rids']['linux-x64']['growthFailureLogSha256'] = 'e' * 64
        subject.admit_policy(policy, 'qualify')
        policy['rids']['linux-arm64']['growthFailureLogSha256'] = 'e' * 64
        with self.assertRaisesRegex(ValueError, 'growth'):
            subject.admit_policy(policy, 'qualify')

    def test_artifact_parent_traversal_is_rejected_before_any_extraction(self):
        subject = self.subject()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'unsafe.zip'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('../outside', b'never extracted')
            with zipfile.ZipFile(path) as archive, self.assertRaisesRegex(ValueError, 'Unsafe'):
                subject.safe_names(archive)

    def test_native_payload_must_match_the_manifest_not_just_the_package_label(self):
        subject = self.subject()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture.nupkg'
            original = b'synthetic ELF metadata control; never loaded'
            record = dict(name='libRanvierWebCoreHost.so', bytes=len(original), sha256=hashlib.sha256(original).hexdigest())
            manifest = dict(rid='linux-x64', flavor='gpu', abi=64, version=subject.VERSION,
                            source=dict(commit=subject.PRODUCT, dirty=False, builder='ci'), files=[record], total_bytes=len(original))
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('manifest.json', json.dumps(manifest))
                archive.writestr('fixture.nuspec', f'<package><metadata><id>Ranvier.WebCore.Native.Gpu.linux-x64</id><version>{subject.VERSION}</version></metadata></package>')
                archive.writestr('runtimes/linux-x64/native/libRanvierWebCoreHost.so', b'tampered')
            with self.assertRaisesRegex(ValueError, 'payload'):
                subject.verify_package(path, 'linux-x64', subject.sha(path))


if __name__ == '__main__':
    unittest.main()
