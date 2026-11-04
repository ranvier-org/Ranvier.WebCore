import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/public-cocoa-contracts.yml'


def admission_script(text):
    start = text.index("python3 - <<'PY'\n") + len("python3 - <<'PY'\n")
    return textwrap.dedent(text[start:text.index('\n          PY\n', start)])


class PublicCocoaWorkflow(unittest.TestCase):
    def test_default_off_main_only_and_owner_phases_are_distinct(self):
        text = WORKFLOW.read_text()
        self.assertNotIn('  push:', text)
        self.assertIn('options: [off, collect-owner, replay]', text)
        self.assertIn('default: off', text)
        self.assertIn("github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'", text)
        self.assertIn("(data.get('ownerProofText') is None) != (os.environ['PHASE'] == 'collect-owner')", text)
        self.assertIn('\npermissions:\n  contents: read\n  actions: read\n\n', text)
        self.assertEqual(text.count('permissions:'), 1)
        self.assertNotIn('id-token:', text)
        for suffix in ('json', 'log', 'png', 'rgba'):
            self.assertIn('public-cocoa-contracts/**/*.' + suffix, text)

    def test_admission_arms_only_a_matching_phase_and_an_immutable_source(self):
        script = admission_script(WORKFLOW.read_text())
        source = 'c' * 40
        cases = [
            (dict(armed=False, ownerProofText=None), 'collect-owner', 'false', ''),
            (dict(armed='true', ownerProofText=None), 'collect-owner', 'false', ''),
            (dict(armed=True, ownerProofText=None), 'off', 'false', ''),
            (dict(armed=True, ownerProofText=None), 'collect-owner', 'true', source),
            (dict(armed=True, ownerProofText='{}'), 'replay', 'true', source),
            (dict(armed=True, ownerProofText='{}'), 'collect-owner', None, None),
            (dict(armed=True, ownerProofText=None), 'replay', None, None),
            (dict(armed=True, ownerProofText=None, source='C' * 40), 'collect-owner', None, None),
            (dict(armed=True, ownerProofText=None, source='main'), 'collect-owner', None, None),
        ]
        for data, phase, armed, expected_source in cases:
            with self.subTest(data=data, phase=phase), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / 'tests/controls').mkdir(parents=True)
                inputs = dict(data, policy=dict(controllerSource=data.pop('source', source)))
                (root / 'tests/controls/public_cocoa_replay_inputs.json').write_text(json.dumps(inputs))
                output = root / 'github-output'
                result = subprocess.run([sys.executable, '-I', '-c', script], cwd=root, capture_output=True, text=True,
                                        env=dict(os.environ, PHASE=phase, GITHUB_OUTPUT=str(output)))
                if armed is None:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(output.exists() and 'armed=true' in output.read_text())
                else:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(output.read_text(), f'armed={armed}\nsource={expected_source}\n')


if __name__ == '__main__':
    unittest.main()
