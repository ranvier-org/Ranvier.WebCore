"""Count completed main-frame layouts without turning observation into a layout check."""
import ctypes as C
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe
from utf8_inputs import Utf8


def run(directory):
    with SvgProbe(directory, 160, 100) as p:
        P, I = p.pointer, p.integer
        count = p.bind('rv_host_layout_count', I, [P, C.POINTER(C.c_uint32)])
        has = p.bind('rv_abi_has', I, [C.c_char_p])
        p.expect(has(b'host-layout-metrics') == 1, 'capability')

        def layouts():
            value = C.c_uint32()
            p.expect(count(p.host, C.byref(value)) == 0, 'layout counter')
            return value.value

        p.load('<div id="x" style="width:20px;height:10px">x</div>', standalone=False)
        node = p.node('x')
        width = lambda: p.read('html_element', node, 'offset_width', I)
        p.expect(width() == 20, 'initial geometry')
        clean = layouts()
        for _ in range(10):
            p.expect(width() == 20 and layouts() == clean, 'clean getters do not lay out')
        p.call('rv_element_set_attribute', [P, C.c_char_p, Utf8], node, b'style', b'width:40px;height:10px')
        p.expect(layouts() == clean, 'counter does not flush pending style or layout')
        p.expect(width() == 40 and layouts() > clean, 'synchronous getter returns fresh geometry and records actual layout')
        clean = layouts()
        for width_value in (50, 60, 70):
            p.call('rv_element_set_attribute', [P, C.c_char_p, Utf8], node, b'style', f'width:{width_value}px;height:10px'.encode())
        p.expect(layouts() == clean, 'batched writes remain unflushed')
        p.expect(width() == 70 and layouts() == clean + 1, 'one layout for batched writes')
        wrong = []
        worker = threading.Thread(target=lambda: wrong.append(count(p.host, C.byref(C.c_uint32()))))
        worker.start()
        worker.join()
        p.expect(wrong == [-2], 'owner thread only')
        p.expect(count(p.host, None) == -1, 'null output rejected')
        p.release_all()
        stale = p.host
        p.dispose_host()
        value = C.c_uint32(123)
        p.expect(count(stale, C.byref(value)) == -10 and value.value == 123, 'detached host preserves output')
        print('layout phase assertions:', p.assertions)


if __name__ == '__main__':
    run(sys.argv[1])
