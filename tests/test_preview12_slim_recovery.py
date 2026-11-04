import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import warnings
import zipfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class SlimRecovery(unittest.TestCase):
    def subject(self):
        path = ROOT / 'scripts/recover_preview12_slim.py'
        self.assertTrue(path.exists(), 'Slim recovery requires a separate fail-closed controller')
        spec = importlib.util.spec_from_file_location('slim_recovery', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def policy(self, subject):
        policy = json.loads((ROOT / 'docs/preview12-slim-recovery.json').read_text())
        policy.update(armed=True, controllerSource='a' * 40, publicationEnabled=False, qualification=None)
        for index, record in enumerate(policy['original'].values(), 1):
            record['artifact'].update(id=index, sha256='b' * 64)
            record['packageSha256'] = 'c' * 64
        mac = policy['macRecovery']
        mac.update(run=7, workflowSource='d' * 40, packageSha256='e' * 64,
                   recoveryReceiptSha256='f' * 64, sidecarReceiptSha256='1' * 64, proofPrefix='exact/retained/')
        for index, key in enumerate(['packageArtifact', 'proofArtifact'], 5):
            mac[key].update(id=index, sha256='2' * 64)
        return policy

    def test_complete_qualification_policy_does_not_also_authorize_export(self):
        subject = self.subject()
        policy = self.policy(subject)
        subject.admit_policy(policy, 'qualify')
        with self.assertRaisesRegex(ValueError, 'Publication'):
            subject.admit_policy(policy, 'export')
        policy['publicationEnabled'] = True
        policy['qualification'] = dict(run=8, workflowSource='a' * 40, policySha256='b' * 64, receiptSha256='c' * 64,
            proofArtifact=dict(id=8, name='qualified-preview12-slim', sha256='d' * 64),
            packagesArtifact=dict(id=9, name='package-preview12-slim-recovered', sha256='e' * 64),
            packageHashes={name:'f' * 64 for name in subject.PACKAGE_IDS})
        subject.admit_policy(policy, 'export')
        policy['qualification']['packageHashes'].pop('Ranvier.WebCore')
        with self.assertRaisesRegex(ValueError, 'Seven'):
            subject.admit_policy(policy, 'export')

    def test_wrong_artifact_run_source_or_digest_rejects_before_download(self):
        subject = self.subject()
        record = dict(id=1, name='package-linux-x64-slim', sha256='a' * 64)
        metadata = dict(id=1, name=record['name'], expired=False, digest='sha256:' + record['sha256'],
                        workflow_run=dict(id=subject.PRODUCER_RUN, head_sha=subject.PRODUCT))
        with tempfile.TemporaryDirectory() as directory:
            for key, value in [('id', 2), ('name', 'another'), ('expired', True), ('digest', 'sha256:' + 'b' * 64),
                               ('workflow_run', dict(id=2, head_sha=subject.PRODUCT)),
                               ('workflow_run', dict(id=subject.PRODUCER_RUN, head_sha='c' * 40))]:
                with patch.object(subject, 'api', return_value=dict(metadata, **{key:value})), \
                        patch.object(subject.subprocess, 'run') as run:
                    with self.assertRaisesRegex(ValueError, 'lineage'):
                        subject.artifact(record, subject.PRODUCER_RUN, subject.PRODUCT, Path(directory))
                    run.assert_not_called()

    def test_wrong_or_failed_qualification_run_cannot_export(self):
        subject = self.subject()
        expected = dict(run=8, workflowSource='a' * 40)
        run = dict(id=8, head_sha='a' * 40, path='.github/workflows/preview12-slim-recovery.yml',
                   event='workflow_dispatch', head_branch='main', run_attempt=1, status='completed', conclusion='success',
                   repository=dict(full_name=subject.REPO), head_repository=dict(full_name=subject.REPO))
        jobs = dict(total_count=1, jobs=[dict(name='qualify-slim-preview12', conclusion='success')])
        subject.admit_qualification_run(run, jobs, expected)
        for key, value in [('head_sha', 'b' * 40), ('path', '.github/workflows/build.yml'), ('conclusion', 'failure'),
                           ('event', 'push'), ('run_attempt', 2), ('head_branch', 'unreviewed')]:
            with self.assertRaises(ValueError):
                subject.admit_qualification_run(dict(run, **{key:value}), jobs, expected)

    def test_qualification_workflow_is_readonly_default_off_and_policy_gated(self):
        workflow = (ROOT / '.github/workflows/preview12-slim-recovery.yml').read_text()
        self.assertIn('permissions:\n  contents: read\n  actions: read\n', workflow)
        self.assertNotIn('id-token:', workflow)
        policy = json.loads((ROOT / 'docs/preview12-slim-recovery.json').read_text())
        self.assertIn('default: off', workflow)
        self.assertIn("os.environ['PHASE'] == 'qualify'", workflow)
        subject = self.subject()
        with self.assertRaisesRegex(ValueError, 'unarmed'):
            subject.admit_policy(dict(policy, armed=False), 'qualify')
        if policy['armed']:
            subject.admit_policy(policy, 'qualify')
        self.assertTrue(policy['controllerSource'] is None or subject.revision(policy['controllerSource']))
        self.assertIn("github.ref == 'refs/heads/main'", workflow)

    def test_unallocated_policy_cannot_qualify_or_export(self):
        subject = self.subject()
        for phase in ['qualify', 'export']:
            with self.assertRaisesRegex(ValueError, 'unarmed'):
                subject.admit_policy(dict(schemaVersion=1, armed=False), phase)

    def test_unsafe_or_duplicate_archive_members_reject(self):
        subject = self.subject()
        with tempfile.TemporaryDirectory() as directory:
            for names in [['a', 'a'], ['a', 'A'], ['../a'], ['/absolute'], ['a\\b'], ['a/../b']]:
                path = Path(directory) / 'fixture.zip'
                with warnings.catch_warnings(), zipfile.ZipFile(path, 'w') as archive:
                    warnings.simplefilter('ignore', UserWarning)
                    for name in names:
                        info = zipfile.ZipInfo(name)
                        info.filename = name
                        archive.writestr(info, b'fixture')
                with zipfile.ZipFile(path) as archive, self.assertRaises(ValueError, msg=str(names)):
                    subject.safe_names(archive)

    def test_only_the_original_F_successful_native_jobs_are_admitted(self):
        subject = self.subject()
        run = dict(id=subject.PRODUCER_RUN, head_sha=subject.PRODUCT, head_branch='v' + subject.VERSION,
                   event='push', path='.github/workflows/build.yml', run_attempt=1, status='completed', conclusion='cancelled',
                   repository=dict(full_name=subject.REPO), head_repository=dict(full_name=subject.REPO))
        gates = [dict(name=name, conclusion='success') for name in ['Package', 'Check the staged files and paint a page',
                  'Verify mutation observation delivery and ownership', 'Run the probes']]
        jobs = [dict(name='native (' + rid + ', fixture)', status='completed', conclusion='success', steps=gates) for rid in subject.ORIGINAL_RIDS]
        jobs.append(dict(name='native (osx-arm64, fixture)', status='completed', conclusion='cancelled'))
        subject.admit_original_run(run, dict(total_count=len(jobs), jobs=jobs))
        for key, value in [('head_sha', 'a' * 40), ('event', 'workflow_dispatch'), ('run_attempt', 2), ('status', 'in_progress'),
                           ('repository', dict(full_name='elsewhere/Ranvier.WebCore'))]:
            wrong = dict(run, **{key: value})
            with self.assertRaises(ValueError):
                subject.admit_original_run(wrong, dict(total_count=len(jobs), jobs=jobs))
        jobs[0]['conclusion'] = 'failure'
        with self.assertRaises(ValueError):
            subject.admit_original_run(run, dict(total_count=len(jobs), jobs=jobs))

    def test_exact_signatures_reject_equal_count_but_changed_parameter(self):
        subject = self.subject()
        expected = {f'rv_fixture_{i}': dict(returns='int', parameters=[dict(type='nativeint', input=False, output=False, marshal='')]) for i in range(349)}
        actual = dict(assemblySha256='a' * 64, functions={name: dict(signature=value, library='RanvierWebCoreHost', convention=256) for name, value in expected.items()})
        subject.verify_signatures(actual, expected, 'a' * 64)
        actual['functions']['rv_fixture_1']['signature'] = dict(returns='int', parameters=[dict(type='int', input=False, output=False, marshal='')])
        with self.assertRaisesRegex(ValueError, 'signature'):
            subject.verify_signatures(actual, expected, 'a' * 64)

    def test_signature_manifest_normalizes_only_the_double_alias_not_float32(self):
        subject = self.subject()
        manifest = subject.signature_manifest(ROOT)
        parameters = manifest['rv_event_number']['parameters']
        self.assertEqual(parameters[-1]['type'], 'float&')
        self.assertTrue(any(parameter['type'] == 'float32' for signature in manifest.values() for parameter in signature['parameters']))

    def test_same_count_with_wrong_native_library_convention_or_marshalling_rejects(self):
        subject = self.subject()
        expected = {f'rv_fixture_{i}':dict(returns='int', parameters=[dict(type='string', input=False, output=False, marshal='30')]) for i in range(349)}
        correct = dict(assemblySha256='a' * 64, functions={name:dict(signature=value, library='RanvierWebCoreHost', convention=256) for name, value in expected.items()})
        for key, value in [('library', 'anotherLibrary'), ('convention', 512),
                           ('signature', dict(returns='int', parameters=[dict(type='string', input=False, output=False, marshal='')]))]:
            actual = json.loads(json.dumps(correct))
            actual['functions']['rv_fixture_0'][key] = value
            with self.assertRaisesRegex(ValueError, 'signature'):
                subject.verify_signatures(actual, expected, 'a' * 64)

    def test_aggregate_requires_exact_five_bracketed_dependencies(self):
        subject = self.subject()
        dependencies = {f'Ranvier.WebCore.Native.{rid}': '[' + subject.VERSION + ']' for rid in subject.RIDS}
        subject.verify_aggregate_dependencies(dependencies)
        dependencies.pop('Ranvier.WebCore.Native.osx-arm64')
        with self.assertRaises(ValueError):
            subject.verify_aggregate_dependencies(dependencies)


if __name__ == '__main__':
    unittest.main()
