"""Check the actual tag publication expression against failed and skipped job outcomes."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SHA = '0123456789abcdef0123456789abcdef01234567'


def main_run(**changes):
    """A successful push run of build.yml on main for the tag's commit, as the workflow run list reports it."""
    return dict(dict(id=7, path='.github/workflows/build.yml', head_sha=SHA, head_branch='main', event='push',
                     conclusion='success', repository={'full_name': 'owner/repo'}), **changes)


def package_artifacts(*cells, expired=False):
    return [{'name': f'package-{rid}-{flavor}', 'expired': expired} for rid, flavor in cells]


def permits_publish(native='success', prebuilt='skipped', managed='success', contract='success', flavor='', cancelled=False, atspi='success',
                    ref='refs/tags/v0.1.0-preview.14', owner='owner'):
    workflow = (ROOT / '.github/workflows/build.yml').read_text()
    job = workflow.split('\n  publish:\n', 1)[1]
    expression = job.split('if:', 1)[1].split('${{', 1)[1].split('}}', 1)[0]
    results = {'native': native, 'prebuilt': prebuilt, 'managed': managed, 'package-contract': contract, 'atspi-package': atspi}
    expression = re.sub(r'needs\.([a-z-]+)\.result', lambda match: repr(results[match[1]]), expression)
    for name, value in [('github.ref', ref), ('vars.NUGET_USER', owner), ('inputs.flavor', flavor)]:
        expression = expression.replace(name, repr(value))
    expression = expression.replace('!cancelled()', repr(not cancelled)).replace('&&', ' and ').replace('||', ' or ')
    return eval(' '.join(expression.split()), {'__builtins__': {}}, {'startsWith': lambda value, prefix: value.startswith(prefix)})


def plan_cells(event='push', ref='refs/tags/v0.1.2-rc.1', flavor='slim', rids='', release=None, runs=(), artifacts=(),
               sources=False):
    """The matrix and prebuilt cells the plan job writes for one event, with the release API answering `release`,
    the workflow run list answering `runs` and every run's artifact list answering `artifacts`. With `sources`,
    each prebuilt cell also carries the run it is taken from ('' for a release asset)."""
    import io, json, os, tempfile, urllib.error
    from unittest import mock
    workflow = (ROOT / '.github/workflows/build.yml').read_text()
    job = workflow.split('\n  plan:\n', 1)[1].split('\n  prebuilt:\n', 1)[0]
    script = job.split('        run: |\n', 1)[1]
    script = '\n'.join(line[10:] for line in script.splitlines())

    def answer(request, timeout):
        if '/actions/runs?' in request.full_url:
            return io.BytesIO(json.dumps({'workflow_runs': list(runs)}).encode())
        if '/actions/runs/' in request.full_url:
            return io.BytesIO(json.dumps({'artifacts': list(artifacts)}).encode())
        if release is None:
            raise urllib.error.HTTPError(request.full_url, 404, 'Not Found', {}, None)
        return io.BytesIO(json.dumps(release).encode())

    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / 'output'
        env = dict(RIDS=rids, HEAD_REF='', FULL_LABEL='false', FLAVOR=flavor, GH_TOKEN='token', GITHUB_EVENT_NAME=event,
                   GITHUB_REF=ref, GITHUB_SHA=SHA, GITHUB_REPOSITORY_OWNER='owner', GITHUB_REPOSITORY='owner/repo',
                   GITHUB_API_URL='https://api.example', GITHUB_OUTPUT=str(output))
        cwd = os.getcwd()
        os.chdir(ROOT)
        try:
            with mock.patch.dict(os.environ, env), mock.patch('urllib.request.urlopen', answer), \
                    mock.patch('builtins.print'):
                exec(compile(script, 'plan', 'exec'), {'__name__': 'plan'})
        finally:
            os.chdir(cwd)
        values = dict(line.split('=', 1) for line in output.read_text().splitlines())

    def cells(key):
        return [(c['rid'], c['flavor']) for c in json.loads(values[key])['include']] if values[key] else []

    if sources:
        return cells('matrix'), [(c['rid'], c['flavor'], c['run']) for c in json.loads(values['prebuilt'])['include']]             if values['prebuilt'] else []
    return cells('matrix'), cells('prebuilt')


