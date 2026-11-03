"""Verify and relay accepted local P12 evidence without executing qualification."""
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile

ROOT=Path(__file__).resolve().parents[1]
POLICY=ROOT/'providers/atspi/preview12-x64-relay.json'
MANIFEST='qualification-evidence-manifest.json'


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


old=load('relay11',ROOT/'scripts/relay_atspi_preview11_x64.py')
aggregate=load('aggregate12',ROOT/'providers/atspi/public_aggregate.py')
managed=load('public_managed12',ROOT/'tests/atspi/public_managed.py')
helper=load('managed12',ROOT/'tests/atspi/arm64_managed.py')
sha=lambda data:hashlib.sha256(data).hexdigest()
require=old.require


def validate_policy(policy,transport=False):
    require(policy.get('schemaVersion')==1 and policy.get('proofKind')=='local-qualified-relayed' and policy.get('testsExecutedByRelay') is False,'Relay must not claim test execution')
    expected=dict(rid='linux-x64',nativeVersion='0.1.1-preview.11',nativeSourceClaim=managed.NATIVE_SOURCE,
                  providerSourceClaim=managed.PROVIDER_SOURCE,viewSource='8a788889ec41e8264e5b017fcc6666c581f34d31',domVersion='0.1.0-alpha.58',hostSha256=managed.HOST['linux-x64'])
    require(all(policy.get(k)==v for k,v in expected.items()),'Wrong P12/P11 relay cohort')
    for name in ('providerSha256','sdkPackageSha256','qualificationReceiptSha256','assetSha256','evidenceManifestSha256','harnessSha256'):
        require(isinstance(policy.get(name),str) and re.fullmatch('[0-9a-f]{64}',policy[name]),'Missing exact byte pin: '+name)
    require(type(policy.get('assetBytes')) is int and policy['assetBytes']>0,'Missing exact asset size')
    if transport:
        require(policy.get('armed') is True,'The relay is unarmed')
        for name in ('releaseId','assetId'):require(type(policy.get(name)) is int and policy[name]>0,'Missing exact transport pin: '+name)
        require(isinstance(policy.get('releaseTargetCommit'),str) and re.fullmatch('[0-9a-f]{40}',policy['releaseTargetCommit']),'Missing exact release target')
        for name in ('assetName','releaseAuthor','assetUploader'):require(isinstance(policy.get(name),str) and re.fullmatch('[A-Za-z0-9_.-]+',policy[name]),'Missing transport identity: '+name)


def validate_graph_shape(assets,mode,provider_id,provider_version):
    libraries=assets['libraries'];expected=managed.selected(mode,'linux-x64')
    require(not any(value.get('type')=='project' for value in libraries.values()),'Project source fallback')
    family={name.casefold() for name in managed.PUBLIC}|{provider_id.casefold()}
    actual=[(key.rsplit('/',1)[0].casefold(),key.rsplit('/',1)[1]) for key in libraries if key.rsplit('/',1)[0].casefold() in family or key.rsplit('/',1)[0].casefold().startswith('ranvier.webcore.native.')]
    wanted={(name.casefold(),managed.PUBLIC[name][0]) for name in expected}|{(provider_id.casefold(),provider_version)}
    require(len(actual)==len(wanted) and set(actual)==wanted and 'FSharp.Core/10.1.403' in libraries,'Mixed public managed graph')
    targets=[value for name,value in assets['targets'].items() if name.endswith('/linux-x64')];require(len(targets)==1,'Wrong RID target')
    hosts=[(key,name) for key,value in targets[0].items() for category in ('native','runtimeTargets') for name in value.get(category,{}) if name.casefold().endswith('libranvierwebcorehost.so')]
    require(len(hosts)==1 and hosts[0][0]=='Ranvier.WebCore.Native.linux-x64/0.1.1-preview.11','Wrong selected Host asset')


