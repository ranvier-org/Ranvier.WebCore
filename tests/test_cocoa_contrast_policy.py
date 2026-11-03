"""Compile the patched page/system resolver; this is not a native painter build."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RELATIVE = Path('Source/WebCore/rendering/cocoa/RenderThemeCocoa.mm')


class CocoaContrastPolicy(unittest.TestCase):
    def test_page_policy_and_other_platform_fallback(self):
        source = os.environ.get('RANVIER_WEBKIT_SOURCE')
        compiler = os.environ.get('CXX') or shutil.which('clang++') or shutil.which('c++')
        if not source or not compiler:
            self.skipTest('Set RANVIER_WEBKIT_SOURCE and provide C++20 compiler for pinned source control')
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            target = directory / RELATIVE
            target.parent.mkdir(parents=True)
            target.write_bytes((Path(source) / RELATIVE).read_bytes())
            subprocess.run(['git', 'apply', str(ROOT / 'patches/0072-cocoa-page-contrast.patch')],
                           cwd=directory, check=True)
            text = target.read_text(encoding='utf-8')
            begin = text.index('static bool prefersIncreasedContrastForRenderer(')
            end = text.index('\n}\n', begin) + 2
            resolver = text[begin:end]
            self.assertEqual(text.count('Theme::singleton().userPreferredContrast()'), 1)
            self.assertEqual(text.count('prefersIncreasedContrastForRenderer('), 19)
            enum_header = Path(source) / 'Source/WebCore/accessibility/ForcedAccessibilityValue.h'
            (directory / 'ForcedAccessibilityValue.h').write_bytes(enum_header.read_bytes())
            cpp = directory / 'policy.cpp'
            cpp.write_text('''using uint8_t = unsigned char;
#include "ForcedAccessibilityValue.h"
#define PLATFORM(name) TEST_MAC
using WebCore::ForcedAccessibilityValue;
enum class InterfaceContrastPreference { MoreContrast, NoPreference };
struct Settings {
    ForcedAccessibilityValue value;
    auto forcedPrefersContrastAccessibilityValue() const { return value; }
};
struct RenderObject { Settings setting; const Settings& settings() const { return setting; } };
struct Theme {
    bool system; int queries = 0;
    static Theme& singleton() { static Theme instance; return instance; }
    auto userPreferredContrast() {
        ++queries;
        return system ? InterfaceContrastPreference::MoreContrast : InterfaceContrastPreference::NoPreference;
    }
};
''' + resolver + '''
int main() {
    for (int system = 0; system != 2; ++system) {
        Theme::singleton().system = system;
        for (int mode = 0; mode != 3; ++mode) {
            auto page = static_cast<ForcedAccessibilityValue>(mode);
            Theme::singleton().queries = 0;
            bool expected = TEST_MAC ? page == ForcedAccessibilityValue::On ||
                (page == ForcedAccessibilityValue::System && system) : !!system;
            bool actual = prefersIncreasedContrastForRenderer(RenderObject{Settings{page}});
            if (actual != expected)
                return 1;
            int expectedQueries = !TEST_MAC || page == ForcedAccessibilityValue::System ? 1 : 0;
            if (Theme::singleton().queries != expectedQueries)
                return 2;
        }
    }
}
''', encoding='utf-8')
            for mac in [0, 1]:
                exe = directory / f'policy-{mac}.exe'
                subprocess.run([compiler, '-std=c++20', '-Wall', '-Wextra', '-Werror',
                                f'-DTEST_MAC={mac}', str(cpp), '-o', str(exe)], check=True)
                subprocess.run([str(exe)], check=True)


if __name__ == '__main__':
    unittest.main()
