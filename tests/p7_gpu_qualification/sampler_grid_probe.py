"""Isolate fixed-format filtering from output blending on the existing ANGLE device."""
import ctypes as C
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

root = Path(__file__).parent
stage = root / 'precision-runtime' / 'runtimes' / 'win-x64' / 'native'
sys.path.insert(0, str(root / 'helpers'))
from resize_observation import Native, Scene, P, I


def hashes():
    return {p.relative_to(stage).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in stage.rglob('*') if p.is_file()}


before = hashes()
native = Native(stage)
scene = Scene(native, '<!doctype html><div style="width:20px;height:20px;background:red;transform:translate3d(1px,1px,0);will-change:transform"></div>', 1.5)
objects = {'textures': [], 'framebuffers': [], 'shaders': [], 'programs': [], 'buffers': []}
rows = []
try:
    scene.update()
    scene.update()
    rgba = (C.c_ubyte * (1200 * 900 * 4))()
    native.ok('rv_host_paint_rgba', [P, P, I], scene.host, rgba, len(rgba))
    gl = C.WinDLL(str(stage / 'libGLESv2.dll'))

    def bind(name, result, args):
        function = getattr(gl, name)
        function.restype, function.argtypes = result, args
        return function

    U, F, Z = C.c_uint, C.c_float, C.c_size_t
    for name, result, args in [
        ('glGetString', C.c_char_p, [U]), ('glGetError', U, []),
        ('glCreateShader', U, [U]), ('glShaderSource', None, [U, I, C.POINTER(C.c_char_p), C.POINTER(I)]),
        ('glCompileShader', None, [U]), ('glGetShaderiv', None, [U, U, C.POINTER(I)]),
        ('glGetShaderInfoLog', None, [U, I, C.POINTER(I), P]), ('glCreateProgram', U, []),
        ('glAttachShader', None, [U, U]), ('glLinkProgram', None, [U]),
        ('glGetProgramiv', None, [U, U, C.POINTER(I)]), ('glUseProgram', None, [U]),
        ('glGetUniformLocation', I, [U, C.c_char_p]), ('glUniform2f', None, [I, F, F]),
        ('glUniform1i', None, [I, I]), ('glUniform1f', None, [I, F]), ('glGenTextures', None, [I, C.POINTER(U)]),
        ('glBindTexture', None, [U, U]), ('glTexParameteri', None, [U, U, I]),
        ('glTexImage2D', None, [U, I, I, I, I, I, U, U, P]),
        ('glGenFramebuffers', None, [I, C.POINTER(U)]), ('glBindFramebuffer', None, [U, U]),
        ('glFramebufferTexture2D', None, [U, U, U, U, I]), ('glCheckFramebufferStatus', U, [U]),
        ('glViewport', None, [I, I, I, I]), ('glDisable', None, [U]), ('glEnable', None, [U]),
        ('glBlendFunc', None, [U, U]), ('glClearColor', None, [F, F, F, F]),
        ('glClear', None, [U]), ('glDrawArrays', None, [U, I, I]),
        ('glReadPixels', None, [I, I, I, I, U, U, P]), ('glActiveTexture', None, [U]),
        ('glDeleteTextures', None, [I, C.POINTER(U)]), ('glDeleteFramebuffers', None, [I, C.POINTER(U)]),
        ('glDeleteShader', None, [U]), ('glDeleteProgram', None, [U]),
    ]:
        bind(name, result, args)

    extensions = gl.glGetString(0x1F03).decode()
    renderer = gl.glGetString(0x1F01).decode()
    assert 'GL_EXT_color_buffer_float' in extensions, 'Float target unavailable; retain this control as unsupported'
    vertex = b'''#version 300 es
    void main(){vec2 p=vec2((gl_VertexID<<1)&2,gl_VertexID&2);gl_Position=vec4(p*2.0-1.0,0.0,1.0);}'''
    fragment = b'''#version 300 es
    precision highp float; uniform sampler2D image; uniform vec2 uv; uniform float grid; out vec4 color;
    void main(){color=texture(image,grid>0.0 ? ((gl_FragCoord.xy-vec2(0.5))/256.0+vec2(0.5))/2.0 : uv);}'''
    shaders = []
    for kind, source in [(0x8B31, vertex), (0x8B30, fragment)]:
        shader = gl.glCreateShader(kind)
        objects['shaders'].append(shader)
        pointer = C.c_char_p(source)
        gl.glShaderSource(shader, 1, C.byref(pointer), None)
        gl.glCompileShader(shader)
        status = I()
        gl.glGetShaderiv(shader, 0x8B81, C.byref(status))
        if not status.value:
            log = C.create_string_buffer(4096)
            gl.glGetShaderInfoLog(shader, len(log), None, log)
            raise AssertionError(log.value.decode())
        shaders.append(shader)
    program = gl.glCreateProgram()
    objects['programs'].append(program)
    for shader in shaders:
        gl.glAttachShader(program, shader)
    gl.glLinkProgram(program)
    status = I()
    gl.glGetProgramiv(program, 0x8B82, C.byref(status))
    assert status.value, 'Program link failed'
    gl.glUseProgram(program)
    uv_location = gl.glGetUniformLocation(program, b'uv')
    gl.glUniform1i(gl.glGetUniformLocation(program, b'image'), 0)

    def texture(width, height, data, floating=False):
        value = U()
        gl.glGenTextures(1, C.byref(value))
        objects['textures'].append(value.value)
        gl.glBindTexture(0x0DE1, value)
        for parameter, setting in [(0x2801, 0x2601), (0x2800, 0x2601), (0x2802, 0x812F), (0x2803, 0x812F)]:
            gl.glTexParameteri(0x0DE1, parameter, setting)
        gl.glTexImage2D(0x0DE1, 0, 0x8814 if floating else 0x8058, width, height, 0,
                        0x1908, 0x1406 if floating else 0x1401, data)
        return value.value

    targets = []
    for floating in [True, False]:
        target = texture(256, 256, None, floating)
        framebuffer = U()
        gl.glGenFramebuffers(1, C.byref(framebuffer))
        objects['framebuffers'].append(framebuffer.value)
        gl.glBindFramebuffer(0x8D40, framebuffer)
        gl.glFramebufferTexture2D(0x8D40, 0x8CE0, 0x0DE1, target, 0)
        assert gl.glCheckFramebufferStatus(0x8D40) == 0x8CD5
        targets.append(framebuffer.value)
    gl.glViewport(0, 0, 1, 1)
    for capability in [0x0B71, 0x0C11, 0x0B44, 0x0BD0]:
        gl.glDisable(capability)
    gl.glActiveTexture(0x84C0)
    # Full backing pixels are reconstructed from the independently derived integer rectangles.
    data = np.zeros((89, 175, 4), dtype=np.uint8)
    data[1:88, 1:174, 3] = 255
    data[8:81, 8:167, :] = 0
    data[23:72, 11:161] = [255, 0, 0, 255]
    source = texture(175, 89, data.ctypes.data)
    for x, y in [(188, 22), (181, 29), (26, 44), (175, 93), (100, 45), (100, 50), (15, 22)]:
        uv = np.array([(x + .5 - 14.859375) / 174.984375,
                       (y + .5 - 21.234375) / 88.9921875], dtype=np.float32)
        for dx, dy in [(0, 0), (-1, -1), (1, 1)]:
            actual_uv = uv + np.array([dx, dy], dtype=np.float32) * np.float32(8.940699629534556e-7)
            gl.glUniform2f(uv_location, *map(float, actual_uv))
            record = {'pixel': [x, y], 'attributeBudgetSigns': [dx, dy], 'uvFloat32': list(map(float, actual_uv))}
            for name, framebuffer, floating, blend in [('sampleFloat', targets[0], True, False),
                                                       ('sampleUnorm', targets[1], False, False),
                                                       ('whiteBlendUnorm', targets[1], False, True)]:
                gl.glBindFramebuffer(0x8D40, framebuffer)
                gl.glBindTexture(0x0DE1, source)
                gl.glClearColor(1, 1, 1, 1)
                gl.glClear(0x4000)
                (gl.glEnable if blend else gl.glDisable)(0x0BE2)
                gl.glBlendFunc(1, 0x0303)
                gl.glDrawArrays(4, 0, 3)
                output = (F * 4)() if floating else (C.c_ubyte * 4)()
                gl.glReadPixels(0, 0, 1, 1, 0x1908, 0x1406 if floating else 0x1401, output)
                assert gl.glGetError() == 0
                record[name] = list(output)
            if dx == dy == 0 and [x,y] in [[188,22],[181,29]]:
                factors = []
                for axis in [0,1]:
                    one = np.zeros_like(data)
                    if axis == 0: one[:,:,3] = np.where(np.arange(175)[None,:] < (174 if x==188 else 167),255,0)
                    else: one[:,:,3] = np.where(np.arange(89)[:,None] >= (1 if y==22 else 8),255,0)
                    one_texture = texture(175,89,one.ctypes.data)
                    gl.glBindFramebuffer(0x8D40,targets[0])
                    gl.glDisable(0x0BE2)
                    gl.glBindTexture(0x0DE1,one_texture)
                    gl.glDrawArrays(4,0,3)
                    one_output=(F*4)()
                    gl.glReadPixels(0,0,1,1,0x1908,0x1406,one_output)
                    assert gl.glGetError()==0
                    factors.append(list(one_output))
                record['factorSamplesFloat']=factors
                gl.glBindTexture(0x0DE1,source)
            rows.append(record)
    grid_rows=[]
    gl.glUniform1f(gl.glGetUniformLocation(program,b'grid'),1)
    gl.glViewport(0,0,256,256)
    yy,xx=np.mgrid[0:256,0:256]/256
    for bits in range(16):
        taps=np.array([(bits>>i)&1 for i in range(4)],dtype=np.uint8).reshape(2,2)
        pixels=np.zeros((2,2,4),dtype=np.uint8)
        pixels[:,:,3]=taps*255
        tex=texture(2,2,pixels.ctypes.data)
        ideal=(1-xx)*(1-yy)*taps[0,0]+xx*(1-yy)*taps[0,1]+(1-xx)*yy*taps[1,0]+xx*yy*taps[1,1]
        sampled=None
        for name,framebuffer,floating,blend in [('float',targets[0],True,False),('unorm',targets[1],False,False),('white',targets[1],False,True)]:
            gl.glBindFramebuffer(0x8D40,framebuffer)
            gl.glBindTexture(0x0DE1,tex)
            gl.glClearColor(1,1,1,1)
            gl.glClear(0x4000)
            (gl.glEnable if blend else gl.glDisable)(0x0BE2)
            gl.glDrawArrays(4,0,3)
            values=np.empty((256,256,4),dtype=np.float32 if floating else np.uint8)
            gl.glReadPixels(0,0,256,256,0x1908,0x1406 if floating else 0x1401,values.ctypes.data)
            assert gl.glGetError()==0
            if floating:
                sampled=values[:,:,3].astype(float)
                error=np.abs(sampled-ideal)
                assert np.max(error)<=1/255
                assert sampled.min()>=taps.min() and sampled.max()<=taps.max()
                assert np.all(values[:,:,:3]==0)
                record={'patternBits':bits,'samples':65536,'maximumAbsoluteFilterError':float(error.max()),'meanAbsoluteFilterError':float(error.mean()),'outputFloatSha256':hashlib.sha256(values.tobytes()).hexdigest()}
            elif not blend:
                error=np.abs(values[:,:,3]-sampled*255)
                assert error.max()<=.6
                record['unormMaximumErrorUnits']=float(error.max())
            else:
                expected=255*(1-sampled)
                error=np.abs(values[:,:,0]-expected)
                assert error.max()<=.6
                assert np.all(values[:,:,0]==values[:,:,1]) and np.all(values[:,:,1]==values[:,:,2]) and np.all(values[:,:,3]==255)
                record['blendMaximumErrorUnits']=float(error.max())
        grid_rows.append(record)
finally:
    scene.close()
assert hashes() == before
result = {'renderer': renderer, 'sourceBacking': {'size': [175, 89], 'outer': [1,1,174,88],
          'inner': [8,8,167,81], 'red': [11,23,161,72]}, 'rows': rows,
          'shaders': {'vertex': vertex.decode(), 'fragment': fragment.decode()},
          'runtimeHashes': before, 'runtimeUnchanged': True,
          'gridRows':grid_rows, 'scope': 'Independent sampler/blend isolation; constant UVs do not qualify WebCore interpolator'}
(root / 'sampler-grid-probe.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps({'gridPatterns':len(grid_rows),'gridSamples':sum(r['samples'] for r in grid_rows),'rows': len(rows), 'runtimeUnchanged': True, 'renderer': renderer}))