class PublishGateTests(unittest.TestCase):
    def test_a_failed_runtime_cannot_publish_an_uploaded_package(self):
        self.assertFalse(permits_publish(native='failure', managed='skipped'))

    def test_every_selected_verification_and_contract_job_must_succeed(self):
        for status in ['failure', 'cancelled']:
            with self.subTest(status=status):
                self.assertFalse(permits_publish(prebuilt=status))
                self.assertFalse(permits_publish(contract=status))
                self.assertFalse(permits_publish(managed=status))
        self.assertFalse(permits_publish(native='skipped', prebuilt='skipped'))
        self.assertFalse(permits_publish(cancelled=True))
        self.assertFalse(permits_publish(ref='refs/heads/main'))
        self.assertFalse(permits_publish(owner=''))

    def test_full_slim_release_requires_the_managed_cohort(self):
        self.assertTrue(permits_publish())
        self.assertTrue(permits_publish(native='skipped', prebuilt='success'))
        self.assertTrue(permits_publish(prebuilt='success'))
        for flavor in ['', 'slim']:
            self.assertFalse(permits_publish(managed='skipped', flavor=flavor))

    def test_full_slim_release_requires_the_atspi_provider_package(self):
        for status in ['failure', 'skipped', 'cancelled']:
            with self.subTest(status=status):
                self.assertFalse(permits_publish(atspi=status))
        self.assertTrue(permits_publish(managed='skipped', atspi='skipped', flavor='gpu'))

    def test_manual_gpu_and_lean_keep_the_selected_runtime_gate(self):
        for flavor in ['gpu', 'lean']:
            self.assertTrue(permits_publish(managed='skipped', flavor=flavor))
            self.assertFalse(permits_publish(native='failure', managed='skipped', flavor=flavor))

    def test_publication_waits_for_all_gate_dependencies(self):
        workflow = (ROOT / '.github/workflows/build.yml').read_text()
        job = workflow.split('\n  publish:\n', 1)[1]
        needs = re.search(r'^    needs: \[([^]]+)\]', job, re.MULTILINE)[1]
        self.assertEqual({name.strip() for name in needs.split(',')}, {'native', 'prebuilt', 'managed', 'atspi-package', 'package-contract'})
        self.assertIn('python -I tests/test_publish_gate.py', workflow)

    def test_the_required_check_waits_for_every_job_but_publication(self):
        workflow = (ROOT / '.github/workflows/build.yml').read_text()
        jobs = set(re.findall(r'^  ([a-z-]+):$', workflow.split('\njobs:\n', 1)[1], re.MULTILINE))
        job = workflow.split('\n  result:\n', 1)[1]
        needs = re.search(r'^    needs: \[([^]]+)\]', job, re.MULTILINE)[1]
        self.assertEqual({name.strip() for name in needs.split(',')}, jobs - {'result', 'publish'})


