import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('cohort_source', Path(__file__).with_name('cohort_source.py'))
cohort = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cohort)


class CohortSourceTests(unittest.TestCase):
    def setUp(self):
        self.baseline = [(f'rv_baseline_{index}', 'int32_t', []) for index in range(344)]
        self.tail = [(name, 'int32_t', []) for name in ['rv_host_ime_surrounding', 'rv_host_ime_delete_surrounding', 'rv_ax_text_style_run']]

    def test_style_only_is_not_final_union(self):
        with self.assertRaisesRegex(ValueError, '347'):
            cohort.verify_abi(self.baseline, self.baseline + self.tail[-1:], 63)

    def test_existing_signature_drift_is_rejected(self):
        changed = list(self.baseline)
        changed[42] = (changed[42][0], 'void', [])
        with self.assertRaisesRegex(ValueError, '344'):
            cohort.verify_abi(self.baseline, changed + self.tail, 63)

    def test_tail_order_and_abi_version_are_required(self):
        with self.assertRaisesRegex(ValueError, 'order'):
            cohort.verify_abi(self.baseline, self.baseline + list(reversed(self.tail)), 63)
        with self.assertRaisesRegex(ValueError, '63'):
            cohort.verify_abi(self.baseline, self.baseline + self.tail, 62)

    def test_final_shape_passes_source_contract_only(self):
        cohort.verify_abi(self.baseline, self.baseline + self.tail, 63)


if __name__ == '__main__':
    unittest.main()
