"""Private synchronous DOM printing experiment; not a product ABI or OS spooler."""

import argparse
import base64
import ctypes as C
import hashlib
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'abi'))
from svg_paint_probe import SvgProbe
from pypdf import PdfReader
from PIL import Image

P, I = C.c_void_p, C.c_int32


class Options(C.Structure):
    _fields_ = [('size', C.c_uint32), ('no_event_pumping', C.c_uint32),
                ('paper_width_points', C.c_double), ('paper_height_points', C.c_double),
                ('margin_top_points', C.c_double), ('margin_right_points', C.c_double),
                ('margin_bottom_points', C.c_double), ('margin_left_points', C.c_double),
                ('output_budget_bytes', C.c_uint64), ('cancel_after_pages', I),
                ('max_pages', C.c_uint32), ('raster_dpi', C.c_float), ('reserved', C.c_uint32)]

    def __init__(self, **changes):
        super().__init__(C.sizeof(self), 1, 576, 720, 36, 36, 36, 36, 8 * 1024 * 1024, -1, 16, 144, 0)
        for name, value in changes.items():
            setattr(self, name, value)


class Info(C.Structure):
    _fields_ = [('size', C.c_uint32), ('outcome', I), ('page_count', C.c_uint32),
                ('painted_pages', C.c_uint32), ('printing_before', C.c_uint32),
                ('printing_after', C.c_uint32), ('layout_page_width', C.c_double),
                ('layout_page_height', C.c_double), ('pdf_bytes', C.c_uint64)]


def markup(webkit_source):
    font = (webkit_source / 'Tools/TestWebKitAPI/Resources/cocoa/Ahem.ttf').read_bytes()
    assert hashlib.sha256(font).hexdigest() == '63d2abd0041c3e3b4b52ad8d382353b53c51c6785e76ce56ed9dacad2d2e31c4'
    font_url = 'data:font/ttf;base64,' + base64.b64encode(font).decode()
    image = io.BytesIO()
    Image.new('RGB', (4, 4), (0, 0, 255)).save(image, format='PNG')
    image_url = 'data:image/png;base64,' + base64.b64encode(image.getvalue()).decode()
    pages = ''.join(f'<article><h1>PRINT177 PAGE {n}</h1><p>Invoice document {n}: text stays text.</p>'
                    '<svg width="180" height="35"><rect width="96" height="10" fill="#f00"/>'
                    '<rect x="120" width="30" height="30" fill="#008000"/></svg>'
                    f'<img width="32" height="32" src="{image_url}">'
                    '<p class="font">XXXX</p><p class="screen-only">SCREEN ONLY</p></article>' for n in (1, 2, 3))
    return ('<!doctype html><meta charset="utf-8"><style>'
            f'@font-face{{font-family:PrintAhem;src:url({font_url})}}'
            'html,body{margin:0}article{height:450px;padding:12px;font:16px Arial,sans-serif}'
            '.font{font:20px PrintAhem}h1{font-size:24px}'
            '@media print{article{height:220px;padding:0;break-before:page}article:first-child{break-before:auto}'
            '.screen-only{display:none}}</style><body>' + pages + '</body>')


