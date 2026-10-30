"""Exercise host-file installation in a fresh isolated source tree."""
import ast
from pathlib import Path
import shutil
import tempfile
import types
import unittest


class HostPrepare(unittest.TestCase):
    def test_installs_transitive_capability_includes(self):
        root=Path(__file__).resolve().parents[1]
        tree=ast.parse((root/'scripts/build.py').read_text())
        prepare=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='prepare')
        with tempfile.TemporaryDirectory() as temporary:
            source=Path(temporary)
            api=source/'Tools/TestWebKitAPI'
            api.mkdir(parents=True)
            (api/'CMakeLists.txt').write_text('# fresh isolated API test tree\n')
            scope=dict(root=root,source=source,shutil=shutil,commit='fixture',args=types.SimpleNamespace(strict=True),
                       sys=types.SimpleNamespace(executable='unused'),run=lambda *args:None,git=lambda *args,**kwargs:None,
                       subprocess=types.SimpleNamespace(run=lambda *args,**kwargs:types.SimpleNamespace(returncode=0)))
            exec(compile(ast.Module(body=[prepare],type_ignores=[]),'<actual-prepare>','exec'),scope)
            scope['prepare']()
            installed=api/'RanvierAbi'
            for filename in ['RanvierWebCoreAbi.cpp','RanvierCapabilities.inc','RanvierCapabilityCatalogue.inc','RanvierSvgViewGlue.h']:
                self.assertEqual((installed/filename).read_bytes(),(root/'host'/filename).read_bytes())
            self.assertIn('#include "RanvierCapabilities.inc"',(installed/'RanvierWebCoreAbi.cpp').read_text())
            self.assertIn('#include "RanvierCapabilityCatalogue.inc"',(installed/'RanvierCapabilities.inc').read_text())


if __name__=='__main__': unittest.main()
