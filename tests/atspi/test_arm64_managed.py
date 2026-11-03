import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).with_name('arm64_managed.py')
spec = importlib.util.spec_from_file_location('arm64_managed', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ManagedArm64Qualification(unittest.TestCase):
    def test_reusable_workflow_remains_unarmed(self):
        workflow = (path.parents[2] / '.github/workflows/atspi-arm64-qualification.yml').read_text()
        self.assertIn('if: ${{ false }}', workflow)
        self.assertIn("dotnet-version: '10.0.403'", workflow)

    def test_all_three_provider_profiles_are_required(self):
        self.assertEqual(module.PROFILES, ('present', 'absent', 'no-bus'))

    def test_x64_workflow_is_unarmed_and_passes_explicit_rid(self):
        workflow = (path.parents[2] / '.github/workflows/atspi-x64-qualification.yml').read_text()
        self.assertIn('if: ${{ false }}', workflow)
        self.assertIn('runs-on: ubuntu-24.04\n', workflow)
        self.assertIn('arm64_managed.py --rid linux-x64', workflow)
        self.assertIn('qualification_receipt.py --rid linux-x64', workflow)
        self.assertNotIn('--test-only-arm64', workflow)

    def test_selected_rid_requires_matching_runner_and_elf(self):
        for rid, machine, elf in [('linux-arm64', 'aarch64', 'AArch64'),
                                  ('linux-x64', 'x86_64', 'Advanced Micro Devices X86-64')]:
            module.validate_architecture(rid, machine)
            module.validate_elf('ELF64\nMachine: ' + elf, rid)
            other = 'linux-x64' if rid == 'linux-arm64' else 'linux-arm64'
            with self.assertRaises(ValueError):
                module.validate_architecture(other, machine)
            with self.assertRaises(ValueError):
                module.validate_elf('ELF64\nMachine: ' + elf, other)

    def test_x64_provider_graph_cannot_select_arm_package(self):
        provider = 'Ranvier.Private.Accessibility.Atspi.X64Qualification'
        libraries = {'Ranvier.Dom/0.1.0-alpha.57': {}, 'Ranvier/0.1.1-preview.1': {}, 'Ranvier.WebCore/private': {}, provider + '/1': {}}
        module.validate_assets(libraries, 'normal', 'private', '1', provider)
        del libraries[provider + '/1']
        libraries[module.PROVIDER_ID + '/1'] = {}
        with self.assertRaises(ValueError):
            module.validate_assets(libraries, 'normal', 'private', '1', provider)

    def test_native_aot_result_requires_all_lifecycles_and_no_dynamic_code(self):
        good = {'windows': 3, 'directHosts': 3, 'expectedAttached': True, 'dynamicCodeSupported': False}
        module.validate_result(good, True)
        for key, wrong in [('windows', 2), ('directHosts', 2), ('expectedAttached', False), ('dynamicCodeSupported', True)]:
            with self.subTest(key=key):
                bad = dict(good, **{key: wrong})
                with self.assertRaises(ValueError):
                    module.validate_result(bad, True)

    def test_trimming_warnings_and_always_throw_are_failures(self):
        module.validate_publish_log('build successful')
        for message in ('warning IL2026: missing metadata', 'method will always throw because: missing code'):
            with self.assertRaises(ValueError):
                module.validate_publish_log(message)

    def test_elf_requires_arm64_and_no_coreclr_dependency(self):
        module.validate_elf('Class: ELF64\nMachine: AArch64\nNEEDED libdl.so.2')
        for elf in ('Class: ELF64\nMachine: Advanced Micro Devices X86-64',
                    'Class: ELF64\nMachine: AArch64\nNEEDED libcoreclr.so'):
            with self.assertRaises(ValueError):
                module.validate_elf(elf)

    def test_package_claim_must_match_the_selected_producer_source(self):
        module.validate_source_claim({'callerClaimedProviderSourceRevision': 'a' * 40}, 'a' * 40)
        with self.assertRaises(ValueError):
            module.validate_source_claim({'callerClaimedProviderSourceRevision': 'b' * 40}, 'a' * 40)

    def test_package_graph_requires_matching_mode_core_interop_and_provider(self):
        libraries = {'Ranvier.Dom.Traced/0.1.0-alpha.57': {}, 'Ranvier.Traced/0.1.1-preview.1': {}, 'Ranvier.WebCore/0.0.0-arm64.1': {},
                     module.PROVIDER_ID + '/0.0.0-ci.5': {}}
        module.validate_assets(libraries, 'traced', '0.0.0-arm64.1', '0.0.0-ci.5')
        with self.assertRaises(ValueError):
            module.validate_assets(libraries, 'normal', '0.0.0-arm64.1', '0.0.0-ci.5')
        for extra in ('Ranvier/0.1.1-preview.1', 'Ranvier.Traced/0.1.1-preview.2', 'Ranvier.Dom/0.1.0-alpha.57', 'Ranvier.Dom.Traced/0.1.0-alpha.56', 'Ranvier.WebCore/0.1.1-preview.7',
                      module.PROVIDER_ID + '/0.0.0-ci.6'):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                module.validate_assets(dict(libraries, **{extra: {}}), 'traced', '0.0.0-arm64.1', '0.0.0-ci.5')


if __name__ == '__main__':
    unittest.main()
