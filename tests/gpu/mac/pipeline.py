"""Real ANGLE/Metal producer completion and bounded IOSurface lifetime acceptance."""
import ctypes as C
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'abi'))
from portable_pipeline import exercise
from svg_paint_probe import SvgProbe

P, I, U = C.c_void_p, C.c_int32, C.c_uint32
surface_api = C.CDLL('/System/Library/Frameworks/IOSurface.framework/IOSurface')
def bind(name, result, *parameters):
    fn = getattr(surface_api, name)
    fn.restype, fn.argtypes = result, parameters
    return fn
lock = bind('IOSurfaceLock', I, P, U, P)
unlock = bind('IOSurfaceUnlock', I, P, U, P)
address = bind('IOSurfaceGetBaseAddress', P, P)
with SvgProbe(sys.argv[1], 80, 60) as probe:
    probe.call('rv_host_set_accelerated_compositing', [P, I], probe.host, 1)
    html = b'<style>html,body{margin:0;background:rgb(17,34,51)}div{transform:translate3d(0,0,0)}</style><div>frame</div>'
    load = probe.library.rv_host_load_html
    load.argtypes, load.restype = [P, C.c_char_p, I], I
    assert load(probe.host, html, len(html)) == 0
    info = probe.bind('rv_gpu_frame_info', I, [P, C.POINTER(P), C.POINTER(I), C.POINTER(I), C.POINTER(I)])
    def inspect(frame, expected_width, expected_height):
        surface, width, height, format_ = P(), I(), I(), I()
        assert info(frame, C.byref(surface), C.byref(width), C.byref(height), C.byref(format_)) == 0
        assert (width.value, height.value, format_.value) == (expected_width, expected_height, 2)
        assert lock(surface, 1, None) == 0
        try:
            assert list((C.c_ubyte * 4).from_address(address(surface))) == [51, 34, 17, 255]
        finally:
            assert unlock(surface, 1, None) == 0
    exercise(probe.library, probe.host, P(1), inspect)
    probe.host = None # exercise destroyed the host while retaining its final lease.
