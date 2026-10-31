from pathlib import Path
import hashlib,json,os,re,shutil,subprocess
repo=Path('C:/wk/native-capabilities')
freeze=repo/'artifacts/h07/native20-frozen'
runtime=freeze/'runtimes/win-x64/native'
receipt=json.loads((freeze/'runtime-receipt.json').read_text())
parent=json.loads((repo/'docs/svg-surfaces-evidence/final-evidence.json').read_text())
out=repo/'artifacts/h07/full-producer'
out.mkdir(exist_ok=True)
records=[]
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def verify_runtime():
    for entry in receipt['shippingFiles']:
        assert digest(runtime/entry['name'])==entry['sha256'],entry['name']
def run(name,command,expected=None,environment=None,executed=None):
    existing=next((item for item in records if item['name']==name and item['exitCode']==0),None)
    if existing:
        assert digest(Path(existing['log']))==existing['logSha256']
        verify_runtime()
        print(name,'retained prior exit0',flush=True)
        return
    verify_runtime()
    before={str(p):digest(p) for p in (executed or [])}
    result=subprocess.run(['rtk','proxy',*command],cwd=repo,env=environment,capture_output=True,timeout=180)
    log=out/(name+'.log')
    if log.exists():
        number=1
        while log.with_name(log.stem+f'-previous{number}.log').exists():number+=1
        log.rename(log.with_name(log.stem+f'-previous{number}.log'))
    log.write_bytes(result.stdout+result.stderr+f'\nEXIT_CODE={result.returncode}\n'.encode())
    verify_runtime()
    assert before=={str(p):digest(p) for p in (executed or [])},'Executed managed assets changed'
    record={'name':name,'exitCode':result.returncode,'log':str(log),'logSha256':digest(log),'executedAssets':before,'runtimeReceipt':str(freeze/'runtime-receipt.json')}
    records[:]=[item for item in records if item['name']!=name]
    records.append(record)
    (out/'results.json').write_text(json.dumps(records,indent=2))
    print(name,'exit',result.returncode,flush=True)
    if result.returncode:
        print((result.stdout+result.stderr).decode('utf-8','replace')[-5000:],flush=True)
        raise SystemExit(result.returncode)
    if expected is not None:
        assert re.search(rb'PASS[^\n]*\b'+str(expected).encode()+rb'\b',result.stdout),name+' expected count'
        record['assertions']=expected
if (out/'results.json').exists():records=json.loads((out/'results.json').read_text())
for probe in parent['probes']:
    name=probe['probe']
    source=repo/'tests/abi'/(name+'.py')
    if not source.exists():continue
    arguments=['C:/Python314/python.exe','-I','-X','utf8',str(source),'--native-directory',str(runtime)]
    if name == 'svg_surfaces':arguments+=['--webkit-source','C:/wk/src']
    run(name,arguments,probe.get('assertions'))
for name in ['frames','teardown']:
    driver=repo/'artifacts/h07/abi-driver'
    for entry in receipt['shippingFiles']:
        destination=driver/entry['name'];destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(runtime/entry['name'],destination)
        assert digest(destination)==entry['sha256']
    env=dict(os.environ,RANVIER_WEBKIT_SOURCE='C:/wk/src',RANVIER_WEBCORE_OUT=str(out/name),RANVIER_TRACE='1')
    if name=='teardown':env['RANVIER_WEBCORE_PROBE']='teardown'
    else:env.pop('RANVIER_WEBCORE_PROBE',None)
    assets=[p for p in driver.rglob('*') if p.is_file() and p.suffix.lower() in ['.dll','.exe','.json']]
    run(name,['dotnet',str(driver/'RanvierWebCoreAbi.Driver.dll')],environment=env,executed=assets)
teardown=json.loads((out/'teardown/teardown-probes.json').read_text())
assert len(teardown)==42 and all(item['documentRefsAfterCollection']==-1 and item['targetRefsAfterCollection']==-1 for item in teardown)
(out/'results.json').write_text(json.dumps(records,indent=2))
print('NATIVE20_FULL_PARENT_REGRESSION='+str(sum(item.get('assertions',0) for item in records))+' RAW +42TEARDOWN',flush=True)
