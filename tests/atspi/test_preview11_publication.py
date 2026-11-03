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
    def test_allocated_identity_keeps_actual_inputs_and_candidate_pending(self):
        policy = json.loads((release.PROVIDER / 'public-preview11.json').read_text())
        self.assertIs(policy['armed'], False)
        self.assertEqual(policy['id'], 'Ranvier.WebCore.Accessibility.Atspi')
        self.assertEqual(policy['version'], '0.1.1-preview.11')
        self.assertEqual(policy['nativeSource'], '8b8db298eba294876c27bd9a3200881f872684df')
        self.assertEqual(policy['abi'], 63)
        self.assertEqual(set(policy['rids']), {'linux-x64', 'linux-arm64'})
        for rid, pins in policy['rids'].items():
            self.assertEqual(pins, dict(packageSha256=None, receiptSha256=None,
                                       proofKind='local-qualified-relayed' if rid=='linux-x64' else 'runner-executed'))
            self.assertEqual(release.QUALIFICATIONS[rid], (None, None, None, None, None))
        pins = json.loads((release.PROVIDER / 'preview11-publication.json').read_text())
        for name in ['candidateRun', 'candidateHead', 'packageSha256', 'candidateReceiptSha256']:
            self.assertIsNone(pins[name])

    def test_unarmed_prepare_and_verify_stop_before_network_or_authentication(self):
        policy = json.loads((release.PROVIDER / 'public-preview11.json').read_text())
        with tempfile.TemporaryDirectory() as directory, patch.object(release.subprocess, 'check_output') as network:
            with self.assertRaisesRegex(ValueError, 'unarmed'):
                release.qualify_inputs(Path(directory), policy)
            with self.assertRaises(ValueError):
                release.verify(Path(directory))
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
                    self.assertEqual(workflow.permitted(job, atspi11=mode), mode=='relay-x64' and job=='relay-atspi-preview11-x64')
                    self.assertFalse(workflow.permitted(job, atspi='prepare', atspi11=mode))
        for options in [dict(event='push'),dict(ref='refs/heads/other'),dict(recovery=True),dict(recovery4=True),dict(recovery7=True),dict(recovery7windows=True)]:
            with self.subTest(options=options):
                self.assertFalse(workflow.permitted('relay-atspi-preview11-x64',atspi11='relay-x64',**options))

    def test_existing_trusted_subject_verifies_before_login_and_remains_disabled(self):
        prepare = workflow.job('prepare-atspi-preview11')
        publish = workflow.job('publish-atspi-preview11')
        self.assertIn('if: ${{ false &&', prepare)
        self.assertIn('if: ${{ false &&', publish)
        self.assertNotIn('id-token: write', prepare)
        self.assertNotIn('NuGet/login', prepare)
        self.assertIn("github.ref == 'refs/heads/main'", publish)
        self.assertLess(publish.index('prepare_atspi_preview11.py verify'), publish.index('NuGet/login@v1'))
        self.assertIn('export/Ranvier.WebCore.Accessibility.Atspi.0.1.1-preview.11.nupkg', publish)
        self.assertNotIn('--skip-duplicate', publish)


if __name__ == '__main__':
    unittest.main()
