import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('abi_layouts', ROOT / 'tests' / 'abi' / 'abi_layouts.py')
abi_layouts = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(abi_layouts)


class AbiLayoutTests(unittest.TestCase):
    def test_issue_structs_have_the_expected_64_bit_layouts(self):
        expected = {
            'RvImageDataLayout': (40, [0, 4, 8, 12, 16, 20, 24, 32]),
            'RvImageBitmapOptions': (48, [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44]),
            'RvDomKeyframeAnimationOptions':
                (168, [0, 8, 16, 24, 32, 40, 48, 56, 64, 88, 92, 96, 120, 144, 152, 160]),
        }
        for name, (size, offsets) in expected.items():
            with self.subTest(name=name):
                _, actual_size, actual_offsets, _ = abi_layouts.LAYOUTS[name]
                self.assertEqual((actual_size, actual_offsets), (size, offsets))

    def test_native_probe_comparison_rejects_offset_drift(self):
        actual = {
            name: (size, offsets.copy())
            for name, (_, size, offsets, _) in abi_layouts.LAYOUTS.items()
        }
        actual['RvImageDataLayout'][1][-1] += 8
        with self.assertRaisesRegex(AssertionError, 'RvImageDataLayout compiler offsets'):
            abi_layouts.check_native_layouts(actual)


if __name__ == '__main__':
    unittest.main()
