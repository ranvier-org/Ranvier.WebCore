import importlib.util
from pathlib import Path, PurePosixPath
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('glyph_recovery', ROOT / 'scripts/mac_preview12_recovery.py')
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


class GlyphRecoveryTests(unittest.TestCase):
    def test_public_glyph_control_consumes_f_sources_and_exact_native_stage(self):
        product, native, output = PurePosixPath('/actual-F'), PurePosixPath('/actual-F-native'), PurePosixPath('/owned-proof')
        commands = dict(recovery.glyph_recipe(product, native, output, ['-I/pinned-sdl/include', '-lSDL3']))
        self.assertEqual(list(commands), ['glyph-compile', 'glyph-capture', 'glyph-oracle'])
        compile = [str(value) for value in commands['glyph-compile']]
        self.assertIn('/actual-F/tests/gpu/mac/glyph_orientation.mm', compile)
        self.assertIn('-DRANVIER_MAC_PUBLIC_TRANSPORT=1', compile)
        self.assertIn('-Wl,-undefined,error', compile)
        self.assertIn('-L/actual-F-native', compile)
        self.assertIn('-Wl,-rpath,/actual-F-native', compile)
        self.assertEqual(commands['glyph-capture'], [output / 'glyph-orientation', '--output', output])
        self.assertIn(product / 'tests/gpu/mac/glyph_orientation.py', commands['glyph-oracle'])
        self.assertNotIn(str(ROOT), ' '.join(compile))
        self.assertNotIn('build.py', ' '.join(compile))


if __name__ == '__main__':
    unittest.main()
