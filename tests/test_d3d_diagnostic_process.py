import ctypes
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest


SOURCE = Path(__file__).resolve().parent / 'gpu/d3d11_diagnostic_process.py'
spec = importlib.util.spec_from_file_location('d3d11_diagnostic_process', SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@unittest.skipUnless(sys.platform == 'win32', 'Windows taskkill consumer controller')
class DiagnosticProcessTests(unittest.TestCase):
    def test_timeout_ends_the_owned_child_tree_and_records_the_failure(self):
        code = '''import json,os,subprocess,sys,time
child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])
print(json.dumps({'parent':os.getpid(),'child':child.pid}),flush=True)
time.sleep(60)
'''
        events = []
        started = time.monotonic()
        with tempfile.TemporaryDirectory() as directory:
            result = module.bounded([sys.executable, '-u', '-c', code], cwd=directory, env=dict(os.environ), timeout=0.5, cleanup_timeout=2, events=events)
        self.assertLess(time.monotonic() - started, 8)
        self.assertEqual(result.returncode, 124)
        self.assertTrue(events[0]['timedOut'])
        self.assertTrue(events[0]['processEnded'])
        self.assertEqual(events[0]['treeCleanup']['exit'], 0)
        pids = json.loads(result.stdout.splitlines()[0])
        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        for pid in pids.values():
            handle = kernel.OpenProcess(0x1000, False, pid)
            if handle:
                try:
                    status = ctypes.c_uint32()
                    self.assertTrue(kernel.GetExitCodeProcess(handle, ctypes.byref(status)))
                    self.assertNotEqual(status.value, 259, 'owned child remains alive')
                finally:
                    kernel.CloseHandle(handle)


if __name__ == '__main__':
    unittest.main()