def validate_bundle(archive,policy):
    validate_policy(policy)
    require(archive.stat().st_size==policy['assetBytes'] and sha(archive.read_bytes())==policy['assetSha256'],'Evidence archive bytes differ')
    with zipfile.ZipFile(archive) as z:require(sha(z.read(MANIFEST))==policy['evidenceManifestSha256'],'Evidence manifest differs')
    files,manifest=old.inventory(archive)
    expected=dict(schemaVersion=1,proofKind='local-qualified',rid='linux-x64',abi=63,nativeVersion=policy['nativeVersion'],nativeSourceClaim=policy['nativeSourceClaim'],providerSourceClaim=policy['providerSourceClaim'],viewSource=policy['viewSource'],sourceProvenance='unverified-caller-claim',allSixProfileEvidenceBound=True,hostSha256=policy['hostSha256'],providerSha256=policy['providerSha256'])
    require(all(manifest.get(k)==v for k,v in expected.items()),'Local source or cohort claims differ')
    require(sha(files['source/public_managed.py'])==policy['harnessSha256'],'Local harness bytes differ')
    package=files[manifest['packagePath']];receipt=files[manifest['qualificationReceiptPath']]
    require(sha(package)==policy['sdkPackageSha256']==manifest['packageSha256'] and sha(receipt)==policy['qualificationReceiptSha256']==manifest['qualificationReceiptSha256'],'Package or qualification receipt differs')
    pins=dict(packageSha256=policy['sdkPackageSha256'],receiptSha256=policy['qualificationReceiptSha256'])
    cohort=dict(nativeVersion=policy['nativeVersion'],nativeSource=policy['nativeSourceClaim'],providerSourceClaim=policy['providerSourceClaim'],rids={'linux-x64':pins})
    with tempfile.TemporaryDirectory(prefix='atspi-p12-relay-') as directory:
        directory=Path(directory);p=directory/'provider.nupkg';q=directory/'receipt.json';p.write_bytes(package);q.write_bytes(receipt)
        checked=aggregate.checked_receipt(q,pins,cohort,'linux-x64');aggregate.read_input(p,cohort,'linux-x64',checked)
    m=json.loads(files[manifest['managedReceiptPath']]);require(sha(files[manifest['managedReceiptPath']])==manifest['managedReceiptSha256'],'Managed receipt differs')
    require(m.get('sourceRevision')==policy['providerSourceClaim'] and m.get('nativeSource')==policy['nativeSourceClaim'] and m.get('nativeVersion')==policy['nativeVersion'] and m.get('publicViewVersion')=='0.1.46' and m.get('sourceProvenance')=='unverified-caller-claim','Managed source claims differ')
    require(m.get('hostSha256')==policy['hostSha256'] and m.get('providerSha256')==policy['providerSha256'] and m.get('packageSha256')==policy['sdkPackageSha256'] and m.get('allOwnedProcessesExited') is True and m.get('tcpClosed') is True and m.get('privateDisplayDirectoryRemoved') is True,'Managed runtime inputs or cleanup differ')
    with zipfile.ZipFile(io.BytesIO(package)) as z:provider_manifest=json.loads(z.read('provider-manifest.json'))
    cache=json.loads(files['public-cache-audit.json'])
    require(set(manifest['rawAssetGraphs'])=={'normal','traced'},'Both raw graphs required')
    for mode,item in manifest['rawAssetGraphs'].items():
        raw=files[item['path']];require(sha(raw)==item['sha256']==m['assetGraphs'][mode]['sha256']==cache[mode]['assetSha256'],'Raw asset graph differs')
        validate_graph_shape(json.loads(raw),mode,provider_manifest['id'],provider_manifest['version'])
        expected_packages={name:dict(version=managed.PUBLIC[name][0],sha256=managed.PUBLIC[name][1],source='https://api.nuget.org/v3/index.json') for name in sorted(managed.selected(mode,'linux-x64'))}
        require(cache[mode]['publicPackages']==expected_packages and cache[mode]['providerPackageSha256']==policy['sdkPackageSha256'],'Local public-cache audit claims differ')
        project=ET.fromstring(files['managed-aot/source/'+mode+'/AccessibilityAot.fsproj']);require(not list(project.iter('ProjectReference')),'Project fallback')
        program=files['managed-aot/source/'+mode+'/Program.fs'].replace(b'\r\n',b'\n');require(sha(program)==managed.PROGRAM_SHA,'Program differs')
        publish=files['managed-aot/publish-'+mode+'.log'].decode(errors='replace');helper.validate_publish_log(publish)
    pairs={(mode,profile) for mode in ('normal','traced') for profile in ('present','absent','no-bus')}
    require(len(m['runs'])==6 and {(row['mode'],row['profile']) for row in m['runs']}==pairs and set(manifest['runtimeLogs'])=={a+'-'+b for a,b in pairs},'Six profiles required')
    for row in m['runs']:
        item=manifest['runtimeLogs'][row['mode']+'-'+row['profile']];raw=files[item['path']];binary=files[item['binaryPath']]
        require(sha(raw)==item['sha256']==row['logSha256'] and sha(binary)==item['binarySha256']==row['binarySha256'],'Runtime log or binary differs')
        require(binary[:6]==b'\x7fELF\x02\x01' and int.from_bytes(binary[18:20],'little')==62,'Wrong ELF architecture')
        text=raw.decode();result=next(json.loads(line) for line in text.splitlines() if line.startswith('{'));helper.validate_result(result,row['profile']=='present')
        require(result==row['result'] and row['nativeBefore']==row['nativeAfter'] and row['hostSha256']==policy['hostSha256'],'Runtime results or native inputs differ')
        if row['profile']=='absent':require('libRanvierWebCoreAtspi.so' not in row['nativeBefore'],'Absent profile bundled provider')
        else:require(row['nativeBefore'].get('libRanvierWebCoreAtspi.so')==policy['providerSha256'],'Runtime provider differs')
        require(sorted({line.split()[-1] for line in text.splitlines() if line.startswith('native-map ')})==sorted(row['maps']),'Native maps differ')
    sdk=json.loads(files[manifest['ordinarySdkReceiptPath']]);require(sha(files[manifest['ordinarySdkReceiptPath']])==manifest['ordinarySdkReceiptSha256'] and sdk['packageSha256']==policy['sdkPackageSha256'] and sdk['consumer']['loaded'] is True and sdk['consumer']['providerSha256']==policy['providerSha256'],'Ordinary SDK load differs')
    require(sdk['nativeBefore']==sdk['nativeAfter'] and sdk['nativeBefore']['libRanvierWebCoreHost.so']==policy['hostSha256'] and sdk['nativeBefore']['libRanvierWebCoreAtspi.so']==policy['providerSha256'],'Ordinary SDK native bytes differ')
    for label,directory in [('direct','protocol'),('queued','protocol-queued'),('session','protocol-session')]:
        report=json.loads(files[directory+'/client-report.json']);process=json.loads(files[directory+'/receipt.json'])
        require(type(report['assertions']) is int and report['assertions']>=87 and len(report['rows'])==report['assertions'] and all(row.get('passed') is True for row in report['rows']),'Protocol assertion differs: '+label)
        require(process['allOwnedProcessesExited'] is True and process['nativeBefore']==process['nativeAfter']==policy['hostSha256'] and process['providerSha256']==policy['providerSha256'],'Protocol runtime differs: '+label)
    style=json.loads(files['direct-style-report.json']);require(len(style)>=23 and all(row.get('passed') is True for row in style),'Direct style differs')
    return files,manifest


