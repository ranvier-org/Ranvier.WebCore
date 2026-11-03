"""Reject a real old host before acquiring an optional-provider callback lease."""
import argparse
import ctypes as C
import json
import os
from pathlib import Path
import select
import subprocess


class Geometry(C.Structure):
    _fields_ = [('size', C.c_uint32), ('known', C.c_int32), ('x', C.c_int32), ('y', C.c_int32), ('scale', C.c_double)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--provider', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--expect-attached', action='store_true')
    args = parser.parse_args()
    host_library = C.CDLL(str(args.native.resolve()), mode=os.RTLD_NOW | os.RTLD_GLOBAL)
    host_library.rv_abi_version.restype = C.c_int
    assert host_library.rv_abi_version() == 62
    host_library.rv_host_create.argtypes = [C.c_int, C.c_int]
    host_library.rv_host_create.restype = C.c_void_p
    host_library.rv_host_destroy.argtypes = [C.c_void_p]
    host_library.rv_host_destroy.restype = None
    module = C.CDLL(str(args.provider.resolve()), mode=os.RTLD_LAZY | os.RTLD_LOCAL)
    module.rv_atspi_bridge_create.argtypes = [C.c_void_p, C.c_char_p, C.c_char_p, C.c_int, C.POINTER(Geometry), C.POINTER(C.c_uint64)]
    module.rv_atspi_bridge_create.restype = C.c_int
    module.rv_atspi_bridge_release.argtypes = [C.c_uint64]
    module.rv_atspi_bridge_release.restype = C.c_int
    bus = subprocess.Popen(['dbus-daemon', '--session', '--nofork', '--print-address=1'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    host = None
    token = C.c_uint64(99)
    try:
        assert select.select([bus.stdout], [], [], 3)[0]
        address = bus.stdout.readline().strip()
        assert address
        host = host_library.rv_host_create(80, 60)
        assert host
        geometry = Geometry(C.sizeof(Geometry), 0, 0, 0, 1)
        status = module.rv_atspi_bridge_create(host, address, b'Compatibility', 13, C.byref(geometry), C.byref(token))
        value = token.value
        attached = status == 0 and value != 0
        if attached:
            assert module.rv_atspi_bridge_release(token) == 0
            token.value = 0
        result = dict(status=status, returnedToken=value, actualOldHostAbi=62, attached=attached,
            expected='attached baseline' if args.expect_attached else 'unsupported with no lease')
        args.report.write_text(json.dumps(result, indent=2))
        print(json.dumps(result))
        assert attached if args.expect_attached else status == -9 and value == 0
    finally:
        if token.value not in [0, 99]:
            module.rv_atspi_bridge_release(token)
        if host:
            host_library.rv_host_destroy(host)
        bus.terminate()
        try: bus.wait(timeout=3)
        except subprocess.TimeoutExpired: bus.kill(); bus.wait(timeout=3)
        bus.stdout.close()


if __name__ == '__main__':
    main()
