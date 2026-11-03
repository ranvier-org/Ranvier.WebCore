"""Release-record consistency controls; metadata fixtures never load native code."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[2]
path=ROOT/'providers/atspi/release_candidate.py'
spec=importlib.util.spec_from_file_location('atspi_release_candidate',path) if path.exists() else None
candidate=importlib.util.module_from_spec(spec) if spec else None
if spec:spec.loader.exec_module(candidate)


class ReleaseCandidateTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(candidate,'Release-candidate recorder is missing.')
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.cohort=dict(schemaVersion=1,armed=True,id='Ranvier.WebCore.Accessibility.Atspi',version='0.1.1-preview.10',nativeVersion='0.1.1-preview.10',nativeSource='1'*40,providerSourceClaim='2'*40,abi=63,rids={rid:dict(packageSha256='a'*64,receiptSha256='b'*64) for rid in ['linux-x64','linux-arm64']})
        self.manifest=dict(schemaVersion=2,id=self.cohort['id'],version=self.cohort['version'],nativeVersion=self.cohort['nativeVersion'],abi=63,callerClaimedNativeSourceRevision='1'*40,callerClaimedProviderSourceRevision='2'*40,sourceProvenance='unverified-caller-claim',hostBundled=False,runtimes={rid:dict(rid=rid,abi=63,hostSha256='c'*64,providerSha256='d'*64,inputPackageSha256='a'*64,qualificationReceiptSha256='b'*64) for rid in self.cohort['rids']})
        self.package=self.root/'fixture.nupkg'
        with zipfile.ZipFile(self.package,'w') as archive:archive.writestr('provider-manifest.json',json.dumps(self.manifest))
        self.packageSha=hashlib.sha256(self.package.read_bytes()).hexdigest()
        self.record=dict(path=str(self.package),sha256=self.packageSha,manifest=self.manifest)
        self.recordPath=self.root/'aggregate.json';self.recordPath.write_text(json.dumps(self.record))
        self.cohortPath=self.root/'cohort.json';self.cohortPath.write_text(json.dumps(self.cohort))
        self.layouts={}
        for rid in self.cohort['rids']:
            path=self.root/(rid+'.json');path.write_text(json.dumps(dict(packageSha256=self.packageSha,selectedRid=rid,selectedRuntime=self.manifest['runtimes'][rid],executed=False,consumer=None)))
            self.layouts[rid]=path

    def test_candidate_records_exact_bytes_without_enabling_publication(self):
        record=candidate.record_candidate(self.recordPath,self.cohortPath,self.layouts)
        self.assertFalse(record['publicationEnabled'])
        self.assertEqual(record['package']['sha256'],self.packageSha)
        self.assertEqual(set(record['sdkLayout']),set(self.layouts))
        self.assertEqual(record['sourceProvenance'],'unverified-caller-claim')
        self.assertIn('not renderer',record['scope'])

    def test_reviewed_provider12_host11_remains_distinct_in_release_record(self):
        self.cohort.update(schemaVersion=2,version='0.1.1-preview.12',nativeVersion='0.1.1-preview.11',
                           nativeSource='8b8db298eba294876c27bd9a3200881f872684df',
                           providerSourceClaim='05adae5c9829472306e85b6b3b4aac068e79a5ec')
        self.manifest.update(version=self.cohort['version'],nativeVersion=self.cohort['nativeVersion'],
                             callerClaimedNativeSourceRevision=self.cohort['nativeSource'],
                             callerClaimedProviderSourceRevision=self.cohort['providerSourceClaim'])
        with zipfile.ZipFile(self.package,'w') as archive: archive.writestr('provider-manifest.json',json.dumps(self.manifest))
        self.packageSha=hashlib.sha256(self.package.read_bytes()).hexdigest()
        self.record.update(sha256=self.packageSha,manifest=self.manifest)
        self.recordPath.write_text(json.dumps(self.record)); self.cohortPath.write_text(json.dumps(self.cohort))
        for path in self.layouts.values():
            value=json.loads(path.read_text()); value['packageSha256']=self.packageSha; path.write_text(json.dumps(value))
        record=candidate.record_candidate(self.recordPath,self.cohortPath,self.layouts)
        self.assertEqual(record['package']['version'],'0.1.1-preview.12')
        self.assertEqual(record['nativeVersion'],'0.1.1-preview.11')
        self.assertEqual(record['sourceProvenance'],'unverified-caller-claim')
        self.cohort['providerSourceClaim']='9'*40; self.cohortPath.write_text(json.dumps(self.cohort))
        with self.assertRaises(ValueError): candidate.record_candidate(self.recordPath,self.cohortPath,self.layouts)

    def test_missing_or_opposing_rid_and_execution_claim_are_rejected(self):
        with self.assertRaises(ValueError):candidate.record_candidate(self.recordPath,self.cohortPath,{'linux-x64':self.layouts['linux-x64']})
        for key,bad in [('selectedRid','linux-arm64'),('executed',True),('packageSha256','0'*64),('selectedRuntime',{})]:
            path=self.layouts['linux-x64'];original=json.loads(path.read_text());changed=deepcopy(original);changed[key]=bad;path.write_text(json.dumps(changed))
            with self.subTest(key=key),self.assertRaises(ValueError):candidate.record_candidate(self.recordPath,self.cohortPath,self.layouts)
            path.write_text(json.dumps(original))

    def test_changed_package_or_unarmed_cohort_is_rejected(self):
        original=self.package.read_bytes()
        self.package.write_bytes(original+b'changed')
        with self.assertRaises(ValueError):candidate.record_candidate(self.recordPath,self.cohortPath,self.layouts)
        self.package.write_bytes(original)
        self.cohort['armed']=False;self.cohortPath.write_text(json.dumps(self.cohort))
        with self.assertRaises(ValueError):candidate.record_candidate(self.recordPath,self.cohortPath,self.layouts)

    def test_checked_in_target_retains_null_public_allocation(self):
        value=json.loads((ROOT/'providers/atspi/public-cohort.example.json').read_text())
        self.assertFalse(value['armed'])
        self.assertIsNone(value['version'])
        self.assertEqual(value['nativeVersion'],'0.1.1-preview.10')
        self.assertEqual(value['nativeSource'],'233c8045c9384e5eb97e8688ca0ed0caa11a8f17')
        self.assertTrue(all(pin is None for record in value['rids'].values() for pin in record.values()))


if __name__=='__main__':unittest.main()
