"""Run a Windows child with a pinned affinity and report its exact exit DWORD."""

import ctypes
import os
import subprocess
import sys
from ctypes import wintypes


CREATE_SUSPENDED = 0x00000004
STARTF_USESTDHANDLES = 0x00000100
STD_INPUT_HANDLE = ctypes.c_ulong(-10).value
STD_OUTPUT_HANDLE = ctypes.c_ulong(-11).value
STD_ERROR_HANDLE = ctypes.c_ulong(-12).value
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
WAIT_OBJECT_0 = 0
WAIT_FAILED = 0xFFFFFFFF


class StartupInfo(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(wintypes.BYTE)),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class ProcessInformation(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


def affinity_mask(text):
    value = text.strip()
    if value.lower().startswith("0x"):
        mask = int(value[2:], 16)
    else:
        mask = int(value, 10)
    if mask <= 0:
        raise ValueError("affinity mask must be positive")
    return mask


def launch_pinned(mask, arguments):
    if os.name != "nt":
        raise OSError("pinned mode requires Windows")

    executable = arguments[0]
    command_line = ctypes.create_unicode_buffer(subprocess.list2cmdline(arguments))
    startup = StartupInfo()
    startup.cb = ctypes.sizeof(startup)
    startup.dwFlags |= STARTF_USESTDHANDLES

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetStdHandle.argtypes = [wintypes.DWORD]
    kernel32.GetStdHandle.restype = wintypes.HANDLE
    std_handles = [
        kernel32.GetStdHandle(STD_INPUT_HANDLE),
        kernel32.GetStdHandle(STD_OUTPUT_HANDLE),
        kernel32.GetStdHandle(STD_ERROR_HANDLE),
    ]
    if any(handle is None or handle == INVALID_HANDLE_VALUE for handle in std_handles):
        raise ctypes.WinError(ctypes.get_last_error())
    startup.hStdInput, startup.hStdOutput, startup.hStdError = std_handles

    kernel32.CreateProcessW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.BOOL,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.LPCWSTR,
        ctypes.POINTER(StartupInfo),
        ctypes.POINTER(ProcessInformation),
    ]
    kernel32.CreateProcessW.restype = wintypes.BOOL
    kernel32.SetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.c_size_t]
    kernel32.SetProcessAffinityMask.restype = wintypes.BOOL
    kernel32.ResumeThread.argtypes = [wintypes.HANDLE]
    kernel32.ResumeThread.restype = wintypes.DWORD
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    process = ProcessInformation()
    created = kernel32.CreateProcessW(
        executable,
        command_line,
        None,
        None,
        True,
        CREATE_SUSPENDED,
        None,
        None,
        ctypes.byref(startup),
        ctypes.byref(process),
    )
    if not created:
        raise ctypes.WinError(ctypes.get_last_error())

    resumed = False
    try:
        if not kernel32.SetProcessAffinityMask(process.hProcess, mask):
            error = ctypes.get_last_error()
            kernel32.TerminateProcess(process.hProcess, 1)
            raise ctypes.WinError(error)
        if kernel32.ResumeThread(process.hThread) == WAIT_FAILED:
            error = ctypes.get_last_error()
            kernel32.TerminateProcess(process.hProcess, 1)
            raise ctypes.WinError(error)
        resumed = True
        wait_result = kernel32.WaitForSingleObject(process.hProcess, 0xFFFFFFFF)
        if wait_result != WAIT_OBJECT_0:
            raise ctypes.WinError(ctypes.get_last_error())
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(process.hProcess, ctypes.byref(exit_code)):
            raise ctypes.WinError(ctypes.get_last_error())
        return exit_code.value
    finally:
        if not resumed:
            kernel32.TerminateProcess(process.hProcess, 1)
        kernel32.CloseHandle(process.hThread)
        kernel32.CloseHandle(process.hProcess)


def main(argv):
    if len(argv) < 3:
        print("usage: pinned-run.py <affinity-mask> <executable> [args...]", file=sys.stderr)
        return 127
    try:
        mask = affinity_mask(argv[1])
        code = launch_pinned(mask, argv[2:])
    except (OSError, ValueError) as error:
        print(f"pinned-run: {error}", file=sys.stderr)
        return 127
    print(f"BURN_CHILD_EXIT_CODE={code}", flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
