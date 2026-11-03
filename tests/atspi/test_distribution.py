import importlib.util
from pathlib import Path
import unittest
import shutil
import subprocess
import tempfile
from unittest.mock import patch
from types import SimpleNamespace

source = Path(__file__).resolve().parents[2] / 'providers/atspi/package.py'
spec = importlib.util.spec_from_file_location('atspi_package', source)
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class DistributionPolicyTests(unittest.TestCase):
    def test_runtime64_requires_explicit_selection_instead_of_default63(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = [Path(temporary) / name for name in ['provider.so', 'host.so']]
            image = bytearray(64)
            image[:6] = b'\x7fELF\x02\x01'
            image[18:20] = (62).to_bytes(2, 'little')
            for path in paths:
                path.write_bytes(image)
            host = SimpleNamespace(rv_abi_version=lambda: 64, rv_abi_has=lambda name: 1)
            with patch.object(package.subprocess, 'check_output', return_value='(RUNPATH) [$ORIGIN]'), \
                    patch.object(package.ctypes, 'CDLL', return_value=host):
                with self.assertRaises(ValueError):
                    package.validate_runtime(*paths, 'linux-x64')
                self.assertEqual(package.validate_runtime(*paths, 'linux-x64', expected_host_abi=64), 64)
                host.rv_abi_version = lambda: 65
                with self.assertRaises(ValueError):
                    package.validate_runtime(*paths, 'linux-x64', expected_host_abi=64)

    def test_host_abi_is_exact_and_style_capability_remains_required(self):
        for abi in [63, 64]:
            self.assertEqual(package.validate_host_abi(abi, abi, 1), abi)
        for actual, expected, capability in [(64, 63, 1), (63, 64, 1), (65, 65, 1), (64, 64, 0), (True, 63, 1)]:
            with self.subTest(actual=actual, expected=expected, capability=capability), self.assertRaises(ValueError):
                package.validate_host_abi(actual, expected, capability)

    @unittest.skipUnless(shutil.which('cc'), 'A C compiler is required for the installed SDK header check.')
    def test_public_header_compiles_without_repository_layout(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copy2(source.parent / 'RanvierAtspi.h', root)
            shutil.copy2(source.parents[2] / 'host/RanvierWebCoreAbi.h', root)
            (root / 'consumer.c').write_text('#include "RanvierAtspi.h"\nint main(void) { return 0; }\n')
            result = subprocess.run(['cc', '-fsyntax-only', '-I', str(root), str(root / 'consumer.c')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_arm_runtime_requires_actual_qualification(self):
        with self.assertRaisesRegex(ValueError, 'qualified'):
            package.validate_distribution('linux-arm64', '5b34cc0dd3932d434fd3f0c35c6bfc6497c3bd6c')

    def test_arm_test_only_mode_does_not_enable_ordinary_distribution(self):
        revision = '1' * 40
        package.validate_distribution('linux-arm64', revision, test_only_arm64=True)
        with self.assertRaisesRegex(ValueError, 'ARM64'):
            package.validate_distribution('linux-x64', revision, test_only_arm64=True)

    def test_malformed_caller_source_claim_is_rejected(self):
        for revision in ['', 'HEAD', '../source', '5b34cc0d']:
            with self.subTest(revision=revision), self.assertRaisesRegex(ValueError, 'revision'):
                package.validate_distribution('linux-x64', revision)

    def test_qualified_x64_source_is_accepted(self):
        package.validate_distribution('linux-x64', '5b34cc0dd3932d434fd3f0c35c6bfc6497c3bd6c')

    def test_unallocated_public_identity_cannot_be_packed(self):
        with self.assertRaisesRegex(ValueError, 'private'):
            package.validate_identity('Ranvier.WebCore.Accessibility.Atspi', '0.1.1-preview.8')

    def test_private_identity_requires_private_or_ci_version(self):
        with self.assertRaisesRegex(ValueError, 'private'):
            package.validate_identity('Ranvier.Private.Atspi.Control', '1.0.0')
        package.validate_identity('Ranvier.Private.Atspi.Control', '0.0.0-private182.1')
        package.validate_identity('Ranvier.Private.Atspi.Control', '0.0.0-ci.1234')

    def test_private_cohort_labels_are_claims_not_qualification(self):
        for label in ['private-unspecified', 'private-style-only-abi63', 'private-da11-abi347']:
            package.validate_cohort_label(label)
        for label in ['', 'final-abi347', 'public-linux-x64', '../private-test', 'private-X64', 'private-', 'private-a/b', 'private-test\n']:
            with self.subTest(label=label), self.assertRaisesRegex(ValueError, 'cohort label'):
                package.validate_cohort_label(label)


if __name__ == '__main__':
    unittest.main()
