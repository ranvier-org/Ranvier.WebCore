import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class GpuCohort(unittest.TestCase):
    def setUp(self):
        path = ROOT / 'scripts/recover_preview12_gpu_cohort.py'
        self.assertTrue(path.is_file(), 'Four-RID GPU exporter is missing')
        spec = importlib.util.spec_from_file_location('gpu_cohort', path)
        self.subject = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.subject)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.package = Path(self.temp.name) / 'fixture.nupkg'
        data = bytearray(20)
        data[:6] = b'\x7fELF\x02\x01'
        struct.pack_into('<HH', data, 16, 3, 62)
        self.data = bytes(data)
        self.manifest = dict(rid='linux-x64', flavor='gpu', version=self.subject.VERSION, abi=64,
            webkit=self.subject.WEBKIT, source=dict(commit=self.subject.PRODUCT, dirty=False, builder='ci'),
            files=[dict(name='libRanvierWebCoreHost.so', bytes=len(data), sha256=hashlib.sha256(data).hexdigest())], total_bytes=len(data))

    def package_check(self, extra=False):
        with zipfile.ZipFile(self.package, 'w') as archive:
            archive.writestr('fixture.nuspec', '<package><metadata><id>Ranvier.WebCore.Native.Gpu.linux-x64</id><version>' + self.subject.VERSION + '</version></metadata></package>')
            archive.writestr('manifest.json', json.dumps(self.manifest))
            archive.writestr('runtimes/linux-x64/native/libRanvierWebCoreHost.so', self.data)
            if extra:
                archive.writestr('runtimes/linux-x64/native/extra', b'extra')
        return self.subject.verify_package(self.package, 'linux-x64', self.subject.sha(self.package))

    def test_exact_gpu_package_passes(self):
        self.assertEqual(self.package_check(), self.manifest)

    def test_source_flavor_abi_and_unknown_payload_reject(self):
        for key, value in [('abi', 63), ('abi', True), ('flavor', 'slim'), ('source', dict(commit='a' * 40, dirty=False, builder='ci'))]:
            old = self.manifest[key]
            self.manifest[key] = value
            with self.assertRaises(ValueError):
                self.package_check()
            self.manifest[key] = old
        with self.assertRaises(ValueError):
            self.package_check(extra=True)

    def test_inner_payload_tamper_rejects(self):
        self.data += b'tampered'
        with self.assertRaises(ValueError):
            self.package_check()

    def resource_check(self, name):
        resource = b'png'
        self.manifest['files'].append(dict(name=name, bytes=len(resource), sha256=hashlib.sha256(resource).hexdigest()))
        self.manifest['total_bytes'] += len(resource)
        with zipfile.ZipFile(self.package, 'w') as archive:
            archive.writestr('fixture.nuspec', '<package><metadata><id>Ranvier.WebCore.Native.Gpu.linux-x64</id><version>' + self.subject.VERSION + '</version></metadata></package>')
            archive.writestr('manifest.json', json.dumps(self.manifest))
            archive.writestr('runtimes/linux-x64/native/libRanvierWebCoreHost.so', self.data)
            archive.writestr('runtimes/linux-x64/native/' + name, resource)
        return self.subject.verify_package(self.package, 'linux-x64', self.subject.sha(self.package))

    def test_nested_resource_payload_passes(self):
        self.assertEqual(self.resource_check('WebKit.resources/icons/missingImage.png'), self.manifest)

    def test_unsafe_manifest_names_reject(self):
        for name in ['../escape.png', 'WebKit.resources/../../escape.png', 'WebKit.resources\\icon.png',
                     '/abs.png', 'C:x.png', 'WebKit.resources/./icon.png']:
            self.setUp()
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.resource_check(name)

    def test_policy_is_unarmed_and_incomplete_never_admits(self):
        policy = json.loads((ROOT / 'docs/preview12-gpu-cohort.json').read_text())
        policy.update(armed=False, publicationEnabled=False)
        with self.assertRaises(ValueError):
            self.subject.admit_policy(policy)
        policy.update(armed=True, publicationEnabled=True, controllerSource=None)
        with self.assertRaises(ValueError):
            self.subject.admit_policy(policy)

    def test_windows_admits_only_a_probe_step_failure_after_packaging(self):
        run = dict(status='completed', conclusion='failure', head_sha=self.subject.PRODUCT,
            head_branch='v' + self.subject.VERSION, event='workflow_dispatch', run_attempt=1,
            path='.github/workflows/build.yml', repository={'full_name': self.subject.REPO}, head_repository={'full_name': self.subject.REPO})

        def job(conclusion, steps):
            return dict(total_count=1, jobs=[dict(name='native (win-x64, gpu)', conclusion=conclusion,
                steps=[dict(name=name, conclusion=value) for name, value in steps])])

        packaged = [('Package', 'success'), ('Run the probes', 'failure'), ('Upload the probe logs', 'success')]
        self.subject.admit_windows_run(run, job('failure', packaged))
        for conclusion, steps in [('success', packaged),
                                  ('failure', [('Package', 'failure'), ('Run the probes', 'failure')]),
                                  ('failure', [('Package', 'success'), ('Run the probes', 'failure'), ('Build', 'failure')]),
                                  ('failure', [('Package', 'success'), ('Run the probes', 'success')]),
                                  ('failure', [('Package', 'success'), ('Run the probes', 'cancelled')]),
                                  ('failure', [('Package', 'success'), ('Run the probes', 'timed_out')]),
                                  ('failure', [('Package', 'success'), ('Run the probes', None)])]:
            with self.subTest(conclusion=conclusion, steps=steps), self.assertRaises(ValueError):
                self.subject.admit_windows_run(run, job(conclusion, steps))
        incomplete = job('failure', packaged)
        incomplete['total_count'] = 2
        with self.assertRaises(ValueError):
            self.subject.admit_windows_run(run, incomplete)

    def windows_probes(self, first, log=b'tests/gpu/windows_view_transition_pixels.py\nassert ... == 63\nAssertionError\n'):
        path = Path(self.temp.name) / 'probes.zip'
        summary = (first + '\nFAIL 3.0 s  ' + self.subject.WINDOWS_GUARD + '  (exit code 1), 02-guard.log\n').encode()
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('summary.txt', summary)
            archive.writestr('02-guard.log', log)
        record = dict(summarySha256=hashlib.sha256(summary).hexdigest(), failureLogSha256=hashlib.sha256(log).hexdigest())
        return path, record

    def test_windows_probes_retain_only_the_pinned_abi_guard(self):
        expected = [dict(name='Other native contract'), dict(name=self.subject.WINDOWS_GUARD)]
        path, record = self.windows_probes('PASS 0.1 s  Other native contract')
        self.subject.verify_windows_probes(path, record, expected)
        path, record = self.windows_probes('FAIL 0.1 s  Other native contract  (exit code 1), 01-other.log')
        with self.assertRaisesRegex(ValueError, 'Unexpected'):
            self.subject.verify_windows_probes(path, record, expected)
        path, record = self.windows_probes('PASS 0.1 s  Other native contract', log=b'pixel mismatch\nAssertionError\n')
        with self.assertRaisesRegex(ValueError, 'guard'):
            self.subject.verify_windows_probes(path, record, expected)
        path, record = self.windows_probes('PASS 0.1 s  Other native contract')
        with self.assertRaisesRegex(ValueError, 'inventory'):
            self.subject.verify_windows_probes(path, record, expected[1:])
        record['failureLogSha256'] = 'f' * 64
        with self.assertRaisesRegex(ValueError, 'guard'):
            self.subject.verify_windows_probes(path, record, expected)

    def replay_fixture(self, change=None, omit=None):
        s = self.subject
        original = b'original immutable proof fixture'
        record = dict(replayController='a' * 40, replayRun=123,
            originalGlyphReceiptSha256='e' * 64,
            proofArtifact=dict(id=13282342479, sha256=hashlib.sha256(original).hexdigest()),
            packageArtifact=dict(id=13281332839, sha256='b' * 64))
        native = {row['name']: row['sha256'] for row in self.manifest['files']}
        prefix = s.CAPTURE_PREFIX
        members = {'original-proof.zip': original, 'public-output-input.log': b'outer replay command output'}
        for name in s.CAPTURES:
            members[prefix + name] = b'BMP fixture:' + name.encode()
        for name in s.PUBLIC_STEPS:
            members[prefix + name + '.log'] = b'actual log fixture:' + name.encode()
        logs = {name: hashlib.sha256(data).hexdigest() for name, data in members.items()
                if name.startswith(prefix) and name.endswith('.log')}
        public = dict(passed=True, nativeBefore=native, nativeAfter=native, steps=[dict(name=name,
            exit=1 if name == 'reject-steady-base-repaint' else 0,
            expectedFailure='MAC_GPU_SPIKE FAIL transform and opacity animation reuse base backing',
            logSha256=logs[prefix + name + '.log']) for name in s.PUBLIC_STEPS])
        members[prefix + 'receipt.json'] = json.dumps(public).encode()
        receipt = dict(schemaVersion=1, boundary='immutable-d31-gpu-public-capture-replay-v1',
            productSource=s.PRODUCT, controlSource=record['replayController'], run=123,
            originalRun=s.ORIGINAL_MAC_RUN, originalController=s.ORIGINAL_MAC_CONTROL,
            originalProofArtifact=record['proofArtifact']['id'], originalProofSha256=record['proofArtifact']['sha256'],
            originalGlyphReceiptSha256=record['originalGlyphReceiptSha256'],
            packageArtifact=record['packageArtifact']['id'], packageArchiveSha256=record['packageArtifact']['sha256'],
            packageSha256='c' * 64, nativeBefore=native, nativeAfter=native, nativeUnchanged=True,
            productClean=True, controlClean=True, originalAccepted=True, originalGlyphPinned=True,
            originalPhases=dict(build=True, helpers=True, qualify=True), passed=True,
            originalTransportComplete=False, engineBuild=False, hostBuild=False, helperBuild=False,
            catalogueRepeated=False, glyphRepeated=False, packageUnchanged=True, acquisitionCredentialsRemoved=True,
            ownedProcessesExited=True, remainingOwnedProcesses=[],
            steps=[dict(name='public-output-input', exit=0, groupKillRequested=True, directChildReaped=True,
                        logSha256=hashlib.sha256(members['public-output-input.log']).hexdigest())],
            rawCaptureMembers={name: hashlib.sha256(data).hexdigest() for name, data in members.items() if name.endswith('.bmp')},
            rawLogMembers=logs, publicReceipt=prefix + 'receipt.json',
            publicReceiptSha256=hashlib.sha256(members[prefix + 'receipt.json']).hexdigest())
        if change:
            change(receipt)
        members['capture-replay.json'] = json.dumps(receipt).encode()
        record['replayReceiptSha256'] = hashlib.sha256(members['capture-replay.json']).hexdigest()
        if omit:
            members.pop(prefix + omit)
        seal = dict(schemaVersion=1, layout='mac-recovery-proof-root-v1', sources=[],
                    members={name: hashlib.sha256(data).hexdigest() for name, data in members.items()})
        members['artifact-members.json'] = json.dumps(seal).encode()
        path = Path(self.temp.name) / 'replay.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            for name, data in members.items():
                archive.writestr(name, data)
        s.verify_mac_replay(path, record, self.manifest, 'c' * 64)

    def test_mac_stitched_replay_preserves_original_failure(self):
        self.replay_fixture()

    def test_mac_missing_raw_capture_or_cleanup_and_scope_tampering_reject(self):
        with self.assertRaises(ValueError):
            self.replay_fixture(omit='input-15-scrolled.bmp')
        for key, value in [('originalTransportComplete', True), ('engineBuild', True), ('nativeAfter', {}),
                           ('originalPhases', {}), ('ownedProcessesExited', False), ('rawCaptureMembers', {})]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.replay_fixture(change=lambda receipt: receipt.update({key: value}))

    def test_original_mac_only_named_transport_step_may_fail(self):
        expected = ['Recover the warm immutable product', 'Retain immutable product package',
            'Retain immutable product manifest', 'Build matching helpers',
            'Collect the independent immutable product gates', 'Always retain original SDK and helper proof']
        rows = [dict(name=name, conclusion='success') for name in expected]
        rows.append(dict(name='Consolidate the explicit owned proof root', conclusion='failure'))
        jobs = dict(total_count=1, jobs=[dict(name='recover', conclusion='failure', steps=rows)])
        self.subject.admit_mac_job(jobs)
        rows[3]['conclusion'] = 'failure'
        with self.assertRaises(ValueError):
            self.subject.admit_mac_job(jobs)

    def test_changed_glyph_receipt_rejects_before_oracle(self):
        path = Path(self.temp.name) / 'glyph.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('glyph-proof/orientation.json', '{}')
        with zipfile.ZipFile(path) as archive, self.assertRaises(ValueError):
            self.subject.verify_glyph(archive, {'originalGlyphReceiptSha256': 'a' * 64}, Path(self.temp.name) / 'glyph')


if __name__ == '__main__':
    unittest.main()
