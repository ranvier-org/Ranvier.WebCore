"""Exercise host-file installation in a fresh isolated source tree."""
import ast
import os
from pathlib import Path
import shutil
import tempfile
import subprocess
import types
import unittest


class HostPrepare(unittest.TestCase):
    def test_refreshes_an_old_cached_embedder_source_list(self):
        cmake=os.environ.get('RANVIER_CMAKE') or shutil.which('cmake')
        if not cmake:self.skipTest('CMake is not available')
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            script=Path(temporary)/'cache.cmake'
            script.write_text('set(RANVIER_RID win-x64)\nset(WebCore_EMBEDDER_SOURCES obsolete.cpp CACHE STRING "")\ninclude("'+(root/'config/common.cmake').as_posix()+'")\nlist(FIND WebCore_EMBEDDER_SOURCES "'+(root/'host/RanvierSvgViewGlue.cpp').as_posix()+'" selected)\nif(selected EQUAL -1)\nmessage(FATAL_ERROR "The cached list omitted the SVG view helper")\nendif()\n')
            result=subprocess.run([cmake,'-P',str(script)],cwd=temporary,capture_output=True)
            self.assertEqual(result.returncode,0,result.stdout.decode()+result.stderr.decode())

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
            for filename in ['RanvierWebCoreAbi.cpp','RanvierCapabilities.inc','RanvierCapabilityCatalogue.inc','RanvierSvgViewGlue.h','RanvierEventGlue.h','RanvierViewportGlue.h','RanvierInspectGlue.h']:
                self.assertEqual((installed/filename).read_bytes(),(root/'host'/filename).read_bytes())
            self.assertIn('#include "RanvierCapabilities.inc"',(installed/'RanvierWebCoreAbi.cpp').read_text())
            self.assertIn('#include "RanvierCapabilityCatalogue.inc"',(installed/'RanvierCapabilities.inc').read_text())


if __name__=='__main__': unittest.main()
