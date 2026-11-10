"""Exercise the actual EGL release body with failed flushes and tracked fence ownership."""
from pathlib import Path
import os
import subprocess
import tempfile

source = (Path(__file__).resolve().parents[2] / 'host/RanvierWebCoreEGL.cpp').read_text()
body = source.split('bool RvEGLSurface::releaseConsumer(bool nonblocking)', 1)[1].split('\n}', 1)[0] + '\n}'
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    program = root / 'release.cpp'
    program.write_text('''#include <cassert>
#include <utility>
constexpr int EGL_NO_SYNC_KHR = 0, EGL_SYNC_FENCE_KHR = 1, GL_NO_ERROR = 0;
int liveFences = 0, error = 0, context = 2, finishes = 0;
bool failCreate = false;
int eglGetCurrentDisplay() { return 1; }
int eglGetCurrentContext() { return context; }
int eglCreateSyncKHR(int, int, void*) { if (failCreate) return 0; return ++liveFences; }
bool eglDestroySyncKHR(int, int) { --liveFences; return true; }
void glFlush() { }
void glFinish() { ++finishes; }
int glGetError() { return std::exchange(error, 0); }
struct State { bool acquired = true; int display = 1, consumerContext = 2, consumerFence = 0; };
struct RvEGLSurface { State storage; State* state = &storage; bool releaseConsumer(bool); };
bool RvEGLSurface::releaseConsumer(bool nonblocking)''' + body + '''
int main() {
    RvEGLSurface surface;
    context = 3;
    assert(!surface.releaseConsumer(true) && liveFences == 0 && surface.storage.acquired);
    context = 2;
    failCreate = true;
    assert(!surface.releaseConsumer(true) && liveFences == 0 && surface.storage.acquired);
    failCreate = false;
    error = 1;
    assert(!surface.releaseConsumer(true) && surface.storage.acquired);
    assert(liveFences == 0 && surface.storage.consumerFence == 0);
    assert(surface.releaseConsumer(true) && liveFences == 1 && !surface.storage.acquired);
    assert(!surface.releaseConsumer(true) && liveFences == 1);
    assert(finishes == 0);
}
''')
    executable = root / 'release'
    subprocess.run([os.environ.get('CXX', 'c++'), str(program), '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
print('EGL_CONSUMER_FENCE=PASS')