def run(args):
    args.output.mkdir(exist_ok=False, parents=True)
    report = {'assertions': 0, 'failures': [], 'jobs': [], 'prototype': 'private synchronous owner-turn; no pumping/reentrancy claim'}

    def check(value, label):
        report['assertions'] += 1
        if not value:
            report['failures'].append(label)
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')

    with SvgProbe(args.native_directory, 500, 300) as p:
        retained_results = []
        bridge = C.CDLL(str(args.bridge_library))
        try:
            export = bridge.ranvier_print177_export
        except AttributeError as error:
            raise AssertionError('private printing entry point absent; official runtime cannot perform this prototype') from error
        export.restype, export.argtypes = I, [P, C.POINTER(Options), C.POINTER(P)]
        info_of, bytes_of, release = bridge.ranvier_print177_info, bridge.ranvier_print177_bytes, bridge.ranvier_print177_release
        info_of.restype, info_of.argtypes = I, [P, C.POINTER(Info)]
        bytes_of.restype, bytes_of.argtypes = I, [P, C.POINTER(P), C.POINTER(C.c_uint64)]
        release.restype, release.argtypes = None, [P]
        p.load(markup(args.webkit_source), standalone=False)
        document = p.bind('rv_host_document', P, [P])(p.host)
        p.retained.append(('rv_node_release', document))
        font_status = p.bind('rv_fonts_status', I, [P, C.POINTER(I)])
        for _ in range(200):
            p.update()
            state = I(-1)
            assert font_status(p.host, C.byref(state)) == 0
            if state.value == 0:
                break
            p.bind('rv_run_loop_cycle', I, [I])(5)
        else:
            raise AssertionError('font did not settle before synchronous admission')
        p.call('rv_host_scroll_to', [P, I, I], p.host, 0, 80)
        p.update()

        def screen():
            p.update()
            x, y = I(), I()
            p.call('rv_host_scroll_position', [P, C.POINTER(I), C.POINTER(I)], p.host, C.byref(x), C.byref(y))
            width, height = I(), I()
            p.call('rv_host_paint_size', [P, C.POINTER(I), C.POINTER(I)], p.host, C.byref(width), C.byref(height))
            rgba = (C.c_uint8 * (width.value * height.value * 4))()
            p.call('rv_host_paint_rgba', [P, P, I], p.host, rgba, len(rgba))
            data = bytes(rgba)
            return {'scroll': [x.value, y.value], 'paint': hashlib.sha256(data).hexdigest(),
                    'size': [width.value, height.value]}

        def job(label, options, expected, keep=False):
            before = screen()
            result = P()
            status = export(document, C.byref(options), C.byref(result))
            check(status == 0 and bool(result), label + ': admission')
            if not result:
                return b''
            try:
                info = Info(C.sizeof(Info))
                check(info_of(result, C.byref(info)) == 0, label + ': metadata')
                pointer, length = P(), C.c_uint64()
                check(bytes_of(result, C.byref(pointer), C.byref(length)) == 0, label + ': bytes view')
                data = C.string_at(pointer, length.value) if length.value else b''
                check(info.outcome == expected, label + ': outcome ' + str(info.outcome))
                check(info.printing_before == info.printing_after == 0, label + ': print mode restored')
                check(screen() == before, label + ': screen pixels and scroll restored')
                check(bool(data) == (expected == 0), label + ': no partial PDF published')
                report['jobs'].append({'label': label, 'info': {k: getattr(info, k) for k, _ in Info._fields_}, 'sha256': hashlib.sha256(data).hexdigest()})
                if keep:
                    retained_results.append((result.value, hashlib.sha256(data).hexdigest()))
                return data
            finally:
                if not any(handle == result.value for handle, _ in retained_results):
                    release(result)

        first = job('three-pages', Options(), 0)
        if first:
            pdf_path = args.output / 'three-pages.pdf'
            pdf_path.write_bytes(first)
            pdf = PdfReader(io.BytesIO(first), strict=True)
            check(len(pdf.pages) == 3, 'three real paginated pages')
            for index, page in enumerate(pdf.pages):
                check([float(page.mediabox.width), float(page.mediabox.height)] == [576, 720], 'page physical box ' + str(index))
                text = page.extract_text()
                check('PRINT177 PAGE ' + str(index + 1) in text, 'page marker remains text ' + str(index))
                check('SCREEN ONLY' not in text, 'print media style ' + str(index))
                check(bool(page['/Resources'].get('/Font')), 'font resources ' + str(index))
                font_descriptors = []
                font_resources = page['/Resources'].get('/Font', {})
                if hasattr(font_resources, 'get_object'):
                    font_resources = font_resources.get_object()
                for font in font_resources.values():
                    font = font.get_object()
                    for candidate in [font] + [x.get_object() for x in font.get('/DescendantFonts', [])]:
                        descriptor = candidate.get('/FontDescriptor')
                        if descriptor:
                            font_descriptors.append(descriptor.get_object())
                check(any('Ahem' in str(d.get('/FontName')) and any(k in d for k in ['/FontFile', '/FontFile2', '/FontFile3'])
                          for d in font_descriptors), 'fixture font embedded ' + str(index))
            renderer = shutil.which('pdftoppm')
            if not renderer:
                raise RuntimeError('existing pdftoppm is required; do not install a dependency silently')
            command = [renderer, '-png', '-r', '72', str(pdf_path), str(args.output / 'page')]
            subprocess.run(command, check=True, timeout=45, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            rendered = sorted(args.output.glob('page-*.png'))
            check(len(rendered) == 3, 'independent rasterizer page count')
            for path in rendered:
                image = Image.open(path).convert('RGB')
                check(image.size == (576, 720), 'independent physical raster size ' + path.name)
                red = [(x, y) for y in range(image.height) for x in range(image.width) if (lambda c: c[0] > 240 and c[1] < 20 and c[2] < 20)(image.getpixel((x, y)))]
                span = max(x for x, _ in red) - min(x for x, _ in red) + 1 if red else 0
                check(abs(span - 72) <= 1, 'CSS one-inch ruler is 72 PDF points: ' + str(span))
                check(any(c[2] > 240 and c[0] < 20 and c[1] < 20 for c in image.get_flattened_data()), 'decoded image survives PDF ' + path.name)
        job('cancel-before', Options(cancel_after_pages=0), 1)
        job('cancel-after-first-page', Options(cancel_after_pages=1), 1)
        job('bounded-output-failure', Options(output_budget_bytes=128), 2)
        job('repeat-after-failures', Options(), 0)
        job('invalid-geometry', Options(paper_width_points=0), 3)
        for scale in (1.5, 2.0):
            p.call('rv_host_set_device_scale', [P, C.c_float], p.host, scale)
            scaled = job('screen-device-scale-' + str(scale), Options(), 0)
            if scaled:
                scaled_pdf = PdfReader(io.BytesIO(scaled), strict=True)
                check(len(scaled_pdf.pages) == 3 and all([float(x.mediabox.width), float(x.mediabox.height)] == [576, 720]
                                                       for x in scaled_pdf.pages), 'screen scale preserves physical page boxes ' + str(scale))
        job('result-outlives-host', Options(), 0, keep=True)
        p.load('<p>HOST RELOADED AFTER PRINT</p>', standalone=False)
        p.update()
        check(bool(bytes(p.paint())), 'host reload remains renderable')
        p.release_nodes()
        p.dispose_host()
        check(p.host is None, 'close after restored print has completed')
        for handle, digest in retained_results:
            try:
                pointer, length = P(), C.c_uint64()
                check(bytes_of(handle, C.byref(pointer), C.byref(length)) == 0, 'owned PDF readable after host close')
                check(hashlib.sha256(C.string_at(pointer, length.value)).hexdigest() == digest, 'owned PDF unchanged after host close')
            finally:
                release(handle)
    report['native_directory'] = str(args.native_directory)
    report['bridge_library'] = str(args.bridge_library)
    (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return 1 if report['failures'] else 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True, type=Path)
    parser.add_argument('--bridge-library', required=True, type=Path)
    parser.add_argument('--webkit-source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    raise SystemExit(run(parser.parse_args()))
