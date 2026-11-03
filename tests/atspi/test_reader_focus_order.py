import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

script = Path(__file__).with_name('reader_focus_order.py')
focus = "EVENT MANAGER: object:state-changed:focused for [entry: 'Travel note'] (1, 0,)"
caret = "EVENT MANAGER: object:text-caret-moved for [entry: 'Travel note'] (12, 0,)"
speech = "SPEECH OUTPUT: 'Travel note text'"


class ReaderOracleTests(unittest.TestCase):
    def run_log(self, lines):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'orca.log'
            path.write_text('\n'.join(lines), encoding='utf8')
            result = subprocess.run([sys.executable, str(script), str(path), '--label', 'Travel note'], capture_output=True, text=True)
            return result.returncode, json.loads(result.stdout)

    def test_focused_then_caret_and_speech_passes(self):
        code, report = self.run_log([focus, caret, speech])
        self.assertEqual(code, 0)
        self.assertTrue(report['focusBeforeCaret'] and report['labelSpoken'])

    def test_missing_caret_fails_even_with_focus_and_speech(self):
        code, report = self.run_log([focus, speech])
        self.assertEqual(code, 1)
        self.assertFalse(report['focusBeforeCaret'])

    def test_caret_before_focus_fails(self):
        code, report = self.run_log([caret, focus, speech])
        self.assertEqual(code, 1)
        self.assertFalse(report['focusBeforeCaret'])


if __name__ == '__main__':
    unittest.main()
