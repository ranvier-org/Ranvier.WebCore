"""Generic font families on Windows: serif, sans-serif, monospace, cursive, fantasy and an unset family each lay
out like the installed font the host maps it to, in HTML text and in SVG text."""
import argparse
import ctypes
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utf8_inputs import Utf8, bind as bind_utf8

TEXT = 'Sphinx of black quartz, judge my vow 0123456789 Il1'
# Generic family (None: no font-family declaration) and the installed family the host maps it to.
MAPPED = [(None, 'Times New Roman'), ('serif', 'Times New Roman'), ('sans-serif', 'Arial'), ('monospace', 'Consolas'),
          ('cursive', 'Comic Sans MS'), ('fantasy', 'Impact'), ('NoSuchFont, sans-serif', 'Arial')]
# Fonts every supported Windows version installs; the test needs them to lay the text out at different widths.
REQUIRED = ['Times New Roman', 'Arial', 'Consolas']


def verify(native_directory):
    if sys.platform != 'win32':
        print('generic font families: the host maps them on Windows only; skipped')
        return
    directory = Path(native_directory).resolve()
    search = os.add_dll_directory(str(directory))
    library = ctypes.CDLL(str(directory / 'RanvierWebCoreHost.dll'))
    pointer, integer, double = ctypes.c_void_p, ctypes.c_int32, ctypes.c_double
    assertions = 0
    nodes = []

    def bind(name, result, args):
        return bind_utf8(library, name, result, args)

    def expect(condition, label):
        nonlocal assertions
        assertions += 1
        if not condition:
            raise AssertionError(label)

    release_node = bind('rv_node_release', None, [pointer])
    rect = bind('rv_element_rect', integer, [pointer] + [ctypes.POINTER(double)] * 4)
    find = bind('rv_document_get_element_by_id', pointer, [pointer, Utf8])
    host = bind('rv_host_create', pointer, [integer, integer])(1600, 900)
    expect(bool(host), 'host creation')
    try:
        body = bind('rv_document_body', pointer, [pointer])(host)
        nodes.append(body)
        families = [family for family, _ in MAPPED] + sorted({mapped for _, mapped in MAPPED})
        rows = []
        for index, family in enumerate(families):
            style = '' if family is None else f' style="font-family:{family}"'
            attribute = '' if family is None else f' font-family="{family}"'
            rows.append(f'<div><span id="h{index}"{style}>{TEXT}</span></div>'
                        f'<svg width="1600" height="50"><g{attribute} font-size="32">'
                        f'<text id="s{index}" x="0" y="36">{TEXT}</text></g></svg>')
        markup = '<style>body{margin:0} div{white-space:nowrap} span{font-size:32px} svg{display:block}</style>' + ''.join(rows)
        expect(bind('rv_dom_element_set_inner_html', integer, [pointer, Utf8])(body, markup.encode('utf-8')) == 0, 'fixture markup')
        expect(bind('rv_host_update', integer, [pointer])(host) == 0, 'layout')

        def width(prefix, family):
            element = find(host, f'{prefix}{families.index(family)}'.encode('utf-8'))
            nodes.append(element)
            expect(bool(element), f'fixture element for {family!r}')
            x, y, w, h = double(), double(), double(), double()
            expect(rect(element, ctypes.byref(x), ctypes.byref(y), ctypes.byref(w), ctypes.byref(h)) == 0, f'rect of {family!r}')
            expect(w.value > 0, f'{family!r} has a width')
            return round(w.value, 2)

        for prefix, kind in [('h', 'HTML'), ('s', 'SVG')]:
            required = [width(prefix, family) for family in REQUIRED]
            expect(len(set(required)) == len(REQUIRED), f'{kind}: {REQUIRED} are installed and lay out at different widths: {required}')
            for family, mapped in MAPPED:
                actual, expected = width(prefix, family), width(prefix, mapped)
                expect(actual == expected, f'{kind}: {family or "an unset family"!r} lays out as {mapped!r}: {actual} != {expected}')
    finally:
        for node in reversed(nodes):
            if node:
                release_node(node)
        bind('rv_host_destroy', None, [pointer])(host)
        search.close()
    print(f'PASS generic font families: {assertions} assertions')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    verify(parser.parse_args().native_directory)
