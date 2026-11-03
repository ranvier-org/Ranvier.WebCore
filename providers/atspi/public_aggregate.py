"""Assemble one optional package from explicitly pinned per-RID qualification inputs."""
import hashlib
import argparse
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT=Path(__file__).resolve().parent
IDENTITY='Ranvier.WebCore.Accessibility.Atspi'
RIDS={'linux-x64':62,'linux-arm64':183}
HEADER_SHA256='a991d384426af8d8c295fb83fb797f50480f93056bf28d940c412ab3fbaa52b7'
REQUIRED_COMMON={'include/RanvierAtspi.h','include/RanvierWebCoreAbi.h','NOTICE.md','THIRD-PARTY.md','licenses/LGPL-2.1.txt','README.md'}
spec=importlib.util.spec_from_file_location('private_atspi',ROOT/'package.py')
private=importlib.util.module_from_spec(spec); spec.loader.exec_module(private)


def digest(data): return hashlib.sha256(data).hexdigest()


def full_hash(value,length,label):
    if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{'+str(length)+'}',value):
        raise ValueError(label+' requires a full lowercase hash.')


def relative(name):
    path=PurePosixPath(name)
    if not name or path.is_absolute() or path.as_posix()!=name or '\\' in name or any(part in {'.','..'} or ':' in part or part.endswith(('.',' ')) for part in path.parts):
        raise ValueError('Unsafe package path: '+name)
    return name


def validate_policy(policy):
    if policy.get('schemaVersion')!=1 or policy.get('armed') is not True:
        raise ValueError('The public aggregate is unarmed.')
    if policy.get('id')!=IDENTITY or policy.get('version')!=policy.get('nativeVersion'):
        raise ValueError('Use the reserved public ID and coordinated Native version.')
    if not isinstance(policy.get('version'),str) or not re.fullmatch(r'\d+\.\d+\.\d+(?:-[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*)?',policy['version']):
        raise ValueError('An allocated public cohort version is required.')
    if re.search(r'(?:^|[.-])(?:private\w*|local\w*|ci)(?:[.-]|$)',policy['version'],re.I):
        raise ValueError('The public aggregate requires its allocated public version.')
    if type(policy.get('abi')) is not int or policy['abi']!=63 or set(policy.get('rids',{}))!=set(RIDS):
        raise ValueError('Require the matching ABI63 x64 and ARM64 qualification records.')
    for field in ['nativeSource','providerSourceClaim']: full_hash(policy.get(field),40,field)
    for rid,pins in policy['rids'].items():
        for field in ['packageSha256','receiptSha256']: full_hash(pins.get(field),64,rid+' '+field)
        if 'proofKind' in pins and pins['proofKind'] not in ('local-qualified-relayed','runner-executed'):
            raise ValueError('Unknown qualification transport kind.')


def checked_receipt(path,pins,policy,rid):
    data=Path(path).read_bytes()
    if digest(data)!=pins['receiptSha256']: raise ValueError('The supplied qualification receipt hash differs.')
    receipt=json.loads(data)
    expected=dict(schemaVersion=1,rid=rid,abi=63,nativeVersion=policy['nativeVersion'],nativeSource=policy['nativeSource'],providerSourceClaim=policy['providerSourceClaim'],packageSha256=pins['packageSha256'])
    if type(receipt.get('abi')) is not int or any(receipt.get(key)!=value for key,value in expected.items()): raise ValueError('Qualification receipt cohort identity differs.')
    for field in ['hostSha256','providerSha256']: full_hash(receipt.get(field),64,'receipt '+field)
    checks=receipt.get('checks',{})
    if type(checks.get('nativeExports')) is not int or checks['nativeExports']!=347 or type(checks.get('directStyleAssertions')) is not int or checks['directStyleAssertions']<23 or checks.get('ordinarySdkConsumer') is not True:
        raise ValueError('The RID has incomplete native/style/ordinary SDK qualification.')
    protocol=checks.get('protocolAssertions',{})
    if any(type(protocol.get(mode)) is not int or protocol[mode]<84 for mode in ['direct','queued','session']):
        raise ValueError('The RID has incomplete actual protocol qualification.')
    for mode in ['normal','traced']:
        profiles=checks.get('managedAot',{}).get(mode,{})
        for profile in ['present','absent','no-bus']:
            result=profiles.get(profile,{})
            if (result.get('passed') is not True or type(result.get('windows')) is not int or result['windows']!=3 or type(result.get('directHosts')) is not int or result['directHosts']!=3
                    or result.get('expectedAttached') is not (profile=='present') or result.get('dynamicCodeSupported') is not False
                    or result.get('nativeUnchanged') is not True or result.get('ownedProcessesExited') is not True
                    or (profile=='present' and result.get('nonBmpStyle') is not True)):
                raise ValueError('The RID lacks complete normal/traced real Window/Host NativeAOT controls.')
    return receipt


