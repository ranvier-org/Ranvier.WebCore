"""Qualify the optional provider with public View/Core/Native package consumers."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('managed_profiles',Path(__file__).with_name('arm64_managed.py'))
managed=importlib.util.module_from_spec(spec);spec.loader.exec_module(managed)
PROGRAM_SHA='fb8e7bd3ef059962036bb79ed9786ed8e081c39e3c13ad837b0375c35b3b0589'
NATIVE_SOURCE='8b8db298eba294876c27bd9a3200881f872684df'
PROVIDER_SOURCE='05adae5c9829472306e85b6b3b4aac068e79a5ec'
PUBLIC={
 'Ranvier.View':('0.1.46','bc9a8dec1b7428da52f62fe926772cc841e6c0d76494ac28fe78b49d7876d1fb'),
 'Ranvier.View.Traced':('0.1.46','0722c39ffca099cded1fde871e10a8bcc0f45eb6935e971375404456752604a0'),
 'Ranvier.View.Dom':('0.1.46','fdc23e3d55fef6cdf5685e475861f587bc0a09dd8027715fe498b2b64027ff70'),
 'Ranvier.View.Dom.Traced':('0.1.46','29d1bae6aa5e0965c1a88522ad342f6d42a5ce03dadfaa177fb042e4171f2cb9'),
 'Ranvier.View.WebCore':('0.1.0-alpha.46','b9727e57b67881970fb77771a77e5bae7abcbe9b355239964e74d5eb1c97251e'),
 'Ranvier.View.WebCore.Traced':('0.1.0-alpha.46','d940925e96027b3dd600b9faa385ff060f0b4d8cc759ac5fa93a5c69ab519599'),
 'Ranvier.View.WebCore.Sdl':('0.1.0-alpha.46','a8b46515a51d9e08f0ed7f51a5848cbfd3af9a4c5964ce3783fd61811f0bdba2'),
 'Ranvier.View.WebCore.Sdl.Traced':('0.1.0-alpha.46','d8c62d4544861fce7e67c652f0156c7f9ef0ba9ad8b86167c2de7afd0b9ea074'),
 'Ranvier':('0.1.1-preview.1','fba88bba064128f4edb6a2e927f784560d4b3268c3a9a2d684f317ea2a827a2d'),
 'Ranvier.Traced':('0.1.1-preview.1','75ca08706143315f6f08db10fa9feee9032cf0666f0dc2aa44b44b6408db8ea6'),
 'Ranvier.Dom':('0.1.0-alpha.58','3888a085a01676f95e59cb5a0a91449daf99a7ee05f00ff8f1883547990f0658'),
 'Ranvier.Dom.Traced':('0.1.0-alpha.58','663ef00ed6fddbc022ab09a619cf902c7ca78c26f0b068246611c338d3e8392e'),
 'Ranvier.WebCore':('0.1.1-preview.11','761136a5f618755ebbfa698afe4a2fbdd5893bc28812fbfd274633b7c674577b'),
 'Ranvier.WebCore.Native.linux-x64':('0.1.1-preview.11','0be487e2bafacf7930ae98ed6b15e6fe1080bfdaf31a694b983abbdc4925abe2'),
 'Ranvier.WebCore.Native.linux-arm64':('0.1.1-preview.11','649d7e9e405cda6bda5c4a11fb02c774673b5ba6e3e29de3ef0601fdd0ed70c4'),
}
HOST={'linux-x64':'29d884e207dadf98cfb11552faa6d5304856c43b6516b19d4ae278cbdb6dd0ac',
      'linux-arm64':'daa08ce43551bd04c819c09d5d4ac6b8a89ae7a776b3135373e3266170c5a388'}


def selected(mode,rid):
    if mode not in ('normal','traced') or rid not in HOST: raise ValueError('Unsupported mode or RID')
    suffix='.Traced' if mode=='traced' else ''
    return {name+suffix for name in ('Ranvier','Ranvier.Dom','Ranvier.View','Ranvier.View.Dom','Ranvier.View.WebCore','Ranvier.View.WebCore.Sdl')} | {'Ranvier.WebCore','Ranvier.WebCore.Native.'+rid}


def program_bytes(path):
    data=path.read_bytes().replace(b'\r\n',b'\n')
    if hashlib.sha256(data).hexdigest()!=PROGRAM_SHA: raise ValueError('AccessibilityAot program differs')
    return data


def validate_graph(assets,mode,rid,provider_id,provider_version,provider_sha,private_feed):
    libraries=assets['libraries']; expected=selected(mode,rid)
    if any(value.get('type')=='project' for value in libraries.values()): raise ValueError('Project source fallback')
    family={name.casefold() for name in PUBLIC} | {provider_id.casefold()}
    actual=[(key.rsplit('/',1)[0].casefold(),key.rsplit('/',1)[1]) for key in libraries
            if key.rsplit('/',1)[0].casefold() in family or key.rsplit('/',1)[0].casefold().startswith('ranvier.webcore.native.')]
    required={(name.casefold(),PUBLIC[name][0]) for name in expected}|{(provider_id.casefold(),provider_version)}
    if len(actual)!=len(required) or set(actual)!=required: raise ValueError('Mixed or missing public package graph')
    if 'FSharp.Core/10.1.403' not in libraries: raise ValueError('Wrong FSharp.Core')
    targets=[target for name,target in assets['targets'].items() if name.endswith('/'+rid)]
    if len(targets)!=1: raise ValueError('Ambiguous RID target')
    host_refs=[(key,name) for key,value in targets[0].items() for category in ('native','runtimeTargets')
               for name in value.get(category,{}) if name.casefold().endswith('libranvierwebcorehost.so')]
    if len(host_refs)!=1 or host_refs[0][0]!='Ranvier.WebCore.Native.'+rid+'/0.1.1-preview.11':
        raise ValueError('Wrong selected native Host')
    folders=[Path(folder) for folder in assets['packageFolders']]
    provider=libraries[provider_id+'/'+provider_version]
    found=[folder/provider['path'] for folder in folders if (folder/provider['path']/'.nupkg.metadata').is_file()]
    if len(found)!=1 or Path(json.loads((found[0]/'.nupkg.metadata').read_text())['source']).resolve()!=private_feed.resolve():
        raise ValueError('Provider package source differs')
    archive=found[0]/(provider_id.lower()+'.'+provider_version.lower()+'.nupkg')
    if managed.sha(archive)!=provider_sha: raise ValueError('Provider package hash differs')
    for name in expected:
        version,digest=PUBLIC[name]; item=libraries[name+'/'+version]
        found=[folder/item['path'] for folder in folders if (folder/item['path']/'.nupkg.metadata').is_file()]
        if len(found)!=1 or json.loads((found[0]/'.nupkg.metadata').read_text())['source'].rstrip('/')!='https://api.nuget.org/v3/index.json': raise ValueError('Public package source differs: '+name)
        archive=found[0]/(name.lower()+'.'+version.lower()+'.nupkg')
        if managed.sha(archive)!=digest: raise ValueError('Public package hash differs: '+name)


def config_file(path,feed,provider_id):
    root=ET.Element('configuration');sources=ET.SubElement(root,'packageSources');ET.SubElement(sources,'clear')
    ET.SubElement(sources,'add',key='private',value=str(feed));ET.SubElement(sources,'add',key='nuget',value='https://api.nuget.org/v3/index.json')
    mappings=ET.SubElement(root,'packageSourceMapping');private=ET.SubElement(mappings,'packageSource',key='private')
    ET.SubElement(private,'package',pattern=provider_id);public=ET.SubElement(mappings,'packageSource',key='nuget');ET.SubElement(public,'package',pattern='*')
    path.write_bytes(ET.tostring(root))


def project_file(path,mode,rid,provider_id,provider_version):
    root=ET.Element('Project',Sdk='Microsoft.NET.Sdk');props=ET.SubElement(root,'PropertyGroup')
    for name,value in [('OutputType','Exe'),('TargetFramework','net10.0'),('AssemblyName','AccessibilityAot'),('FSharpCoreImplicitPackageVersion','10.1.403'),('DefineConstants','ATSPI_STYLE_TRIAL'),('PublishAot','true'),('TrimmerSingleWarn','false'),('TreatWarningsAsErrors','true'),('IlcTreatWarningsAsErrors','true'),('ILLinkTreatWarningsAsErrors','true')]: ET.SubElement(props,name).text=value
    items=ET.SubElement(root,'ItemGroup');ET.SubElement(items,'Compile',Include='Program.fs')
    for name in sorted(selected(mode,rid)): ET.SubElement(items,'PackageReference',Include=name,Version='['+PUBLIC[name][0]+']')
    ET.SubElement(items,'PackageReference',Include=provider_id,Version='['+provider_version+']')
    ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('program','native','package','output'): parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--rid',choices=tuple(HOST),required=True);parser.add_argument('--package-sha256',required=True)
    parser.add_argument('--runtime-admission',type=Path)
    parser.add_argument('--xvfb-tcp',action='store_true');args=parser.parse_args()
    managed.validate_architecture(args.rid,platform.machine())
    program=program_bytes(args.program)
    if managed.sha(args.native)!=HOST[args.rid]: raise ValueError('Public Host differs')
    package_sha=managed.sha(args.package)
    if package_sha!=args.package_sha256: raise ValueError('Provider package hash differs')
    with zipfile.ZipFile(args.package) as z:
        manifest=json.loads(z.read('provider-manifest.json'));managed.validate_source_claim(manifest,PROVIDER_SOURCE)
        provider_id=managed.PROVIDER_ID if args.rid=='linux-arm64' else 'Ranvier.Private.Accessibility.Atspi.X64Qualification'
        if manifest['id']!=provider_id or manifest['rid']!=args.rid or manifest['hostSha256']!=HOST[args.rid]: raise ValueError('Provider identity/Host/RID differs')
        for name,digest in manifest['payloads'].items():
            if hashlib.sha256(z.read(name)).hexdigest()!=digest: raise ValueError('Provider payload differs')
    work=args.output.resolve();work.mkdir(parents=True,exist_ok=False);feed=work/'feed';feed.mkdir()
    provider_id=manifest['id'];provider_version=manifest['version']
    shutil.copy2(args.package,feed/(provider_id+'.'+provider_version+'.nupkg'))
    config=work/'NuGet.Config';config_file(config,feed,provider_id)
    (work/'global.json').write_text(json.dumps({'sdk':{'version':'10.0.403','rollForward':'disable'}}))
    if subprocess.check_output(['dotnet','--version'],cwd=work,text=True).strip()!='10.0.403': raise ValueError('Wrong SDK')
    projects={};graphs={}
    for mode in ('normal','traced'):
        source=work/('source-'+mode);source.mkdir();(source/'Program.fs').write_bytes(program)
        project=source/'AccessibilityAot.fsproj';project_file(project,mode,args.rid,provider_id,provider_version)
        output=work/('publish-'+mode);artifacts=work/('artifacts-'+mode)
        command=['dotnet','publish',str(project),'-c','Release','-r',args.rid,'-m:1','/nr:false',
                 '-p:RestoreConfigFile='+str(config),'-p:RestorePackagesPath='+str(work/'cache'),'-p:NuGetAudit=false',
                 '-p:UseSharedCompilation=false','--artifacts-path',str(artifacts),'-o',str(output)]
        managed.validate_publish_log(managed.run_checked(command,work/('publish-'+mode+'.log'),cwd=work))
        assets=artifacts/'obj/AccessibilityAot/project.assets.json';validate_graph(json.loads(assets.read_text()),mode,args.rid,provider_id,provider_version,package_sha,feed)
        managed.validate_elf(subprocess.check_output(['readelf','-h','-d',str(output/'AccessibilityAot')],text=True),args.rid)
        for name,digest in [('libRanvierWebCoreHost.so',HOST[args.rid]),('libRanvierWebCoreAtspi.so',manifest['providerSha256'])]:
            if managed.sha(output/name)!=digest: raise ValueError('Published native asset differs: '+name)
        projects[mode]=output;graphs[mode]={'path':str(assets),'sha256':managed.sha(assets)}
    receipt=dict(architecture=platform.machine(),rid=args.rid,sourceRevision=PROVIDER_SOURCE,nativeSource=NATIVE_SOURCE,
                 nativeVersion='0.1.1-preview.11',sourceProvenance=manifest['sourceProvenance'],hostSha256=HOST[args.rid],
                 providerSha256=manifest['providerSha256'],packageSha256=package_sha,domVersion='0.1.0-alpha.58',
                 publicViewVersion='0.1.46',assetGraphs=graphs,runs=[])
    if args.runtime_admission:
        files=[args.native,args.package,*[Path(record['path']) for record in graphs.values()]]
        for output in projects.values(): files.extend(output/name for name in ('AccessibilityAot','libRanvierWebCoreHost.so','libRanvierWebCoreAtspi.so','libSDL3.so'))
        receipt['runtimeAdmission']=managed.await_runtime_admission(args.runtime_admission,work,files)
    managed.run_profiles(work,projects,receipt,None,args.xvfb_tcp)


if __name__=='__main__': main()
