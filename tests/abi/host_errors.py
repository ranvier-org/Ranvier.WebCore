"""Check host error records against a native runtime and a removed D3D device."""
import ctypes as C
from pathlib import Path
import sys
import threading
sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe

class Record(C.Structure):
    _fields_ = [('operation', C.c_int32), ('source', C.c_int32), ('status', C.c_int32),
                ('native_code', C.c_int32)]

def run(directory, helper_path):
    with SvgProbe(directory, 64, 64) as p:
        P, I = p.pointer, p.integer
        enable = p.bind('rv_host_error_enable', I, [P, I])
        take = p.bind('rv_host_error_take', I, [P, C.POINTER(Record), C.POINTER(I)])
        helper = C.CDLL(helper_path)
        helper.gpu_readback_create.argtypes, helper.gpu_readback_create.restype = [C.POINTER(P)], I
        helper.gpu_readback_destroy.argtypes = [P]
        helper.native_input_removable.argtypes, helper.native_input_removable.restype = [P, C.POINTER(P), C.POINTER(P)], I
        helper.native_input_remove.argtypes, helper.native_input_remove.restype = [P, P, C.POINTER(I)], I
        helper.native_input_removal_release.argtypes = [P]
        helper.native_input_release.argtypes = [P]
        device, texture, removal = P(), P(), P()
        p.expect(helper.gpu_readback_create(C.byref(device)) == 0, 'create D3D device')
        try:
            p.expect(helper.native_input_removable(device, C.byref(texture), C.byref(removal)) == 0, 'create removable device')
            get_device = C.WINFUNCTYPE(None, P, C.POINTER(P))(C.cast(texture, C.POINTER(C.POINTER(P))).contents[3])
            removed_device = P()
            get_device(texture, C.byref(removed_device))
            release = C.WINFUNCTYPE(C.c_ulong, P)(C.cast(removed_device, C.POINTER(C.POINTER(P))).contents[2])
            try:
                p.load('<div style="transform:translateZ(0);width:10px;height:10px">x</div>', standalone=False)
                p.call('rv_host_set_accelerated_compositing', [P, I], p.host, 1)
                p.call('rv_host_update', [P], p.host)
                reasons = (I * 4)()
                p.expect(helper.native_input_remove(removal, texture, reasons) == 0 and reasons[3] != 0, 'real device removal')
                record, present, frame = Record(), I(-1), P()
                acquire = p.bind('rv_host_acquire_d3d11_frame', I, [P, P, C.POINTER(P)])
                p.expect(acquire(p.host, removed_device, C.byref(frame)) < 0, 'disabled failure')
                p.expect(take(p.host, C.byref(record), C.byref(present)) == 0 and present.value == 0, 'disabled by default')
                p.expect(enable(p.host, 1) == 0, 'enable error records')
                status = acquire(p.host, removed_device, C.byref(frame))
                p.expect(status < 0 and not frame.value, 'removed device acquisition fails')
                p.expect(take(p.host, C.byref(record), C.byref(present)) == 0 and present.value == 1, 'take device failure')
                p.expect((record.operation, record.source, record.status, record.native_code) == (1, 1, status, reasons[3]), 'operation, D3D source, status and actual removal reason')
                p.expect(take(p.host, C.byref(record), C.byref(present)) == 0 and present.value == 0, 'take removes record')
                p.expect(acquire(p.host, removed_device, C.byref(frame)) < 0, 'record another failure')
                p.expect(enable(p.host, 0) == 0 and enable(p.host, 1) == 0, 'disable and re-enable')
                p.expect(take(p.host, C.byref(record), C.byref(present)) == 0 and present.value == 0, 'transition clears record')
                wrong = []
                thread = threading.Thread(target=lambda: wrong.append(enable(p.host, 0)))
                thread.start(); thread.join()
                p.expect(wrong == [-2], 'wrong thread rejected')
                p.expect(enable(p.host, 2) == -9, 'invalid enabled value rejected')
            finally:
                release(removed_device)
        finally:
            if texture.value: helper.native_input_release(texture)
            if removal.value: helper.native_input_removal_release(removal)
            helper.gpu_readback_destroy(device)
        p.release_all()
        stale = p.host
        p.dispose_host()
        p.expect(enable(stale, 1) == -10, 'destroyed host rejected')
        print('host error assertions:', p.assertions)

if __name__ == '__main__':
    run(sys.argv[1], sys.argv[2])
