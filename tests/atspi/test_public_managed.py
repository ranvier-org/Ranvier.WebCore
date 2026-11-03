"""Fail-closed public managed graph controls; no native code is executed."""
import hashlib
import io
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

path=Path(__file__).with_name('public_managed.py')
spec=importlib.util.spec_from_file_location('public_managed',path)
subject=importlib.util.module_from_spec(spec);spec.loader.exec_module(subject)


class PublicManagedTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.provider='Ranvier.Private.Accessibility.Atspi.X64Qualification'
        self.pins={name:(version,hashlib.sha256(name.encode()).hexdigest()) for name,(version,_) in subject.PUBLIC.items()}
        self.patch=patch.object(subject,'PUBLIC',self.pins);self.patch.start();self.addCleanup(self.patch.stop)
        self.feed=self.root/'feed';self.feed.mkdir();self.provider_sha=hashlib.sha256(b'provider').hexdigest()
        provider_path=self.provider.lower()+'/0.0.0-private12.1';folder=self.root/provider_path;folder.mkdir(parents=True)
        (folder/'.nupkg.metadata').write_text(json.dumps({'source':str(self.feed)}))
        (folder/(self.provider.lower()+'.0.0.0-private12.1.nupkg')).write_bytes(b'provider')
        self.libraries={'FSharp.Core/10.1.403':{'type':'package'},self.provider+'/0.0.0-private12.1':{'type':'package','path':provider_path}}
        for name in subject.selected('normal','linux-x64'):
            version,_=self.pins[name];relative=name.lower()+'/'+version.lower();folder=self.root/relative;folder.mkdir(parents=True)
            (folder/'.nupkg.metadata').write_text(json.dumps({'source':'https://api.nuget.org/v3/index.json'}))
            (folder/(name.lower()+'.'+version.lower()+'.nupkg')).write_bytes(name.encode())
            self.libraries[name+'/'+version]={'type':'package','path':relative}
        self.assets={'libraries':self.libraries,'packageFolders':{str(self.root):{}},
                     'targets':{'net10.0/linux-x64':{'Ranvier.WebCore.Native.linux-x64/0.1.1-preview.11':
                                {'native':{'runtimes/linux-x64/native/libRanvierWebCoreHost.so':{}}}}}}

    def test_exact_public_graph_passes(self):
        self.validate()

    def validate(self):
        subject.validate_graph(self.assets,'normal','linux-x64',self.provider,'0.0.0-private12.1',self.provider_sha,self.feed)

    def test_project_opposing_mode_duplicate_provider_and_wrong_rid_fail(self):
        cases=[('Project/1',{'type':'project'}),('rAnViEr.ViEw.TrAcEd/9.0',{'type':'package'}),
               (self.provider.lower()+'/0.0.0-private12.2',{'type':'package'}),
               ('Ranvier.WebCore.Native.linux-riscv64/0.1.1-preview.11',{'type':'package'}),
               ('Ranvier.WebCore.Native.Gpu.linux-x64/0.1.1-preview.11',{'type':'package'})]
        for key,value in cases:
            with self.subTest(key=key):
                self.libraries[key]=value
                with self.assertRaises(ValueError): self.validate()
                del self.libraries[key]

    def test_wrong_host_asset_fails(self):
        self.assets['targets']['net10.0/linux-x64']['other/1']={'native':{'libRanvierWebCoreHost.so':{}}}
        with self.assertRaisesRegex(ValueError,'Host'): self.validate()

    def test_package_hash_or_source_change_fails(self):
        name='Ranvier.View';version,_=self.pins[name];folder=self.root/self.libraries[name+'/'+version]['path']
        archive=folder/(name.lower()+'.'+version+'.nupkg');archive.write_bytes(b'wrong')
        with self.assertRaisesRegex(ValueError,'hash'): self.validate()
        archive.write_bytes(name.encode());(folder/'.nupkg.metadata').write_text(json.dumps({'source':'https://private.invalid'}))
        with self.assertRaisesRegex(ValueError,'source'): self.validate()

    def test_provider_cache_hash_and_source_are_bound(self):
        folder=self.root/self.libraries[self.provider+'/0.0.0-private12.1']['path']
        archive=folder/(self.provider.lower()+'.0.0.0-private12.1.nupkg');archive.write_bytes(b'other')
        with self.assertRaisesRegex(ValueError,'Provider package hash'): self.validate()
        archive.write_bytes(b'provider');(folder/'.nupkg.metadata').write_text(json.dumps({'source':'https://private.invalid'}))
        with self.assertRaisesRegex(ValueError,'Provider package source'): self.validate()

    def test_project_contains_only_package_references(self):
        project=self.root/'consumer.fsproj';subject.project_file(project,'traced','linux-arm64',self.provider,'0.0.0-private12.1')
        text=project.read_text();self.assertNotIn('ProjectReference',text);self.assertIn('Ranvier.View.WebCore.Sdl.Traced',text)
        self.assertIn('Ranvier.WebCore.Native.linux-arm64',text);self.assertIn('10.1.403',text)

    def test_program_pin_normalizes_checkout_line_endings_but_rejects_edits(self):
        path=self.root/'Program.fs';data=b'one\ntwo\n'
        with patch.object(subject,'PROGRAM_SHA',hashlib.sha256(data).hexdigest()):
            path.write_bytes(data.replace(b'\n',b'\r\n'));self.assertEqual(subject.program_bytes(path),data)
            path.write_bytes(data+b'changed')
            with self.assertRaisesRegex(ValueError,'program differs'): subject.program_bytes(path)

    def test_provider_claim_and_module_are_not_promoted_or_substituted(self):
        data=b'provider module';member='runtimes/linux-x64/native/libRanvierWebCoreAtspi.so';digest=hashlib.sha256(data).hexdigest()
        manifest=dict(id=self.provider,rid='linux-x64',hostSha256=subject.HOST['linux-x64'],
                      callerClaimedProviderSourceRevision=subject.PROVIDER_SOURCE,sourceProvenance='unverified-caller-claim',
                      hostBundled=False,providerSha256=digest,payloads={member:digest})
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as z: z.writestr(member,data)
        with zipfile.ZipFile(buffer) as z:
            subject.validate_provider(z,manifest,'linux-x64')
            for field,value in [('sourceProvenance','verified'),('hostBundled',True),('providerSha256','0'*64)]:
                altered=dict(manifest);altered[field]=value
                with self.subTest(field=field),self.assertRaises(ValueError): subject.validate_provider(z,altered,'linux-x64')


if __name__=='__main__': unittest.main()
