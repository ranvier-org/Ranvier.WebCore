import ctypes
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
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


    def test_probe_directory_cleanup_retries_transient_lock(self):
        directory = Path(tempfile.mkdtemp(prefix='ranvier-abi-layout-cleanup-test-'))
        (directory / 'abi_layout_probe.exe').write_bytes(b'owned probe')
        real_rmtree = shutil.rmtree
        attempts = []

        def fail_once(path):
            attempts.append(Path(path))
            if len(attempts) == 1:
                raise PermissionError(5, 'temporary delete-sharing lock')
            return real_rmtree(path)

        with patch.object(abi_layouts.shutil, 'rmtree', side_effect=fail_once), patch('time.sleep'):
            abi_layouts.cleanup_probe_directory(directory)

        self.assertEqual(len(attempts), 2)
        self.assertTrue(all(path == directory for path in attempts))
        self.assertFalse(directory.exists())

    def test_probe_directory_cleanup_surfaces_persistent_lock_and_retains_path(self):
        directory = Path(tempfile.mkdtemp(prefix='ranvier-abi-layout-cleanup-test-'))
        probe = directory / 'abi_layout_probe.exe'
        probe.write_bytes(b'owned probe')
        attempts = []

        def remain_locked(path):
            attempts.append(Path(path))
            raise PermissionError(5, 'temporary delete-sharing lock')

        try:
            with patch.object(abi_layouts.shutil, 'rmtree', side_effect=remain_locked), patch('time.sleep'):
                with self.assertRaises(PermissionError) as caught:
                    abi_layouts.cleanup_probe_directory(directory)
                self.assertIn(str(directory), str(caught.exception))
            self.assertGreater(len(attempts), 1)
            self.assertLessEqual(len(attempts), 5)
            self.assertTrue(probe.exists())
        finally:
            shutil.rmtree(directory)

    @unittest.skipUnless(os.name == 'nt', 'Win32 file sharing is Windows-specific')
    def test_probe_directory_cleanup_recovers_after_owned_win32_delete_lock(self):
        directory = Path(tempfile.mkdtemp(prefix='ranvier-abi-layout-win32-lock-'))
        probe = directory / 'abi_layout_probe.exe'
        probe.write_bytes(b'owned probe')
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                                         ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
        kernel32.CreateFileW.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int
        handle = kernel32.CreateFileW(str(probe), 0x80000000, 0x1 | 0x2, None, 3, 0x80, None)
        if handle in (None, ctypes.c_void_p(-1).value):
            raise ctypes.WinError(ctypes.get_last_error())
        sleep_calls = []

        def release_owned_lock(_delay):
            sleep_calls.append(1)
            if len(sleep_calls) == 1:
                self.assertTrue(kernel32.CloseHandle(handle))

        try:
            with patch('time.sleep', side_effect=release_owned_lock):
                abi_layouts.cleanup_probe_directory(directory)
            self.assertEqual(len(sleep_calls), 1)
            self.assertFalse(directory.exists())
        finally:
            if probe.exists():
                kernel32.CloseHandle(handle)
                shutil.rmtree(directory)

    def test_native_layout_result_is_checked_and_logged_before_temp_cleanup(self):
        expected_output = '\n'.join(
            f'{name}|{size}|{",".join(str(offset) for offset in offsets)}'
            for name, (_, size, offsets, _) in abi_layouts.LAYOUTS.items()
        ) + '\n'
        events = []
        original_check = abi_layouts.check_native_layouts
        original_cleanup = getattr(abi_layouts, 'cleanup_probe_directory', None)

        def check(actual):
            events.append(('check', actual))
            return original_check(actual)

        def cleanup(directory):
            events.append(('cleanup', Path(directory)))
            return original_cleanup(directory)

        def run(command, **kwargs):
            events.append(('subprocess', tuple(command)))
            if command[0].endswith('cl.exe'):
                return subprocess.CompletedProcess(command, 0, '', '')
            return subprocess.CompletedProcess(command, 0, expected_output, '')

        with (
            patch.object(abi_layouts.shutil, 'which', side_effect=lambda name: 'C:/tools/cl.exe' if name == 'cl' else None),
            patch.object(abi_layouts.subprocess, 'run', side_effect=run),
            patch.object(abi_layouts, 'check_native_layouts', side_effect=check),
            patch.object(abi_layouts, 'cleanup_probe_directory', side_effect=cleanup),
            patch('builtins.print', side_effect=lambda *args, **kwargs: events.append(('print', ' '.join(map(str, args))))),
        ):
            actual = abi_layouts.run_native_probe()

        self.assertEqual(actual['RvImageDataLayout'], (40, [0, 4, 8, 12, 16, 20, 24, 32]))
        check_index = next(i for i, item in enumerate(events) if item[0] == 'check')
        cleanup_index = next(i for i, item in enumerate(events) if item[0] == 'cleanup')
        self.assertLess(check_index, cleanup_index)
        self.assertTrue(any(item[0] == 'print' and 'exit=0' in item[1] for item in events[:cleanup_index]))


if __name__ == '__main__':
    unittest.main()
