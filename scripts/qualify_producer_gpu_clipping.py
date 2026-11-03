"""Qualify a producer's staged GPU paint using reviewed renderer-specific contracts."""
import argparse
import base64
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import signal
import zlib


ROOT = Path(__file__).resolve().parents[1]
WEBKIT = 'b95c91b1c0ee43cc86d25ff7af73038f67a88e04'
FIXED = {'bordered-half-phase','negative-origin','nested-offset','always-composited'}
PROMOTED = {('composited-translate',1.5),('composited-translate',2)}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    temporary.replace(path)


def check_stage(native, manifest, rid, expected_abi, expected_source):
    assert (manifest['rid'],manifest['flavor'],manifest['abi']) == (rid,'gpu',expected_abi)
    assert manifest['webkit'] == WEBKIT, 'Unqualified WebKit source contract'
    assert manifest['source']['dirty'] is False
    assert len(manifest['source']['commit']) == 40 and all(c in '0123456789abcdef' for c in manifest['source']['commit'])
    assert manifest['source']['commit'] == expected_source, 'Native stage does not match producer checkout HEAD'
    assert manifest['files'], 'Empty native manifest'
    hashes = {}
    for row in manifest['files']:
        path = (native/row['name']).resolve()
        assert path.is_relative_to(native.resolve()) and path != native.resolve()
        assert row['name'] not in hashes
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
        hashes[row['name']] = row['sha256']
    assert {p.relative_to(native).as_posix() for p in native.rglob('*') if p.is_file()} == set(hashes)
    return hashes


def check_profile(actual, rid):
    assert rid in ['win-x64','linux-x64']
    profiles = json.loads((ROOT/'tests/gpu/clipping-profiles.json').read_text())
    for row in profiles['windows' if rid == 'win-x64' else 'linux']:
        if all(actual.get(key) == value for key,value in row['profile'].items()):
            return row['name']
    raise AssertionError('Unqualified actual GPU profile: '+json.dumps(actual))


def check_original(report, rid):
    assert report['rid'] == rid and report['flavor'] == 'gpu'
    fixture = json.loads((ROOT/'tests/fixtures/background-content-clip-cases.json').read_text())
    expected = {(case['name'],scale) for case in fixture['cases'] for scale in fixture['scales']}
    rows = {(row['name'],row['scale']):row for row in report['results']}
    assert len(rows) == len(report['results']) == len(expected) == report['completeKeys'] == 54
    assert set(rows) == expected
    strict = [row for row in rows.values() if row['strictFixedCase']]
    assert len(strict) == report['strictContentMaskKeys'] == 12
    assert all(row['strictFixedCase'] == (row['name'] in FIXED) for row in rows.values())
    actual_failures = set()
    half_rows = []
    for key,row in rows.items():
        if row['strictFixedCase']: assert row['contentMaskDifference'] == 0
        if row['unexplainedWorsePixels'] or (row['strictFixedCase'] and row['contentMaskDifference']):
            actual_failures.add(key)
        if row['qualifiedHalfCoveragePixels']:
            assert rid == 'win-x64' and key == ('composited-translate',1)
            assert set(row['worsePixels']) == set(row['qualifiedHalfCoveragePixels']) and not row['unexplainedWorsePixels']
            half_rows.append({'name':row['name'],'scale':row['scale'],'pixels':len(row['qualifiedHalfCoveragePixels'])})
    assert actual_failures <= PROMOTED
    assert len(report['failures']) == len(actual_failures)
    assert {(row['name'],row['scale']) for row in report['failures']} == actual_failures
    assert report['result'] == ('FAIL' if actual_failures else 'PASS')
    return {'strictPass':12,'otherPass':52,'originalFailureCount':len(actual_failures),'dpr1ExistingPolicy':half_rows}


