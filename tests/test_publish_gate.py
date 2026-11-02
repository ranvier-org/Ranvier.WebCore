"""Check the actual tag publication expression against failed and skipped job outcomes."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


def permits_publish(native='success', prebuilt='skipped', managed='success', contract='success', flavor='', cancelled=False,
                    ref='refs/tags/v0.1.0-preview.14', owner='owner', diagnostic=False):
    workflow = (ROOT / '.github/workflows/build.yml').read_text()
    job = workflow.split('\n  publish:\n', 1)[1]
    expression = job.split('if:', 1)[1].split('${{', 1)[1].split('}}', 1)[0]
    results = {'native': native, 'prebuilt': prebuilt, 'managed': managed, 'package-contract': contract}
    expression = re.sub(r'needs\.([a-z-]+)\.result', lambda match: repr(results[match[1]]), expression)
    for name, value in [('github.ref', ref), ('vars.NUGET_USER', owner), ('inputs.flavor', flavor)]:
        expression = expression.replace(name, repr(value))
    expression = expression.replace('!inputs.diagnostic_d3d11', repr(not diagnostic))
    expression = expression.replace('!cancelled()', repr(not cancelled)).replace('&&', ' and ').replace('||', ' or ')
    return eval(' '.join(expression.split()), {'__builtins__': {}}, {'startsWith': lambda value, prefix: value.startswith(prefix)})


class PublishGateTests(unittest.TestCase):
    def test_diagnostic_cannot_publish_even_with_successful_release_dependencies(self):
        self.assertFalse(permits_publish(diagnostic=True))
        self.assertFalse(permits_publish(diagnostic=True, flavor='gpu', managed='skipped'))

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
    def test_diagnostic_concurrency_preserves_normal_groups_and_never_cancels_them(self):
        workflow = (ROOT / '.github/workflows/build.yml').read_text()
        expression = re.search(r'^  group: \$\{\{ (.+) \}\}$', workflow, re.MULTILINE)[1]
        for diagnostic in [False, True]:
            for flavor in ['', 'slim', 'gpu', 'lean']:
                values = {'inputs.diagnostic_d3d11': diagnostic, 'github.run_id': 123, 'github.workflow': 'build',
                          'github.ref': 'refs/heads/diagnostic', 'inputs.flavor': flavor}
                selected = expression
                for name, value in values.items():
                    selected = selected.replace(name, repr(value))
                selected = selected.replace('&&', ' and ').replace('||', ' or ')
                group = eval(selected, {'__builtins__': {}}, {'format': lambda value, *args: value.format(*args)})
                self.assertEqual(group, 'd3d11-diagnostic-123' if diagnostic else f'build-refs/heads/diagnostic-{flavor or "slim"}')
        self.assertIn('cancel-in-progress: ${{ !inputs.diagnostic_d3d11 }}', workflow)

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
