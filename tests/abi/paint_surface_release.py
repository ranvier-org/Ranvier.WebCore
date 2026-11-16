"""Kept-surface probe against an actual runtime directory. A CPU paint of the whole viewport keeps the surface it
draws into, so the next one does not make a new surface. The probe checks what that must not cost:

- the pixels of a paint into a kept surface are those of a paint into a new one, also after the document, the size
  or the device scale changed;
- the host gives the surface back once it has not painted for a few seconds, and at once on rv_release_memory;
- on Windows, it also gives it back when the app pumps its own messages and never calls rv_run_loop_cycle.

Memory is the process's private commit, read on Windows only; elsewhere the probe checks the pixels. On Linux
resident memory cannot show a surface being given back: the allocator keeps one freed frame resident after any
paint, with or without a kept surface (measured under WSL on 2026-11-16, also on the 0.1.1 package)."""

import argparse
import ctypes
import hashlib
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import Native, I, P
from utf8_inputs import Utf8

WIDTH, HEIGHT = 2560, 1600
SURFACE = WIDTH * HEIGHT * 4
# The host drops the surface between two and four seconds after its last whole-viewport paint.
IDLE_SECONDS = 12
MB = 1048576.0

FIRST = ('<!doctype html><html><body style="margin:0;font:20px Arial"><div style="height:900px;background:'
         'linear-gradient(#246,#c84)">kept surface</div><p style="opacity:.5">half</p></body></html>')
SECOND = ('<!doctype html><html><body style="margin:0;font:20px Arial"><div style="width:300px;height:120px;'
          'border-radius:40px;background:rgba(200,30,30,.4)">second</div></body></html>')


def memory_reader():
    """A function returning the bytes this process holds privately, or None where the probe does not read them."""
    if sys.platform == 'win32':
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [(name, ctypes.c_size_t) for name in (
                'PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage',
                'QuotaPeakNonPagedPoolUsage', 'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage', 'PrivateUsage')]

        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        kernel.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]

        def commit():
            counters = Counters()
            counters.cb = ctypes.sizeof(counters)
            assert kernel.K32GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
            return counters.PrivateUsage
        return commit
    return None


def pump_messages(seconds):
    """Dispatches this thread's window messages for a while, as an app with its own message loop does."""
    from ctypes import wintypes
    user = ctypes.WinDLL('user32', use_last_error=True)
    message = wintypes.MSG()
    user.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
    user.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        while user.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):
            user.TranslateMessage(ctypes.byref(message))
            user.DispatchMessageW(ctypes.byref(message))
        time.sleep(0.005)


class Painter:
    def __init__(self, native):
        self.native = native
        self.create = native.bind('rv_host_create', P, [I, I])
        self.destroy = native.bind('rv_host_destroy', None, [P])
        self.resize = native.bind('rv_host_resize', I, [P, I, I])
        self.scale = native.bind('rv_host_set_device_scale', I, [P, ctypes.c_float])
        self.update = native.bind('rv_host_update', I, [P])
        self.cycle = native.bind('rv_run_loop_cycle', I, [I])
        self.paint_whole = native.bind('rv_host_paint_rgba', I, [P, P, I])
        self.paint_rect = native.bind('rv_host_paint_rgba_rect', I, [P, P, I, I, I, I, I])
        self.release = native.bind('rv_release_memory', None, [])
        self.collect = native.bind('rv_collect_garbage', None, [])
        self.pixels = (ctypes.c_uint8 * SURFACE)()
        ctypes.memset(self.pixels, 1, SURFACE)

    def host(self, width, height, markup, scale=None):
        host = self.create(width, height)
        self.native.expect(bool(host), 'host')
        if scale is not None:
            self.native.expect(self.scale(host, scale) == 0, 'device scale status')
        self.load(host, markup)
        return host

    def load(self, host, markup):
        self.native.expect(self.native.call('rv_host_load_html', [P, Utf8], host, markup.encode()) == 0, 'load status')

    def paint(self, host, label, device_width=WIDTH, device_height=HEIGHT):
        """Paints the whole viewport and returns a hash of its pixels."""
        length = device_width * device_height * 4
        self.cycle(0)
        self.update(host)
        status = self.paint_whole(host, self.pixels, length)
        self.native.expect(status >= 0, f'{label}: paint status {status}')
        return hashlib.sha256(memoryview(self.pixels)[:length]).hexdigest()