def receive(policy,work):
    validate_policy(policy,transport=True)
    require(os.environ.get('GITHUB_EVENT_NAME')=='workflow_dispatch' and os.environ.get('GITHUB_REF')=='refs/heads/main'
            and os.environ.get('GITHUB_WORKFLOW_REF')=='ranvier-org/Ranvier.WebCore/.github/workflows/atspi-preview12-relay.yml@refs/heads/main'
            and re.fullmatch('[0-9a-f]{40}',os.environ.get('GITHUB_SHA','')),'Require the exact main relay workflow dispatch')
    release=json.loads(subprocess.check_output(['gh','api','repos/ranvier-org/Ranvier.WebCore/releases/'+str(policy['releaseId'])],text=True,timeout=30));old.validate_release(release,policy)
    work.mkdir(parents=True,exist_ok=False);archive=work/'accepted-local-proof.zip'
    with archive.open('wb') as stream:subprocess.run(['gh','api','-H','Accept: application/octet-stream','repos/ranvier-org/Ranvier.WebCore/releases/assets/'+str(policy['assetId'])],stdout=stream,check=True,timeout=180)
    files,manifest=validate_bundle(archive,policy);output=work/'validated'
    for name,data in files.items():p=output/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    with zipfile.ZipFile(archive) as z:(output/MANIFEST).write_bytes(z.read(MANIFEST))
    record=dict(schemaVersion=1,proofKind='local-qualified-relayed',testsExecutedByRelay=False,sourceProvenance='unverified-caller-claim',originalBundleSha256=policy['assetSha256'],qualificationReceiptSha256=policy['qualificationReceiptSha256'],sdkPackageSha256=policy['sdkPackageSha256'],releaseId=policy['releaseId'],assetId=policy['assetId'],receiverWorkflow='.github/workflows/atspi-preview12-relay.yml',receiverHead=os.environ['GITHUB_SHA'],receiverEvent=os.environ['GITHUB_EVENT_NAME'])
    (output/'relay-receipt.json').write_text(json.dumps(record,indent=2));print(json.dumps(record))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['verify-bundle','receive']);parser.add_argument('--bundle',type=Path);parser.add_argument('--work',type=Path);args=parser.parse_args()
    policy=json.loads(POLICY.read_text())
    if args.mode=='receive':
        if args.work is None:parser.error('--work required')
        receive(policy,args.work)
    else:
        if args.bundle is None:parser.error('--bundle required')
        files,_=validate_bundle(args.bundle,policy);print(json.dumps(dict(scope='offline local evidence validation only; no tests executed',members=len(files),bundleSha256=policy['assetSha256'])))
