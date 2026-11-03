import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import os


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('producer_gpu_clipping', ROOT/'scripts/qualify_producer_gpu_clipping.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class ProducerGpuClippingTests(unittest.TestCase):
    def report(self):
        fixture = json.loads((ROOT/'tests/fixtures/background-content-clip-cases.json').read_text())
        rows = [{'name':case['name'], 'scale':scale, 'strictFixedCase':case['name'] in gate.FIXED,
                 'contentMaskDifference':0, 'worsePixels':[], 'qualifiedHalfCoveragePixels':[],
                 'unexplainedWorsePixels':[]} for scale in fixture['scales'] for case in fixture['cases']]
        return {'result':'PASS','rid':'win-x64','flavor':'gpu','completeKeys':54,'strictContentMaskKeys':12,'results':rows,'failures':[]}

    def test_all_unchanged_controls_pass_without_requiring_historical_red(self):
        result = gate.check_original(self.report(), 'win-x64')
        self.assertEqual((result['strictPass'],result['otherPass']), (12,52))

    def test_only_two_known_promoted_failures_can_use_the_model(self):
        report = self.report()
        for row in report['results']:
            if (row['name'],row['scale']) in gate.PROMOTED:
                row['unexplainedWorsePixels'] = [4]
                row['worsePixels'] = [4]
                report['failures'].append(row)
        report['result'] = 'FAIL'
        self.assertEqual(gate.check_original(report,'win-x64')['originalFailureCount'],2)
        report['results'][0]['unexplainedWorsePixels'] = [4]
        with self.assertRaises(AssertionError): gate.check_original(report,'win-x64')

    def test_missing_duplicate_and_strict_failure_are_rejected(self):
        for change in ['missing','duplicate','strict']:
            report = self.report()
            if change == 'missing': report['results'].pop()
            elif change == 'duplicate': report['results'][-1] = report['results'][0].copy()
            else: report['results'][0]['contentMaskDifference'] = 1
            with self.assertRaises(AssertionError): gate.check_original(report,'win-x64')

    def test_half_coverage_policy_cannot_spread_to_another_case_or_linux(self):
        report = self.report()
        row = next(row for row in report['results'] if row['name']=='composited-translate' and row['scale']==1)
        row['worsePixels'] = row['qualifiedHalfCoveragePixels'] = [3]
        gate.check_original(report,'win-x64')
        report['rid'] = 'linux-x64'
        with self.assertRaises(AssertionError): gate.check_original(report,'linux-x64')
        report['rid'] = 'win-x64'
        row['scale'] = 1.5
        with self.assertRaises(AssertionError): gate.check_original(report,'win-x64')

    def test_unknown_driver_and_precision_change_are_rejected(self):
        profiles = json.loads((ROOT/'tests/gpu/clipping-profiles.json').read_text())
        actual = profiles['windows'][0]['profile']
        self.assertEqual(gate.check_profile(actual,'win-x64'),profiles['windows'][0]['name'])
        unknown = dict(actual,renderer=actual['renderer']+' changed')
        with self.assertRaises(AssertionError): gate.check_profile(unknown,'win-x64')
        precision = json.loads(json.dumps(actual))
        precision['shaderPrecision']['fragment']['high']['fractionBits'] = 10
        with self.assertRaises(AssertionError): gate.check_profile(precision,'win-x64')

    def test_manifest_binds_current_inputs_without_a_p7_package_hash(self):
        import hashlib
        with tempfile.TemporaryDirectory() as directory:
            native = Path(directory)/'native'; native.mkdir()
            payload = native/'current.so'; payload.write_bytes(b'new producer')
            manifest = {'abi':63,'rid':'linux-x64','flavor':'gpu','webkit':gate.WEBKIT,
                        'source':{'commit':'a'*40,'dirty':False,'builder':'ci'},
                        'files':[{'name':'current.so','bytes':len(payload.read_bytes()),
                                  'sha256':hashlib.sha256(payload.read_bytes()).hexdigest()}]}
            self.assertEqual(gate.check_stage(native,manifest,'linux-x64',63,'a'*40)['current.so'],manifest['files'][0]['sha256'])
            with self.assertRaises(AssertionError): gate.check_stage(native,manifest,'linux-x64',63,'b'*40)
            payload.write_bytes(b'changed')
            with self.assertRaises(AssertionError): gate.check_stage(native,manifest,'linux-x64',63,'a'*40)

    def test_manifest_unknown_webkit_abi_or_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            native = Path(directory)
            for field, value in [('webkit','f'*40),('abi',64),('files',[{'name':'../escape','bytes':0,'sha256':'a'*64}])]:
                manifest = {'abi':63,'rid':'linux-x64','flavor':'gpu','webkit':gate.WEBKIT,
                            'source':{'commit':'a'*40,'dirty':False,'builder':'ci'},'files':[]}
                manifest[field] = value
                with self.assertRaises(AssertionError): gate.check_stage(native,manifest,'linux-x64',63,'a'*40)

    def test_owned_process_memory_census_includes_a_live_child(self):
        import subprocess
        import sys
        before = gate.aggregate_memory()
        child = subprocess.Popen([sys.executable,'-c',
                                  'import time; data=bytearray(8*1024*1024); data[::4096]=b"x"*(len(data)//4096); print("ready",flush=True); time.sleep(5)'],
                                 stdout=subprocess.PIPE,text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(),'ready')
            self.assertGreater(gate.aggregate_memory(),before+8*1024*1024)
        finally:
            child.terminate(); child.wait(timeout=5); child.stdout.close()

    @unittest.skipUnless(os.name == 'nt', 'Windows job-object ownership')
    def test_timeout_closes_the_owned_child_and_its_spawned_descendant(self):
        import ctypes
        from ctypes import wintypes as W
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory)/'descendant.py'
            script.write_text('import subprocess,sys,time\nchild=subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"])\nprint(child.pid,flush=True)\ntime.sleep(30)\n',encoding='utf-8')
            owner = gate.OwnedChild([sys.executable,'-I',str(script)],subprocess.PIPE,os.environ.copy(),ROOT)
            kernel = ctypes.WinDLL('kernel32',use_last_error=True)
            kernel.OpenProcess.argtypes,kernel.OpenProcess.restype = [W.DWORD,W.BOOL,W.DWORD],W.HANDLE
            kernel.WaitForSingleObject.argtypes,kernel.WaitForSingleObject.restype = [W.HANDLE,W.DWORD],W.DWORD
            kernel.CloseHandle.argtypes = [W.HANDLE]
            descendant_handle = None
            try:
                descendant_pid = int(owner.process.stdout.readline().strip())
                descendant_handle = kernel.OpenProcess(0x00100000|0x1000,False,descendant_pid)
                self.assertTrue(descendant_handle)
                self.assertEqual(kernel.WaitForSingleObject(descendant_handle,0),258)
                with self.assertRaises(subprocess.TimeoutExpired): owner.process.wait(timeout=.15)
                owner.close()
                self.assertIsNotNone(owner.process.returncode)
                self.assertEqual(kernel.WaitForSingleObject(descendant_handle,5000),0)
                if os.environ.get('RANVIER_GPU_JOB_TEST_RECEIPT'):
                    receipt = Path(os.environ['RANVIER_GPU_JOB_TEST_RECEIPT'])
                    receipt.parent.mkdir(parents=True,exist_ok=True)
                    temporary = receipt.with_suffix('.tmp')
                    temporary.write_text(json.dumps({'mainPid':owner.process.pid,'descendantPid':descendant_pid,
                                                     'timeoutObserved':True,'mainExit':owner.process.returncode,
                                                     'descendantHandleSignalled':True,'ownedJobClosed':True},indent=2)+'\n',encoding='utf-8')
                    temporary.replace(receipt)
            finally:
                owner.close()
                owner.process.stdout.close()
                if descendant_handle: kernel.CloseHandle(descendant_handle)

    @unittest.skipUnless(os.name == 'nt', 'Windows isolated bootstrap')
    def test_job_bootstrap_restores_the_normal_isolated_global_site(self):
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory)/'site_probe.py'
            script.write_text('import json,sys,pip\nprint(json.dumps({"path":sys.path,"isolated":sys.flags.isolated,"pip":pip.__version__}))\n',encoding='utf-8')
            expected = json.loads(subprocess.check_output([sys.executable,'-I',str(script)],text=True))
            owner = gate.OwnedChild([sys.executable,'-I',str(script)],subprocess.PIPE,os.environ.copy(),ROOT)
            try:
                actual = json.loads(owner.process.stdout.read())
                self.assertEqual(owner.process.wait(timeout=5),0)
                self.assertEqual(actual,expected)
            finally:
                owner.close(); owner.process.stdout.close()


if __name__ == '__main__': unittest.main()
