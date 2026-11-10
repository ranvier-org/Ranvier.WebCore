"""Compile the actual extension admission body against an injected extension provider."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

source = (Path(__file__).resolve().parents[2] / 'host/RanvierWebCoreEGL.cpp').read_text()
body = source.split('bool RvEGLSurface::supportsPipeline(void* display)', 1)[1].split('\n}', 1)[0] + '\n}'
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    program = root / 'matrix.cpp'
    program.write_text('''#include <cstring>
#include <cassert>
static unsigned extensions;
bool epoxy_has_egl_extension(void*, const char* name) {
    if (!std::strcmp(name, "EGL_KHR_fence_sync")) return extensions & 1;
    if (!std::strcmp(name, "EGL_KHR_image_base")) return extensions & 2;
    if (!std::strcmp(name, "EGL_KHR_gl_texture_2D_image")) return extensions & 4;
    return false;
}
struct RvEGLSurface { static bool supportsPipeline(void*); };
bool RvEGLSurface::supportsPipeline(void* display)''' + body + '''
int main() {
    for (extensions = 0; extensions != 8; ++extensions) {
        assert(!RvEGLSurface::supportsPipeline(nullptr));
        assert(RvEGLSurface::supportsPipeline(reinterpret_cast<void*>(1)) == (extensions == 7));
    }
}
''')
    if sys.platform == 'win32':
        # Use the same isolated MSVC environment as the existing state tests.
        bootstrap = Path(__file__).with_name('pipeline_state.py').read_text().split('subprocess.run(command, cwd=out, env=env, check=True)', 1)[0]
        scope = {'__file__': str(Path(__file__).with_name('pipeline_state.py'))}
        exec(compile(bootstrap, 'pipeline_state.py', 'exec'), scope)
        executable = root / 'matrix.exe'
        command = [scope['compiler'], '/nologo', '/EHsc', str(program), '/Fe:' + str(executable), '/Fo:' + str(root) + '/']
        environment = scope['env']
    else:
        executable = root / 'matrix'
        command = [os.environ.get('CXX', 'c++'), str(program), '-o', str(executable)]
        environment = os.environ
    subprocess.run(command, env=environment, cwd=root, check=True)
    subprocess.run([str(executable)], env=environment, cwd=root, check=True)
print('EGL_EXTENSION_MATRIX=PASS')