class WindowsJob:
    def __init__(self):
        from ctypes import wintypes as W
        class Limits(ctypes.Structure):
            _fields_ = [('processTime',ctypes.c_longlong),('jobTime',ctypes.c_longlong),('flags',W.DWORD),
                        ('minimumWorking',ctypes.c_size_t),('maximumWorking',ctypes.c_size_t),
                        ('activeLimit',W.DWORD),('affinity',ctypes.c_size_t),('priority',W.DWORD),('scheduling',W.DWORD)]
        class Io(ctypes.Structure):
            _fields_ = [(name,ctypes.c_ulonglong) for name in ['readOps','writeOps','otherOps','readBytes','writeBytes','otherBytes']]
        class Extended(ctypes.Structure):
            _fields_ = [('basic',Limits),('io',Io),('processMemory',ctypes.c_size_t),('jobMemory',ctypes.c_size_t),
                        ('peakProcessMemory',ctypes.c_size_t),('peakJobMemory',ctypes.c_size_t)]
        class Accounting(ctypes.Structure):
            _fields_ = [(name,ctypes.c_longlong) for name in ['user','kernel','periodUser','periodKernel']]+[
                (name,W.DWORD) for name in ['faults','total','active','terminated']]
        self.accounting = Accounting
        self.kernel = ctypes.WinDLL('kernel32',use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes,self.kernel.CreateJobObjectW.restype = [ctypes.c_void_p,W.LPCWSTR],W.HANDLE
        self.kernel.SetInformationJobObject.argtypes,self.kernel.SetInformationJobObject.restype = [W.HANDLE,ctypes.c_int,ctypes.c_void_p,W.DWORD],W.BOOL
        self.kernel.AssignProcessToJobObject.argtypes,self.kernel.AssignProcessToJobObject.restype = [W.HANDLE,W.HANDLE],W.BOOL
        self.kernel.TerminateJobObject.argtypes,self.kernel.TerminateJobObject.restype = [W.HANDLE,W.UINT],W.BOOL
        self.kernel.QueryInformationJobObject.argtypes,self.kernel.QueryInformationJobObject.restype = [W.HANDLE,ctypes.c_int,ctypes.c_void_p,W.DWORD,ctypes.c_void_p],W.BOOL
        self.kernel.CloseHandle.argtypes = [W.HANDLE]
        self.handle = self.kernel.CreateJobObjectW(None,None)
        if not self.handle: raise ctypes.WinError(ctypes.get_last_error())
        limits = Extended()
        limits.basic.flags = 0x2000|0x200
        limits.jobMemory = 8*1024**3
        if not self.kernel.SetInformationJobObject(self.handle,9,ctypes.byref(limits),ctypes.sizeof(limits)):
            error = ctypes.get_last_error(); self.kernel.CloseHandle(self.handle); self.handle = None
            raise ctypes.WinError(error)

    def attach(self,process):
        # The live Popen handle avoids assigning a reused PID.
        if not self.kernel.AssignProcessToJobObject(self.handle,int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if not self.handle: return
        try:
            if not self.kernel.TerminateJobObject(self.handle,1): raise ctypes.WinError(ctypes.get_last_error())
            deadline = time.monotonic()+5
            while True:
                info = self.accounting()
                if not self.kernel.QueryInformationJobObject(self.handle,1,ctypes.byref(info),ctypes.sizeof(info),None):
                    raise ctypes.WinError(ctypes.get_last_error())
                if not info.active: break
                assert time.monotonic() < deadline, 'Owned Windows job did not empty after termination'
                time.sleep(.01)
        finally:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


class OwnedChild:
    def __init__(self,command,log,environment,cwd):
        self.process = None
        self.job = None
        self.launch_command = command
        if os.name == 'nt':
            assert command[:2] == [sys.executable,'-I'], 'Windows probe must use the isolated Python entry point'
            self.job = WindowsJob()
            bootstrap = ('import sys; '
                         'assert sys.stdin.buffer.read(1)==b"G", "Missing parent job admission"; '
                         'import site; site.main(); import runpy; '
                         'sys.argv=sys.argv[1:]; runpy.run_path(sys.argv[0],run_name="__main__")')
            self.launch_command = [sys.executable,'-I','-S','-c',bootstrap,*command[2:]]
        try:
            options = {'creationflags':subprocess.CREATE_NEW_PROCESS_GROUP} if self.job else {'start_new_session':True}
            self.process = subprocess.Popen(self.launch_command,stdout=log,stderr=subprocess.STDOUT,
                                            stdin=subprocess.PIPE if self.job else subprocess.DEVNULL,
                                            env=environment,cwd=cwd,**options)
            if self.job:
                self.job.attach(self.process)
                self.process.stdin.write(b'G'); self.process.stdin.flush(); self.process.stdin.close()
        except BaseException:
            self.close()
            raise

    def close(self):
        try:
            if self.job: self.job.close()
            elif self.process:
                try: os.killpg(self.process.pid,signal.SIGKILL)
                except ProcessLookupError: pass
        finally:
            if self.process:
                if self.process.poll() is None: self.process.kill()
                self.process.wait(timeout=5)
                if self.process.stdin and not self.process.stdin.closed: self.process.stdin.close()


def aggregate_memory():
    records = {}
    if os.name == 'nt':
        from ctypes import wintypes as W
        class Entry(ctypes.Structure):
            _fields_ = [('size',W.DWORD),('usage',W.DWORD),('pid',W.DWORD),('heap',ctypes.c_size_t),
                        ('module',W.DWORD),('threads',W.DWORD),('parent',W.DWORD),('priority',W.LONG),
                        ('flags',W.DWORD),('exe',W.WCHAR*260)]
        class Counters(ctypes.Structure):
            _fields_ = [('size',W.DWORD),('faults',W.DWORD),*[(name,ctypes.c_size_t) for name in
                        ['peakWorking','working','peakPaged','paged','peakNonpaged','nonpaged','pagefile','peakPagefile','private']]]
        kernel = ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateToolhelp32Snapshot.argtypes,kernel.CreateToolhelp32Snapshot.restype = [W.DWORD,W.DWORD],W.HANDLE
        kernel.Process32FirstW.argtypes = kernel.Process32NextW.argtypes = [W.HANDLE,ctypes.POINTER(Entry)]
        kernel.OpenProcess.argtypes,kernel.OpenProcess.restype = [W.DWORD,W.BOOL,W.DWORD],W.HANDLE
        kernel.CloseHandle.argtypes = [W.HANDLE]
        memory = ctypes.WinDLL('psapi',use_last_error=True).GetProcessMemoryInfo
        memory.argtypes,memory.restype = [W.HANDLE,ctypes.POINTER(Counters),W.DWORD],W.BOOL
        snapshot = kernel.CreateToolhelp32Snapshot(2,0)
        assert snapshot not in (None,ctypes.c_void_p(-1).value)
        entry = Entry(); entry.size = ctypes.sizeof(entry)
        try:
            present = kernel.Process32FirstW(snapshot,ctypes.byref(entry))
            while present:
                records[entry.pid] = (entry.parent,0)
                present = kernel.Process32NextW(snapshot,ctypes.byref(entry))
        finally: kernel.CloseHandle(snapshot)
    else:
        for path in Path('/proc').iterdir():
            if not path.name.isdigit(): continue
            try:
                text = (path/'stat').read_text(); fields = text[text.rfind(')')+2:].split()
                records[int(path.name)] = (int(fields[1]),int(fields[21])*os.sysconf('SC_PAGE_SIZE'))
            except (FileNotFoundError,ProcessLookupError,PermissionError): pass
    selected = {os.getpid()}
    while True:
        expanded = selected | {pid for pid,(parent,_) in records.items() if parent in selected}
        if expanded == selected: break
        selected = expanded
    if os.name == 'nt':
        for pid in selected:
            handle = kernel.OpenProcess(0x0400|0x0010,False,pid)
            if not handle:
                assert ctypes.get_last_error() == 87, 'Cannot inspect owned process memory'
                continue
            try:
                counters = Counters(); counters.size = ctypes.sizeof(counters)
                assert memory(handle,ctypes.byref(counters),counters.size)
                records[pid] = (records[pid][0],counters.private)
            finally: kernel.CloseHandle(handle)
    return sum(records[pid][1] for pid in selected if pid in records)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory',type=Path,required=True)
    parser.add_argument('--rid',choices=['win-x64','linux-x64'],required=True)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    native = args.native_directory.resolve()
    output = args.output.resolve()
    assert not output.is_relative_to(native) and not args.report.resolve().is_relative_to(native), 'Evidence must stay outside native inputs'
    output.mkdir(parents=True,exist_ok=False)
    manifest_path = native.parents[2]/'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    sys.path.insert(0,str(ROOT/'tests/abi'))
    from form_collections import ABI
    source_command = ['git','-C',str(ROOT),'rev-parse','HEAD']
    expected_source = subprocess.check_output(source_command,text=True).strip()
    assert not subprocess.check_output(['git','-C',str(ROOT),'status','--porcelain','--untracked-files=no'],text=True).strip(), 'Producer tracked checkout is dirty'
    before = check_stage(native,manifest,args.rid,ABI,expected_source)
    receipt = {'result':'RUNNING','rid':args.rid,'manifest':manifest,'manifestSha256':sha(manifest_path),
               'nativeBefore':before,'commands':[],'sourceInputs':{},'producerCheckoutHead':expected_source,
               'guard':{'aggregateBytes':8*1024**3,'seconds':540,'sampleSeconds':.05,
                        'memoryMetric':'private commit' if os.name == 'nt' else 'RSS'}}
    receipt['historicalCrossDraw'] = json.loads((ROOT/'tests/p7_gpu_qualification/sampler-format-premises.json').read_text())['historical']
    paths = [ROOT/'scripts/qualify_producer_gpu_clipping.py',ROOT/'tests/abi/background_content_clip_regression.py',
             ROOT/'tests/gpu/producer_clipping_capture.py',ROOT/'tests/gpu/clipping-profiles.json']
    paths.extend(ROOT/'tests/abi'/name for name in ['background_content_clip_capture.py','resize_observation.py',
                                                   'form_collections.py','utf8_inputs.py'])
    paths.extend(ROOT/'tests/fixtures'/name for name in ['background-content-clip-cases.json','background-content-clip-oracle.json'])
    paths.extend(p for p in (ROOT/'tests/fixtures/background-content-clip-baselines').rglob('*') if p.is_file())
    for directory in ['tests/p7_gpu_qualification','tests/diagnostics/p7_profile']:
        paths.extend(p for p in (ROOT/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    receipt['sourceInputs'] = {p.relative_to(ROOT).as_posix():sha(p) for p in paths}
    started = time.monotonic()
    env = os.environ.copy()
    for key in ['LD_PRELOAD','GALLIVM_DEBUG','RANVIER_DIAGNOSTIC_TEXTURE_MODEL']: env.pop(key,None)
    if args.rid == 'linux-x64':
        env.update(EGL_PLATFORM='surfaceless',LIBGL_ALWAYS_SOFTWARE='1',MESA_SHADER_CACHE_DISABLE='true',
                   MESA_SHADER_CACHE_DIR=str(output/'shader-cache'),
                   FONTCONFIG_FILE=str(ROOT/'tests/fixtures/background-content-clip-baselines/linux-fonts.conf'))

    def run(command,name,expected=0,child_env=None,timeout=180):
        selected_env = child_env or env
        record = {'argv':command,'expectedExit':expected,'environment':{key:selected_env.get(key) for key in
                  ['EGL_PLATFORM','LIBGL_ALWAYS_SOFTWARE','LD_PRELOAD','GALLIVM_DEBUG','MESA_SHADER_CACHE_DISABLE',
                   'MESA_SHADER_CACHE_DIR','FONTCONFIG_FILE','RV_GL_PROFILE_PATH']}}
        receipt['commands'].append(record)
        peak = 0
        at = time.monotonic()
        with (output/(name+'.log')).open('wb') as log:
            owner = OwnedChild(command,log,selected_env,ROOT)
            process = owner.process
            record['pid'] = process.pid
            record['actualLaunchArgv'] = owner.launch_command
            record['cleanup'] = 'owned Windows job kill-on-close; probe body admitted after assignment' if owner.job else 'owned POSIX process group'
            try:
                while process.poll() is None:
                    peak = max(peak,aggregate_memory())
                    assert peak <= 8*1024**3, 'Aggregate GPU probe memory limit'
                    assert time.monotonic()-started <= 540 and time.monotonic()-at <= timeout, 'GPU probe timeout'
                    time.sleep(.05)
            finally:
                failure = sys.exc_info()[1]
                if failure is not None: record.update(failureType=type(failure).__name__,failure=str(failure))
                owner.close()
                record.update(exit=process.returncode,peakAggregateBytes=peak,seconds=time.monotonic()-at)
                save(output/'receipt.json',receipt)
        assert process.returncode == expected, (name,process.returncode,expected)

    try:
        import numpy
        receipt['numpyVersion'] = numpy.__version__
        receipt['pythonVersion'] = sys.version
        assert numpy.__version__ == '2.4.3'
        run([sys.executable,'-I',str(ROOT/'tests/gpu/producer_clipping_capture.py'),
             '--native-directory',str(native),'--rid',args.rid,'--report',str(args.report),
             '--profile',str(output/'capture-profile.json')],'original')
        original = json.loads(args.report.read_text())
        receipt['original'] = check_original(original,args.rid)
        receipt['originalReportSha256'] = sha(args.report)
        for row in original['results']:
            raw = zlib.decompress(base64.b64decode(row['rgbaZlibBase64']))
            assert len(raw) == int(800*row['scale'])*int(600*row['scale'])*4
            assert hashlib.sha256(raw).hexdigest() == row['rgbaSha256']
        receipt['allRawCasesBound'] = 54
        capture = {'results':[dict(row,width=int(800*row['scale']),height=int(600*row['scale'])) for row in original['results']]}
        save(output/'capture.json',capture)
        capture_profile = json.loads((output/'capture-profile.json').read_text())
        if args.rid == 'win-x64':
            policy = ROOT/'tests/p7_gpu_qualification'
            run([sys.executable,'-I',str(policy/'vertex-precision-probe.py'),
                 '--native-directory',str(native),'--output',str(output)],'precision')
            precision = json.loads((output/'vertex-fragment-precision.json').read_text())
            receipt['profileName'] = check_profile(precision,args.rid)
            assert all(precision[key] == capture_profile[key] for key in ['renderer','version','vendor'])
            run([sys.executable,'-I',str(policy/'sampler_format_probe.py'),
                 '--native-directory',str(native),'--output',str(output)],'sampler')
            sampler = json.loads((output/'sampler-format-probe.json').read_text())
            assert sampler['runtimeBefore'] == precision['runtime'] == before
            assert sampler['runtimeUnchanged'] and precision['nativeUnchanged']
            assert sampler['renderer'] == precision['renderer'] and sampler['policy']['completePatterns']
            assert sampler['policy']['samplesPerDestination'] == 1048576 and sampler['policy']['result'] == 'PASS'
            assert sampler['controlsPass'] and sampler['negativeControlsPass']
            receipt['samplerPolicy'] = sampler['policy']
            inputs = json.loads((policy/'gpu-model-inputs-v2.json').read_text())
            inputs['shaderPrecision'] = precision
            inputs['gpu'].update({key:precision[key] for key in ['renderer','vendor','version']})
            for name in ['low','medium','high']:
                item = precision['shaderPrecision']['fragment'][name]
                inputs['gpu']['fragment'+name.title()+'Float'] = {'range':item['range'],'precision':item['fractionBits']}
            model_script = policy/'gpu_pixel_gate_v3.py'
            old_cpu = policy/'baseline-a9.json'
        else:
            policy = ROOT/'tests/diagnostics/p7_profile'
            helper = output/'egl_profile.so'
            run(['cc','-shared','-fPIC','-std=c17','-O2','-Wall','-Wextra','-Werror',str(policy/'egl_profile.c'),'-ldl','-o',str(helper)],'compile-profile',timeout=60)
            profiled_env = dict(env,GALLIVM_DEBUG='ir',RV_GL_PROFILE_PATH=str(output/'profile.jsonl'))
            for kind in ['plain','profile']:
                child_env = dict(profiled_env)
                if kind == 'profile': child_env['LD_PRELOAD'] = str(helper)
                run([sys.executable,str(policy/'full_capture.py'),str(native),str(output/(kind+'-capture.json'))],kind,child_env=child_env)
            hashes = lambda rows:{(row['name'],row['scale']):row['rgbaSha256'] for row in rows}
            assert hashes(capture['results']) == hashes(json.loads((output/'plain-capture.json').read_text())['results']) == hashes(json.loads((output/'profile-capture.json').read_text())['results'])
            profiles = [json.loads(line) for line in (output/'profile.jsonl').read_text().splitlines()]
            assert profiles, 'Actual host context was not observed'
            names = {check_profile(profile,args.rid) for profile in profiles}
            assert len(names) == 1 and all(all(profile[key] == capture_profile[key] for key in ['renderer','version','vendor']) for profile in profiles)
            receipt['profileName'] = names.pop()
            known = next(row for row in json.loads((ROOT/'tests/gpu/clipping-profiles.json').read_text())['linux'] if row['name'] == receipt['profileName'])
            assert sha(output/'profile.log') == known['shaderCaptureLogSha256'], 'Unqualified compiled shader/profile log'
            receipt.update(profiles=profiles,shaderCaptureLogSha256=sha(output/'profile.log'),
                           profileHelperSha256=sha(helper),profileByteEquivalentCases=54)
            inputs = json.loads((policy/'linux-model-inputs.json').read_text())
            inputs.update(actualProfile=profiles[0],sourceCommit=manifest['source']['commit'],
                          runtimeSha256=before['libRanvierWebCoreHost.so'])
            model_script = policy/'gpu_pixel_gate_mesa.py'
            old_cpu = ROOT/'tests/fixtures/background-content-clip-baselines/linux-x64-gpu.json'
        save(output/'model-inputs.json',inputs)
        run([sys.executable,'-I',str(model_script),'--inputs',str(output/'model-inputs.json'),
             '--capture',str(output/'capture.json'),'--output',str(output/'model.json')],'model')
        model = json.loads((output/'model.json').read_text())
        assert model['result'] == 'PASS' and {(r['scale'],r['checkedPixels'],r['failures']) for r in model['cases']} == {(1.5,1080000,0),(2,1920000,0)}
        negatives = []
        for mutation in ['shift','erase','recolor','bleed','solid-lsb','pink-to-red','edge-channel','filter-low-bound','filter-high-bound','old-cpu-path']:
            destination = output/('negative-'+mutation+'.json')
            command = [sys.executable,'-I',str(model_script),'--inputs',str(output/'model-inputs.json'),
                       '--capture',str(old_cpu if mutation == 'old-cpu-path' else output/'capture.json'),'--output',str(destination)]
            if mutation != 'old-cpu-path': command += ['--mutation',mutation]
            run(command,'negative-'+mutation,expected=1,timeout=60)
            negative = json.loads(destination.read_text())
            assert negative['result'] == 'FAIL' and len(negative['cases']) == 2 and all(row['failures'] > 0 for row in negative['cases'])
            negatives.append({'mutation':mutation,'sha256':sha(destination)})
        receipt.update(result='PASS',negativeControls=negatives,modelSha256=sha(output/'model.json'),
                       scope='Current producer inputs; original54 report/12strict/52other/DPR1policy retained; reviewed profile model only for2promotedcases')
    finally:
        receipt['nativeAfter'] = {p.relative_to(native).as_posix():sha(p) for p in native.rglob('*') if p.is_file()}
        receipt['nativeUnchanged'] = receipt['nativeAfter'] == before
        receipt['manifestAfterSha256'] = sha(manifest_path)
        receipt['sourceInputsAfter'] = {p.relative_to(ROOT).as_posix():sha(p) for p in paths}
        receipt['producerCheckoutHeadAfter'] = subprocess.check_output(source_command,text=True).strip()
        receipt['producerTrackedChangesAfter'] = subprocess.check_output(['git','-C',str(ROOT),'status','--porcelain','--untracked-files=no'],text=True).strip()
        stable = receipt['nativeUnchanged'] and receipt['manifestAfterSha256'] == receipt['manifestSha256'] and receipt['sourceInputsAfter'] == receipt['sourceInputs'] and receipt['producerCheckoutHeadAfter'] == expected_source and not receipt['producerTrackedChangesAfter']
        if receipt['result'] != 'PASS' or not stable: receipt['result'] = 'FAIL'
        receipt['totalSeconds'] = time.monotonic()-started
        save(output/'receipt.json',receipt)
        assert stable
    print(json.dumps({'result':receipt['result'],'profile':receipt['profileName'],'strict':12,'other':52,'modelPixels':3000000}))


if __name__ == '__main__': main()
