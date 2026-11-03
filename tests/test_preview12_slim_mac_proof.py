import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class MacProof(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('slim', ROOT / 'scripts/recover_preview12_slim.py')
        self.subject = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.subject)
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.package = self.root / 'fixture.nupkg'
        binary = struct.pack('<IIII', 0xfeedfacf, 0x100000c, 0, 6)
        native = {name: hashlib.sha256(binary).hexdigest() for name in
                  ['libRanvierWebCoreHost.dylib', 'libWebCore.dylib', 'libJavaScriptCore.dylib', 'libWebGPU.dylib']}
        self.manifest = dict(files=[dict(name=name, sha256=value) for name, value in native.items()])
        raw_manifest = json.dumps(self.manifest).encode()
        with zipfile.ZipFile(self.package, 'w') as archive:
            archive.writestr('manifest.json', raw_manifest)
        self.files = {name + '.dylib': binary for name in ['timer', 'page', 'motion', 'contrast']}
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('inputs/sdk/config.h', 'immutable fixture input')
        capsule = buffer.getvalue()
        self.compile = {}
        for name in ['timer', 'page']:
            self.files[name + '/consumed-inputs.zip'] = capsule
            self.compile[name] = dict(status='compiled', inputsUnchanged=True, runtimeUnchanged=True,
                runtimeBefore=native, runtimeAfter=native, inputsBefore={'fixture': 'a' * 64}, inputsAfter={'fixture': 'a' * 64},
                hostReplaced=False, headerReconstruction=False, engineCompilation=False, compilerSha256='a' * 64,
                compileCommandsSha256='b' * 64, producerConfigurationSha256='c' * 64,
                consumedInputsArchiveSha256=hashlib.sha256(capsule).hexdigest(),
                steps=[dict(name=step, exit=0) for step in ['dependencies', 'compile', 'link', 'final-install-name',
                                                        'sign-helper', 'verify-helper-signature', 'helper-dependencies']],
                commands=[['clang', '-Wl,-undefined,error', '-Wl,-install_name,@rpath/libTestWebCore.dylib']])
        self.sidecars = dict(boundary='producer-Host-unchanged-sidecars-v1', status='compiled', abi=64, declarations=349,
            nativeSource=self.subject.PRODUCT, controllerSource='b' * 40, producerSourceAfter=self.subject.PRODUCT,
            controllerSourceAfter='b' * 40, sourcesUnchanged=True, controllerTrackedDirty=False,
            unsignedPackageSha256=self.subject.sha(self.package), nativeBefore=native, nativeAfter=native,
            nativeUnchanged=True, hostReplaced=False, headerReconstruction=False, engineCompilation=False,
            helpers={name:dict(path=name + '.dylib', sha256=hashlib.sha256(binary).hexdigest()) for name in ['timer', 'page', 'motion', 'contrast']},
            appkitConsumedInputs={}, appkitInputs={'sdk/config.h': 'a' * 64}, commands=[])
        for name in ['motion', 'contrast']:
            self.files[name + '-consumed-inputs.zip'] = capsule
            self.sidecars['appkitConsumedInputs'][name] = dict(path=name + '-consumed-inputs.zip', sha256=hashlib.sha256(capsule).hexdigest())
            self.sidecars['commands'] += [dict(name=name + '-' + step, exit=0,
                argv=['clang', '-Wl,-undefined,error'] if step == 'compile' else [step]) for step in ['compile', 'sign', 'verify']]
        product = '/Users/runner/work/product'
        gates = [('-B', product + '/scripts/build.py', 'smoke', '--rid', 'osx-arm64', '--flavor', 'slim', '--version', self.subject.VERSION, '--work', '/Users/runner/rw'),
                 ('-I', product + '/tests/abi/mutation_observation.py', '--native-directory', '/Users/runner/rw/out/slim/runtimes/osx-arm64/native'),
                 ('-I', product + '/scripts/probes.py', 'run', '--rid', 'osx-arm64', '--flavor', 'slim', '--work', '/Users/runner/rw', '--expected-abi', '64')]
        self.recovery = dict(accepted=True, publication=False, productSource=self.subject.PRODUCT, controlSource='b' * 40,
            workflowRun='7', flavor='slim', version=self.subject.VERSION, reviewedHelperSource=self.subject.HELPER_SOURCE,
            helperBlobs=self.subject.HELPER_BLOBS, productRoot=product, controlRoot='/private/control',
            phases={name:dict(passed=True, productClean=True, builderClean=True, identityErrors=[]) for name in ['build', 'helpers', 'qualify']},
            commands=[dict(name=name, phase='qualify', exit=0, directChildReaped=True, argv=['python3', *command])
                      for name, command in zip(['smoke', 'mutation', 'probes'], gates)])
        self.recovery['phases']['build'].update(native=native, packageSha256=self.subject.sha(self.package),
            manifestSha256=hashlib.sha256(raw_manifest).hexdigest())
        self.record = dict(run=7, workflowSource='b' * 40, proofPrefix='retained/exact-evidence/')
        self.proof = self.root / 'proof.zip'

    def tearDown(self):
        self.temporary.cleanup()

    def write(self):
        for name, value in self.compile.items():
            self.files[name + '/build-receipt.json'] = json.dumps(value).encode()
        self.sidecars['artifacts'] = {name:hashlib.sha256(value).hexdigest() for name, value in self.files.items()}
        raw = json.dumps(self.sidecars).encode()
        self.record['sidecarReceiptSha256'] = hashlib.sha256(raw).hexdigest()
        recovery = json.dumps(self.recovery).encode()
        self.record['recoveryReceiptSha256'] = hashlib.sha256(recovery).hexdigest()
        with zipfile.ZipFile(self.proof, 'w') as archive:
            prefix = self.record['proofPrefix']
            archive.writestr(prefix + 'recovery-receipt.json', recovery)
            archive.writestr(prefix + 'sidecars/producer-sidecars.json', raw)
            for name, value in self.files.items():
                archive.writestr(prefix + 'sidecars/' + name, value)

    def check(self):
        self.write()
        return self.subject.verify_mac_proof(self.proof, self.record, self.manifest, self.package)

    def test_all_independent_gates_and_exact_nonroot_proof_prefix_pass(self):
        result = self.check()
        self.assertEqual(result['productSource'], self.subject.PRODUCT)
        self.assertEqual(result['controlSource'], 'b' * 40)

    def test_failed_native_phase_rejects_even_with_rehashed_receipts(self):
        self.recovery['phases']['qualify']['passed'] = False
        with self.assertRaisesRegex(ValueError, 'phases'):
            self.check()

    def test_fake_success_command_is_not_native_qualification(self):
        self.recovery['commands'][2]['argv'] = ['echo', 'passed']
        with self.assertRaisesRegex(ValueError, 'original F commands'):
            self.check()

    def test_sidecar_H_cannot_be_relabelled_as_F(self):
        self.sidecars['controllerSource'] = self.subject.PRODUCT
        with self.assertRaisesRegex(ValueError, 'boundary'):
            self.check()

    def test_replaced_host_rejects_even_when_source_labels_match(self):
        self.sidecars['hostReplaced'] = True
        with self.assertRaisesRegex(ValueError, 'boundary'):
            self.check()

    def test_missing_appkit_capsule_rejects(self):
        del self.sidecars['appkitConsumedInputs']['motion']
        with self.assertRaisesRegex(ValueError, 'AppKit'):
            self.check()

    def test_helper_link_suppression_rejects(self):
        self.compile['page']['commands'] = [['clang', '-Wl,-undefined,dynamic_lookup']]
        with self.assertRaisesRegex(ValueError, 'strict-link'):
            self.check()

    def test_changed_sdk_capsule_rejects_even_if_artifact_map_is_rehashed(self):
        self.files['page/consumed-inputs.zip'] = b'changed'
        with self.assertRaisesRegex(ValueError, 'capsule'):
            self.check()

    def completion_fixture(self):
        self.recovery['accepted'] = False
        self.recovery['phases']['helpers']['passed'] = False
        self.sidecars.update(status='failed', error='motion-compile failed', headerSha256='2' * 64,
                             appkitCompilerSha256='3' * 64, appkitSdk='/sdk26')
        self.sidecars['helpers'] = {name:self.sidecars['helpers'][name] for name in ['timer', 'page']}
        self.files['motion-compile.log'] = b'undefined ___gxx_personality_v0'
        self.write()
        prior = self.subject.verify_mac_proof(self.proof, self.record, self.manifest, self.package, partial=True)
        self.record['proofArtifact'] = dict(sha256=self.subject.sha(self.proof))
        self.record['packageArtifact'] = dict(sha256=hashlib.sha256(b'original-package-artifact').hexdigest())
        expected = {row['name']:row['sha256'] for row in self.manifest['files']}
        data = dict(boundary='immutable-d31-slim-stitched-helper-completion-v1', accepted=True, status='compiled',
                    productSource=self.subject.PRODUCT, helperControlSource='c' * 40, completionRun='9', originalRun=7,
                    originalControllerSource='b' * 40, originalPhases=dict(build=True, helpers=False, qualify=True),
                    originalProofPrefix=self.record['proofPrefix'], helperBuilderGitBlob='f626b86e23f8e78e5b08adcf17b58c7ec1efbf67',
                    inputsContractSha256='a' * 64, headerSha256=prior['headerSha256'], abi=64, declarations=349,
                    nativeBefore=expected, nativeAfter=expected, packageSha256=self.subject.sha(self.package),
                    compilerSha256=prior['compilerSha256'], sdk=prior['sdk'], compilerInvocation='/bin/clang++', helpers={})
        for key in ['productBuildRepeated', 'nativeGatesRepeated', 'engineCompilation', 'timerPageRecompiled', 'publication', 'runtimeConsumerQualification']:
            data[key] = False
        for key in ['nativeUnchanged', 'sourcesUnchanged', 'archivesUnchanged', 'packageUnchanged', 'compilerUnchanged',
                    'originalConsumedInputsVerified', 'originalConsumedInputsUnchanged', 'acquisitionCredentialsRemoved']:
            data[key] = True
        files = {'proof.zip':self.proof.read_bytes(), 'package.zip':b'original-package-artifact'}
        for name in ['timer', 'page']:
            old = prior['retainedTimerPage'][name]
            data['helpers'][name] = dict(path='retained-sidecars/' + old['path'], sha256=old['sha256'], reusedFromRun=7,
                receipt=f'retained-sidecars/{name}/build-receipt.json', capsule=f'retained-sidecars/{name}/consumed-inputs.zip')
            for member in [old['path'], name + '/build-receipt.json', name + '/consumed-inputs.zip']:
                files['retained-sidecars/' + member] = self.files[member]
        binary = self.files['motion.dylib']
        files['driver-control/new.dylib'] = binary
        driver = dict(result='PASS', source='c' * 40, compilerSha256=prior['compilerSha256'], oldStrictLinkFailed=True,
                      newStrictLinkPassed=True, actualProbe=0, helperSha256=hashlib.sha256(binary).hexdigest(),
                      sourceUnchanged=True, compilerUnchanged=True, probeUnchanged=True, engineBuild=False, nativePackageLoaded=False)
        files['driver-control/driver-diagnostic.json'] = json.dumps(driver).encode()
        names = ['driver-control', 'motion-dependencies', 'motion-compile', 'motion-sign', 'motion-verify',
                 'contrast-dependencies', 'contrast-compile', 'contrast-sign', 'contrast-verify']
        data['commands'] = [dict(name=name, exit=0, directChildReaped=True, argv=['/bin/clang++', '-Wl,-undefined,error']) for name in names]
        for name in ['motion', 'contrast']:
            path = 'libRanvierCocoa' + name.title() + '.dylib'
            files[path] = binary
            files[name + '-consumed-inputs.zip'] = self.files[name + '-consumed-inputs.zip']
            data['helpers'][name] = dict(path=path, sha256=hashlib.sha256(binary).hexdigest(), compiledInRun='9',
                capsule=name + '-consumed-inputs.zip', capsuleSha256=hashlib.sha256(files[name + '-consumed-inputs.zip']).hexdigest(),
                inputs={'/sdk/config.h':hashlib.sha256(b'immutable fixture input').hexdigest()})
        return data, files, prior

    def check_completion(self, data, files, prior):
        data['members'] = {name:hashlib.sha256(value).hexdigest() for name, value in files.items()}
        raw = json.dumps(data).encode()
        completion = dict(run=9, workflowSource='c' * 40, inputsContractSha256='a' * 64, receiptSha256=hashlib.sha256(raw).hexdigest())
        path = self.root / 'completion.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('helper-completion.json', raw)
            for name, value in files.items():
                archive.writestr(name, value)
        return self.subject.verify_helper_completion(path, completion, self.record, prior, self.manifest, self.package)

    def test_stitch_preserves_original_failure_and_separate_new_helper_scope(self):
        data, files, prior = self.completion_fixture()
        result = self.check_completion(data, files, prior)
        self.assertFalse(prior['originalAccepted'])
        self.assertFalse(result['runtimeConsumerQualification'])
        self.assertTrue(result['stitchedHelpersCompiled'])

    def test_recompiled_timer_cannot_be_relabelled_as_reuse(self):
        data, files, prior = self.completion_fixture()
        data['helpers']['timer']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'Timer/page'):
            self.check_completion(data, files, prior)

    def test_stitch_rejects_acquisition_token_leak_or_new_runtime_claim(self):
        data, files, prior = self.completion_fixture()
        for key, value in [('acquisitionCredentialsRemoved', False), ('runtimeConsumerQualification', True), ('engineCompilation', True)]:
            original = data[key]
            data[key] = value
            with self.assertRaisesRegex(ValueError, 'boundary'):
                self.check_completion(data, files, prior)
            data[key] = original

    def test_stitch_requires_actual_positive_driver_control(self):
        data, files, prior = self.completion_fixture()
        control = json.loads(files['driver-control/driver-diagnostic.json'])
        control['actualProbe'] = -1
        files['driver-control/driver-diagnostic.json'] = json.dumps(control).encode()
        with self.assertRaisesRegex(ValueError, 'driver control'):
            self.check_completion(data, files, prior)

    def test_stitch_rejects_changed_new_compiler_input_even_when_outer_receipt_rehashed(self):
        data, files, prior = self.completion_fixture()
        data['helpers']['motion']['inputs']['/sdk/config.h'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'input bytes'):
            self.check_completion(data, files, prior)


if __name__ == '__main__':
    unittest.main()
