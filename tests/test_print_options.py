"""Compile the shared print-option policy without a renderer or platform SDK."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PrintOptionsTests(unittest.TestCase):
    def test_backend_defaults_and_rejected_profiles(self):
        compiler = os.environ.get('CC') or shutil.which('clang') or shutil.which('c++')
        if not compiler:
            self.skipTest('C++ compiler unavailable')
        source = r'''
#include "RanvierPrintOptions.h"
#include <cassert>
#include <limits>
int main() {
    auto defaults = ranvierPrintDefaultOptions();
    assert(defaults.size == sizeof(RvPrintOptions));
    assert(defaults.raster_dpi == 0);
    auto skia = defaults;
    assert(ranvierPrintNormalizeOptions(skia, false));
    assert(skia.raster_dpi == 144);
    auto cg = defaults;
    assert(ranvierPrintNormalizeOptions(cg, true));
    assert(cg.raster_dpi == 72);
    for (float dpi : { 72.0f, 144.0f, 600.0f }) {
        auto options = defaults;
        options.raster_dpi = dpi;
        assert(ranvierPrintNormalizeOptions(options, false));
        options.raster_dpi = dpi;
        assert(ranvierPrintNormalizeOptions(options, true) == (dpi == 72));
    }
    for (float dpi : { -1.0f, 1.0f, 71.0f, 601.0f, std::numeric_limits<float>::infinity(), std::numeric_limits<float>::quiet_NaN() }) {
        auto options = defaults;
        options.raster_dpi = dpi;
        assert(!ranvierPrintNormalizeOptions(options, false));
        assert(!ranvierPrintNormalizeOptions(options, true));
    }
    auto invalid = defaults;
    invalid.paper_width_points = 0;
    assert(!ranvierPrintNormalizeOptions(invalid, true));
    invalid = defaults;
    invalid.output_budget_bytes = 0;
    assert(!ranvierPrintNormalizeOptions(invalid, false));
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            cpp, exe = folder / 'options.cpp', folder / 'options.exe'
            cpp.write_text(source, encoding='utf-8')
            subprocess.run([compiler, '-std=c++20', '-I', str(ROOT / 'host'), str(cpp), '-o', str(exe)], check=True)
            subprocess.run([str(exe)], check=True)


if __name__ == '__main__':
    unittest.main()