def read_input(path,policy,rid,receipt):
    path=Path(path)
    if digest(path.read_bytes())!=policy['rids'][rid]['packageSha256']: raise ValueError('Qualification input package hash differs.')
    files={}; folded=set()
    with zipfile.ZipFile(path) as archive:
        for entry in archive.infolist():
            if entry.is_dir(): continue
            name=relative(entry.filename)
            if name.casefold() in folded or stat.S_ISLNK(entry.external_attr>>16): raise ValueError('Duplicate/symlink package path.')
            folded.add(name.casefold()); files[name]=archive.read(entry)
    nuspecs=[name for name in files if name.lower().endswith('.nuspec')]
    if len(nuspecs)!=1 or '/' in nuspecs[0]: raise ValueError('Expected one root private package nuspec.')
    nodes={node.tag.rsplit('}',1)[-1]:node.text for node in ET.fromstring(files.pop(nuspecs[0])).iter()}
    private.validate_identity(nodes.get('id',''),nodes.get('version',''))
    manifest=json.loads(files.pop('provider-manifest.json'))
    if type(manifest.get('abi')) is not int or (manifest.get('rid'),manifest.get('abi'),manifest.get('callerClaimedProviderSourceRevision'),manifest.get('sourceProvenance'),manifest.get('requiredCapability'),manifest.get('hostBundled'))!=(rid,63,policy['providerSourceClaim'],'unverified-caller-claim','accessibility-text-style',False):
        raise ValueError('Private input ABI/source-claim/capability contracts differ.')
    if (manifest.get('id'),manifest.get('version'))!=(nodes['id'],nodes['version']): raise ValueError('Input nuspec and manifest identities differ.')
    if manifest.get('payloads')!={name:digest(data) for name,data in files.items()}: raise ValueError('Private input payload hashes differ.')
    asset='runtimes/'+rid+'/native/libRanvierWebCoreAtspi.so'
    if {name for name in files if name.startswith('runtimes/')}!={asset}: raise ValueError('Only the exact optional RID module may be bundled.')
    if any(name!=asset and (name.lower().endswith(('.so','.dll','.dylib')) or data.startswith((b'\x7fELF',b'MZ',b'\xcf\xfa\xed\xfe',b'\xfe\xed\xfa\xcf'))) for name,data in files.items()):
        raise ValueError('An extra binary cannot hide among common SDK files.')
    module=files[asset]
    if len(module)<20 or module[:6]!=b'\x7fELF\x02\x01' or int.from_bytes(module[18:20],'little')!=RIDS[rid]:
        raise ValueError('Provider ELF architecture differs from its RID.')
    if manifest.get('providerSha256')!=digest(module) or any(manifest.get(field)!=receipt[field] for field in ['hostSha256','providerSha256']):
        raise ValueError('Input provider/host hashes differ from the supplied qualification receipt.')
    common={name:data for name,data in files.items() if name!=asset}
    if not REQUIRED_COMMON<=set(common): raise ValueError('Required SDK/upstream notice texts are missing.')
    for name in ['THIRD-PARTY.md','licenses/LGPL-2.1.txt']:
        if common[name].replace(b'\r\n',b'\n')!=(ROOT/name).read_bytes().replace(b'\r\n',b'\n'):
            raise ValueError('Required upstream license/notice text differs from the retained source.')
    if digest(common['include/RanvierWebCoreAbi.h'].replace(b'\r\n',b'\n'))!=HEADER_SHA256:
        raise ValueError('The complete reviewed ABI63/347 SDK signature header differs.')
    return asset,module,common,manifest


