"""The platform attachment must be available from the staged native host."""
import ctypes
import pathlib
import sys

native = pathlib.Path(sys.argv[1]).resolve()
with __import__('os').add_dll_directory(str(native)):
    host = ctypes.WinDLL(str(native / 'RanvierWebCoreHost.dll'))
    for symbol in ('rv_host_attach_uia', 'rv_host_detach_uia', 'rv_ax_text_child_range'):
        assert getattr(host, symbol, None), f'{symbol} is missing: no OS accessibility bridge can attach'
    host.rv_abi_has.argtypes = [ctypes.c_char_p]
    host.rv_abi_has.restype = ctypes.c_int
    assert host.rv_abi_has(b'accessibility-uia') == 1, 'Windows host does not advertise its UIA bridge'
print('UIA attachment exports present')
