import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests/abi'))
import resize_observation as probe


class ResizeScope(unittest.TestCase):
    def setUp(self):
        self.oracle = json.loads((probe.FIXTURES / 'resize-observation-oracle.json').read_text())
        self.baseline = json.loads((probe.FIXTURES / 'resize-observation-native-t2.json').read_text())
        self.results = copy.deepcopy(self.baseline['results'])
        self.qualified = json.loads((probe.FIXTURES / 'resize-observation-qualified.json').read_text())['differences']
        self.native = object.__new__(probe.Native)
        self.native.assertions = 0

    def compare(self):
        report = {}
        probe.compare(self.native, self.oracle, self.results, report, self.qualified)
        return report

    def test_measured_device_parity_preserves_extended_css_diagnostics(self):
        report = self.compare()
        self.assertEqual(report['comparedDeviceEntries'], 287)
        self.assertEqual(report['comparedNativeCssFields'], 828)
        self.assertIn('contentBox.entries.f.border', report['extendedCssDifferences'])

    def test_qualified_observer_order_cannot_hide_a_device_size_change(self):
        self.results['1.5']['observerOrder']['entries'][0]['device'][0] += 1
        with self.assertRaisesRegex(AssertionError, 'device pixel'):
            self.compare()

    def test_extended_css_remains_equal_to_the_native_checkpoint(self):
        self.results['1.5']['devicePixelFractionalBorderPadding']['entries'][0]['border'][0] += 1
        with self.assertRaisesRegex(AssertionError, 'native CSS baseline'):
            self.compare()

    def test_original_g10_css_change_is_rejected(self):
        self.results['2']['contentBox']['entries'][0]['content'][0] += 1
        with self.assertRaises(AssertionError):
            self.compare()


if __name__ == '__main__':
    unittest.main()