def prepare(policy,inputs,receipts):
    validate_policy(policy)
    if set(inputs)!=set(RIDS) or set(receipts)!=set(RIDS): raise ValueError('Supply exactly the qualified x64/ARM inputs and receipts.')
    common=None; payload={}; runtimes={}; license_status=None
    for rid in sorted(RIDS):
        receipt=checked_receipt(receipts[rid],policy['rids'][rid],policy,rid)
        asset,module,current,manifest=read_input(inputs[rid],policy,rid,receipt)
        if common is not None and current!=common: raise ValueError('Common SDK/header/tooling/notice bytes disagree across RIDs.')
        if license_status is not None and license_status!=manifest.get('licenseMetadataStatus'): raise ValueError('Input notice metadata contracts differ.')
        common=current; license_status=manifest.get('licenseMetadataStatus'); payload[asset]=module
        runtimes[rid]=dict(rid=rid,abi=63,callerClaimedProviderSourceRevision=policy['providerSourceClaim'],hostSha256=receipt['hostSha256'],providerSha256=receipt['providerSha256'],inputPackageSha256=policy['rids'][rid]['packageSha256'],qualificationReceiptSha256=policy['rids'][rid]['receiptSha256'])
        if 'proofKind' in policy['rids'][rid]:
            runtimes[rid]['qualificationProofKind']=policy['rids'][rid]['proofKind']
    payload.update(common)
    folded={name.casefold() for name in payload}
    for name in ['PUBLIC-README.md','PUBLIC-NOTICE.md','qualification-input/NOTICE.md','qualification-input/README.md']:
        if name.casefold() in folded: raise ValueError('Input collides with aggregate-owned metadata paths.')
    payload['qualification-input/NOTICE.md']=payload['NOTICE.md']
    payload['qualification-input/README.md']=payload.pop('README.md')
    payload['NOTICE.md']=(ROOT/'PUBLIC-NOTICE.md').read_bytes()
    payload['PUBLIC-README.md']=(ROOT/'PUBLIC-README.md').read_bytes()
    manifest=dict(schemaVersion=2,id=IDENTITY,version=policy['version'],nativeVersion=policy['nativeVersion'],abi=63,
                  callerClaimedNativeSourceRevision=policy['nativeSource'],
                  callerClaimedProviderSourceRevision=policy['providerSourceClaim'],sourceProvenance='unverified-caller-claim',
                  qualificationEvidence='supplied receipt hash comparison; independent review/build provenance is not authenticated by this packager',
                  hostBundled=False,requiredCapability='accessibility-text-style',licenseMetadataStatus=license_status,
                  runtimes=runtimes,commonInputPayloads={name:digest(data) for name,data in common.items()},
                  payloads={name:digest(data) for name,data in payload.items()})
    payload['provider-manifest.json']=json.dumps(manifest,indent=2).encode()
    return payload,manifest


def _sdk_command(command,work,environment,label):
    helper=ROOT.parents[1]/'scripts/qualify_producer_gpu_clipping.py'
    spec=importlib.util.spec_from_file_location('owned_sdk_process',helper)
    owner=importlib.util.module_from_spec(spec); spec.loader.exec_module(owner)
    request=work/(label+'-command.json'); request.write_text(json.dumps(command))
    with (work/(label+'.log')).open('wb') as log:
        child=owner.OwnedChild([sys.executable,'-I',str(Path(__file__).resolve()),'--sdk-step',str(request)],log,environment,work)
        try:
            code=child.process.wait(timeout=120)
            if code: raise subprocess.CalledProcessError(code,command)
        finally: child.close()
    return (work/(label+'.log')).read_text(encoding='utf-8',errors='replace')


