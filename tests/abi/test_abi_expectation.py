"""Cohort input and AST-equivalence controls, without loading native code."""
import ast
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('expectation',HERE/'abi_expectation.py')
expectation=importlib.util.module_from_spec(spec)
spec.loader.exec_module(expectation)
BASE=json.loads((HERE.parent/'fixtures/abi63-probe-assertion-asts.json').read_text())


class NormalizeExpectation(ast.NodeTransformer):
    def visit_ImportFrom(self,node):
        return None if node.module=='abi_expectation' else node

    def visit_Call(self,node):
        if isinstance(node.func,ast.Name) and node.func.id=='expected_abi':
            return ast.copy_location(ast.Constant(value=63),node)
        return self.generic_visit(node)


class ExpectedAbiControls(unittest.TestCase):
    def test_standalone_default_and_explicit_versions_are_exact(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(expectation.expected_abi(),63)
        for value in ['63','64','65']:
            with patch.dict(os.environ,{expectation.ENVIRONMENT:value}):
                self.assertEqual(expectation.expected_abi(),int(value))
        for value in ['', ' 64','64 ','0','-1','64.0','064','True','9'*10]:
            with self.subTest(value=value),patch.dict(os.environ,{expectation.ENVIRONMENT:value}),self.assertRaises(ValueError):
                expectation.expected_abi()

    def test_manifest_binding_does_not_mutate_parent_environment(self):
        parent={'PATH':'retained'}
        self.assertEqual(expectation.expected_environment({'abi':64},None,parent),parent)
        self.assertEqual(expectation.expected_environment({'abi':64},64,parent),dict(parent,**{expectation.ENVIRONMENT:'64'}))
        self.assertEqual(parent,{'PATH':'retained'})
        for manifest,value in [({'abi':63},64),({'abi':64.0},64),({'abi':64},63),({'abi':64},True),({'abi':64},0)]:
            with self.subTest(manifest=manifest,value=value),self.assertRaises(ValueError):
                expectation.expected_environment(manifest,value,parent)

    def test_all_original_probe_assertions_are_ast_identical_with_historical_expectation(self):
        changed=[]
        for path in HERE.glob('*.py'):
            if path.name in ['abi_expectation.py','test_abi_expectation.py']:
                continue
            current=path.read_text(encoding='utf-8')
            if 'from abi_expectation import expected_abi' not in current:
                continue
            old=BASE['probes'][path.name]
            normalized=NormalizeExpectation().visit(ast.parse(current))
            if not old['hadSysPathInsert']:
                normalized.body=[node for node in normalized.body if not (
                    isinstance(node,ast.Expr) and isinstance(node.value,ast.Call)
                    and isinstance(node.value.func,ast.Attribute) and node.value.func.attr=='insert'
                    and ast.unparse(node.value.func.value)=='sys.path')]
            self.assertEqual(hashlib.sha256(ast.dump(normalized).encode()).hexdigest(),old['astSha256'],path.name)
            changed.append(path.name)
        self.assertEqual(len(changed),39)

    def test_no_python_version_query_still_compares_to_literal63(self):
        checked=[]
        for path in HERE.glob('*.py'):
            if path.name.startswith('test_'):
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if not isinstance(node,ast.Compare) or not any(isinstance(item,ast.Constant) and item.value=='rv_abi_version' for item in ast.walk(node.left)):
                    continue
                self.assertFalse(any(isinstance(item,ast.Constant) and item.value==63 for item in node.comparators),path.name)
                checked.append(path.name)
        self.assertGreaterEqual(len(checked),40)


if __name__=='__main__':
    unittest.main()
