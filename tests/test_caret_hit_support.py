"""Regression tests for deterministic caret probe accounting without a native engine build."""

import ctypes
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests' / 'abi'))

import caret_hit_support
from svg_paint_probe import SvgProbe


class FakeProbe(SvgProbe):
    pointer = ctypes.c_void_p
    integer = ctypes.c_int32
    double = ctypes.c_double

    def __init__(self, readiness_polls, fail_update=False):
        self.host = ctypes.c_void_p(1)
        self.assertions = 0
        self._assertion_count_suppression = 0
        self.widths = [159.0] * readiness_polls + [160.0]
        self.width_reads = 0
        self.fail_update = fail_update

    def call(self, name, arguments, *values):
        self.expect(True, name + ' status')

    def load(self, markup, standalone=True):
        pass

    def bind(self, name, result, arguments):
        if name == 'rv_host_document':
            return lambda host: ctypes.c_void_p(2)
        if name == 'rv_run_loop_cycle':
            return lambda interval: 0
        return lambda *arguments: 0

    def node(self, identifier):
        self.expect(True, 'real SVG node ' + identifier)
        return ctypes.c_void_p(3)

    def object(self, name, arguments, values, root, nullable=False):
        self.call(name, arguments, *values)
        self.expect(True, name + ': nonnull')
        return ctypes.c_void_p(4)

    def read(self, root, target, field, scalar=None):
        self.call('rv_dom_' + root + '_get_' + field, [], target)
        self.width_reads += 1
        if self.widths:
            return self.widths.pop(0)
        return 159.0

    def update(self):
        self.expect(not self.fail_update, 'SVG paint update')


class CaretHitReadinessTests(unittest.TestCase):
    def construct_page(self, readiness_polls):
        probe = FakeProbe(readiness_polls)
        with patch.object(caret_hit_support, 'page', return_value='fixture'):
            caret_hit_support.CaretPage(probe, 'unused', 1)
        return probe

    def test_ahem_readiness_poll_count_does_not_change_reported_assertions(self):
        fast_font = self.construct_page(1)
        slow_font = self.construct_page(8)

        self.assertEqual(fast_font.assertions, slow_font.assertions)
        self.assertGreater(slow_font.width_reads, fast_font.width_reads)

    def test_ahem_readiness_timeout_still_fails_visibly(self):
        probe = FakeProbe(100)
        with patch.object(caret_hit_support, 'page', return_value='fixture'), \
                patch.object(caret_hit_support.time, 'monotonic', side_effect=[0.0, 11.0]):
            with self.assertRaisesRegex(AssertionError, 'pinned Ahem was not applied'):
                caret_hit_support.CaretPage(probe, 'unused', 1)

    def test_native_update_failure_during_readiness_poll_still_fails(self):
        probe = FakeProbe(1, fail_update=True)
        with patch.object(caret_hit_support, 'page', return_value='fixture'):
            with self.assertRaisesRegex(AssertionError, 'SVG paint update'):
                caret_hit_support.CaretPage(probe, 'unused', 1)


if __name__ == '__main__':
    unittest.main()
