import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parents[1]


class ExportBinding(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('slim_export', ROOT / 'scripts/recover_preview12_slim.py')
        self.subject = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.subject)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.packages = self.root / 'origin'
        self.packages.mkdir()
        self.payloads = {name + '.' + self.subject.VERSION + '.nupkg': name.encode() for name in self.subject.PACKAGE_IDS}
        for name, data in self.payloads.items():
            if name.startswith('Ranvier.WebCore.Native.'):
                (self.packages / name).write_bytes(data)
        self.hashes = {name.removesuffix('.' + self.subject.VERSION + '.nupkg'): hashlib.sha256(data).hexdigest()
                       for name, data in self.payloads.items()}
        self.inputs = dict(product={'fixture': 'a' * 64}, controller={'fixture': 'b' * 64})
        self.origin = dict(originalJobs={'fixture': 'original'}, mac={'originalAccepted': False,
            'helperCompletion': {'uploadByteComplete': False, 'runtimeConsumerQualification': False}})
        self.manifests = {rid: {'fixture': rid} for rid in self.subject.RIDS}
        self.expected = {'fixture': {'returns': 'int'}}
        self.report = {'fixture': 'actual metadata checked separately'}
        self.expected_raw = json.dumps(self.expected).encode()
        self.report_raw = json.dumps(self.report).encode()
        self.q = dict(run=42, workflowSource='b' * 40, policySha256='c' * 64,
            proofArtifact={'id': 1}, packagesArtifact={'id': 2}, packageHashes=self.hashes)
        self.policy = dict(controllerSource='b' * 40, qualification=self.q)
        native = {path.name: self.subject.sha(path) for path in self.packages.iterdir()}
        self.receipt = dict(accepted=True, signedPublic=False, sourcesUnchanged=True, productSource=self.subject.PRODUCT,
            controllerSource='b' * 40, producerRun=self.subject.PRODUCER_RUN, policySha256='c' * 64,
            sourceInputs=self.inputs, origin=copy.deepcopy(self.origin), nativeManifests=self.manifests,
            packages=self.hashes, nativePackagesBefore=native, nativePackagesAfter=native,
            inspectorSourceSha256=self.subject.sha(ROOT / 'tests/recovery/InteropMetadata/Program.cs'),
            inspectorReportSha256=hashlib.sha256(self.report_raw).hexdigest(),
            expectedSignaturesSha256=hashlib.sha256(self.expected_raw).hexdigest(),
            steps=[dict(name=name, exit=0, directChildReaped=True, ownedGroupNoLiveMembers=True) for name in
                   ['generated-signatures', 'canonical-managed-pack', 'inspector-build', 'inspector-run']])
        self.proof = self.root / 'proof.zip'
        self.compiled = self.root / 'packages.zip'
        self.run = dict(id=42, head_sha='b' * 40, path='.github/workflows/preview12-slim-recovery.yml',
            event='workflow_dispatch', head_branch='main', run_attempt=1, status='completed', conclusion='success',
            repository={'full_name': self.subject.REPO}, head_repository={'full_name': self.subject.REPO})
        self.jobs = dict(total_count=1, jobs=[dict(name='qualify-slim-preview12', conclusion='success')])

    def check(self):
        raw = json.dumps(self.receipt).encode()
        self.q['receiptSha256'] = hashlib.sha256(raw).hexdigest()
        with zipfile.ZipFile(self.proof, 'w') as archive:
            for name, data in [('qualification.json', raw), ('interop-metadata.json', self.report_raw),
                               ('expected-signatures.json', self.expected_raw)]:
                archive.writestr(name, data)
        with zipfile.ZipFile(self.compiled, 'w') as archive:
            for name, data in self.payloads.items():
                archive.writestr(name, data)
        product = self.root / 'product'
        product.mkdir(exist_ok=True)
        args = SimpleNamespace(product_root=product, output=self.root / 'export-output')
        with patch.object(self.subject, 'source_identity'), patch.object(self.subject, 'source_inputs', return_value=self.inputs), \
             patch.object(self.subject, 'signature_manifest', return_value=self.expected), \
             patch.object(self.subject, 'origins', return_value=(self.packages, self.manifests, self.origin)), \
             patch.object(self.subject, 'api', return_value=self.run), patch.object(self.subject, 'jobs', return_value=self.jobs), \
             patch.object(self.subject, 'artifact', side_effect=lambda record, *args: self.proof if record['id'] == 1 else self.compiled), \
             patch.object(self.subject, 'verify_native') as native, patch.object(self.subject, 'verify_managed') as managed:
            self.subject.export(args, self.policy)
            self.assertEqual(native.call_count, 5)
            managed.assert_called_once()
        return args.output

    def test_success_exports_exact_seven_bytes_and_unsigned_pre_authentication(self):
        output = self.check()
        self.assertEqual({path.name: path.read_bytes() for path in (output / 'export').iterdir()}, self.payloads)
        receipt = json.loads((output / 'pre-authentication.json').read_text())
        self.assertFalse(receipt['signedPublic'])
        self.assertEqual(receipt['packages'], self.hashes)

    def test_rehashed_receipt_cannot_upgrade_stitched_scope(self):
        self.receipt['origin']['mac']['originalAccepted'] = True
        with self.assertRaisesRegex(ValueError, 'Qualification evidence'):
            self.check()

    def test_rehashed_receipt_cannot_hide_failed_child_or_surviving_descendant(self):
        self.receipt['steps'][-1]['ownedGroupNoLiveMembers'] = False
        with self.assertRaisesRegex(ValueError, 'Qualification evidence'):
            self.check()

    def test_changed_source_inputs_reject_before_export(self):
        self.receipt['sourceInputs'] = {'unreviewed': 'source'}
        with self.assertRaisesRegex(ValueError, 'Qualification evidence'):
            self.check()

    def test_missing_or_substituted_managed_package_is_rejected(self):
        self.payloads.pop('Ranvier.WebCore.' + self.subject.VERSION + '.nupkg')
        with self.assertRaisesRegex(ValueError, 'package set'):
            self.check()

    def test_changed_export_package_bytes_reject(self):
        self.payloads['Ranvier.WebCore.' + self.subject.VERSION + '.nupkg'] = b'changed'
        with self.assertRaisesRegex(ValueError, 'package bytes'):
            self.check()


if __name__ == '__main__':
    unittest.main()
