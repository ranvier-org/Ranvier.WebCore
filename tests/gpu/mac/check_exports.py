"""Check the experimental transport contract before attempting the Mac proof."""
import argparse
import ctypes
import os
from pathlib import Path


def check(directory, texture_input=False):
    directory = Path(directory).resolve()
    name = 'RanvierWebCoreHost.dll' if os.name == 'nt' else 'libRanvierWebCoreHost.dylib'
    cookie = os.add_dll_directory(str(directory)) if os.name == 'nt' else None
    try:
        library = ctypes.CDLL(str(directory / name))
        required = ['rv_mac_spike_acquire_frame', 'rv_mac_spike_frame_info',
                    'rv_mac_spike_frame_release', 'rv_mac_spike_identity', 'rv_mac_spike_counters']
        if texture_input:
            required.append('rv_mac_spike_bind_iosurface')
        missing = [symbol for symbol in required if not hasattr(library, symbol)]
        assert not missing, 'Mac GPU spike transport is absent: ' + ', '.join(missing)
    finally:
        if cookie:
            cookie.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('native_directory')
    parser.add_argument('--texture-input', action='store_true')
    args = parser.parse_args()
    check(args.native_directory, args.texture_input)
    print('MAC_GPU_SPIKE exports PASS')
