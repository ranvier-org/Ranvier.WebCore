from pathlib import Path
import importlib.util
import subprocess
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location('owner_exit', Path(__file__).parent / 'abi/owner_thread_exit.py')
control = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(control)
OUTPUT = '\n'.join(('AFTER_NATIVE_HOST_DESTROY', 'AFTER_COM_UNINITIALIZE',
                    'OWNER_FUNCTION_RETURNING', 'OWNER_THREAD_JOINED', 'PROCESS_MAIN_RETURNING result=0'))


class OwnerThreadExitTests(unittest.TestCase):
    def run_mode(self, code=0, output=OUTPUT, mode='worker-none'):
        with patch.object(control.subprocess, 'run', return_value=subprocess.CompletedProcess([], code, output, '')):
            return control.run_control(Path('control.exe'), Path('host.dll'), mode, {})

    def test_failfast_after_all_cleanup_markers_is_still_failure(self):
        row = self.run_mode(code=0xc0000409)
        self.assertFalse(row['passed'])
        self.assertEqual(row['hexExit'], '0xc0000409')

    def test_success_requires_worker_join_and_process_return(self):
        self.assertTrue(self.run_mode()['passed'])
        self.assertFalse(self.run_mode(output=OUTPUT.replace('OWNER_THREAD_JOINED', ''))['passed'])
        self.assertFalse(self.run_mode(output=OUTPUT.replace('PROCESS_MAIN_RETURNING result=0', ''))['passed'])
        self.assertTrue(self.run_mode(output=OUTPUT.replace('OWNER_THREAD_JOINED', ''), mode='main-none')['passed'])

    def test_timeout_keeps_partial_native_output_and_fails(self):
        with patch.object(control.subprocess, 'run', side_effect=subprocess.TimeoutExpired([], 20, output=b'AFTER_NATIVE_HOST_DESTROY')):
            row = control.run_control(Path('control.exe'), Path('host.dll'), 'worker-sta', {})
        self.assertTrue(row['timeout'])
        self.assertFalse(row['passed'])
        self.assertIn('AFTER_NATIVE_HOST_DESTROY', row['output'])


if __name__ == '__main__':
    unittest.main()
