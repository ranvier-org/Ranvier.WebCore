import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAYOUTS = {
    'RvMutationOptionalBool': (8, {'present': 0, 'value': 4}),
    'RvMutationString': (16, {'data': 0, 'length': 8}),
    'RvMutationOptionalStrings': (24, {'present': 0, 'items': 8, 'count': 16}),
    'RvMutationNodes': (16, {'items': 0, 'count': 8}),
    'RvMutationObserverOptions': (72, {'size': 0, 'child_list': 4, 'subtree': 8, 'attributes': 12,
                                    'character_data': 20, 'attribute_old_value': 28,
                                    'character_data_old_value': 36, 'attribute_filter': 48}),
    'RvMutationRecordView': (128, {'size': 0, 'type': 8, 'target': 24, 'added_nodes': 32,
                                 'removed_nodes': 48, 'previous_sibling': 64, 'next_sibling': 72,
                                 'attribute_name': 80, 'attribute_namespace': 96, 'old_value': 112}),
}
TARGETS = ['x86_64-pc-windows-msvc', 'aarch64-pc-windows-msvc', 'x86_64-unknown-linux-gnu',
           'aarch64-unknown-linux-gnu', 'arm64-apple-macos15']


class MutationContractTests(unittest.TestCase):
    def compile_layout(self, standard, language):
        compiler = os.environ.get('RANVIER_CONTRACT_CLANG') or shutil.which('clang')
        pinned = Path('C:/wk/tools/clang+llvm-23.1.4-x86_64-pc-windows-msvc/bin/clang.exe')
        if not compiler and pinned.is_file():
            compiler = str(pinned)
        if not compiler:
            self.skipTest('clang is unavailable for the standalone C ABI layout gate')
        assertion = 'static_assert' if language == 'c++' else '_Static_assert'
        lines = ['#include <stddef.h>', '#include "RanvierWebCoreAbi.h"']
        for name, (size, fields) in LAYOUTS.items():
            lines.append(f'{assertion}(sizeof({name}) == {size}, "{name}.size");')
            for field, offset in fields.items():
                lines.append(f'{assertion}(offsetof({name}, {field}) == {offset}, "{name}.{field}");')
        with tempfile.TemporaryDirectory(prefix='ranvier-mutation-contract-') as directory:
            source = Path(directory) / ('layout.cpp' if language == 'c++' else 'layout.c')
            source.write_text('\n'.join(lines), encoding='utf-8')
            for target in TARGETS:
                command = [compiler, '-fsyntax-only', '-ffreestanding', '-Werror', '-x', language,
                           '-std=' + standard, '--target=' + target, '-I' + str(ROOT / 'host'), str(source)]
                result = subprocess.run(command, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, target + ': ' + result.stderr[:6000])

    def test_generated_managed_boundary_preserves_mutation_layouts_and_outputs(self):
        spec = importlib.util.spec_from_file_location('mutation_native_generator', ROOT / 'tests/abi/generate_native.py')
        generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generator)
        header = (ROOT / 'host/RanvierWebCoreAbi.h').read_text()
        section = generator.generated(header)
        actual = {name: parameters for name, _, parameters in generator.externs(section)}
        self.assertEqual(actual['rv_host_create_mutation_observer'],
                         ['nativeint', 'nativeint', 'nativeint', 'nativeint', 'nativeint&'])
        self.assertEqual(actual['rv_mutation_observer_observe'],
                         ['nativeint', 'nativeint', 'MutationObserverOptions&'])
        self.assertEqual(actual['rv_mutation_observer_take_records'], ['nativeint', 'nativeint&'])
        self.assertEqual(actual['rv_mutation_record_batch_get_record'],
                         ['nativeint', 'int', 'MutationRecordView&'])
        types = {name: (fields, delegate) for name, fields, delegate in generator.preamble_types(section)}
        self.assertEqual(types['MutationOptionalBool'][0], [('present', 'int'), ('value', 'int')])
        self.assertEqual(types['MutationString'][0], [('data', 'nativeint'), ('length', 'int')])
        self.assertEqual(types['MutationOptionalStrings'][0], [('present', 'int'), ('items', 'nativeint'), ('count', 'int')])
        self.assertEqual(types['MutationNodes'][0], [('items', 'nativeint'), ('count', 'int')])
        self.assertEqual(types['MutationObserverOptions'][0],
                         [('size', 'uint32'), ('child_list', 'int'), ('subtree', 'int'),
                          ('attributes', 'MutationOptionalBool'), ('character_data', 'MutationOptionalBool'),
                          ('attribute_old_value', 'MutationOptionalBool'), ('character_data_old_value', 'MutationOptionalBool'),
                          ('attribute_filter', 'MutationOptionalStrings')])
        self.assertEqual(types['MutationRecordView'][0],
                         [('size', 'uint32'), ('type', 'MutationString'), ('target', 'nativeint'),
                          ('added_nodes', 'MutationNodes'), ('removed_nodes', 'MutationNodes'),
                          ('previous_sibling', 'nativeint'), ('next_sibling', 'nativeint'),
                          ('attribute_name', 'MutationString'), ('attribute_namespace', 'MutationString'),
                          ('old_value', 'MutationString')])
        self.assertEqual(types['MutationCallback'][1],
                         'delegate of context: nativeint * observer: nativeint * records: nativeint -> unit')
        self.assertEqual(types['MutationContextRelease'][1], 'delegate of context: nativeint -> unit')
        for name, _, parameters in generator.declarations(header):
            if name.startswith('rv_mutation_') or name == 'rv_host_create_mutation_observer':
                names = [parameter for _, parameter in parameters]
                self.assertEqual(len(names), len(set(names)), name + ': duplicate generated argument names')

    def test_c11_every_field_on_supported_pointer_layouts(self):
        self.compile_layout('c11', 'c')

    def test_cpp20_every_field_on_supported_pointer_layouts(self):
        self.compile_layout('c++20', 'c++')


if __name__ == '__main__':
    unittest.main()
