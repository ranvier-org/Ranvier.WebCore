import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = os.environ.get('RANVIER_INTEROP_METADATA_TEST_ROOT')


@unittest.skipUnless(FIXTURES, 'Requires the bounded compiled metadata fixtures')
class CompiledInteropMetadata(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('slim_metadata_subject', ROOT / 'scripts/recover_preview12_slim.py')
        cls.subject = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.subject)
        cls.expected = {f'rv_fixture_{index}': dict(returns='int', returnMetadata=dict(input=False, output=False, marshal=''),
            parameters=[dict(type='valuetype:Fixture.Native+Options&', input=False, output=False, marshal='')] if index == 0 else [])
            for index in range(349)}

    def inspect(self, variant):
        directory = Path(FIXTURES)
        assembly = directory / variant / 'Fixture.dll'
        with tempfile.TemporaryDirectory() as temporary:
            expected = Path(temporary) / 'expected.json'
            report = Path(temporary) / 'actual.json'
            expected.write_text(json.dumps(self.expected))
            subprocess.run(['rtk', 'proxy', 'dotnet', directory / 'inspector/InteropMetadata.dll', assembly, expected, report], check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return json.loads(report.read_text())

    def test_canonical_compiled_value_type_and_return_metadata_pass(self):
        actual = self.inspect('baseline')
        self.subject.verify_signatures(actual, self.expected, self.subject.sha(Path(FIXTURES) / 'baseline/Fixture.dll'))

    def rejected(self, variant):
        actual = self.inspect(variant)
        with self.assertRaisesRegex(ValueError, 'signature'):
            self.subject.verify_signatures(actual, self.expected, self.subject.sha(Path(FIXTURES) / variant / 'Fixture.dll'))

    def test_compiled_return_marshal_as_cannot_hide_behind_int_return(self):
        self.rejected('return-marshal')

    def test_compiled_same_name_reference_type_is_not_a_value_type(self):
        self.rejected('reference-type')

    def test_compiled_same_name_type_in_another_namespace_is_rejected(self):
        self.rejected('other-namespace')

    def test_compiled_same_name_type_in_another_declaring_type_is_rejected(self):
        self.rejected('other-declaring-type')

    def test_compiled_calling_convention_must_match_canonical_default(self):
        self.rejected('calling-convention')
