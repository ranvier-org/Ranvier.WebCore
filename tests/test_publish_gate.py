"""Check the actual tag publication expression against failed and skipped job outcomes."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


def permits_publish(native='success', prebuilt='skipped', managed='success', contract='success', flavor='', cancelled=False,
                    ref='refs/tags/v0.1.0-preview.14', owner='owner'):
    workflow = (ROOT / '.github/workflows/build.yml').read_text()
    job = workflow.split('\n  publish:\n', 1)[1]
    expression = job.split('if:', 1)[1].split('${{', 1)[1].split('}}', 1)[0]
    results = {'native': native, 'prebuilt': prebuilt, 'managed': managed, 'package-contract': contract}
    expression = re.sub(r'needs\.([a-z-]+)\.result', lambda match: repr(results[match[1]]), expression)
    for name, value in [('github.ref', ref), ('vars.NUGET_USER', owner), ('inputs.flavor', flavor)]:
        expression = expression.replace(name, repr(value))
    expression = expression.replace('!cancelled()', repr(not cancelled)).replace('&&', ' and ').replace('||', ' or ')
    return eval(' '.join(expression.split()), {'__builtins__': {}}, {'startsWith': lambda value, prefix: value.startswith(prefix)})


def permits_windows_gpu_cohort(native='success', prebuilt='skipped', publish='success', cancelled=False,
                               event='push', ref='refs/tags/v0.1.1-preview.2'):
    workflow = (ROOT / '.github/workflows/build.yml').read_text()
    job = workflow.split('\n  windows-gpu-cohort:\n', 1)[1]
    expression = job.split('if:', 1)[1].split('${{', 1)[1].split('}}', 1)[0]
    success = all(status == 'success' for status in [native, prebuilt, publish])
    # GitHub implicitly adds success() unless a status-check function is present in the actual condition.
    if not re.search(r'\b(?:success|failure|cancelled|always)\s*\(', expression):
        expression = 'success() && (' + expression + ')'
    for name, value in [('github.event_name', event), ('github.ref', ref), ('needs.publish.result', publish)]:
        expression = expression.replace(name, repr(value))
    expression = expression.replace('!cancelled()', repr(not cancelled)).replace('success()', repr(success))
    expression = expression.replace('&&', ' and ').replace('||', ' or ')
    return eval(' '.join(expression.split()), {'__builtins__': {}},
                {'startsWith': lambda value, prefix: value.startswith(prefix)})


class PublishGateTests(unittest.TestCase):
    def test_a_failed_runtime_cannot_publish_an_uploaded_package(self):
        self.assertFalse(permits_publish(native='failure', managed='skipped'))

    def test_every_selected_verification_and_contract_job_must_succeed(self):
        for status in ['failure', 'cancelled']:
            with self.subTest(status=status):
                self.assertFalse(permits_publish(prebuilt=status))
                self.assertFalse(permits_publish(contract=status))
                self.assertFalse(permits_publish(managed=status))
        self.assertFalse(permits_publish(native='skipped', prebuilt='skipped'))
        self.assertFalse(permits_publish(cancelled=True))
        self.assertFalse(permits_publish(ref='refs/heads/main'))
        self.assertFalse(permits_publish(owner=''))

    def test_full_slim_release_requires_the_managed_cohort(self):
        self.assertTrue(permits_publish())
        self.assertTrue(permits_publish(native='skipped', prebuilt='success'))
        self.assertTrue(permits_publish(prebuilt='success'))
        for flavor in ['', 'slim']:
            self.assertFalse(permits_publish(managed='skipped', flavor=flavor))

    def test_manual_gpu_and_lean_keep_the_selected_runtime_gate(self):
        for flavor in ['gpu', 'lean']:
            self.assertTrue(permits_publish(managed='skipped', flavor=flavor))
            self.assertFalse(permits_publish(native='failure', managed='skipped', flavor=flavor))

    def test_publication_waits_for_all_gate_dependencies(self):
        workflow = (ROOT / '.github/workflows/build.yml').read_text()
        job = workflow.split('\n  publish:\n', 1)[1]
        needs = re.search(r'^    needs: \[([^]]+)\]', job, re.MULTILINE)[1]
        self.assertEqual({name.strip() for name in needs.split(',')}, {'native', 'prebuilt', 'managed', 'package-contract'})
        self.assertIn('python -I tests/test_publish_gate.py', workflow)


class GpuCohortTests(unittest.TestCase):
    def test_successful_tag_publication_survives_the_skipped_optional_ancestor(self):
        for native, prebuilt in [('success', 'skipped'), ('skipped', 'success')]:
            with self.subTest(native=native, prebuilt=prebuilt):
                self.assertTrue(permits_windows_gpu_cohort(native=native, prebuilt=prebuilt))

    def test_gpu_recovery_dispatch_does_not_recurse_or_run_after_failed_publication(self):
        self.assertFalse(permits_windows_gpu_cohort(event='workflow_dispatch'))
        self.assertFalse(permits_windows_gpu_cohort(ref='refs/heads/main'))
        self.assertFalse(permits_windows_gpu_cohort(cancelled=True))
        for publish in ['failure', 'cancelled', 'skipped']:
            with self.subTest(publish=publish):
                self.assertFalse(permits_windows_gpu_cohort(publish=publish))

    def test_successful_version_tag_dispatches_only_the_matching_windows_gpu_cohort(self):
        workflow = (ROOT / '.github/workflows/build.yml').read_text()
        self.assertIn('\n  windows-gpu-cohort:\n', workflow)
        job = workflow.split('\n  windows-gpu-cohort:\n', 1)[1]
        self.assertIn('needs: publish', job)
        self.assertIn("github.event_name == 'push'", job)
        self.assertIn("startsWith(github.ref, 'refs/tags/v')", job)
        self.assertIn("needs.publish.result == 'success'", job)
        self.assertIn('actions: write', job)
        self.assertIn('--ref "$GITHUB_REF_NAME"', job)
        self.assertIn('--field flavor=gpu --field rids=win-x64', job)
        self.assertIn('GH_TOKEN: ${{ github.token }}', job)

    def test_flavor_runs_do_not_cancel_the_matching_slim_tag_run(self):
        workflow = (ROOT / '.github/workflows/build.yml').read_text()
        group = re.search(r'^  group: (.+)$', workflow, re.MULTILINE)[1]
        self.assertIn("inputs.flavor || 'slim'", group)
        self.assertIn('github.ref', group)


if __name__ == '__main__':
    unittest.main()
