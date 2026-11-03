"""Compile the page policy and native clock selection from the patched sources."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RELATIVE = Path('Source/WebCore/rendering/RenderTheme.cpp')


class CocoaProgressMotionTests(unittest.TestCase):
    def test_page_policy_and_native_clock_selection(self):
        source = os.environ.get('RANVIER_WEBKIT_SOURCE')
        compiler = os.environ.get('CXX') or shutil.which('clang++') or shutil.which('c++')
        if not source or not compiler:
            self.skipTest('Set RANVIER_WEBKIT_SOURCE and provide a C++ compiler for the pinned source policy test')
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            patch = ROOT / 'patches/0065-cocoa-progress-reduced-motion.patch'
            for relative in re.findall(r'^diff --git a/(\S+) b/\S+$', patch.read_text(encoding='utf-8'), re.M):
                target = directory / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((Path(source) / relative).read_bytes())
            subprocess.run(['git', 'apply', str(patch)], cwd=directory, check=True)
            text = (directory / RELATIVE).read_text(encoding='utf-8')
            body = text.split('bool RenderTheme::prefersReducedMotionForRenderer(const RenderElement& renderer)\n{', 1)[1].split('\n}', 1)[0]
            native = (directory / 'Source/WebCore/platform/graphics/mac/controls/ProgressBarMac.mm').read_text(encoding='utf-8')
            clock = native.split('    constexpr double reducedMotionPhaseSeconds', 1)[1].split('\n    auto coreUISizeForProgressBarSize', 1)[0]
            cpp = directory / 'policy.cpp'
            cpp.write_text('''#include <cassert>
#include <initializer_list>
enum class ForcedAccessibilityValue { On, Off, System };
struct Settings {
    ForcedAccessibilityValue value;
    auto forcedPrefersReducedMotionAccessibilityValue() const { return value; }
};
struct Renderer { Settings setting; const Settings& settings() const { return setting; } };
struct Theme {
    bool system; int queries = 0;
    static Theme& singleton() { static Theme instance; return instance; }
    bool userPrefersReducedMotion() { ++queries; return system; }
};
bool policy(const Renderer& renderer) {''' + body + '''}
struct Seconds { double value; double seconds() const { return value; } };
struct MonotonicTime {
    static double value;
    static MonotonicTime now() { return {}; }
    Seconds secondsSinceEpoch() const { return {value}; }
};
double MonotonicTime::value;
struct Part { double start; Seconds animationStartTime() const { return {start}; } };
struct ControlStyle {
    enum class State { ReducedMotion };
    struct States { bool reduced; bool contains(State) const { return reduced; } } states;
};
double nativeClock(bool isIndeterminate, bool reduced, double start, double now) {
    ControlStyle style{{reduced}};
    Part part{start};
    auto* progressBarPart = &part;
    MonotonicTime::value = now;
    constexpr double reducedMotionPhaseSeconds''' + clock + '''
    return animationTime;
}
int main() {
    for (bool system : {false, true}) {
        Theme::singleton().system = system;
        for (auto page : {ForcedAccessibilityValue::On, ForcedAccessibilityValue::Off, ForcedAccessibilityValue::System}) {
            Theme::singleton().queries = 0;
            bool expected = page == ForcedAccessibilityValue::On || (page == ForcedAccessibilityValue::System && system);
            bool reduced = policy(Renderer{Settings{page}});
            assert(reduced == expected);
            assert(Theme::singleton().queries == (page == ForcedAccessibilityValue::System ? 1 : 0));
            for (bool indeterminate : {false, true}) {
                for (double start : {0.0, 1000.0, 10000000.0}) {
                    for (double elapsed : {0.125, 0.5, 1.5, 2.0}) {
                        double now = start + elapsed;
                        assert(nativeClock(indeterminate, reduced, start, now) ==
                            (indeterminate && reduced ? start + 0.5 : now));
                    }
                }
            }
        }
    }
}
''', encoding='utf-8')
            exe = directory / 'policy.exe'
            subprocess.run([compiler, '-std=c++20', '-Wall', '-Wextra', '-Werror', str(cpp), '-o', str(exe)], check=True)
            subprocess.run([str(exe)], check=True)


if __name__ == '__main__':
    unittest.main()
