import argparse, ctypes as C, hashlib, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'abi'))
from form_collections import Native, Case, P, I
from web_animations import Arena, animate, seek

parser = argparse.ArgumentParser()
parser.add_argument('--native-directory', required=True)
parser.add_argument('--report', required=True)
parser.add_argument('--helper-library', required=True)
args = parser.parse_args()
n = Native(args.native_directory)
helper = C.CDLL(args.helper_library)
helper.gpu_readback_create.argtypes = [C.POINTER(P)]
helper.gpu_readback_create.restype = I
helper.gpu_readback_destroy.argtypes = [P]
helper.gpu_readback_rgba.argtypes = [P, P, P, C.c_uint64, C.c_uint32, C.c_uint32]
helper.gpu_readback_rgba.restype = I
device = P()
assert helper.gpu_readback_create(C.byref(device)) == 0 and device.value
PAGE = '<style>html,body{margin:0;background:#123456}#clip{position:absolute;left:4px;top:4px;width:60px;height:40px;overflow:hidden}#box{position:absolute;left:4px;top:4px;width:20px;height:20px;background:red;will-change:transform,opacity}#top{position:absolute;left:54px;top:8px;width:4px;height:20px;background:blue;z-index:2}</style><div id="clip"><div id="box"></div></div><div id="top"></div>'
rows = []; held = []
def acquire(host, width, height):
    n.ok('rv_host_update', [P], host)
    frame = P()
    n.ok('rv_host_acquire_d3d11_frame', [P, P, P], host, device, C.byref(frame))
    assert frame.value
    return frame
def info(frame):
    texture, width, height, format_ = P(), I(), I(), I()
    n.ok('rv_gpu_frame_info', [P, P, P, P, P], frame, C.byref(texture), C.byref(width), C.byref(height), C.byref(format_))
    assert texture.value and format_.value == 1
    return texture, width.value, height.value
def read(frame, scale):
    texture, width, height = info(frame)
    pixels = (C.c_ubyte * (width * height * 4))()
    assert helper.gpu_readback_rgba(device, texture, pixels, len(pixels), width, height) == 0
    data = bytes(pixels)
    sample = lambda x,y: list(data[(int(y*scale)*width+int(x*scale))*4:(int(y*scale)*width+int(x*scale))*4+4])
    return data, sample
try:
    for scale in [1, 1.5, 2]:
        page = Case(n, PAGE)
        animation = None
        try:
            n.ok('rv_host_resize', [P, I, I], page.host, 101, 67)
            n.ok('rv_host_set_accelerated_compositing', [P, I], page.host, 1)
            n.ok('rv_host_set_device_scale', [P, C.c_float], page.host, scale)
            arena = Arena()
            status, animation = animate(n, page, 'animate', page.node('box'),
                [{'props': {'transform': 'translateX(0px)', 'opacity': '1'}}, {'props': {'transform': 'translateX(40px)', 'opacity': '0.5'}}],
                {'duration': 1000, 'fill': 'both'}, arena)
            assert status == 0 and animation
            n.ok('rv_dom_web_animation_pause', [P], animation)
            for time, center, expected in [(0,16,[255,0,0,255]),(500,36,[196,13,22,255]),(1000,60,[137,26,43,255])]:
                seek(n, animation, time)
                frame = acquire(page.host, 101, 67)
                try:
                    assert info(frame)[1:] == (int(101*scale),int(67*scale))
                    data, at = read(frame, scale)
                    row = {'scale': scale, 'time': time, 'center': at(center,16), 'clipped': at(66,16), 'stack': at(55,16), 'sha256': hashlib.sha256(data).hexdigest()}
                    rows.append(row)
                    assert all(abs(a-b)<=1 for a,b in zip(row['center'], expected)), row
                    assert row['clipped'] == [18,52,86,255], row
                    assert row['stack'] == [0,0,255,255], row
                finally: n.ok('rv_gpu_frame_release', [P], frame)
            frame = acquire(page.host, 101, 67)
            held.append(frame)
            blocked = P(123)
            assert n.call('rv_host_acquire_d3d11_frame', [P,P,P], page.host,device,C.byref(blocked)) == -9 and not blocked.value
            n.ok('rv_host_resize', [P,I,I],page.host,103,69)
            fresh = acquire(page.host,103,69)
            assert info(fresh)[1:] == (int(103*scale),int(69*scale))
            n.ok('rv_gpu_frame_release',[P],fresh)
            assert info(frame)[1:] == (int(101*scale),int(67*scale))
        finally:
            if animation:
                n.ok('rv_dom_web_animation_cancel',[P],animation)
                n.bind('rv_event_target_release',None,[P])(animation)
            page.close()
        assert info(held[-1])[1:] == (int(101*scale),int(67*scale))
        n.ok('rv_gpu_frame_release',[P],held.pop())
finally:
    for frame in held: n.ok('rv_gpu_frame_release',[P],frame)
    helper.gpu_readback_destroy(device)
    Path(args.report).write_text(json.dumps({'rows':rows,'assertions':n.assertions,'hostCpuPaintCalls':0,'productionAcquisition':'D3D shared texture, composite rgba=nullptr; no CPU pixel fallback','readback':'test-only consumer staging'},indent=2)+'\n')
print(f'PASS GPU animation/clip/stack/lifetime {len(rows)} frames {n.assertions} assertions')
