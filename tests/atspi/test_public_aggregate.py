"""Hermetic aggregate/receipt validation; no synthetic library is loaded or renderer qualified."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[2]
SCRIPT=ROOT/'providers/atspi/public_aggregate.py'
if SCRIPT.exists():
    spec=importlib.util.spec_from_file_location('public_aggregate',SCRIPT)
    aggregate=importlib.util.module_from_spec(spec); spec.loader.exec_module(aggregate)
else: aggregate=None


class AggregatePolicyTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(aggregate,'The aggregate validator is not implemented.')
        self.temporary=tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.policy=dict(schemaVersion=1,armed=True,id='Ranvier.WebCore.Accessibility.Atspi',version='0.1.1-preview.8',
                         nativeVersion='0.1.1-preview.8',nativeSource='1'*40,providerSourceClaim='2'*40,abi=63,rids={})
        self.inputs={}; self.receipts={}
        for rid,machine in [('linux-x64',62),('linux-arm64',183)]:
            data=bytearray(64); data[:6]=b'\x7fELF\x02\x01'; data[18:20]=machine.to_bytes(2,'little')
            payload={'runtimes/'+rid+'/native/libRanvierWebCoreAtspi.so':bytes(data),
                     'include/RanvierAtspi.h':(ROOT/'providers/atspi/RanvierAtspi.h').read_bytes(),
                     'include/RanvierWebCoreAbi.h':(ROOT/'host/RanvierWebCoreAbi.h').read_bytes(),
                     'NOTICE.md':b'fixture input notice', 'THIRD-PARTY.md':(ROOT/'providers/atspi/THIRD-PARTY.md').read_bytes(),
                     'licenses/LGPL-2.1.txt':(ROOT/'providers/atspi/licenses/LGPL-2.1.txt').read_bytes(), 'README.md':b'fixture qualification readme',
                     'tools/sdk-check.py':b'fixture passive SDK tooling'}
            manifest=dict(id='Ranvier.Private.Atspi.'+rid,version='0.0.0-ci.1',rid=rid,abi=63,
                          callerClaimedProviderSourceRevision='2'*40,sourceProvenance='unverified-caller-claim',
                          requiredCapability='accessibility-text-style',hostBundled=False,
                          hostSha256=('a' if rid=='linux-x64' else 'b')*64,
                          providerSha256=hashlib.sha256(payload['runtimes/'+rid+'/native/libRanvierWebCoreAtspi.so']).hexdigest(),
                          licenseMetadataStatus='original-project-license-unspecified; embedded-XML-license-not-marked',
                          payloads={name:hashlib.sha256(value).hexdigest() for name,value in payload.items()})
            path=self.root/(rid+'.nupkg'); self.inputs[rid]=path
            self.write_package(path,manifest,payload)
            modes={}
            for mode in ['normal','traced']:
                modes[mode]={profile:dict(passed=True,windows=3,directHosts=3,expectedAttached=profile=='present',dynamicCodeSupported=False,
                                         nativeUnchanged=True,ownedProcessesExited=True,nonBmpStyle=profile=='present') for profile in ['present','absent','no-bus']}
            receipt=dict(schemaVersion=1,rid=rid,abi=63,nativeVersion='0.1.1-preview.8',nativeSource='1'*40,providerSourceClaim='2'*40,
                         hostSha256=manifest['hostSha256'],providerSha256=manifest['providerSha256'],
                         packageSha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                         checks=dict(nativeExports=347,directStyleAssertions=23,protocolAssertions=dict(direct=84,queued=84,session=84),
                                     ordinarySdkConsumer=True,managedAot=modes))
            receipt_path=self.root/(rid+'.json'); self.receipts[rid]=receipt_path
            receipt_path.write_text(json.dumps(receipt))
            self.policy['rids'][rid]=dict(packageSha256=receipt['packageSha256'],receiptSha256=hashlib.sha256(receipt_path.read_bytes()).hexdigest())

    def write_package(self,path,manifest,payload):
        with zipfile.ZipFile(path,'w') as archive:
            archive.writestr('input.nuspec','<package><metadata><id>'+manifest['id']+'</id><version>'+manifest['version']+'</version></metadata></package>')
            archive.writestr('provider-manifest.json',json.dumps(manifest))
            for name,value in payload.items(): archive.writestr(name,value)

    def mutate_package(self,rid,change):
        path=self.inputs[rid]
        with zipfile.ZipFile(path) as archive:
            manifest=json.loads(archive.read('provider-manifest.json'))
            payload={name:archive.read(name) for name in archive.namelist() if name not in ['input.nuspec','provider-manifest.json']}
        change(manifest,payload)
        manifest['providerSha256']=hashlib.sha256(payload['runtimes/'+rid+'/native/libRanvierWebCoreAtspi.so']).hexdigest()
        manifest['payloads']={name:hashlib.sha256(value).hexdigest() for name,value in payload.items()}
        self.write_package(path,manifest,payload)
        receipt=json.loads(self.receipts[rid].read_text()); receipt['packageSha256']=hashlib.sha256(path.read_bytes()).hexdigest(); receipt['providerSha256']=manifest['providerSha256']
        self.receipts[rid].write_text(json.dumps(receipt))
        self.policy['rids'][rid].update(packageSha256=receipt['packageSha256'],receiptSha256=hashlib.sha256(self.receipts[rid].read_bytes()).hexdigest())

    def test_unarmed_example_cannot_assemble_public_artifact(self):
        policy=json.loads((ROOT/'providers/atspi/public-cohort.example.json').read_text())
        with self.assertRaisesRegex(ValueError,'unarmed'): aggregate.prepare(policy,self.inputs,self.receipts)

    def test_one_manifest_selects_two_distinct_native_payloads_without_a_host(self):
        payload,manifest=aggregate.prepare(self.policy,self.inputs,self.receipts)
        self.assertEqual(set(manifest['runtimes']),{'linux-x64','linux-arm64'})
        self.assertEqual(manifest['id'],'Ranvier.WebCore.Accessibility.Atspi')
        self.assertEqual(manifest['sourceProvenance'],'unverified-caller-claim')
        self.assertFalse(manifest['hostBundled'])
        self.assertEqual(len([name for name in payload if name.endswith('.so')]),2)
        self.assertFalse(any('libRanvierWebCoreHost.so' in name for name in payload))

    def test_common_sdk_header_tooling_or_notice_disagreement_is_rejected(self):
        for name in ['include/RanvierAtspi.h','include/RanvierWebCoreAbi.h','tools/sdk-check.py','NOTICE.md']:
            with self.subTest(name=name):
                with zipfile.ZipFile(self.inputs['linux-arm64']) as archive: original=archive.read(name)
                self.mutate_package('linux-arm64',lambda _manifest,payload:payload.update({name:original+b'changed'}))
                with self.assertRaises(ValueError): aggregate.prepare(self.policy,self.inputs,self.receipts)
                self.mutate_package('linux-arm64',lambda _manifest,payload:payload.update({name:original}))

    def test_mixed_abi_source_claim_capability_or_architecture_is_rejected(self):
        for name,value in [('abi',62),('abi',63.0),('callerClaimedProviderSourceRevision','9'*40),('sourceProvenance','verified'),('requiredCapability','old-style')]:
            with self.subTest(name=name):
                with zipfile.ZipFile(self.inputs['linux-arm64']) as archive: original=json.loads(archive.read('provider-manifest.json'))[name]
                self.mutate_package('linux-arm64',lambda manifest,_payload:manifest.update({name:value}))
                with self.assertRaises(ValueError): aggregate.prepare(self.policy,self.inputs,self.receipts)
                self.mutate_package('linux-arm64',lambda manifest,_payload:manifest.update({name:original}))
        self.mutate_package('linux-arm64',lambda _manifest,payload:payload.update({'runtimes/linux-arm64/native/libRanvierWebCoreAtspi.so':b'wrong ELF architecture'}))
        with self.assertRaisesRegex(ValueError,'ELF'): aggregate.prepare(self.policy,self.inputs,self.receipts)

    def test_missing_or_altered_qualification_receipt_blocks_a_rid(self):
        path=self.receipts['linux-arm64']; receipt=json.loads(path.read_text())
        receipt['checks']['managedAot']['traced']['present']['passed']=False
        path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError,'receipt'): aggregate.prepare(self.policy,self.inputs,self.receipts)
        self.policy['rids']['linux-arm64']['receiptSha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaises(ValueError): aggregate.prepare(self.policy,self.inputs,self.receipts)
        missing=deepcopy(self.receipts); del missing['linux-arm64']
        with self.assertRaises(ValueError): aggregate.prepare(self.policy,self.inputs,missing)

    def test_paths_and_unexpected_rid_cannot_inject_payloads(self):
        self.mutate_package('linux-arm64',lambda _manifest,payload:payload.update({'../escape':b'bad'}))
        with self.assertRaises(ValueError): aggregate.prepare(self.policy,self.inputs,self.receipts)
        self.policy['rids']['win-x64']={}
        with self.assertRaises(ValueError): aggregate.prepare(self.policy,self.inputs,self.receipts)

    def test_duplicate_case_paths_and_missing_required_upstream_text_are_rejected(self):
        self.mutate_package('linux-arm64',lambda _manifest,payload:payload.update({'include/ranvieratspi.h':b'duplicate SDK path'}))
        with self.assertRaises(ValueError): aggregate.prepare(self.policy,self.inputs,self.receipts)
        self.mutate_package('linux-arm64',lambda _manifest,payload:payload.pop('include/ranvieratspi.h'))
        for rid in self.inputs: self.mutate_package(rid,lambda _manifest,payload:payload.pop('licenses/LGPL-2.1.txt'))
        with self.assertRaises(ValueError): aggregate.prepare(self.policy,self.inputs,self.receipts)

    def test_a_second_host_cannot_hide_among_common_sdk_files(self):
        for rid in self.inputs:
            self.mutate_package(rid,lambda _manifest,payload:payload.update({'sdk/libRanvierWebCoreHost.so':b'not a permitted SDK file'}))
        with self.assertRaisesRegex(ValueError,'binary'): aggregate.prepare(self.policy,self.inputs,self.receipts)

    def test_unarmed_pack_never_creates_work_or_public_output(self):
        self.assertTrue(callable(getattr(aggregate,'pack',None)),'The guarded SDK pack entry point is missing.')
        policy=json.loads((ROOT/'providers/atspi/public-cohort.example.json').read_text())
        with self.assertRaisesRegex(ValueError,'unarmed'):
            aggregate.pack(policy,self.inputs,self.receipts,self.root/'output',self.root/'work')
        self.assertFalse((self.root/'output').exists())
        self.assertFalse((self.root/'work').exists())

    def test_case_variant_cannot_collide_with_aggregate_metadata(self):
        for rid in self.inputs:
            self.mutate_package(rid,lambda _manifest,payload:payload.update({'public-readme.md':b'owner path collision'}))
        with self.assertRaises(ValueError): aggregate.prepare(self.policy,self.inputs,self.receipts)

    def test_both_inputs_cannot_replace_required_upstream_text_with_matching_placeholders(self):
        for rid in self.inputs:
            self.mutate_package(rid,lambda _manifest,payload:payload.update({'licenses/LGPL-2.1.txt':b'matching placeholder'}))
        with self.assertRaisesRegex(ValueError,'license|notice'): aggregate.prepare(self.policy,self.inputs,self.receipts)


if __name__=='__main__': unittest.main()
