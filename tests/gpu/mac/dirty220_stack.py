"""Read second-host invalidation stacks on the retained counter and native libraries."""
import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import signal
import stat
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[3]
SOURCE = '2a15536b89aa6a72164762803dac76291973d0a0'
WEBKIT = 'b95c91b1c0ee43cc86d25ff7af73038f67a88e04'
ARCHIVE_SHA = '2ece47757b0a002fc4122f0f8fc181b879ed95cda29b29224e4d7e88732031e7'
SOURCE_TREES = {'host':'d407cbe31b8bf47809b9f66412faf1fd8468b17d',
                'gen':'847bf7bcfbaca4a8303643eeefcd6c7affb6b417',
                'src':'0037b66b3e42cfedfb8361537ab2af580ae51a4b',
                'tests/abi':'9fac47b7fd05d4d848a44e7c87fa5c5dd1b7deb0'}
COUNTER_SOURCE_SHA = '1b03f8b0dddb42d2f040a72660974700178a0d0ec2febed11483f0e0bb5aa0a9'
SCALES = ('1','1,1')
SYMBOLS = {'libEGL.dylib': {'sha256': '935bb22fe657a30dc801770abbae2684451f0c0f7cb3a5fd2845725f7bb3c438', 'dwarf': 'libEGL.dylib'}, 'libGLESv2.dylib': {'sha256': '7a106a8e2b6ff89be5a920a2ce4180feee23b4a584a27decbcbd78f1aed411f7', 'dwarf': 'libGLESv2.dylib'}, 'libJavaScriptCore.dylib': {'sha256': '4a0bfeb745cd1b2d155bc8aa3b34ba94591289e1f5706082131e777bd45bfde0', 'dwarf': 'JavaScriptCore'}, 'libRanvierWebCoreHost.dylib': {'sha256': '385378ecb97fef8b2e06ee2be65d793c721a2886a5206de200d581e91a6ae660', 'dwarf': 'libRanvierWebCoreHost.dylib'}, 'libWebCore.dylib': {'sha256': '1f68134c311aec5240a0a39aad97f3e8d2c7a9b7949921584da0614174c2ad94', 'dwarf': 'WebCore'}, 'libWebGPU.dylib': {'sha256': '483905dc7b97d053825d44c4f5c447299a28eca0bcb81199d8a7408e1b8feee6', 'dwarf': 'WebGPU'}}
NATIVE = {
    'libJavaScriptCore.dylib':'9f401b62e5c68fd62895728133f2b3ac823bd07c775afa52e4585bcf46afa8ab',
    'libEGL.dylib':'cb2d5331164dfe5c2e6be2b113c7a835787a9e50827a1544fd0b0e035f33724c',
    'libGLESv2.dylib':'f66c0299af00619c0a5f172fa8750e9b4807fd74d940b876a611a9ae30630693',
    'libRanvierWebCoreHost.dylib':'9bfd1f8a6a7128dc19630a0e675118632cdab6ea83006c22cfa6760b0439115c',
    'libWebCore.dylib':'fa6680992b1b4ce8f0cfe189a33b1aad182681f05139c5e685bcffb3bbd75233',
    'libWebGPU.dylib':'f25896ebade7f0b107bd699062d1fbdfe5ec8a0c6b85493ec7fb1733fb29891c',
}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def extract(archive,directory):
    if sha(archive)!=ARCHIVE_SHA:
        raise ValueError('The exact retained coherent2a archive differs.')
    directory.mkdir(exist_ok=False)
    folded=set()
    with zipfile.ZipFile(archive) as zipped:
        for item in zipped.infolist():
            path=PurePosixPath(item.filename)
            if (item.orig_filename!=item.filename or path.is_absolute() or path.as_posix()!=item.filename or '\\' in item.filename
                    or any(part in ('.','..') or ':' in part or part.endswith(('.', ' ')) for part in path.parts)
                    or stat.S_ISLNK(item.external_attr>>16)):
                raise ValueError('Unsafe retained artifact path.')
            if item.is_dir():
                continue
            if item.filename.casefold() in folded:
                raise ValueError('Duplicate retained artifact path.')
            folded.add(item.filename.casefold())
            destination=directory/item.filename
            destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_bytes(zipped.read(item))


