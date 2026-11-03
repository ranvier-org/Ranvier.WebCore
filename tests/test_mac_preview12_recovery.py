import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('recovery', ROOT / 'scripts/mac_preview12_recovery.py')
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


class CompileDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.product = self.root / 'product'
        self.control = self.root / 'control'
        self.build = self.root / 'build'
        for path in [self.product / 'host', self.control, self.build]:
            path.mkdir(parents=True)
        self.cpp = self.product / 'host/RanvierWebCoreAbi.cpp'
        self.cpp.write_text('int rv_abi_version(void) { return 64; }')
        self.installed = self.root / 'webkit/Tools/TestWebKitAPI/RanvierAbi/RanvierWebCoreAbi.cpp'
        self.installed.parent.mkdir(parents=True)
        self.installed.write_bytes(self.cpp.read_bytes())
        self.entry = dict(file=str(self.installed), directory=str(self.build),
            arguments=['clang++', '-c', str(self.installed), '-o', 'Host.o'])

    def check(self, entries):
        (self.build / 'compile_commands.json').write_text(json.dumps(entries))
        return recovery.admit_compile_database(self.build, self.product, self.control)

    def test_one_exact_installed_product_host(self):
        value = self.check([self.entry])
        self.assertEqual(value['sourceSha256'], recovery.sha(self.cpp))

    def test_duplicate_and_missing_entries_reject(self):
        for entries in [[], [self.entry, self.entry]]:
            with self.subTest(entries=len(entries)), self.assertRaises(ValueError):
                self.check(entries)

    def test_changed_host_source_rejects(self):
        self.installed.write_text('wrong')
        with self.assertRaises(ValueError):
            self.check([self.entry])

    def test_response_file_and_builder_include_reject(self):
        for argument in ['@response.rsp', '-I' + str(self.control)]:
            self.entry['arguments'].append(argument)
            with self.subTest(argument=argument), self.assertRaises(ValueError):
                self.check([self.entry])
            self.entry['arguments'].pop()

    def test_wrong_working_directory_rejects(self):
        self.entry['directory'] = str(self.root)
        with self.assertRaises(ValueError):
            self.check([self.entry])


class BuildPlanTests(unittest.TestCase):
    def test_noop_and_host_only_build_are_allowed(self):
        recovery.require_warm_plan('ninja: no work to do.\n')
        recovery.require_warm_plan('[1/2] Building OBJCXX object Tools/TestWebKitAPI/CMakeFiles/RanvierWebCoreHost.dir/RanvierAbi/RanvierMacGpuSpike.mm.o\n[2/2] Linking CXX shared library Host.dylib\n')

    def test_engine_and_unknown_compilation_reject(self):
        for text in ['[1/2] Building CXX object Source/WebCore/CMakeFiles/WebCore.dir/source.cpp.o',
                     '[1/1] Building Swift object WebGPU.swift.o']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                recovery.require_warm_plan(text)


class ProducerBoundaryTests(unittest.TestCase):
    def test_separately_reviewed_helper_blobs_are_required(self):
        with patch.object(recovery.subprocess, 'check_output', side_effect=list(recovery.HELPER_BLOBS.values())):
            self.assertEqual(recovery.helper_identity(ROOT), recovery.HELPER_BLOBS)
        with patch.object(recovery.subprocess, 'check_output', return_value='a' * 40), self.assertRaises(ValueError):
            recovery.helper_identity(ROOT)

    def test_only_exact_failed_mac_job_is_eligible(self):
        job = dict(name='native (osx-arm64, macos-26, /Users/runner/rw)', status='completed', conclusion='failure')
        self.assertEqual(recovery.failed_mac_job([job]), job)
        for changed in [[], [job, job], [job | {'status': 'in_progress'}], [job | {'conclusion': 'success'}]]:
            with self.subTest(jobs=changed), self.assertRaises(ValueError):
                recovery.failed_mac_job(changed)

    def test_source_branch_and_event_are_exact(self):
        run = dict(head_sha=recovery.PRODUCT_SOURCE, head_branch='v' + recovery.VERSION, event='push', path='.github/workflows/build.yml')
        recovery.require_run(run, run['head_branch'], 'push')
        for field, value in [('head_sha', 'a' * 40), ('head_branch', 'main'), ('event', 'workflow_dispatch'), ('path', '.github/workflows/other.yml')]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                recovery.require_run(run | {field: value}, 'v' + recovery.VERSION, 'push')

    def test_gpu_waits_while_original_slim_is_live(self):
        run = dict(head_sha=recovery.PRODUCT_SOURCE, head_branch='v' + recovery.VERSION, event='push',
                   path='.github/workflows/build.yml', status='in_progress')
        with patch.object(recovery.subprocess, 'check_output', return_value=json.dumps(run)), self.assertRaises(ValueError):
            recovery.recovery_boundary('gpu')

    def test_successful_slim_without_visible_gpu_child_cannot_shortcut(self):
        slim = dict(head_sha=recovery.PRODUCT_SOURCE, head_branch='v' + recovery.VERSION, event='push',
                    path='.github/workflows/build.yml', status='completed', conclusion='success')
        prewarm = slim | dict(head_branch='main', event='workflow_dispatch', conclusion='failure')
        jobs = dict(total_count=1, jobs=[dict(name='native (osx-arm64, macos-26, /Users/runner/rw)', status='completed', conclusion='failure')])
        listing = dict(total_count=0, workflow_runs=[])
        with patch.object(recovery.subprocess, 'check_output', side_effect=[json.dumps(x) for x in [slim, prewarm, jobs, listing]]), self.assertRaises(ValueError):
            recovery.recovery_boundary('gpu')

    def test_failed_slim_and_failed_prewarm_allow_empty_gpu_dispatch_list(self):
        slim = dict(head_sha=recovery.PRODUCT_SOURCE, head_branch='v' + recovery.VERSION, event='push',
                    path='.github/workflows/build.yml', status='completed', conclusion='failure')
        prewarm = slim | dict(head_branch='main', event='workflow_dispatch')
        jobs = dict(total_count=1, jobs=[dict(name='native (osx-arm64, macos-26, /Users/runner/rw)', status='completed', conclusion='failure')])
        listing = dict(total_count=0, workflow_runs=[])
        with patch.object(recovery.subprocess, 'check_output', side_effect=[json.dumps(x) for x in [slim, prewarm, jobs, listing]]):
            self.assertEqual(recovery.recovery_boundary('gpu')['tagGpuRuns'], [])


class WorkflowTests(unittest.TestCase):
    def test_disabled_and_product_artifacts_precede_helpers(self):
        text = (ROOT / '.github/workflows/macos-preview12-recovery.yml').read_text()
        self.assertIn('false &&', text)
        self.assertIn(recovery.PRODUCT_SOURCE, text)
        self.assertLess(text.index('name: Retain immutable product package'), text.index('name: Build matching helpers'))
        self.assertIn('if: always()', text)
        self.assertNotIn('id-token:', text)
        self.assertNotIn('contents: write', text)


if __name__ == '__main__':
    unittest.main()
