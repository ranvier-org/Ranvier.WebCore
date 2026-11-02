"""Actual OS-decoded video and timed DOM captions through the native GPU compositor."""
import argparse
import ctypes as C
import hashlib
import json
import math
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'abi'))
from svg_paint_probe import SvgProbe
from utf8_inputs import Utf8


class Snapshot(C.Structure):
    _fields_ = [('state', C.c_int32), ('error', C.c_int32), ('position', C.c_double), ('duration', C.c_double),
                ('ready', C.c_int32), ('seeking', C.c_int32), ('audio', C.c_int32), ('video', C.c_int32)]


def run(args):
    helper = C.CDLL(str(args.helper.resolve()))
    P, I, U, L, D = C.c_void_p, C.c_int32, C.c_uint32, C.c_int64, C.c_double
    def bind(name, result, parameters):
        value = getattr(helper, name)
        value.restype, value.argtypes = result, parameters
        return value
    create = bind('media_create', I, [C.c_wchar_p, C.POINTER(P)])
    destroy = bind('media_destroy', None, [P])
    close = bind('media_close', I, [P])
    play = bind('media_play', I, [P])
    pause = bind('media_pause', I, [P])
    seek = bind('media_seek', I, [P, D])
    next_frame = bind('media_next', I, [P, C.POINTER(P), C.POINTER(L)])
    republish = bind('media_republish', I, [P])
    readback = bind('media_readback', I, [P, P, P, U, U, U])
    device = bind('media_device', P, [P])
    snapshot = bind('media_snapshot', I, [P, C.POINTER(Snapshot)])
    report = {'assertions': 0, 'scales': []}
    for scale in [1, 1.5, 2]:
        session = P()
        assert create(str(args.fixture.resolve()), C.byref(session)) == 0 and session.value
        try:
            with SvgProbe(args.native_directory, 320, 200) as p:
                p.call('rv_host_set_device_scale', [P, C.c_float], p.host, scale)
                p.load('''<style>body{margin:0;background:white}#clip{position:absolute;left:20px;top:20px;width:90px;height:50px;overflow:hidden}
                #surface{width:96px;height:64px;will-change:transform;transform:translateX(5px);opacity:.75}
                #caption{position:absolute;left:20px;top:90px;font:20px sans-serif}</style>
                <div id="clip"><div id="surface"></div></div><div id="caption"></div>''', standalone=False)
                target, caption = p.node('surface'), p.node('caption')
                p.update()
                frames, bound = [], None
                def state():
                    value = Snapshot()
                    p.expect(snapshot(session, C.byref(value)) == 0, 'actual provider snapshot')
                    p.expect(value.error >= 0, 'provider has no hidden playback error: ' + hex(value.error & 0xffffffff))
                    return value
                def capture(label, phase, *, publish=False):
                    if publish:
                        p.expect(republish(session) == 0, 'application republishes retained paused frame under existing key protocol')
                    frame = P()
                    status = p.bind('rv_host_acquire_d3d11_frame', I, [P,P,C.POINTER(P)])(p.host, device(session), C.byref(frame))
                    p.expect(status == 0 and frame.value, 'strict GPU output acquired: ' + str(status))
                    try:
                        texture, width, height, format_ = P(), I(), I(), I()
                        p.call('rv_gpu_frame_info', [P,P,P,P,P], frame, C.byref(texture), C.byref(width), C.byref(height), C.byref(format_))
                        pixels = (C.c_ubyte * (width.value * height.value * 4))()
                        p.expect(readback(session, texture, pixels, len(pixels), width.value, height.value) == 0, 'actual GPU output readback')
                        output = bytes(pixels)
                        def pixel(x,y):
                            offset = (int(y*scale)*width.value+int(x*scale))*4
                            return list(output[offset:offset+4])
                        center, clipped = pixel(40,35), pixel(115,35)
                        p.expect(center[phase] > 200 and all(45 < center[index] < 100 for index in range(3) if index != phase),
                                 'decoded video follows DOM translation/opacity: ' + str(center))
                        p.expect(clipped == [255,255,255,255], 'decoded video obeys DOM clipping: ' + str(clipped))
                        frames.append({'label':label,'phase':phase,'size':[width.value,height.value],'center':center,'clipped':clipped,'sha256':hashlib.sha256(output).hexdigest()})
                        return hashlib.sha256(output).hexdigest()
                    finally:
                        p.call('rv_gpu_frame_release', [P], frame)
                p.expect(play(session) == 0, 'actual media play')
                deadline = time.monotonic() + 8
                phases = set()
                while time.monotonic() < deadline and len(phases) < 3:
                    texture, timestamp = P(), L()
                    status = next_frame(session, C.byref(texture), C.byref(timestamp))
                    p.expect(status in [0,1], 'actual decoded frame status: ' + hex(status & 0xffffffff))
                    if status == 1:
                        state()
                        time.sleep(.005)
                        continue
                    if texture.value != bound:
                        p.call('rv_host_bind_d3d11_texture', [P,P,P], p.host, target, texture)
                        bound = texture.value
                    phase = 0 if timestamp.value < 6666666 else 1 if timestamp.value < 13333333 else 2
                    cue = ['red cue','green cue','blue cue'][phase]
                    p.call('rv_dom_node_set_text_content', [P,Utf8], caption, cue.encode())
                    p.call('rv_host_native_texture_changed', [P,P], p.host, target)
                    p.expect(p.text('rv_dom_node_get_text_content', [P], caption) == cue, 'caption follows the provider presentation timestamp')
                    capture('frame-' + str(timestamp.value),phase)
                    phases.add(phase)
                    if phase == 1 and len([row for row in frames if row['phase'] == 1]) == 1:
                        p.expect(pause(session) == 0, 'actual media pause')
                        before = state().position
                        first = capture('paused-first',phase,publish=True)
                        time.sleep(.12)
                        second = capture('paused-second',phase,publish=True)
                        p.expect(abs(state().position - before) < .03 and first == second, 'paused audio/video clock and native caption frame remain stable')
                        p.expect(seek(session,1.5) == 0, 'actual seek to blue cue')
                        p.expect(play(session) == 0, 'resume after seek')
                p.expect(phases == {0,1,2}, 'all provider frame/caption phases reach native composition')
                p.call('rv_host_bind_d3d11_texture', [P,P,P], p.host, target, None)
                p.expect(close(session) == 0, 'audio/video session closes after texture unbind')
                p.expect(play(session) < 0, 'closed session rejects playback')
                p.load('<p>replaced after playback</p>', standalone=False)
                p.update()
                report['scales'].append({'scale':scale,'frames':frames})
                report['assertions'] += p.assertions
        finally:
            destroy(session)
    temporary = args.report.with_suffix('.tmp')
    temporary.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    temporary.replace(args.report)
    print(json.dumps({'assertions':report['assertions'],'scales':len(report['scales']),'frames':sum(len(row['frames']) for row in report['scales'])}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory',type=Path,required=True)
    parser.add_argument('--helper',type=Path,required=True)
    parser.add_argument('--fixture',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    run(parser.parse_args())