def validate_stage(stage):
    manifest=json.loads((stage/'manifest.json').read_text())
    if (manifest['abi']!=64 or manifest['source']!=dict(commit=SOURCE,dirty=False,builder='ci')
            or manifest['webkit']!=WEBKIT or manifest['rid']!='osx-arm64'
            or manifest['version']!='0.0.0-project2-mac220.1'):
        raise ValueError('The retained source/cohort identity differs.')
    directory=stage/'runtimes/osx-arm64/native'
    if {p.name for p in directory.iterdir()}!=set(NATIVE):
        raise ValueError('The retained native input set differs.')
    if {p.name:sha(p) for p in directory.iterdir()}!=NATIVE:
        raise ValueError('The retained library bytes differ.')
    expected={'RanvierWebCoreAbi.h':'dc1195fe9d6cb00d6db94931a0a3a1c0ad1c338576494014f42c0dab8e7f893d',
              'RanvierWebCoreDom.h':'81d52c9b692dbe9ecb182d473f25b765b51ba8ee10b0e5326251162e8021fd81'}
    for name,digest in expected.items():
        if sha(stage/'include'/name)!=digest or sha(ROOT/'host'/name)!=digest:
            raise ValueError('The compiled consumer header differs from coherent2a.')
    return directory


def validate_trees(actual):
    if actual!=SOURCE_TREES:
        raise ValueError('Production source or exact ABI64 catalogue source changed.')


