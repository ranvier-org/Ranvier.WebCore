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
    def test_texture_helper_and_host_share_the_configured_compositor_profile(self):
        cmake = shutil.which('cmake')
        if not cmake:
            self.skipTest('CMake is not available')
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for name, mapper, stub, expected in [('windows-slim', 1, 1, 0),
                                                  ('coordinated', 0, 0, 0), ('gpu', 1, 0, 1)]:
                with self.subTest(profile=name):
                    output = directory / (name + '.txt')
                    script = directory / (name + '.cmake')
                    script.write_text('set(ENABLE_WEBCORE ON)\nset(PORT Test)\n'
                        f'set(USE_GRAPHICS_LAYER_TEXTURE_MAPPER {mapper})\nset(USE_GPU_STUB {stub})\n'
                        f'set(WebCore_EMBEDDER_SOURCES "{root.as_posix()}/host/RanvierNativeTextureDraw.cpp")\n'
                        'macro(set_source_files_properties)\n'
                        '  set(arguments ${ARGN})\n'
                        '  list(FIND arguments COMPILE_DEFINITIONS index)\n'
                        '  math(EXPR index "${index} + 1")\n'
                        '  list(GET arguments ${index} definitions)\n'
                        f'  file(WRITE "{output.as_posix()}" "${{definitions}}")\nendmacro()\n'
                        'macro(add_library)\nendmacro()\n'
                        'macro(target_compile_definitions)\nendmacro()\n'
                        'macro(set_target_properties)\nendmacro()\n'
                        'macro(target_link_libraries)\nendmacro()\n'
                        'macro(_WEBKIT_TARGET_LINK_FRAMEWORK)\nendmacro()\n'
                        'macro(_WEBKIT_TARGET)\nendmacro()\n'
                        f'include("{root.as_posix()}/host/RanvierWebCoreHost.cmake")\n')
                    result = subprocess.run([cmake, '-P', str(script)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(output.read_text(), f'RANVIER_COMPOSITING={expected}')

    def test_texture_helpers_do_not_reference_gpu_headers_in_a_stub_build(self):
        compiler = shutil.which('c++') or shutil.which('clang++')
        if not compiler:
            self.skipTest('A C++ compiler is not available')
        source = Path(__file__).resolve().parents[1] / 'host/RanvierNativeTextureDraw.cpp'
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'config.h').write_text('#define USE(feature) USE_##feature\n'
                                                '#define USE_TEXTURE_MAPPER 1\n'
                                                '#define USE_COORDINATED_GRAPHICS 0\n')
            command = [compiler, '-std=c++20', '-fsyntax-only', '-I', str(directory), str(source)]
            result = subprocess.run(command + ['-DRANVIER_COMPOSITING=0'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            gpu = subprocess.run(command + ['-DRANVIER_COMPOSITING=1'], capture_output=True, text=True)
            self.assertNotEqual(gpu.returncode, 0)
            self.assertIn('TextureMapper.h', gpu.stderr)

    def test_view_transitions_require_the_host_compositor(self):
        compiler=shutil.which('c++') or shutil.which('clang++')
        if not compiler:self.skipTest('A C++ compiler is not available')
        root=Path(__file__).resolve().parents[1]
        source=(root/'host/RanvierWebCoreAbi.cpp').read_text()
        capability=source.split('int32_t rv_abi_has(const char* feature)',1)[1].split('\n}\n',1)[0]
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            program=directory/'capability.cpp'
            program.write_text('#include <cstdint>\n#include <cstring>\n#include <initializer_list>\n'
                '#define USE(feature) USE_##feature\n#define ENABLE(feature) 0\n#define PLATFORM(feature) 0\n'
                'int ranvier_dom_has(const char*) { return 0; }\n'
                'int ranvier_print_pdf_supported() { return PRINT_SUPPORTED; }\n'
                'int32_t rv_abi_has(const char* feature)'+capability+'\n}\n'
                'int main() { return rv_abi_has("view-transitions") != EXPECT_SUPPORTED || '
                'rv_abi_has("printing-pdf") != PRINT_SUPPORTED; }\n')
            for name,stub,compositor,expected,printing in [('windows-slim',1,0,0,0),('wpe-slim',0,0,0,1),('gpu',0,1,1,1)]:
                with self.subTest(profile=name):
                    executable=directory/(name+('.exe' if os.name=='nt' else ''))
                    result=subprocess.run([compiler,'-std=c++20',f'-DUSE_GPU_STUB={stub}',
                        f'-DRANVIER_COMPOSITING={compositor}',f'-DEXPECT_SUPPORTED={expected}',f'-DPRINT_SUPPORTED={printing}',
                        str(program),'-o',str(executable)],capture_output=True,text=True)
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                    self.assertEqual(subprocess.run([str(executable)]).returncode,0,
                        name+' must advertise view transitions only with the host compositor')

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
            for filename in ['RanvierWebCoreAbi.cpp','RanvierWebCoreEGL.h','RanvierWebCoreEGL.cpp','RanvierCapabilities.inc','RanvierCapabilityCatalogue.inc','RanvierSvgViewGlue.h','RanvierEventGlue.h','RanvierMutationGlue.h','RanvierPrintOptions.h','RanvierViewportGlue.h','RanvierInspectGlue.h','RanvierWakeLockGlue.h','RanvierNotificationGlue.h','RanvierTransferGlue.h']:
                self.assertTrue((installed/filename).exists(), 'prepare must install ' + filename)
                self.assertEqual((installed/filename).read_bytes(),(root/'host'/filename).read_bytes())
            self.assertIn('#include "RanvierCapabilities.inc"',(installed/'RanvierWebCoreAbi.cpp').read_text())
            self.assertIn('#include "RanvierCapabilityCatalogue.inc"',(installed/'RanvierCapabilities.inc').read_text())


if __name__=='__main__': unittest.main()
