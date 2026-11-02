import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ABI = Path(__file__).resolve().parent / 'abi'
sys.path.insert(0, str(ABI))
spec = importlib.util.spec_from_file_location('mutation_isolation_probe', ABI / 'mutation_observation.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
sys.path.remove(str(ABI))


class MutationIsolationTests(unittest.TestCase):
    def test_a_crashed_case_with_a_partial_report_does_not_hide_later_controls(self):
        called = []

        def child(command, **_):
            mode = command[command.index('--isolated-case') + 1]
            called.append(mode)
            report = Path(command[command.index('--report') + 1])
            report.write_text('{' if len(called) == 1 else json.dumps({'assertions': 1}))
            return subprocess.CompletedProcess(command, 1 if len(called) == 1 else 0, '', '')

        with patch.object(probe.subprocess, 'run', side_effect=child):
            result, passed = probe.run_isolated('unused-private-runtime')
        self.assertFalse(passed)
        self.assertEqual(tuple(called), probe.ISOLATED_CASES)
        self.assertIn('report_error', result['cases'][0])
        self.assertEqual(result['assertions'], 6)

    def test_success_requires_every_isolated_case_to_return_its_report(self):
        def child(command, **_):
            report = Path(command[command.index('--report') + 1])
            report.write_text(json.dumps({'assertions': 1}))
            return subprocess.CompletedProcess(command, 0, '', '')

        with patch.object(probe.subprocess, 'run', side_effect=child):
            result, passed = probe.run_isolated('unused-private-runtime')
        self.assertTrue(passed)
        self.assertEqual(len(result['cases']), 7)
        self.assertEqual(result['assertions'], 7)


if __name__ == '__main__':
    unittest.main()
