"""Compile the shared print-option policy without a renderer or platform SDK."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PrintOptionsTests(unittest.TestCase):
    def test_pdf_off_keeps_a_truthful_unavailable_backend(self):
        compiler = os.environ.get('CXX') or os.environ.get('CC') or shutil.which('clang++') or shutil.which('c++')
        if not compiler:
            self.skipTest('C++ compiler unavailable')
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / 'wtf').mkdir()
            (folder / 'WebCore').mkdir()
            (folder / 'config.h').write_text('#define USE(x) 0\n#define UNUSED_PARAM(x) (void)(x)\n', encoding='utf-8')
            (folder / 'wtf/MainThread.h').write_text('namespace WTF { inline bool isMainThread() { return true; } }\n', encoding='utf-8')
            (folder / 'WebCore/PlatformExportMacros.h').write_text('#define WEBCORE_EXPORT\n', encoding='utf-8')
            (folder / 'off.cpp').write_text('#include "RanvierPrintGlue.h"\n#include <cassert>\n'
                'int main() { assert(!ranvier_print_pdf_supported()); RvPrintPdfData* out = nullptr; '
                'assert(ranvier_print_pdf(reinterpret_cast<RvNode*>(1), nullptr, nullptr, nullptr, &out) == RV_ERR_UNSUPPORTED); '
                'assert(!out); }\n', encoding='utf-8')
            exe = folder / 'off.exe'
            subprocess.run([compiler, '-std=c++20', '-Wall', '-Wextra', '-Werror', '-DRANVIER_ENABLE_PDF=0',
                            '-I', str(folder), '-I', str(ROOT / 'host'), str(ROOT / 'host/RanvierPrintGlue.cpp'),
                            str(folder / 'off.cpp'), '-o', str(exe)], check=True)
            subprocess.run([str(exe)], check=True)

    def test_backend_defaults_and_rejected_profiles(self):
        compiler = os.environ.get('CXX') or os.environ.get('CC') or shutil.which('clang++') or shutil.which('c++')
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
