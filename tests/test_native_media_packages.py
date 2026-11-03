import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('media_managed', ROOT / 'tests/media/managed.py')
MEDIA = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MEDIA)


class PackageGraphs(unittest.TestCase):
    def graph(self, directory, traced, extra=(), pair=True):
        suffix = '.Traced' if traced else ''
        packages = [f'Ranvier.View.WebCore{suffix}/0.1.0-alpha.45']
        if pair:
            packages.append(f'Ranvier.View.WebCore.Sdl{suffix}/0.1.0-alpha.45')
        packages.extend(extra)
        path = directory / 'project.assets.json'
        path.write_text(json.dumps({'libraries': {name: {'type': 'package'} for name in packages}}), encoding='utf-8')

    def validate(self, directory, traced):
        return MEDIA.check_package_graphs(directory, traced,
                                          lambda path: hashlib.sha256(path.read_bytes()).hexdigest())

    def test_matching_normal_and_traced_graphs(self):
        for traced in (False, True):
            with self.subTest(traced=traced), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary)
                self.graph(path, traced, extra=('Ranvier.WebCore/0.1.1-preview.7',))
                self.assertEqual(len(self.validate(path, traced)), 1)

    def test_opposing_view_family_is_rejected_even_with_expected_pair(self):
        for traced in (False, True):
            for family in ('Ranvier.View', 'Ranvier.View.Dom', 'Ranvier.View.WebCore', 'Ranvier.View.WebCore.Sdl'):
                opposing = family if traced else family + '.Traced'
                with self.subTest(traced=traced, family=family), tempfile.TemporaryDirectory() as temporary:
                    path = Path(temporary)
                    self.graph(path, traced, extra=(opposing.lower() + '/0.1.0-alpha.45',))
                    with self.assertRaisesRegex(AssertionError, 'opposingViewPackages'):
                        self.validate(path, traced)

    def test_missing_pair_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            self.graph(path, False, pair=False)
            with self.assertRaises(AssertionError):
                self.validate(path, False)


if __name__ == '__main__':
    unittest.main()
