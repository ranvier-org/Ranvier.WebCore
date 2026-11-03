import importlib.util
import copy
import json
from pathlib import Path
import re
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
        self.assertEqual(recovery.recoverable_mac_job([job]), dict(job=job, classification='terminal-failure'))
        for changed in [[], [job, job], [job | {'status': 'in_progress'}], [job | {'conclusion': 'success'}]]:
            with self.subTest(jobs=changed), self.assertRaises(ValueError):
                recovery.recoverable_mac_job(changed)

    def test_cancelled_before_runner_is_distinct_acquisition_only(self):
        job = dict(name='native (osx-arm64, macos-26, /Users/runner/rw)', status='completed',
                   conclusion='cancelled', runner_id=0, runner_name='', steps=[])
        self.assertEqual(recovery.recoverable_mac_job([job]),
                         dict(job=job, classification='acquisition-only-cancelled-before-runner'))
        for field, value in [('runner_id', 1), ('runner_id', '0'), ('runner_id', False),
                             ('runner_name', 'acquired-runner'), ('runner_name', None),
                             ('steps', [{}]), ('steps', None), ('status', 'in_progress')]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                recovery.recoverable_mac_job([job | {field: value}])

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
    def test_only_explicit_manual_main_gate_and_product_artifact_order(self):
        text = (ROOT / '.github/workflows/macos-preview12-recovery.yml').read_text()
        guards = re.findall(r'^    if: (.+)$', text, re.M)
        disabled = "${{ false && github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main' }}"
        enabled = "${{ github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main' }}"
        self.assertEqual(len(guards), 1)
        self.assertIn(guards[0], [disabled, enabled])
        self.assertNotIn('  push:', text)
        self.assertIn(recovery.PRODUCT_SOURCE, text)
        self.assertLess(text.index('name: Retain immutable product package'), text.index('name: Build matching helpers'))
        self.assertIn("always() && env.EVIDENCE != ''", text)
        self.assertNotIn('id-token:', text)
        self.assertNotIn('contents: write', text)


class IndependentGpuTests(unittest.TestCase):
    def setUp(self):
        self.run = dict(id=recovery.INDEPENDENT_GPU_RUN, run_attempt=1, head_sha=recovery.PRODUCT_SOURCE,
            head_branch='v' + recovery.VERSION, event='workflow_dispatch', path='.github/workflows/build.yml', status='in_progress')
        common = dict(run_id=self.run['id'], run_attempt=1, head_sha=recovery.PRODUCT_SOURCE)
        self.jobs = [common | dict(id=recovery.INDEPENDENT_GPU_PLAN, name='plan', status='completed', conclusion='success'),
                     common | dict(id=recovery.INDEPENDENT_GPU_PREBUILT, name='prebuilt', status='completed', conclusion='skipped')]
        self.jobs.extend(common | dict(id=identity, name='native (' + rid + ', runner, work)', status='in_progress', conclusion=None)
                         for rid, identity in recovery.INDEPENDENT_GPU_NATIVE.items())

    def test_exact_expanded_non_mac_run_can_be_live(self):
        result = recovery.independent_gpu_expansion(self.run, self.jobs)
        self.assertEqual(result['classification'], 'independent-three-rid-no-mac')
        self.assertEqual(len(result['nativeJobs']), 3)

    def test_boundary_excludes_only_known_non_mac_run_while_live(self):
        slim = self.run | dict(id=recovery.SLIM_RUN, event='push', status='completed', conclusion='failure')
        prewarm = self.run | dict(id=recovery.PREWARM_RUN, head_branch='main', status='completed', conclusion='failure')
        prewarm_jobs = dict(total_count=1, jobs=[dict(name='native (osx-arm64, macos-26, work)', status='completed', conclusion='failure')])
        for identity, allowed in [(recovery.INDEPENDENT_GPU_RUN, True), (99, False)]:
            listing = dict(total_count=1, workflow_runs=[self.run | dict(id=identity)])
            replies = [slim, prewarm, prewarm_jobs, listing, dict(total_count=len(self.jobs), jobs=self.jobs)]
            with self.subTest(run=identity), patch.object(recovery.subprocess, 'check_output', side_effect=[json.dumps(x) for x in replies]):
                if allowed:
                    value = recovery.recovery_boundary('gpu')
                    self.assertEqual(len(value['independentNonMacGpuRuns']), 1)
                    self.assertEqual(value['tagGpuRuns'], [])
                else:
                    with self.assertRaises(ValueError):
                        recovery.recovery_boundary('gpu')

    def test_run_source_branch_path_event_attempt_and_id_are_fixed(self):
        for field, value in [('id', 1), ('run_attempt', 2), ('head_sha', 'a' * 40), ('head_branch', 'main'),
                             ('event', 'push'), ('path', '.github/workflows/other.yml')]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                recovery.independent_gpu_expansion(self.run | {field: value}, self.jobs)

    def test_plan_must_be_the_exact_completed_successful_job(self):
        for change in [dict(status='in_progress'), dict(conclusion='failure'), dict(id=1)]:
            jobs = copy.deepcopy(self.jobs)
            jobs[0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                recovery.independent_gpu_expansion(self.run, jobs)

    def test_missing_duplicate_or_mac_native_expansion_rejects(self):
        cases = [self.jobs[:-1], self.jobs + [self.jobs[-1]], self.jobs + [self.jobs[-1] | dict(name='native (osx-arm64, macos-26, work)', id=99)]]
        for jobs in cases:
            with self.subTest(count=len(jobs)), self.assertRaises(ValueError):
                recovery.independent_gpu_expansion(self.run, jobs)

    def test_prebuilt_must_be_the_single_skipped_route(self):
        for change in [dict(name='prebuilt (osx-arm64)'), dict(status='in_progress'), dict(conclusion='success')]:
            jobs = copy.deepcopy(self.jobs)
            jobs[1].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                recovery.independent_gpu_expansion(self.run, jobs)

    def test_job_identities_and_expansion_state_reject_changes(self):
        for index, change in [(2, dict(id=1)), (2, dict(run_id=1)), (2, dict(run_attempt=2)),
                              (2, dict(head_sha='a' * 40)), (2, dict(status='unknown'))]:
            jobs = copy.deepcopy(self.jobs)
            jobs[index].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                recovery.independent_gpu_expansion(self.run, jobs)


if __name__ == '__main__':
    unittest.main()
