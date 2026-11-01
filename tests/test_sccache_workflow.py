from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / '.github/workflows/build.yml').read_text()


def step(name):
    match = re.search(rf'^      - name: {re.escape(name)}\n(.*?)(?=^      - |\Z)',
                      WORKFLOW, re.MULTILINE | re.DOTALL)
    if not match:
        raise AssertionError(f'missing workflow step: {name}')
    return match.group(1)


class SccacheWorkflowTests(unittest.TestCase):
    def test_cache_restore_is_windows_x64_only_and_has_weekly_fallback_prefix(self):
        restore = step('Restore sccache cache')
        self.assertIn("if: steps.sccache-install.outputs.available == 'true'", restore)
        self.assertIn('uses: actions/cache/restore@v4', restore)
        self.assertIn('key: ${{ steps.sccache-key.outputs.key }}', restore)
        self.assertIn('restore-keys: sccache-win-x64-release-clang23-v1-', restore)
        self.assertIn('continue-on-error: true', restore)
        self.assertIn('sccache_cache_policy.py key', step('Set sccache weekly key'))

    def test_preflight_and_final_usage_reads_surround_the_native_compile(self):
        preflight = step('Read sccache budget before build')
        build = step('Build')
        cleanup = step('Prune old sccache entries')
        gate = step('Check sccache save budget')
        save = step('Save sccache cache')
        verify = step('Verify saved sccache archive size')
        self.assertIn('sccache_cache_policy.py preflight', preflight)
        self.assertIn('sccache_cache_policy.py cleanup', cleanup)
        self.assertIn("'gate'", gate)
        self.assertIn('sccache_cache_policy.py @policyArgs', gate)
        self.assertIn("'--compile-succeeded'", gate)
        self.assertIn('--preflight-usage', gate)
        self.assertIn('steps.sccache-gate.outputs.save == \'true\'', save)
        self.assertIn('uses: actions/cache/save@v4', save)
        self.assertIn('continue-on-error: true', save)
        self.assertIn('sccache_cache_policy.py verify', verify)
        self.assertIn('steps.sccache-save.outcome == \'success\'', verify)
        self.assertLess(WORKFLOW.index('      - name: Read sccache budget before build'),
                        WORKFLOW.index('      - name: Build\n'))
        self.assertLess(WORKFLOW.index('      - name: Build\n'),
                        WORKFLOW.index('      - name: Prune old sccache entries'))
        self.assertLess(WORKFLOW.index('      - name: Prune old sccache entries'),
                        WORKFLOW.index('      - name: Check sccache save budget'))
        self.assertLess(WORKFLOW.index('      - name: Check sccache save budget'),
                        WORKFLOW.index('      - name: Save sccache cache'))
        self.assertLess(WORKFLOW.index('      - name: Save sccache cache'),
                        WORKFLOW.index('      - name: Verify saved sccache archive size'))
        self.assertIn("steps.sccache-preflight.outputs.usage_available == 'true'", cleanup)
        self.assertIn("github.event_name == 'push' && github.ref == 'refs/heads/main'", cleanup)
        self.assertNotIn('outputs.budget_ok', cleanup)

    def test_launcher_and_local_cache_limit_apply_only_to_the_windows_x64_toolchain(self):
        setup = step('Install and configure sccache')
        self.assertIn("if: runner.os == 'Windows' && matrix.rid == 'win-x64'", setup)
        self.assertIn('SCCACHE_CACHE_SIZE=192M', setup)
        self.assertIn('RANVIER_SCCACHE=C:\\rw\\tools\\sccache\\sccache.exe', setup)
        self.assertIn('sccache.exe --version', setup)
        self.assertIn('$installed = $LASTEXITCODE -eq 0', setup)
        self.assertIn('Write-Warning', setup)
        self.assertIn("Add-Content $env:GITHUB_OUTPUT 'available=false'", setup)
        self.assertIn('continue-on-error: true', step('sccache stats before build'))
        self.assertIn('continue-on-error: true', step('sccache stats after build'))

    def test_real_powershell_fallback_contract_runs_on_windows_x64(self):
        fallback = step('Verify optional sccache fallback')
        self.assertIn("if: runner.os == 'Windows' && matrix.rid == 'win-x64'", fallback)
        self.assertIn('tests/test_sccache_powershell.py', fallback)

    def test_warm_cmake_launcher_cache_regression_runs_on_windows_x64(self):
        fallback = step('Verify sccache launcher cache fallback')
        self.assertIn("if: runner.os == 'Windows' && matrix.rid == 'win-x64'", fallback)
        self.assertIn('tests/test_build_sccache_launcher.py', fallback)


if __name__ == '__main__':
    unittest.main()