def pixels(native, painter):
    """A paint into a kept surface gives the pixels of a paint into a new one."""
    host = painter.host(WIDTH, HEIGHT, FIRST)
    new = painter.paint(host, 'first paint')
    native.expect(painter.paint(host, 'second paint') == new, 'a paint into the kept surface differs from the first paint')

    painter.load(host, SECOND)
    fresh = painter.host(WIDTH, HEIGHT, SECOND)
    native.expect(painter.paint(host, 'paint after a new document') == painter.paint(fresh, 'new host'),
                  'the kept surface shows through a new document')
    painter.destroy(fresh)

    native.expect(painter.resize(host, WIDTH // 2, HEIGHT // 2) == 0, 'resize status')
    fresh = painter.host(WIDTH // 2, HEIGHT // 2, SECOND)
    native.expect(painter.paint(host, 'paint after a resize', WIDTH // 2, HEIGHT // 2)
                  == painter.paint(fresh, 'new host at half size', WIDTH // 2, HEIGHT // 2), 'a paint after a resize differs')
    painter.destroy(fresh)

    # The same device size at twice the scale: the surface's size in device pixels is unchanged, its scale is not.
    native.expect(painter.scale(host, 2) == 0, 'device scale status')
    native.expect(painter.resize(host, WIDTH // 4, HEIGHT // 4) == 0, 'resize status')
    kept = painter.paint(host, 'paint at half size', WIDTH // 2, HEIGHT // 2)
    native.expect(painter.paint(host, 'second paint at scale 2', WIDTH // 2, HEIGHT // 2) == kept, 'a second paint at scale 2 differs')
    fresh = painter.host(WIDTH // 4, HEIGHT // 4, SECOND, scale=2)
    native.expect(kept == painter.paint(fresh, 'new host at scale 2', WIDTH // 2, HEIGHT // 2), 'a paint after a scale change differs')
    painter.destroy(fresh)
    painter.destroy(host)


def memory(native, painter, read):
    """The host holds one surface while it paints and gives it back; returns the megabytes it held."""
    def settled():
        # Returns freed memory to the system first, so that a surface the host dropped no longer counts.
        painter.collect()
        return read()

    def wait_for_release(step, label):
        end = time.monotonic() + IDLE_SECONDS
        while time.monotonic() < end:
            step()
            if settled() - baseline < SURFACE // 2:
                return
        native.expect(False, f'{label}: {(settled() - baseline) / MB:.1f} MB above the baseline after {IDLE_SECONDS} s '
                             f'without a paint (the surface is {SURFACE / MB:.1f} MB)')

    host = painter.host(WIDTH, HEIGHT, FIRST)
    # Fills the caches a paint fills. A paint of part of the viewport keeps no surface.
    for _ in range(3):
        painter.cycle(0)
        painter.update(host)
        native.expect(painter.paint_rect(host, painter.pixels, SURFACE, 0, 0, WIDTH, HEIGHT - 1) >= 0, 'partial paint status')
    baseline = settled()

    for _ in range(5):
        painter.paint(host, 'whole paint')
    held = settled() - baseline
    native.expect(held > SURFACE // 2, f'the host kept no surface between paints ({held / MB:.1f} MB above the baseline)')

    def cycle():
        for _ in range(10):
            painter.cycle(20)
    wait_for_release(cycle, 'idle in rv_run_loop_cycle')

    for _ in range(5):
        painter.paint(host, 'whole paint')
    native.expect(settled() - baseline > SURFACE // 2, 'the host kept no surface after it had dropped one')
    painter.release()
    after = settled() - baseline
    native.expect(after < SURFACE // 2, f'rv_release_memory left {after / MB:.1f} MB above the baseline')

    if sys.platform == 'win32':
        for _ in range(5):
            painter.paint(host, 'whole paint')
        native.expect(settled() - baseline > SURFACE // 2, 'the host kept no surface before the message loop')
        wait_for_release(lambda: pump_messages(0.25), "idle in the app's own message loop")
    painter.destroy(host)
    return held / MB


def verify(native_directory):
    native = Native(native_directory)
    painter = Painter(native)
    pixels(native, painter)
    read = memory_reader()
    held = memory(native, painter, read) if read else None
    return native.assertions, held


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    args = parser.parse_args()
    assertions, held = verify(args.native_directory)
    note = f'the host held {held:.1f} MB while painting' if held is not None else f'memory is not read on {sys.platform}'
    print(f'PASS paint_surface_release: {assertions} assertions ({note})', flush=True)


if __name__ == '__main__':
    main()
