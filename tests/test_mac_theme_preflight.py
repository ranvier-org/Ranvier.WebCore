import importlib.util
from pathlib import Path
import tempfile
import unittest

path = Path(__file__).parent / 'gpu/mac/host_preflight.py'
spec = importlib.util.spec_from_file_location('host_preflight', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ThemeTranslationUnit(unittest.TestCase):
    def row(self, source, target='WebCoreDOMAndRendering'):
        return {'file': str(source), 'arguments': ['clang++', '-o',
            f'Source/WebCore/CMakeFiles/{target}.dir/unified.mm.o', '-c', str(source)]}

    def test_actual_split_target_with_non_arc_unity(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'UnifiedSource-rendering-1-nonARC.mm'
            source.write_text('#include "rendering/cocoa/RenderThemeCocoa.mm"\n')
            row = self.row(source)
            self.assertIs(module.select_theme_entry([row]), row)

    def test_legacy_monolithic_direct_source(self):
        row = self.row(Path('RenderThemeCocoa.mm'), 'WebCore')
        self.assertIs(module.select_theme_entry([row]), row)

    def test_comment_is_not_a_theme_include(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'UnifiedSource-rendering-1-nonARC.mm'
            source.write_text('// RenderThemeCocoa.mm\n')
            with self.assertRaisesRegex(AssertionError, 'exactly one'):
                module.select_theme_entry([self.row(source)])

    def test_wrong_target_and_duplicate_are_rejected(self):
        row = self.row(Path('RenderThemeCocoa.mm'))
        with self.assertRaisesRegex(AssertionError, 'exactly one'):
            module.select_theme_entry([self.row(Path('RenderThemeCocoa.mm'), 'RanvierWebCoreHost')])
        with self.assertRaisesRegex(AssertionError, 'exactly one'):
            module.select_theme_entry([row, row])

    def test_remove_only_actual_binary_pch_operands(self):
        header = '/owned/Source/WebCore/CMakeFiles/WebCoreDOMAndRendering.dir/cmake_pch.objcxx.hxx'
        original = ['clang++', '-include', 'WebCorePrefix.h', '-Winvalid-pch',
                    '-Xclang', '-include-pch', '-Xclang', header + '.pch',
                    '-Xclang', '-include', '-Xclang', header, '-o', 'out.o', '-c', 'unified.mm']
        result, record = module.textual_prefix_command(original)
        self.assertEqual(result, original[:4] + original[8:])
        self.assertEqual(record['retainedTextualHeader'], header)
        self.assertEqual(original[4:8], record['removed'])

    def test_missing_textual_prefix_fails_closed(self):
        with self.assertRaisesRegex(AssertionError, 'textual prefix'):
            module.textual_prefix_command(['clang++', '-Xclang', '-include-pch', '-Xclang', '/owned/cmake_pch.objcxx.hxx.pch'])

    def test_unrecognized_pch_form_fails_closed(self):
        with self.assertRaises(AssertionError):
            module.textual_prefix_command(['clang++', '-include-pch', '/owned/prefix.pch'])
        with self.assertRaises(AssertionError):
            module.textual_prefix_command(['clang++', '-include-pch=/owned/prefix.pch'])

    def test_no_pch_command_is_unchanged(self):
        command = ['clang++', '-include', 'WebCorePrefix.h', '-c', 'theme.mm']
        self.assertEqual(module.textual_prefix_command(command), (command, None))


if __name__ == '__main__':
    unittest.main()
