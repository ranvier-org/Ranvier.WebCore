from pathlib import Path
import re
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/build.yml'


def job(name):
    marker = '\n  ' + name + ':\n'
    text = WORKFLOW.read_text()
    if marker not in text:
        return None
    return re.split(r'(?m)^  [a-z][\w-]*:\s*$', text.split(marker, 1)[1], maxsplit=1)[0]


def evaluate(expression, recovery=False, recovery4=False, recovery7=False, recovery7windows=False, recovery12=False, recovery12slim=False, result='success', event='workflow_dispatch', ref='refs/heads/main', user='owner', cancelled=False, atspi='off', atspi11='off'):
    values = {'inputs.recover_preview2_gpu': recovery, 'inputs.recover_preview4_gpu': recovery4, 'inputs.recover_preview7_linux': recovery7, 'inputs.recover_preview7_windows': recovery7windows, 'github.event_name': event, 'github.ref': ref,
              'inputs.recover_preview12_linux_gpu': recovery12, 'needs.verify-preview12-linux-recovery.result': result,
              'inputs.recover_preview12_slim': recovery12slim, 'needs.verify-preview12-slim-recovery.result': result,
              'github.workflow': 'build', 'github.run_id': 123, 'inputs.flavor': 'gpu', 'vars.NUGET_USER': user,
              'inputs.rids': '', 'inputs.atspi_preview10': atspi, 'inputs.atspi_preview11': atspi11, 'github.head_ref': 'codex/batch-fixture',
              'github.event.pull_request.labels.*.name': [],
              'needs.plan.outputs.matrix': 'selected', 'needs.plan.outputs.prebuilt': 'attached',
              'needs.recover-preview2-gpu.result': result, 'needs.verify-preview4-gpu-recovery.result': result, 'needs.verify-preview7-linux-recovery.result': result, 'needs.verify-preview7-windows-recovery.result': result, 'needs.native.result': 'success',
              'needs.prebuilt.result': 'skipped', 'needs.managed.result': 'skipped',
              'needs.package-contract.result': 'success', 'needs.publish.result': 'success'}
    for key in sorted(values, key=len, reverse=True):
        expression = expression.replace(key, repr(values[key]))
    expression = expression.replace('!cancelled()', repr(not cancelled))
    expression = re.sub(r'!(?!=)', 'not ', expression)
    expression = expression.replace('&&', ' and ').replace('||', ' or ').replace('false', 'False')
    return eval(' '.join(expression.split()), {'__builtins__': {}},
                {'startsWith': lambda a, b: a.startswith(b), 'format': lambda text, *args: text.format(*args),
                 'contains': lambda items, value: value in items})


def permitted(name, **options):
    block = job(name)
    if block is None:
        return False
    match = re.search(r'(?m)^    if:[ \t]*(.*)', block)
    if match is None:
        return True
    expression = match[1].strip()
    if expression in ['>', '>-']:
        expression = block[match.end():].split('${{', 1)[1].split('}}', 1)[0]
    elif expression.startswith('${{'):
        expression = expression[3:].split('}}', 1)[0]
    return bool(evaluate(expression, **options))


