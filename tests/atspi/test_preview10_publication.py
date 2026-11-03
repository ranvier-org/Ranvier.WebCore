"""Release metadata and routing controls; these tests do not load or qualify a renderer."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('preview10_release', ROOT / 'scripts/prepare_atspi_preview10.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ProviderPublication(unittest.TestCase):
    def test_allocated_cohort_has_both_exact_reviewed_inputs(self):
        policy = json.loads((release.PROVIDER / 'public-preview10.json').read_text())
        release.aggregate.validate_policy(policy)
        self.assertEqual(policy['id'], release.IDENTITY)
        self.assertEqual(policy['version'], '0.1.1-preview.10')
        self.assertEqual(set(policy['rids']), {'linux-x64', 'linux-arm64'})
        pins = json.loads((release.PROVIDER / 'preview10-publication.json').read_text())
        self.assertEqual(pins['id'], release.IDENTITY)
        self.assertEqual(pins['version'], release.VERSION)
        with self.assertRaises(ValueError):
            release.validate_publication_pins(dict(pins, candidateRun=None))

    def test_publisher_requires_complete_exact_identity_pins(self):
        pins = dict(schemaVersion=1, id=release.IDENTITY, version=release.VERSION, candidateRun=1,
                    candidateHead='a' * 40, packageSha256='b' * 64, candidateReceiptSha256='c' * 64)
        release.validate_publication_pins(pins)
        for key, value in [('id', 'other'), ('version', '0.1.1-preview.11'), ('candidateRun', True),
                           ('candidateHead', None), ('packageSha256', 'B' * 64), ('candidateReceiptSha256', '')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                release.validate_publication_pins(dict(pins, **{key:value}))

    def test_run_admission_rejects_wrong_head_event_and_failed_runs(self):
        expected = dict(head_sha='a' * 40, event='workflow_dispatch', conclusion='success')
        with patch.object(release.subprocess, 'check_output', return_value=json.dumps(expected)):
            release.check_run(1, 'a' * 40)
        for key, value in [('head_sha', 'b' * 40), ('event', 'pull_request'), ('conclusion', 'failure')]:
            with patch.object(release.subprocess, 'check_output', return_value=json.dumps(dict(expected, **{key:value}))):
                with self.assertRaises(ValueError):
                    release.check_run(1, 'a' * 40)

    def test_selects_package_directory_not_duplicate_managed_feed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'package').mkdir()
            package = root / 'package/provider.nupkg'
            package.write_bytes(b'metadata-only test input')
            receipt = root / 'qualification-receipt.json'
            receipt.write_bytes(b'{}')
            (root / 'managed-aot/feed').mkdir(parents=True)
            (root / 'managed-aot/feed/provider.nupkg').write_bytes(package.read_bytes())
            pins = dict(packageSha256=release.sha(package), receiptSha256=release.sha(receipt))
            self.assertEqual(release.select_inputs(root, pins), (package, receipt))
            duplicate = root / 'package/duplicate.nupkg'
            duplicate.write_bytes(package.read_bytes())
            with self.assertRaises(ValueError):
                release.select_inputs(root, pins)
            duplicate.unlink()
            receipt.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                release.select_inputs(root, pins)

    def test_absence_requires_actual_404_and_refuses_existing_version(self):
        error = urllib.error.HTTPError('test', 404, 'absent', {}, None)
        with patch.object(release.urllib.request, 'urlopen', side_effect=error):
            release.absent_public_version()
        with patch.object(release.urllib.request, 'urlopen'):
            with self.assertRaises(ValueError):
                release.absent_public_version()
        error = urllib.error.HTTPError('test', 503, 'unavailable', {}, None)
        with patch.object(release.urllib.request, 'urlopen', side_effect=error):
            with self.assertRaises(urllib.error.HTTPError):
                release.absent_public_version()

    def test_prepare_and_publish_use_existing_trusted_workflow_without_engine_jobs(self):
        workflow = (ROOT / '.github/workflows/build.yml').read_text()
        for name in ('package-contract', 'plan', 'prebuilt', 'native', 'managed', 'publish',
                     'recover-preview2-gpu', 'verify-preview4-gpu-recovery',
                     'verify-preview7-linux-recovery', 'verify-preview7-windows-recovery'):
            section = re.search(r'^  ' + name + r':\n(.*?)(?=^  [a-z][a-z0-9-]*:|\Z)', workflow, re.M | re.S).group(1)
            self.assertIn("inputs.atspi_preview10 == '' || inputs.atspi_preview10 == 'off'", section)
        prepare = workflow.split('  prepare-atspi-preview10:', 1)[1].split('  publish-atspi-preview10:', 1)[0]
        publish = workflow.split('  publish-atspi-preview10:', 1)[1]
        self.assertNotIn('id-token: write', prepare)
        self.assertNotIn('NuGet/login', prepare)
        self.assertIn("github.ref == 'refs/heads/main'", publish)
        self.assertIn('id-token: write', publish)
        self.assertLess(publish.index('prepare_atspi_preview10.py verify'), publish.index('NuGet/login@v1'))
        self.assertIn('export/Ranvier.WebCore.Accessibility.Atspi.0.1.1-preview.10.nupkg', publish)
        self.assertNotIn('--skip-duplicate', publish)


if __name__ == '__main__':
    unittest.main()
