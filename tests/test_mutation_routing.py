import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location('mutation_' + name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MutationRoutingTests(unittest.TestCase):
    def test_native_workflow_explicitly_executes_public_mutation_fixture(self):
        workflow = (ROOT / '.github/workflows/build.yml').read_text()
        marker = '      - name: Verify mutation observation delivery and ownership\n'
        self.assertTrue(marker in workflow, 'Missing explicit native mutation-observation step')
        step = workflow.split(marker, 1)[1].split('\n      - ', 1)[0]
        self.assertIn('tests/abi/mutation_observation.py', step)
        self.assertIn('--native-directory', step)
        self.assertIn('runtimes/${{ matrix.rid }}/native', step)
        self.assertIn('timeout-minutes: 5', step)
        self.assertNotIn('\n        if:', step)

    def test_catalogue_selects_mutations_for_every_supported_runtime_and_flavor(self):
        probes = load('probes')
        entries = [entry for entry in probes.PROBES if any('mutation_observation.py' in command for command in entry['commands'])]
        self.assertEqual(len(entries), 1)
        for rid in ['win-x64', 'win-arm64', 'linux-x64', 'linux-arm64', 'osx-arm64']:
            for flavor in ['slim', 'gpu']:
                self.assertTrue(probes.applies(entries[0], rid, flavor), (rid, flavor))

    def test_extracted_package_always_runs_public_mutation_fixture(self):
        package_api = load('check_package_api')
        pairs = [(rid, False) for rid in ['win-x64', 'win-arm64', 'linux-x64', 'linux-arm64', 'osx-arm64']]
        pairs += [(rid, True) for rid in ['win-x64', 'linux-x64', 'linux-arm64']]
        with tempfile.TemporaryDirectory(prefix='ranvier-mutation-routing-') as directory:
            for rid, gpu in pairs:
                with self.subTest(rid=rid, gpu=gpu):
                    package = Path(directory) / (rid + str(gpu) + '.nupkg')
                    with zipfile.ZipFile(package, 'w') as archive:
                        archive.writestr('manifest.json', json.dumps({'abi': package_api.current_abi(), 'rid': rid, 'flavor': 'gpu' if gpu else 'slim'}))
                        archive.writestr(f'runtimes/{rid}/native/fixture.bin', b'not-a-runtime')
                    with mock.patch.object(package_api.subprocess, 'run') as run:
                        package_api.verify(package, gpu=gpu)
                    selected = [call for call in run.call_args_list if any(str(arg).endswith('mutation_observation.py') for arg in call.args[0])]
                    self.assertEqual(len(selected), 1)
                    self.assertIn('--native-directory', selected[0].args[0])
                    self.assertTrue(selected[0].kwargs['check'])
                    if gpu and rid.startswith('linux-'):
                        self.assertEqual(selected[0].kwargs['env']['EGL_PLATFORM'], 'surfaceless')


if __name__ == '__main__':
    unittest.main()
