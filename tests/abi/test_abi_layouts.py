import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


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

    def test_msvc_probe_intermediates_are_confined_to_temporary_directory(self):
        expected_output = '\n'.join(
            f'{name}|{size}|{",".join(str(offset) for offset in offsets)}'
            for name, (_, size, offsets, _) in abi_layouts.LAYOUTS.items()
        ) + '\n'
        caller = Path.cwd()

        def run(command, **kwargs):
            working = Path(kwargs['cwd'])
            self.assertNotEqual(working, caller)
            if command[0].endswith('cl.exe'):
                (working / 'abi_layout_probe.obj').write_bytes(b'probe object')
                return subprocess.CompletedProcess(command, 0, '', '')
            return subprocess.CompletedProcess(command, 0, expected_output, '')

        with (
            patch.object(abi_layouts.shutil, 'which', side_effect=lambda name: 'C:/tools/cl.exe' if name == 'cl' else None),
            patch.object(abi_layouts.subprocess, 'run', side_effect=run),
        ):
            actual = abi_layouts.run_native_probe()

        self.assertEqual(actual['RvImageDataLayout'], (40, [0, 4, 8, 12, 16, 20, 24, 32]))
        self.assertFalse((caller / 'abi_layout_probe.obj').exists())


if __name__ == '__main__':
    unittest.main()
