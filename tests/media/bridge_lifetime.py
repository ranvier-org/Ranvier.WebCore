"""Exercise actual app-owned media handles and publication ownership."""
import argparse
import ctypes as C
import json
from pathlib import Path
import threading
import time


class Snapshot(C.Structure):
    _fields_ = [('size', C.c_uint32), ('state', C.c_int32), ('error', C.c_int32), ('flags', C.c_uint32),
                ('position', C.c_double), ('duration', C.c_double)]


class FrameInfo(C.Structure):
    _fields_ = [('size', C.c_uint32), ('width', C.c_uint32), ('height', C.c_uint32), ('reserved', C.c_uint32),
                ('texture', C.c_void_p), ('timestamp', C.c_int64)]


def run(args):
    dll = C.CDLL(str(args.bridge.resolve()))
    P, I = C.c_void_p, C.c_int32
    def bind(name, parameters):
        call = getattr(dll, 'ranvier_media_' + name)
        call.restype, call.argtypes = I, parameters
        return call
    create = bind('create', [C.POINTER(P), C.POINTER(I)])
    open_ = bind('open', [P, C.c_wchar_p])
    play = bind('play', [P])
    cancel = bind('cancel', [P])
    snapshot = bind('snapshot', [P, C.POINTER(Snapshot)])
    next_ = bind('next_frame', [P, C.POINTER(P)])
    frame_info = bind('frame_info', [P, C.POINTER(FrameInfo)])
    frame_release = bind('frame_release', [C.POINTER(P)])
    release = bind('release', [C.POINTER(P)])
    checks = 0
    rows = []
    def check(value, label):
        nonlocal checks
        checks += 1
        assert value, label
    check(C.sizeof(Snapshot) == C.sizeof(FrameInfo) == 32, 'typed DTO layouts')
    check(release(C.byref(P())) == 0 and frame_release(C.byref(P())) == 0, 'null releases idempotent')
    for action in ['release-session', 'cancel-session', 'unused-publication']:
        session, frame, state = P(), P(), I()
        status = create(C.byref(session), C.byref(state))
        check(status == 0 and session.value, 'actual available OS provider: ' + hex(status & 0xffffffff))
        try:
            check(open_(session, str(args.fixture.resolve())) == 0, 'local source opened')
            check(play(session) == 0, 'actual playback starts')
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                status = next_(session, C.byref(frame))
                check(status in [0, 1], 'frame acquisition keeps exact status')
                if status == 0:
                    break
                time.sleep(.01)
            check(bool(frame.value), 'decoded frame publication')
            info = FrameInfo(size=C.sizeof(FrameInfo))
            check(frame_info(frame, C.byref(info)) == 0 and info.texture and (info.width, info.height) == (96, 64), 'owned decoded texture metadata')
            blocked = P()
            check(next_(session, C.byref(blocked)) < 0 and not blocked.value, 'one publication at a time')
            original_session, original_frame = session.value, frame.value
            outcomes = []
            def other_thread():
                outcomes.extend([release(C.byref(session)), frame_release(C.byref(frame))])
            worker = threading.Thread(target=other_thread)
            worker.start()
            worker.join(5)
            check(not worker.is_alive() and outcomes == [C.c_int32(0x8001010e).value] * 2, 'wrong-thread releases rejected')
            check(session.value == original_session and frame.value == original_frame, 'wrong-thread ownership retained')
            if action == 'release-session':
                check(release(C.byref(session)) == 0 and not session.value, 'session release consumes only its handle')
            elif action == 'cancel-session':
                check(cancel(session) == 0, 'cancel pauses and revokes while publication retained')
                value = Snapshot(size=C.sizeof(Snapshot))
                check(snapshot(session, C.byref(value)) == 0 and value.state == 6 and play(session) < 0, 'cancelled session cannot restart')
            check(frame_info(frame, C.byref(info)) == 0 and info.texture, 'outstanding frame remains owned through session teardown/cancel')
            check(frame_release(C.byref(frame)) == 0 and not frame.value, 'release publication and reclaim unused key1')
            check(frame_release(C.byref(frame)) == 0, 'publication release idempotent')
            if action == 'unused-publication':
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    status = next_(session, C.byref(frame))
                    check(status in [0, 1], 'unused key1 reclaimed for next producer publication')
                    if status == 0:
                        break
                    time.sleep(.01)
                check(bool(frame.value), 'producer can publish after an unconsumed lease is released')
                check(frame_release(C.byref(frame)) == 0, 'second publication cleanup')
            rows.append({'action': action, 'timestamp100ns': info.timestamp, 'width': info.width, 'height': info.height})
        finally:
            frame_release(C.byref(frame))
            release(C.byref(session))
    session, state = P(), I()
    check(create(C.byref(session), C.byref(state)) == 0, 'error-control provider')
    try:
        status = open_(session, str(args.fixture.with_name('absent-media-file.mp4').resolve()))
        check(status < 0, 'missing file preserves actual failure')
        value = Snapshot(size=C.sizeof(Snapshot))
        check(snapshot(session, C.byref(value)) == 0 and value.state == 7 and value.error == status, 'failure not converted into unavailable')
        rows.append({'action': 'missing-file', 'HRESULT': status, 'state': value.state})
    finally:
        release(C.byref(session))
    result = {'assertions': checks, 'failures': 0, 'rows': rows}
    args.report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--bridge', type=Path, required=True)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    run(parser.parse_args())