class FlavorMatrixTests(unittest.TestCase):
    SLIM = [(rid, 'slim') for rid in ['win-x64', 'win-arm64', 'linux-x64', 'linux-arm64', 'osx-arm64']]
    GPU = [(rid, 'gpu') for rid in ['win-x64', 'linux-x64', 'linux-arm64', 'osx-arm64']]

    def test_a_version_tag_builds_both_flavors_in_one_run(self):
        self.assertEqual(plan_cells(), (self.SLIM + self.GPU, []))

    def test_branches_and_pull_requests_build_slim_only(self):
        self.assertEqual(plan_cells(ref='refs/heads/main')[0], self.SLIM)
        self.assertEqual(plan_cells(event='pull_request', ref='refs/pull/1/merge')[0], [('win-x64', 'slim')])

    def test_a_manual_run_builds_its_selected_flavor_and_runtimes(self):
        self.assertEqual(plan_cells(event='workflow_dispatch', flavor='gpu', rids='win-x64,osx-arm64')[0],
                         [('win-x64', 'gpu'), ('osx-arm64', 'gpu')])

    def test_an_owner_attached_package_moves_only_its_own_cell_to_prebuilt(self):
        release = {'author': {'login': 'owner'},
                   'assets': [{'name': 'Ranvier.WebCore.Native.linux-x64.0.1.2-rc.1.nupkg', 'uploader': {'login': 'owner'}}]}
        matrix, prebuilt = plan_cells(release=release)
        self.assertEqual(prebuilt, [('linux-x64', 'gpu')])
        self.assertIn(('linux-x64', 'slim'), matrix)
        self.assertNotIn(('linux-x64', 'gpu'), matrix)

    def test_a_tag_of_the_pinned_version_takes_the_packages_the_main_run_of_its_commit_built(self):
        import json
        tag = 'refs/tags/v' + json.loads((ROOT / 'pins.json').read_text())['package']['version']
        matrix, prebuilt = plan_cells(ref=tag, runs=[main_run()], artifacts=package_artifacts(*self.SLIM), sources=True)
        self.assertEqual(prebuilt, [(rid, flavor, '7') for rid, flavor in self.SLIM])
        self.assertEqual(matrix, self.GPU)

    def test_only_this_workflows_successful_main_push_run_of_the_commit_is_taken(self):
        import json
        tag = 'refs/tags/v' + json.loads((ROOT / 'pins.json').read_text())['package']['version']
        refused = [dict(path='.github/workflows/other.yml'), dict(head_sha='f' * 40), dict(head_branch='feature'),
                   dict(event='pull_request'), dict(conclusion='failure'), dict(repository={'full_name': 'fork/repo'})]
        for change in refused:
            with self.subTest(change=change):
                self.assertEqual(plan_cells(ref=tag, runs=[main_run(**change)], artifacts=package_artifacts(*self.SLIM)),
                                 (self.SLIM + self.GPU, []))
        self.assertEqual(plan_cells(ref=tag, runs=[main_run()], artifacts=package_artifacts(*self.SLIM, expired=True)),
                         (self.SLIM + self.GPU, []))

    def test_a_main_run_package_of_another_version_is_built_again(self):
        self.assertEqual(plan_cells(runs=[main_run()], artifacts=package_artifacts(*self.SLIM)), (self.SLIM + self.GPU, []))

    def test_an_owner_attached_package_precedes_the_main_runs(self):
        import json
        version = json.loads((ROOT / 'pins.json').read_text())['package']['version']
        release = {'author': {'login': 'owner'},
                   'assets': [{'name': f'Ranvier.WebCore.Native.Cpu.win-x64.{version}.nupkg', 'uploader': {'login': 'owner'}}]}
        prebuilt = plan_cells(ref=f'refs/tags/v{version}', release=release, runs=[main_run()],
                              artifacts=package_artifacts(('win-x64', 'slim'), ('linux-x64', 'slim')), sources=True)[1]
        self.assertEqual(prebuilt, [('win-x64', 'slim', ''), ('linux-x64', 'slim', '7')])

    def test_the_prebuilt_job_downloads_a_main_run_package_from_that_run_and_checks_it_like_an_attached_one(self):
        workflow = (ROOT / '.github/workflows/build.yml').read_text()
        job = workflow.split('\n  prebuilt:\n', 1)[1].split('\n  native:\n', 1)[0]
        self.assertIn("if: matrix.run == ''", job)
        self.assertIn("if: matrix.run != ''", job)
        self.assertIn('run-id: ${{ matrix.run }}', job)
        self.assertIn('--expect-commit "$GITHUB_SHA"', job)
        self.assertIn('--expect-version "${GITHUB_REF_NAME#v}"', job)
        self.assertIn('actions: read', job)

    def test_cells_read_their_flavor_and_do_not_queue_behind_each_other(self):
        workflow = (ROOT / '.github/workflows/build.yml').read_text()
        self.assertNotIn('\n  gpu-cohort:\n', workflow)
        for name in ['prebuilt', 'native']:
            job = workflow.split(f'\n  {name}:\n', 1)[1].split('\n    steps:\n', 1)[0]
            with self.subTest(job=name):
                self.assertIn('FLAVOR: ${{ matrix.flavor }}', job)
                self.assertNotIn('inputs.flavor', job)
        native = workflow.split('\n  native:\n', 1)[1]
        self.assertIn("format('native-{0}-{1}-{2}', github.run_id, matrix.rid, matrix.flavor)", native)
        self.assertIn('BUILD_DIR: ${{ matrix.work }}/build-${{ matrix.flavor }}', native)

    def test_managed_packs_the_gpu_aggregate_from_the_tag_run(self):
        workflow = (ROOT / '.github/workflows/build.yml').read_text()
        job = workflow.split('\n  managed:\n', 1)[1].split('\n  atspi:\n', 1)[0]
        self.assertIn('pattern: package-*-gpu', job)
        self.assertIn('packages/Ranvier.WebCore.Native.[0-9]*.nupkg', job)
        self.assertIn('packages/Ranvier.WebCore.Native.Cpu.[0-9]*.nupkg', job)
        self.assertIn('packages/Ranvier.WebCore.Native.Gpu.[0-9]*.nupkg', job)


if __name__ == '__main__':
    unittest.main()
