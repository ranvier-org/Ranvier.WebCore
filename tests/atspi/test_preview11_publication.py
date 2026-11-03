"""P11 source preparation controls; no renderer qualification or publication occurs here."""
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('preview11_release', ROOT / 'scripts/prepare_atspi_preview11.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)
spec = importlib.util.spec_from_file_location('provider_workflow', ROOT / 'tests/test_preview2_recovery_workflow.py')
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)


class Preview11Preparation(unittest.TestCase):
    def test_allocated_identity_binds_actual_inputs_and_audited_candidate(self):
        policy = json.loads((release.PROVIDER / 'public-preview11.json').read_text())
        self.assertIs(policy['armed'], True)
        self.assertEqual(policy['id'], 'Ranvier.WebCore.Accessibility.Atspi')
        self.assertEqual(policy['version'], '0.1.1-preview.11')
        self.assertEqual(policy['nativeSource'], '8b8db298eba294876c27bd9a3200881f872684df')
        self.assertEqual(policy['abi'], 63)
        self.assertEqual(set(policy['rids']), {'linux-x64', 'linux-arm64'})
        self.assertEqual(policy['rids']['linux-x64'],dict(packageSha256='84c3da7dcb0bc0ad7d420bd135c6cd8234296d05c42a329d0c137812280ae6bd',
                         receiptSha256='1d69946f2073fc0cf128c835a698ba244de86c111cd65bc5fffbc61f581a830c',proofKind='local-qualified-relayed'))
        self.assertEqual(release.QUALIFICATIONS['linux-x64'],(41640893465,'0ac88abef20548c662877991987898c1e9aa9f0d',
                         'atspi-preview11-local-x64-qualified','workflow_dispatch','.github/workflows/build.yml'))
        self.assertEqual(policy['rids']['linux-arm64'],dict(proofKind='runner-executed',
                         packageSha256='964e03576b31720e438a1c6c92a73a9c18c56b32687d2136b9a46bf941b9e279',
                         receiptSha256='4e85ebf15f6b410ceecc4af609246ff346343896aa6d2c94b0dac29ca1ade7df'))
        self.assertEqual(release.QUALIFICATIONS['linux-arm64'],(41627017174,'5b5ef82a0af3011fc6615d442e9d2618147b08a8',
                         'unqualified-atspi-arm64-5b5ef82a0af3011fc6615d442e9d2618147b08a8','push',
                         '.github/workflows/atspi-p11-arm64-qualification.yml'))
        pins = json.loads((release.PROVIDER / 'preview11-publication.json').read_text())
        self.assertEqual(pins['candidateRun'],41642147423)
        self.assertEqual(pins['candidateHead'],'708058bcd9ff83575cda85238d586dc31d03231b')
        self.assertEqual(pins['packageSha256'],'bd2b2d0d760d33efedac1aef0381b4019b495812152f3685d4f3520f3a33e1bb')
        self.assertEqual(pins['candidateReceiptSha256'],'9791aedf253c5307e114d50e8ca6f717a8337fd80e70ae1a37845ec40b3f937e')
        release.validate_publication_pins(pins)

    def test_unarmed_aggregate_stops_before_network_or_authentication(self):
        policy = json.loads((release.PROVIDER / 'public-preview11.json').read_text())
        with tempfile.TemporaryDirectory() as directory, patch.object(release.subprocess, 'check_output') as network:
            with self.assertRaisesRegex(ValueError, 'unarmed'):
                release.qualify_inputs(Path(directory), dict(policy,armed=False))
            network.assert_not_called()

    def test_pending_or_malformed_qualification_run_fails_before_network(self):
        with patch.object(release.subprocess, 'check_output') as network:
            for run, head in [(None, None), (True, 'a' * 40), (0, 'a' * 40), (1, 'A' * 40), (1, 'a' * 39)]:
                with self.subTest(run=run, head=head), self.assertRaises(ValueError):
                    release.check_run(run, head, 'push', '.github/workflows/atspi-arm64-qualification.yml')
            network.assert_not_called()

    def test_actual_run_event_workflow_head_and_outcome_are_independently_bound(self):
        path = '.github/workflows/atspi-arm64-qualification.yml'
        for event in ['push', 'workflow_dispatch']:
            expected = dict(head_sha='a' * 40, event=event, path=path, conclusion='success')
            with patch.object(release.subprocess, 'check_output', return_value=json.dumps(expected)):
                release.check_run(1, 'a' * 40, event, path)
            for key, value in [('event', 'pull_request'), ('path', '.github/workflows/build.yml'),
                               ('head_sha', 'b' * 40), ('conclusion', 'failure')]:
                with self.subTest(event=event, key=key), patch.object(release.subprocess, 'check_output', return_value=json.dumps(dict(expected, **{key:value}))):
                    with self.assertRaises(ValueError):
                        release.check_run(1, 'a' * 40, event, path)
        with patch.object(release.subprocess, 'check_output') as network:
            for event, workflow in [(None, None), ('pull_request', path), ('push', None), ('push', '../workflow.yml')]:
                with self.assertRaises(ValueError):
                    release.check_run(1, 'a' * 40, event, workflow)
            network.assert_not_called()

    def test_publication_requires_exact_p11_candidate(self):
        pins = dict(schemaVersion=1, id=release.IDENTITY, version=release.VERSION, candidateRun=1,
                    candidateHead='a' * 40, packageSha256='b' * 64, candidateReceiptSha256='c' * 64)
        release.validate_publication_pins(pins)
        for field, value in [('version', '0.1.1-preview.10'), ('candidateRun', True),
                             ('candidateHead', None), ('packageSha256', None), ('candidateReceiptSha256', 'C' * 64)]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                release.validate_publication_pins(dict(pins, **{field:value}))

    def test_absence_probe_targets_p11_and_requires_404(self):
        error = urllib.error.HTTPError('test', 404, 'absent', {}, None)
        with patch.object(release.urllib.request, 'urlopen', side_effect=error) as request:
            release.absent_public_version()
            self.assertIn('/0.1.1-preview.11/', request.call_args.args[0])
        with patch.object(release.urllib.request, 'urlopen'), self.assertRaises(ValueError):
            release.absent_public_version()

    def test_p11_modes_do_not_launch_engine_recovery_or_p10_jobs(self):
        text = (ROOT / '.github/workflows/build.yml').read_text()
        jobs = re.findall(r'^  ([a-z][a-z0-9-]*):$', text.split('jobs:', 1)[1], re.M)
        for mode in ['prepare', 'publish', 'relay-x64']:
            for job in jobs:
                with self.subTest(mode=mode, job=job):
                    self.assertEqual(workflow.permitted(job, atspi11=mode), mode=='publish' and job=='publish-atspi-preview11')
                    self.assertFalse(workflow.permitted(job, atspi='prepare', atspi11=mode))
        for options in [dict(event='push'),dict(ref='refs/heads/other'),dict(recovery=True),dict(recovery4=True),dict(recovery7=True),dict(recovery7windows=True),dict(user='')]:
            with self.subTest(options=options):
                self.assertFalse(workflow.permitted('publish-atspi-preview11',atspi11='publish',**options))

    def test_disabled_p12_mode_launches_no_job(self):
        text = (ROOT / '.github/workflows/build.yml').read_text()
        jobs = re.findall(r'^  ([a-z][a-z0-9-]*):$', text.split('jobs:', 1)[1], re.M)
        for job in jobs:
            with self.subTest(job=job):
                self.assertFalse(workflow.permitted(job, atspi11='publish-p12'))
                self.assertFalse(workflow.permitted(job, atspi='prepare', atspi11='publish-p12'))
        for options in [dict(event='push'),dict(ref='refs/heads/other'),dict(recovery=True),dict(recovery4=True),dict(recovery7=True),dict(recovery7windows=True),dict(user='')]:
            with self.subTest(options=options):
                self.assertFalse(workflow.permitted('publish-atspi-preview12',atspi11='publish-p12',**options))

    def test_main_publisher_verifies_before_login_and_completed_routes_are_disabled(self):
        prepare = workflow.job('prepare-atspi-preview11')
        publish = workflow.job('publish-atspi-preview11')
        self.assertIn('if: ${{ false &&', prepare)
        self.assertIn("github.ref == 'refs/heads/main'",prepare)
        self.assertNotIn('if: ${{ false &&', publish)
        self.assertNotIn('id-token: write', prepare)
        self.assertNotIn('NuGet/login', prepare)
        self.assertIn("github.ref == 'refs/heads/main'", publish)
        self.assertLess(publish.index('prepare_atspi_preview11.py verify'), publish.index('NuGet/login@v1'))
        self.assertIn('export/Ranvier.WebCore.Accessibility.Atspi.0.1.1-preview.11.nupkg', publish)
        self.assertNotIn('--skip-duplicate', publish)


if __name__ == '__main__':
    unittest.main()
