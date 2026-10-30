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


if __name__ == '__main__':
    unittest.main()
