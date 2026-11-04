"""GPU build trees travel between release tag runs as artifacts named by their cache key."""

import importlib.util
import os
import pathlib
import tempfile
import unittest
import urllib.error
import zipfile
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('tree_artifacts', ROOT / 'scripts/tree_artifacts.py')
trees = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trees)

EXACT = 'tree-linux-x64-gpu-webkit-tool-core-host-manifest-v2'
PREFIXES = ['tree-linux-x64-gpu-webkit-tool-core-', 'tree-linux-x64-gpu-webkit-tool-']


def artifact(name, created, expired=False, identity=1):
    return dict(id=identity, name=name, created_at=created, expired=expired, size_in_bytes=1 << 20)


def tree(parent: pathlib.Path, text='objects', when=1_600_000_000):
    build = parent / 'build-gpu'
    (build / 'obj').mkdir(parents=True)
    file = build / 'obj' / 'a.o'
    file.write_text(text)
    os.utime(file, (when, when))
    return build


def artifact_zip(build: pathlib.Path, target: pathlib.Path):
    tarball = target.with_suffix('.tar.gz')
    trees.pack(build, tarball)
    with zipfile.ZipFile(target, 'w') as archive:
        archive.write(tarball, trees.MEMBER)


class ChooseTests(unittest.TestCase):
    def test_the_exact_key_wins_over_newer_prefix_matches(self):
        chosen = trees.choose([artifact(PREFIXES[0] + 'other', '2026-11-04'), artifact(EXACT, '2026-10-01')], EXACT, PREFIXES)
        self.assertEqual(chosen['name'], EXACT)

    def test_the_narrowest_matching_prefix_wins_then_the_newest(self):
        artifacts = [artifact(PREFIXES[1] + 'wide-new', '2026-11-04'), artifact(PREFIXES[0] + 'old', '2026-10-01'),
                     artifact(PREFIXES[0] + 'new', '2026-10-20')]
        self.assertEqual(trees.choose(artifacts, EXACT, PREFIXES)['name'], PREFIXES[0] + 'new')
        self.assertEqual(trees.choose(artifacts[:1], EXACT, PREFIXES)['name'], PREFIXES[1] + 'wide-new')

    def test_expired_and_foreign_artifacts_are_never_chosen(self):
        artifacts = [artifact(EXACT, '2026-11-04', expired=True), artifact('tree-win-x64-gpu-x', '2026-11-04'),
                     artifact('package-linux-x64-gpu', '2026-11-04')]
        self.assertIsNone(trees.choose(artifacts, EXACT, PREFIXES))


class PackTests(unittest.TestCase):
    def test_a_packed_tree_unpacks_with_its_file_times(self):
        with tempfile.TemporaryDirectory() as directory:
            source = tree(pathlib.Path(directory) / 'source')
            archive = pathlib.Path(directory) / 'artifact.zip'
            artifact_zip(source, archive)
            target = pathlib.Path(directory) / 'target' / 'build-gpu'
            target.parent.mkdir()
            trees.unpack(archive, target)
            restored = target / 'obj' / 'a.o'
            self.assertEqual(restored.read_text(), 'objects')
            self.assertEqual(int(restored.stat().st_mtime), 1_600_000_000)

    def test_restore_replaces_the_tree_with_the_chosen_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = pathlib.Path(directory) / 'artifact.zip'
            artifact_zip(tree(pathlib.Path(directory) / 'source', text='restored'), archive)
            build = tree(pathlib.Path(directory) / 'work', text='stale')
            fetch = lambda repository, identity, target: target.write_bytes(archive.read_bytes())
            with mock.patch.object(trees, 'listed', return_value=[artifact(EXACT, '2026-11-04')]), \
                    mock.patch.object(trees, 'download', fetch):
                self.assertEqual(trees.restore(build, EXACT, PREFIXES, 'owner/repo', 'token'), EXACT)
            self.assertEqual((build / 'obj' / 'a.o').read_text(), 'restored')

    def test_a_miss_or_a_failure_restores_nothing_and_leaves_no_partial_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            build = tree(pathlib.Path(directory))
            with mock.patch.object(trees, 'listed', return_value=[]):
                self.assertEqual(trees.restore(build, EXACT, PREFIXES, 'owner/repo', 'token'), '')
            self.assertTrue(build.exists(), 'a miss keeps whatever tree is there')
            broken = lambda repository, identity, target: target.write_bytes(b'not a zip')
            with mock.patch.object(trees, 'listed', return_value=[artifact(EXACT, '2026-11-04')]), \
                    mock.patch.object(trees, 'download', broken):
                self.assertEqual(trees.restore(build, EXACT, PREFIXES, 'owner/repo', 'token'), '')
            self.assertFalse(build.exists())
            with mock.patch.object(trees, 'listed', side_effect=urllib.error.URLError('offline')):
                self.assertEqual(trees.restore(build, EXACT, PREFIXES, 'owner/repo', 'token'), '')


class WorkflowTests(unittest.TestCase):
    def step(self, name):
        workflow = (ROOT / '.github/workflows/build.yml').read_text()
        return workflow.split(f'      - name: {name}\n', 1)[1].split('\n      - ', 1)[0]

    def test_a_gpu_cell_restores_an_artifact_only_after_a_cache_miss(self):
        step = self.step('Restore the GPU build tree of an earlier release')
        self.assertIn("matrix.flavor == 'gpu' && steps.tree.outputs.cache-matched-key == ''", step)
        self.assertIn('EXACT: ${{ steps.keys.outputs.tree }}', step)
        self.assertIn('PREFIXES: ${{ steps.keys.outputs.tree-restore }}', step)
        self.assertIn("steps.gpu-tree.outputs.matched-key == ''", self.step('Restore vcpkg archives'))

    def test_only_a_tag_runs_gpu_cell_leaves_its_tree_and_never_fails_the_release_for_it(self):
        pack = self.step('Pack the GPU build tree for the next release')
        self.assertIn("matrix.flavor == 'gpu' && startsWith(github.ref, 'refs/tags/v')", pack)
        self.assertIn('steps.gpu-tree.outputs.matched-key != steps.keys.outputs.tree', pack)
        self.assertIn('continue-on-error: true', pack)
        upload = self.step('Upload the GPU build tree')
        self.assertIn('continue-on-error: true', upload)
        self.assertIn('name: ${{ steps.keys.outputs.tree }}', upload)
        self.assertIn('retention-days: 90', upload)
        self.assertIn('/gpu-tree/tree.tar.gz', upload)
        self.assertEqual(trees.MEMBER, 'tree.tar.gz')


if __name__ == '__main__':
    unittest.main()
