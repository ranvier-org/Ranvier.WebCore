import ctypes
import sys
from ctypes import wintypes

mode = sys.argv[1]
value = sys.argv[2] if len(sys.argv) > 2 else ""

if mode == "exit":
    raise SystemExit(int(value))
if mode == "unhandled":
    raise RuntimeError("intentional child exception")
if mode == "crash":
    kernel32 = ctypes.windll.kernel32
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
    kernel32.TerminateProcess.restype = wintypes.BOOL
    kernel32.TerminateProcess(kernel32.GetCurrentProcess(), 0xC0000005)
    raise SystemExit(1)
if mode == "affinity":
    process_mask = wintypes.DWORD()
    system_mask = wintypes.DWORD()
    kernel32 = ctypes.windll.kernel32
    get_mask = kernel32.GetProcessAffinityMask
    get_mask.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD))
    get_mask.restype = wintypes.BOOL
    if not get_mask(kernel32.GetCurrentProcess(), ctypes.byref(process_mask), ctypes.byref(system_mask)):
        raise ctypes.WinError()
    print(f"AFFINITY={process_mask.value}", flush=True)
    print(f"ARG={value}", flush=True)
    raise SystemExit(0)

raise SystemExit(f"unknown child mode: {mode}")