def _emit_sdk_package(payload,manifest,output,work,dotnet='dotnet'):
    output=Path(output).resolve(); work=Path(work).resolve()
    destination=output/(manifest['id']+'.'+manifest['version']+'.nupkg')
    if destination.exists(): raise FileExistsError(destination)
    work.mkdir(parents=True,exist_ok=False)
    files=work/'payload'; files.mkdir()
    package=ET.Element('package'); metadata=ET.SubElement(package,'metadata')
    fields=[('id',manifest['id']),('version',manifest['version']),('authors','Ranvier'),
            ('description','Optional native AT-SPI modules for application-selected matching WebCore hosts.'),('readme','PUBLIC-README.md')]
    for name,value in fields: ET.SubElement(metadata,name).text=value
    ET.SubElement(metadata,'license',type='file').text='NOTICE.md'
    ET.SubElement(metadata,'repository',type='git',url='https://github.com/ranvier-org/Ranvier.WebCore')
    entries=ET.SubElement(package,'files')
    for name,data in payload.items():
        relative(name); target=files/name; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(data)
        parent=PurePosixPath(name).parent.as_posix()
        ET.SubElement(entries,'file',src=str(target),target='' if parent=='.' else parent)
    nuspec=work/'provider.nuspec'; ET.ElementTree(package).write(nuspec,encoding='utf-8',xml_declaration=True)
    project=work/'Provider.csproj'
    project_xml=ET.Element('Project',Sdk='Microsoft.NET.Sdk'); properties=ET.SubElement(project_xml,'PropertyGroup')
    for name,value in [('TargetFramework','net10.0'),('IsPackable','true'),('IncludeBuildOutput','false'),('EnableDefaultItems','false'),('NuspecFile',str(nuspec))]:
        ET.SubElement(properties,name).text=value
    ET.ElementTree(project_xml).write(project,encoding='utf-8',xml_declaration=True)
    (work/'global.json').write_text(json.dumps(dict(sdk=dict(version='10.0.403',rollForward='disable',allowPrerelease=False))))
    config=work/'NuGet.Config'; config.write_text('<configuration><packageSources><clear/></packageSources></configuration>')
    environment=dict(os.environ,NUGET_PACKAGES=str(work/'cache'),NUGET_HTTP_CACHE_PATH=str(work/'http-cache'),DOTNET_CLI_USE_MSBUILD_SERVER='0',MSBUILDDISABLENODEREUSE='1')
    if _sdk_command([dotnet,'--version'],work,environment,'sdk').strip()!='10.0.403': raise ValueError('Use the reviewed SDK10.0.403.')
    _sdk_command([dotnet,'restore',str(project),'--configfile',str(config),'-m:1','/nr:false'],work,environment,'restore')
    _sdk_command([dotnet,'pack',str(project),'-c','Release','--no-restore','--no-build','-o',str(work/'packed'),'-m:1','/nr:false'],work,environment,'pack')
    packed=work/'packed'/destination.name
    with zipfile.ZipFile(packed) as archive:
        if any(archive.read(name)!=data for name,data in payload.items()): raise ValueError('SDK packaging changed aggregate payload bytes.')
        nuspecs=[name for name in archive.namelist() if name.endswith('.nuspec')]
        if len(nuspecs)!=1: raise ValueError('SDK emitted an ambiguous package identity.')
        emitted=ET.fromstring(archive.read(nuspecs[0]))
        if any(node.tag.rsplit('}',1)[-1]=='repository' and node.get('commit') is not None for node in emitted.iter()):
            raise ValueError('SDK metadata must not upgrade an unverified source claim into a repository commit.')
        if any(node.tag.rsplit('}',1)[-1]=='dependency' for node in emitted.iter()):
            raise ValueError('The optional aggregate must not add renderer/managed dependencies.')
    output.mkdir(parents=True,exist_ok=True)
    with destination.open('xb') as stream: stream.write(packed.read_bytes())
    return destination


def pack(policy,inputs,receipts,output,work,dotnet='dotnet'):
    payload,manifest=prepare(policy,inputs,receipts)
    path=_emit_sdk_package(payload,manifest,output,work,dotnet)
    record=dict(scope='aggregate from supplied qualification records; source/review provenance is not authenticated',path=str(path),sha256=digest(path.read_bytes()),manifest=manifest)
    (Path(work)/'aggregate-receipt.json').write_text(json.dumps(record,indent=2))
    return record


if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--sdk-step':
        command=json.loads(Path(sys.argv[2]).read_text())
        raise SystemExit(subprocess.run(command,check=False).returncode)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cohort',required=True,type=Path)
    parser.add_argument('--inputs',required=True,type=Path,help='JSON mapping RID to private package and qualification receipt paths.')
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--work',required=True,type=Path)
    parser.add_argument('--dotnet',default='dotnet')
    args=parser.parse_args(); inputs=json.loads(args.inputs.read_text())
    print(json.dumps(pack(json.loads(args.cohort.read_text()),{rid:row['package'] for rid,row in inputs.items()},{rid:row['receipt'] for rid,row in inputs.items()},args.output,args.work,args.dotnet)))
