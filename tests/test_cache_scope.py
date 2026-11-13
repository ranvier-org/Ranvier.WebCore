"""Only refs whose entries later runs can restore save the dependency caches."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SAVES = ['Save gperf', 'Save LLVM', 'Save ICU', 'Save vcpkg archives', 'Save vcpkg downloads']


def condition(name):
    workflow = (ROOT / '.github/workflows/build.yml').read_text()
    step = workflow.split(f'      - name: {name}\n', 1)[1]
    return re.match(r'        if: (.+)\n', step)[1]


class CacheScopeTests(unittest.TestCase):
    def test_tag_runs_save_no_dependency_cache(self):
        for name in SAVES:
            with self.subTest(step=name):
                self.assertTrue(condition(name).startswith("${{ !startsWith(github.ref, 'refs/tags/') && "))

    def test_the_build_tree_is_saved_only_by_the_default_and_batch_refs(self):
        workflow = (ROOT / '.github/workflows/build.yml').read_text()
        save = workflow.split('\n      TREE_SAVE: >-\n', 1)[1].split('\n    steps:', 1)[0]
        self.assertNotIn('refs/tags', save)
        self.assertIn("github.ref == 'refs/heads/main'", save)


if __name__ == '__main__':
    unittest.main()