def run_cases(run,program,output,record):
    images=output/'default-images'
    images.mkdir()
    cases=[('default',['--output',str(images)])]+[('scales-'+value.replace(',','_'),['--diagnostic-scales',value]) for value in SCALES]
    for name,arguments in cases:
        row,_=run(name,[program,*arguments],allow_failure=True)
        record['groups'].append(dict(group=name,exit=row['exit'],diagnosticOnly=name!='default'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',required=True,type=Path)
    args=parser.parse_args()
    if sys.platform!='darwin' or platform.machine()!='arm64':
        parser.error('Use the actual macOS arm64 runner.')
    def terminated(_signum,_frame):
        raise SystemExit(143)
    signal.signal(signal.SIGTERM,terminated)
    work=args.work.resolve()
    if work.is_relative_to(ROOT) or ROOT.is_relative_to(work):
        parser.error('Use a fresh owned work directory outside source.')
    work.mkdir(parents=True,exist_ok=False)
    output=work/'results'
    output.mkdir()
    (output/'global.json').write_text(json.dumps(dict(sdk=dict(version='10.0.403',rollForward='disable'))))
    record=dict(scope='Consumer-only coherent2a runtime diagnostics; no engine or Host compilation/link/repack',
                nativeSource=SOURCE,archiveSha256=ARCHIVE_SHA,steps=[],groups=[],status='SETUP',allOwnedChildrenExited=False)
    record['mode']='artifact-only-invalidation-stack'
    record['retainedCounterRun']=41652031792
    spec=importlib.util.spec_from_file_location('owned_child',ROOT/'scripts/qualify_producer_gpu_clipping.py')
    owner=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(owner)
    environment=dict(os.environ,DOTNET_CLI_USE_MSBUILD_SERVER='0',MSBUILDDISABLENODEREUSE='1',
                     NUGET_PACKAGES=str(work/'cache'),NUGET_HTTP_CACHE_PATH=str(work/'http-cache'))
    environment.pop('DYLD_LIBRARY_PATH',None)
    def save():
        (output/'receipt.json').write_text(json.dumps(record,indent=2))
    def run(name,command,timeout=120,allow_failure=False,cwd=output,env=None):
        log=output/(name+'.log')
        with log.open('wb') as stream:
            child=owner.OwnedChild([str(x) for x in command],stream,env or environment,cwd)
            timed_out=False
            try:
                try:
                    code=child.process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    timed_out=True
                    code=-9
            finally:
                child.close()
        row=dict(name=name,command=[str(x) for x in command],exit=code,timedOut=timed_out,
                 pid=child.process.pid,ownedGroupReaped=True,logSha256=sha(log))
        record['steps'].append(row)
        save()
        if code and not allow_failure:
            raise RuntimeError(name+' failed; see '+str(log))
        return row,log.read_text(errors='replace')
    retained=None
    before=None
    try:
        run('source',['git','-C',ROOT,'rev-parse','HEAD'])
        record['controllerSource']=(output/'source.log').read_text().strip()
        trees={name:run('tree-'+name.replace('/','-'),['git','-C',ROOT,'rev-parse','HEAD:'+name])[1].strip() for name in SOURCE_TREES}
        validate_trees(trees)
        if run('tracked-clean',['git','-C',ROOT,'status','--porcelain','--untracked-files=no'])[1].strip():
            raise ValueError('The compiled source checkout is dirty.')
        if sha(ROOT/'tests/gpu/mac/spike.mm')!=COUNTER_SOURCE_SHA:
            raise ValueError('The exact reviewed dirty-phase counter fixture changed.')
        record['sourceTrees']=trees
        if run('sdk',['dotnet','--version'])[1].strip()!='10.0.403':
            raise ValueError('The consumer SDK differs.')
        archive=work/'coherent2a.zip'
        run('download',[sys.executable,'-I',__file__,'--download',archive],timeout=240)
        run('download-counter',[sys.executable,'-I',__file__,'--download-counter',work/'counter.zip'],timeout=240)
        environment.pop('GH_TOKEN',None)
        environment.pop('GITHUB_TOKEN',None)
        retained=work/'retained'
        extract(archive,retained)
        before={str(p.relative_to(retained)):sha(p) for p in retained.rglob('*') if p.is_file()}
        stage=retained/'ranvier-mac220/out/gpu'
        native=validate_stage(stage)
        original=retained/'ranvier-mac220/spike-evidence'
        if run('xcode',['xcodebuild','-version'])[1].strip()!=(original/'xcode.log').read_text().strip():
            raise ValueError('Xcode changed from the retained producer.')
        if run('mac-sdk',['xcrun','--show-sdk-version'])[1].strip()!=(original/'environment.log').read_text().strip():
            raise ValueError('The Mac SDK changed from the retained producer.')
        library=ctypes.CDLL(str(native/'libRanvierWebCoreHost.dylib'))
        library.rv_abi_version.restype=ctypes.c_int
        if library.rv_abi_version()!=64:
            raise ValueError('Actual retained runtime ABI is not64.')
        generator=importlib.util.spec_from_file_location('native_signatures',ROOT/'tests/abi/generate_native.py')
        signatures=importlib.util.module_from_spec(generator)
        generator.loader.exec_module(signatures)
        declarations=signatures.declarations((stage/'include/RanvierWebCoreAbi.h').read_text())
        if len(declarations)!=349 or any(not hasattr(library,name) for name,_,_ in declarations):
            raise ValueError('The exact349 catalogue exports are unavailable.')
        record['actualAbi']=64
        record['nativeExports']=349
        def counters():
            sdl=work/'sdl'
            run('sdl-sdk',[sys.executable,'-I',ROOT/'tests/gpu/mac/prepare_sdk.py','--directory',sdl],timeout=300)
            sdl_receipt=json.loads((sdl/'sdk-receipt.json').read_text())
            old_sdl=json.loads((retained/'ranvier-mac220-sdl/sdk-receipt.json').read_text())
            if any(sdl_receipt[key]!=old_sdl[key] for key in ['packageVersion','packageSha256','sdlCommit','dylibSha256','installName']):
                raise ValueError('The presenter SDK differs from the actual producer.')
            counter_environment=dict(environment,DYLD_LIBRARY_PATH=str(native)+':'+str(sdl/'lib'))
            counter_archive=work/'counter.zip'
            if sha(counter_archive)!='af77a0704e5ea8d36c2de9199a5a8b09485844cb8605d870c60b7131cf3f4ed4':
                raise ValueError('The retained counter artifact differs.')
            with zipfile.ZipFile(counter_archive) as zipped:
                if zipped.namelist().count('mac-gpu-counter')!=1:
                    raise ValueError('Ambiguous retained counter executable.')
                data=zipped.read('mac-gpu-counter')
            program=output/'mac-gpu-counter'
            program.write_bytes(data)
            program.chmod(0o755)
            if sha(program)!='4c1aaa98754817bc5b6bc2de49fee400ef1476119a3b33531a282ddfd68f89f6':
                raise ValueError('The actual retained counter executable differs.')
            record['counterFixtureSha256']=sha(program)
            proof_path=ROOT/'tests/gpu/mac/proof.json'
            if hashlib.sha256(proof_path.read_text(encoding='utf-8').encode('utf-8')).hexdigest()!='3a66a2c4ec7a2150b5388d8b8056a8f6201c7a4ed504a207ced3b89117bac14f':
                raise ValueError('The reviewed raw-symbol proof changed.')
            proof=json.loads(proof_path.read_text())
            if proof['counter']['sha256']!=sha(program) or any(
                    proof['pairs'][name]['before']['packaged']!=sha(native/name) for name in NATIVE):
                raise ValueError('The raw-symbol proof does not match staged executable bytes.')
            record['rawSymbolProofSha256']=sha(proof_path)
            run('counter-imports',['xcrun','otool','-L',program])
            run('host-symbols',['xcrun','nm','-a',native/'libRanvierWebCoreHost.dylib'])
            symbol_commands=[]
            symbol_records=[]
            for name,item in SYMBOLS.items():
                digest=item['sha256']
                symbol=stage/'symbols/osx-arm64'/(name+'.dSYM')
                if sha(symbol/'Contents/Resources/DWARF'/item['dwarf'])!=digest:
                    raise ValueError('Retained native symbols differ: '+name)
                _,actual_uuid=run('uuid-'+name,['xcrun','dwarfdump','--uuid',native/name])
                _,symbol_uuid=run('symbol-uuid-'+name,['xcrun','dwarfdump','--uuid',symbol])
                actual=re.findall(r'UUID: ([0-9A-Fa-f-]+) \(arm64\)',actual_uuid)
                debug=re.findall(r'UUID: ([0-9A-Fa-f-]+) \(arm64\)',symbol_uuid)
                if len(actual)!=1 or actual!=debug:
                    raise ValueError('Native/symbol UUID mismatch: '+name)
                symbol_records.append(dict(module=name,uuid=actual[0],dwarfSha256=digest))
                symbol_commands.extend(['target modules add '+str(native/name), 'target symbols add '+str(symbol)])
            record['nativeSymbolIdentities']=symbol_records
            commands=output/'stack.lldb'
            commands.write_text(
                'settings set target.disable-aslr false\n'
                'settings set target.env-vars DYLD_LIBRARY_PATH='+str(native)+':'+str(sdl/'lib')+'\n'
                'command script import '+str(ROOT/'tests/gpu/mac/dirty220_lldb.py')+'\n'
                +'\n'.join(symbol_commands)+'\n'
                'breakpoint set -n main\n'
                'run --diagnostic-scales 1,1\n'
                'script dirty220_lldb.install(lldb.debugger)\n'
                'continue\n'
                'script p=lldb.debugger.GetSelectedTarget().GetProcess(); print("MAC_LLDB_FINAL exited="+str(p.GetState()==lldb.eStateExited)+" exit="+str(p.GetExitStatus()))\n')
            row,text=run('invalidation-stacks',['xcrun','lldb','--batch','--source',commands,str(program)],
                         timeout=240,allow_failure=True,env=counter_environment)
            stacks=[]
            for line in text.splitlines():
                if line.startswith('MAC_INVALIDATE_STACK '):
                    stacks.append(json.loads(line[len('MAC_INVALIDATE_STACK '):]))
            (output/'invalidation-stacks.json').write_text(json.dumps(stacks,indent=2))
            record['groups'].append(dict(group='readonly-invalidation-stacks',exit=row['exit'],
                completed=text.count('MAC_ADDRESS_BREAKPOINT ')==4 and any(item['rect']==[40,130,92,23] for item in stacks) and 'MAC_LLDB_FINAL exited=True' in text,
                addressBreakpointsInstalled=text.count('MAC_ADDRESS_BREAKPOINT ')==4,
                textRectStackCount=sum(item['rect']==[40,130,92,23] for item in stacks),
                strictCounterFailureRetained='transform and opacity animation reuse base backing' in text,
                scope='Diagnostic stacks only; a debugger exit code does not establish native product acceptance'))
        counters()
        record['status']='DIAGNOSTIC_COLLECTED' if record['groups'] and all(row.get('completed') for row in record['groups']) else 'DIAGNOSTIC_INCONCLUSIVE'
    except BaseException as error:
        record['error']=repr(error)
        raise
    finally:
        if before is not None:
            after={str(p.relative_to(retained)):sha(p) for p in retained.rglob('*') if p.is_file()}
            record['retainedInputsUnchanged']=before==after
            record['retainedFileHashes']=before
            if before!=after:
                record['status']='RETAINED_INPUT_MUTATION'
        record['allOwnedChildrenExited']=all(row['ownedGroupReaped'] for row in record['steps'])
        save()
    return 0 if record['status']=='DIAGNOSTIC_COLLECTED' else 1


if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--download':
        with Path(sys.argv[2]).open('xb') as stream:
            subprocess.run(['gh','api','repos/ranvier-org/Ranvier.WebCore/actions/artifacts/13230604772/zip'],stdout=stream,check=True,timeout=180)
    elif len(sys.argv)==3 and sys.argv[1]=='--download-counter':
        with Path(sys.argv[2]).open('xb') as stream:
            subprocess.run(['gh','api','repos/ranvier-org/Ranvier.WebCore/actions/artifacts/13248668771/zip'],stdout=stream,check=True,timeout=180)
    else:
        raise SystemExit(main())
