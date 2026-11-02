"""Actual host PDF ABI, existing resource ownership, and deferred host teardown."""

import argparse
import ctypes as C
import hashlib
import io
import json
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'printing'))
from svg_paint_probe import SvgProbe
from print177_probe import markup
from pypdf import PdfReader

P, I, U64, I64 = C.c_void_p, C.c_int32, C.c_uint64, C.c_int64
Cancel = C.CFUNCTYPE(I, P)
Completion = C.CFUNCTYPE(None, P, I, I, I)


class Options(C.Structure):
    _fields_ = [('size', C.c_uint32), ('max_pages', C.c_uint32),
                ('paper_width_points', C.c_double), ('paper_height_points', C.c_double),
                ('margin_top_points', C.c_double), ('margin_right_points', C.c_double),
                ('margin_bottom_points', C.c_double), ('margin_left_points', C.c_double),
                ('output_budget_bytes', U64), ('raster_dpi', C.c_float), ('reserved', C.c_uint32)]

    def __init__(self, **changes):
        super().__init__(C.sizeof(self), 16, 576, 720, 36, 36, 36, 36, 8 * 1024 * 1024, 144, 0)
        for name, value in changes.items():
            setattr(self, name, value)


def run(args):
    report = {'assertions': 0, 'cases': []}
    with SvgProbe(args.native_directory, 500, 300) as p:
        export = p.bind('rv_host_print_pdf', I, [P, C.POINTER(Options), Cancel, P, Completion, P, C.POINTER(I), C.POINTER(U64)])
        result_of = p.bind('rv_print_pdf_result', I, [U64, P, I64, C.POINTER(I64)])
        release = p.bind('rv_resource_release', I, [U64])
        cycle = p.bind('rv_run_loop_cycle', I, [I])
        check = p.expect
        check(p.bind('rv_abi_has', I, [C.c_char_p])(b'printing-pdf') == 1, 'PDF renderer capability')
        check(C.sizeof(Options) == 72, 'typed options layout')
        p.load(markup(args.webkit_source), standalone=False)
        for _ in range(200):
            p.update()
            state = I(-1)
            check(p.bind('rv_fonts_status', I, [P, C.POINTER(I)])(p.host, C.byref(state)) == 0, 'font status')
            if state.value == 0:
                break
            cycle(5)
        else:
            raise AssertionError('font readiness timeout')
        callbacks = []
        tokens = []

        def read(token):
            length = I64(-1)
            status = result_of(token, None, 0, C.byref(length))
            check(status == (-6 if length.value else 0), 'byte size query')
            if not length.value:
                return b''
            data = C.create_string_buffer(length.value)
            check(result_of(token, data, len(data), C.byref(length)) == 0, 'PDF bytes copy')
            return data.raw

        def request(label, *, options=None, cancel_action=None, expected_status=0, expected_outcome=0):
            polls, events = [], []

            def poll(context):
                polls.append(context)
                return int(bool(cancel_action(len(polls)))) if cancel_action else 0

            def completed(context, outcome, width, height):
                events.append([outcome, width, height])

            cancel, completion = Cancel(poll), Completion(completed)
            callbacks.extend([cancel, completion])
            pages, token = I(-1), U64(0xdead)
            chosen = options or Options()
            before = hashlib.sha256(bytes(p.paint())).hexdigest()
            status = export(p.host, C.byref(chosen), cancel, 123, completion, 456, C.byref(pages), C.byref(token))
            check(status == expected_status, label + ': status ' + str(status))
            check(not events, label + ': no callback inside synchronous render')
            check(hashlib.sha256(bytes(p.paint())).hexdigest() == before, label + ': screen restored')
            if status:
                check(token.value == pages.value == 0, label + ': no result on admission/render failure')
                check(not events, label + ': failed call owns no callback')
                return 0, b''
            check(bool(token.value), label + ': existing resource token')
            tokens.append(token.value)
            for _ in range(100):
                if events:
                    break
                cycle(1)
            check(events == [[expected_outcome, 0, 0]], label + ': one deferred terminal ' + str(events))
            data = read(token.value)
            check(bool(data) == (expected_outcome == 0), label + ': no partial PDF')
            report['cases'].append({'label': label, 'polls': len(polls), 'pages': pages.value,
                                    'outcome': expected_outcome, 'sha256': hashlib.sha256(data).hexdigest()})
            return token.value, data

        try:
            _, pdf = request('three-pages')
            parsed = PdfReader(io.BytesIO(pdf), strict=True)
            check(len(parsed.pages) == 3, 'real three-page PDF')
            for index, page in enumerate(parsed.pages):
                check([float(page.mediabox.width), float(page.mediabox.height)] == [576, 720], 'point page box')
                check('PRINT177 PAGE ' + str(index + 1) in page.extract_text(), 'actual DOM text remains text')
            request('cancel-before', cancel_action=lambda count: True, expected_outcome=3)
            request('cancel-after-first-page', cancel_action=lambda count: count >= 3, expected_outcome=3)
            request('output-budget', options=Options(output_budget_bytes=128), expected_status=-5)
            request('invalid-geometry', options=Options(paper_width_points=0), expected_status=-9)
            request('page-budget', options=Options(max_pages=2), expected_status=-9)
            request('repeat-after-failure')
            thread_result = []

            def wrong_thread():
                pages, token = I(-1), U64(0xdead)
                option = Options()
                thread_result.append((export(p.host, C.byref(option), callbacks[0], None, callbacks[1], None,
                                             C.byref(pages), C.byref(token)), pages.value, token.value))

            worker = threading.Thread(target=wrong_thread)
            worker.start()
            worker.join(5)
            check(not worker.is_alive() and thread_result == [(-2, 0, 0)], 'wrong thread never starts a print')
            load_attempts = []

            def reload_in_poll(count):
                if count == 1:
                    text = b'<p>REENTRANT LOAD</p>'
                    load_attempts.append(p.bind('rv_host_load_html', I, [P, P, I])(p.host, text, len(text)))
                return True

            request('reentrant-load-rejected', cancel_action=reload_in_poll, expected_outcome=3)
            check(load_attempts == [-12], 'printing transaction rejects document replacement')
            retained, retained_bytes = request('bytes-outlive-host')
            p.release_nodes()
            p.dispose_host()
            check(read(retained) == retained_bytes, 'completed PDF resource survives host destruction')
        finally:
            for token in tokens:
                check(release(token) == 0, 'release owned PDF operation')
                check(release(token) == 0, 'resource release remains idempotent')
        report['assertions'] += p.assertions
    with SvgProbe(args.native_directory, 100, 100) as p:
        p.load('<p>close at print admission</p>', standalone=False)
        p.update()
        polls, events = [], []

        def close_from_poll(_):
            polls.append(1)
            p.bind('rv_host_destroy', None, [P])(p.host)
            return 1

        cancel = Cancel(close_from_poll)
        completed = Completion(lambda *values: events.append(values))
        options, pages, token = Options(), I(-1), U64(0xdead)
        export = p.bind('rv_host_print_pdf', I, [P, C.POINTER(Options), Cancel, P, Completion, P, C.POINTER(I), C.POINTER(U64)])
        status = export(p.host, C.byref(options), cancel, None, completed, None, C.byref(pages), C.byref(token))
        p.expect(status == -12 and pages.value == token.value == 0 and polls == [1] and not events,
                 'reentrant close defers until print state is restored and publishes no operation')
        p.host = None
        report['assertions'] += p.assertions
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', type=Path, required=True)
    parser.add_argument('--webkit-source', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    run(parser.parse_args())
