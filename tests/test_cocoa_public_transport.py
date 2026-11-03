import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PublicIOSurfaceContract(unittest.TestCase):
    def test_c_and_cpp_consumers_can_use_common_frame_lifetime(self):
        source = '''
#include "RanvierWebCoreAbi.h"
int32_t (*acquire)(RvHost*, RvGpuFrame**) = rv_host_acquire_iosurface_frame;
int32_t (*bind_surface)(RvHost*, RvNode*, void*, int32_t) = rv_host_bind_iosurface;
int32_t (*inspect)(RvGpuFrame*, void**, int32_t*, int32_t*, int32_t*) = rv_gpu_frame_info;
int32_t (*release_frame)(RvGpuFrame*) = rv_gpu_frame_release;
int format = RV_GPU_BGRA8_PREMULTIPLIED;
'''
        compiler = shutil.which('clang') or shutil.which('cc')
        if not compiler:
            self.skipTest('C/C++ compiler unavailable')
        with tempfile.TemporaryDirectory(prefix='ranvier-iosurface-header-') as temporary:
            for language in ('c', 'c++'):
                with self.subTest(language=language):
                    path = Path(temporary) / ('consumer.' + ('c' if language == 'c' else 'cpp'))
                    path.write_text(source)
                    result = subprocess.run([compiler, '-x', language, '-fsyntax-only', '-Werror',
                                             '-I' + str(ROOT / 'host'), str(path)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
