import ast
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


class SidecarGroupOwnership(unittest.TestCase):
    def runner(self, output, receipt):
        tree = ast.parse((ROOT / 'tests/controls/build_cocoa_sidecars.py').read_text())
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
        function = next(node for node in main.body if isinstance(node, ast.FunctionDef) and node.name == 'run')
        namespace = dict(output=output, receipt=receipt, os=os, subprocess=subprocess, signal=signal)
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'actual-sidecar-run', 'exec'), namespace)
        return namespace['run']

    def test_standalone_requests_group_termination_and_reaps_its_child(self):
        with tempfile.TemporaryDirectory() as directory:
            receipt = dict(commands=[])
            child = Mock(pid=123456)
            child.wait.return_value = 0
            with patch.dict(os.environ, {'RANVIER_COCOA_OWNED_GROUP': ''}), \
                    patch.object(subprocess, 'Popen', return_value=child) as popen, \
                    patch.object(os, 'killpg', create=True) as killpg, patch.object(signal, 'SIGKILL', 9, create=True):
                self.runner(Path(directory), receipt)('fixture', ['not-executed'])
            self.assertTrue(popen.call_args.kwargs['start_new_session'])
            killpg.assert_called_once_with(123456, 9)
            self.assertTrue(receipt['commands'][0]['ownsProcessGroup'])
            self.assertTrue(receipt['commands'][0]['processGroupKillRequested'])
            self.assertNotIn('processGroupReaped', receipt['commands'][0])
            self.assertTrue(receipt['commands'][0]['childReaped'])

    def test_inherited_group_timeout_kills_only_child_and_leaves_group_to_outer_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            receipt = dict(commands=[])
            child = Mock(pid=123456)
            child.wait.side_effect = [subprocess.TimeoutExpired('fixture', 300), -9]
            child.poll.return_value = None
            with patch.dict(os.environ, {'RANVIER_COCOA_OWNED_GROUP': '1'}), \
                    patch.object(subprocess, 'Popen', return_value=child) as popen, \
                    patch.object(os, 'killpg', create=True) as killpg:
                with self.assertRaises(subprocess.TimeoutExpired):
                    self.runner(Path(directory), receipt)('fixture', ['not-executed'])
            self.assertFalse(popen.call_args.kwargs['start_new_session'])
            self.assertEqual(popen.call_args.kwargs['env']['RANVIER_COCOA_OWNED_GROUP'], '1')
            killpg.assert_not_called()
            child.kill.assert_called_once_with()
            self.assertTrue(receipt['commands'][0]['childReaped'])
            self.assertFalse(receipt['commands'][0]['ownsProcessGroup'])
            self.assertNotIn('processGroupReaped', receipt['commands'][0])


if __name__ == '__main__':
    unittest.main()
