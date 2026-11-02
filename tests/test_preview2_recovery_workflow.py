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


def evaluate(expression, recovery=False, recovery4=False, result='success', event='workflow_dispatch', ref='refs/heads/main', user='owner', cancelled=False):
    values = {'inputs.recover_preview2_gpu': recovery, 'inputs.recover_preview4_gpu': recovery4, 'github.event_name': event, 'github.ref': ref,
              'github.workflow': 'build', 'github.run_id': 123, 'inputs.flavor': 'gpu', 'vars.NUGET_USER': user,
              'inputs.rids': '', 'github.head_ref': 'codex/batch-fixture',
              'github.event.pull_request.labels.*.name': [],
              'needs.plan.outputs.matrix': 'selected', 'needs.plan.outputs.prebuilt': 'attached',
              'needs.recover-preview2-gpu.result': result, 'needs.verify-preview4-gpu-recovery.result': result, 'needs.native.result': 'success',
              'needs.prebuilt.result': 'skipped', 'needs.managed.result': 'skipped',
              'needs.package-contract.result': 'success', 'needs.publish.result': 'success'}
    for key in sorted(values, key=len, reverse=True):
        expression = expression.replace(key, repr(values[key]))
    expression = expression.replace('!cancelled()', repr(not cancelled))
    expression = re.sub(r'!(?!=)', 'not ', expression)
    expression = expression.replace('&&', ' and ').replace('||', ' or ')
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
    def test_preview4_skips_all_other_jobs_and_requires_main(self):
        for name in ['plan', 'package-contract', 'native', 'prebuilt', 'managed', 'publish',
                     'windows-gpu-cohort', 'recover-preview2-gpu', 'publish-preview2-recovery']:
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
        for name in ['plan', 'package-contract', 'native', 'prebuilt', 'managed', 'publish', 'windows-gpu-cohort']:
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