class RecoveryWorkflowControls(unittest.TestCase):
    def test_preview12_slim_is_isolated_from_every_other_mode(self):
        text = WORKFLOW.read_text()
        own = {'verify-preview12-slim-recovery', 'publish-preview12-slim-recovery'}
        names = re.findall(r'^  ([a-z][a-z0-9-]*):$', text.split('\njobs:\n', 1)[1], re.M)
        for name in names:
            if name not in own:
                with self.subTest(job=name):
                    self.assertFalse(permitted(name, recovery12slim=True))
        for name in own:
            self.assertTrue(permitted(name, recovery12slim=True))
            for options in [dict(recovery12=True), dict(recovery7windows=True), dict(atspi='prepare'),
                            dict(ref='refs/tags/v0.1.1-preview.12'), dict(event='push')]:
                with self.subTest(job=name, options=options):
                    self.assertFalse(permitted(name, recovery12slim=True, **options))
        for options in [dict(result='failure'), dict(cancelled=True), dict(user='')]:
            self.assertFalse(permitted('publish-preview12-slim-recovery', recovery12slim=True, **options))
        publish = job('publish-preview12-slim-recovery')
        self.assertLess(publish.index('recover_preview12_slim.py export'), publish.index('NuGet/login@v1'))

    def test_preview12_recovers_only_through_its_verified_main_route(self):
        text = WORKFLOW.read_text()
        own = {'verify-preview12-linux-recovery', 'publish-preview12-linux-recovery'}
        names = re.findall(r'^  ([a-z][a-z0-9-]*):$', text.split('\njobs:\n', 1)[1], re.M)
        for name in names:
            if name not in own:
                with self.subTest(job=name):
                    self.assertFalse(permitted(name, recovery12=True))
        self.assertTrue(permitted('verify-preview12-linux-recovery', recovery12=True))
        self.assertTrue(permitted('publish-preview12-linux-recovery', recovery12=True))
        for options in [dict(ref='refs/tags/v0.1.1-preview.12'), dict(event='push'), dict(recovery4=True), dict(atspi='prepare'), dict(recovery12slim=True)]:
            for name in own:
                with self.subTest(job=name, options=options):
                    self.assertFalse(permitted(name, recovery12=True, **options))
        for options in [dict(result='failure'), dict(cancelled=True), dict(user='')]:
            self.assertFalse(permitted('publish-preview12-linux-recovery', recovery12=True, **options))
        publish = job('publish-preview12-linux-recovery')
        self.assertLess(publish.index('recover_preview12_linux_gpu.py export'), publish.index('NuGet/login@v1'))

    def test_provider_modes_are_exclusive_and_publisher_requires_main(self):
        ordinary = ['plan', 'package-contract', 'native', 'prebuilt', 'managed', 'publish', 'gpu-cohort',
                    'recover-preview2-gpu', 'publish-preview2-recovery', 'verify-preview4-gpu-recovery',
                    'publish-preview4-gpu-recovery', 'verify-preview7-linux-recovery', 'publish-preview7-linux-recovery',
                    'verify-preview7-windows-recovery', 'publish-preview7-windows-recovery']
        for mode in ('prepare', 'publish'):
            for name in ordinary:
                with self.subTest(mode=mode, job=name):
                    self.assertFalse(permitted(name, atspi=mode))
        self.assertTrue(permitted('prepare-atspi-preview10', atspi='prepare'))
        self.assertFalse(permitted('prepare-atspi-preview10', atspi='prepare', recovery=True))
        self.assertTrue(permitted('publish-atspi-preview10', atspi='publish'))
        self.assertFalse(permitted('publish-atspi-preview10', atspi='publish', ref='refs/heads/other'))
        self.assertFalse(permitted('publish-atspi-preview10', atspi='publish', user=''))
        self.assertFalse(permitted('publish-atspi-preview10', atspi='publish', recovery7=True))

    def test_preview7_isolated_and_main_only(self):
        for name in ['plan', 'package-contract', 'native', 'prebuilt', 'managed', 'publish', 'gpu-cohort',
                     'recover-preview2-gpu', 'publish-preview2-recovery', 'verify-preview4-gpu-recovery', 'publish-preview4-gpu-recovery']:
            with self.subTest(job=name): self.assertFalse(permitted(name, recovery7=True))
        self.assertTrue(permitted('verify-preview7-linux-recovery', recovery7=True))
        self.assertFalse(permitted('verify-preview7-linux-recovery', recovery7=True, recovery=True))
        self.assertFalse(permitted('verify-preview7-linux-recovery', recovery7=True, recovery4=True))
        self.assertFalse(permitted('verify-preview7-linux-recovery', recovery7=True, ref='refs/heads/other'))
        self.assertFalse(permitted('verify-preview7-linux-recovery', recovery7=True, event='push'))
        self.assertTrue(permitted('publish-preview7-linux-recovery', recovery7=True))
        self.assertFalse(permitted('publish-preview7-linux-recovery', recovery7=True, result='failure'))
        self.assertFalse(permitted('publish-preview7-linux-recovery', recovery7=True, user=''))
        self.assertFalse(permitted('publish-preview7-linux-recovery', recovery7=True, cancelled=True))

    def test_preview7_concurrency_and_verification_before_authentication(self):
        text = WORKFLOW.read_text()
        group = re.search(r'(?m)^  group: (.+)$', text)[1].split('${{')[1].split('}}')[0]
        cancel = re.search(r'(?m)^  cancel-in-progress: (.+)$', text)[1].split('${{')[1].split('}}')[0]
        self.assertEqual(evaluate(group, recovery7=True), 'preview7-linux-recovery-123')
        self.assertFalse(evaluate(cancel, recovery7=True))
        publication = job('publish-preview7-linux-recovery')
        self.assertLess(publication.index('scripts/prepare_preview7_linux_gpu.py'), publication.index('NuGet/login@v1'))
        self.assertIn('needs: [verify-preview7-linux-recovery]', publication)

    def test_preview4_skips_all_other_jobs_and_requires_main(self):
        for name in ['plan', 'package-contract', 'native', 'prebuilt', 'managed', 'publish',
                     'gpu-cohort', 'recover-preview2-gpu', 'publish-preview2-recovery']:
            with self.subTest(job=name):
                self.assertFalse(permitted(name, recovery4=True))
        self.assertTrue(permitted('verify-preview4-gpu-recovery', recovery4=True))
        self.assertFalse(permitted('verify-preview4-gpu-recovery', recovery4=True, recovery=True))
        self.assertFalse(permitted('verify-preview4-gpu-recovery', recovery4=True, ref='refs/heads/unreviewed'))
        self.assertFalse(permitted('verify-preview4-gpu-recovery', recovery4=True, event='push'))

    def test_preview4_publish_requires_verified_main_and_owner(self):
        self.assertTrue(permitted('publish-preview4-gpu-recovery', recovery4=True))
        for state in ['failure', 'cancelled', 'skipped']:
            self.assertFalse(permitted('publish-preview4-gpu-recovery', recovery4=True, result=state))
        self.assertFalse(permitted('publish-preview4-gpu-recovery', recovery4=True, user=''))
        self.assertFalse(permitted('publish-preview4-gpu-recovery', recovery4=True, cancelled=True))
        self.assertFalse(permitted('publish-preview4-gpu-recovery', recovery4=True, ref='refs/tags/v0.1.1-preview.4'))

    def test_preview4_uses_separate_concurrency_and_rechecks_before_login(self):
        text = WORKFLOW.read_text()
        group = re.search(r'(?m)^  group: (.+)$', text)[1].split('${{')[1].split('}}')[0]
        cancel = re.search(r'(?m)^  cancel-in-progress: (.+)$', text)[1].split('${{')[1].split('}}')[0]
        self.assertEqual(evaluate(group, recovery4=True), 'preview4-artifact-recovery-123')
        self.assertFalse(evaluate(cancel, recovery4=True))
        publication = job('publish-preview4-gpu-recovery')
        self.assertLess(publication.index('scripts/recover_preview4_gpu.py'), publication.index('NuGet/login@v1'))
        self.assertIn('needs: [verify-preview4-gpu-recovery]', publication)

    def test_recovery_skips_every_ordinary_job(self):
        for name in ['plan', 'package-contract', 'native', 'prebuilt', 'managed', 'publish', 'gpu-cohort']:
            with self.subTest(job=name):
                self.assertFalse(permitted(name, recovery=True, event='push', ref='refs/tags/v0.1.1-preview.2'))

    def test_proof_only_runs_as_explicit_main_dispatch(self):
        self.assertTrue(permitted('recover-preview2-gpu', recovery=True))
        self.assertFalse(permitted('recover-preview2-gpu'))
        self.assertFalse(permitted('recover-preview2-gpu', recovery=True, event='pull_request'))
        self.assertFalse(permitted('recover-preview2-gpu', recovery=True, ref='refs/heads/unreviewed'))

    def test_publish_requires_successful_full_recovery_and_owner(self):
        self.assertTrue(permitted('publish-preview2-recovery', recovery=True))
        for state in ['failure', 'cancelled', 'skipped']:
            self.assertFalse(permitted('publish-preview2-recovery', recovery=True, result=state))
        self.assertFalse(permitted('publish-preview2-recovery', recovery=True, cancelled=True))
        self.assertFalse(permitted('publish-preview2-recovery', recovery=True, user=''))
        self.assertFalse(permitted('publish-preview2-recovery', recovery=True, ref='refs/tags/v0.1.1-preview.2'))

    def test_normal_concurrency_identity_remains_exact_and_recovery_cannot_cancel_it(self):
        text = WORKFLOW.read_text()
        group = re.search(r'(?m)^  group: (.+)$', text)[1]
        def rendered(recovery):
            return re.sub(r'\$\{\{(.*?)\}\}', lambda m: str(evaluate(m[1], recovery=recovery)), group)
        self.assertEqual(rendered(False), 'build-refs/heads/main-gpu')
        self.assertEqual(rendered(True), 'preview2-artifact-recovery-123')
        cancel = re.search(r'(?m)^  cancel-in-progress: (.+)$', text)[1]
        self.assertIn('${{', cancel)
        self.assertFalse(evaluate(cancel.split('${{')[1].split('}}')[0], recovery=True))
        self.assertTrue(evaluate(cancel.split('${{')[1].split('}}')[0]))


if __name__ == '__main__':
    unittest.main()
