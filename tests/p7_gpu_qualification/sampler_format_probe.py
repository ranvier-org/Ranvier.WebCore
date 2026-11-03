"""Isolate fixed-format filtering from output blending on the existing ANGLE device."""
import ctypes as C
import argparse
import hashlib
import json
from pathlib import Path
import sys


import numpy as np

root = Path(__file__).parent
parser = argparse.ArgumentParser()
parser.add_argument('--native-directory', type=Path)
parser.add_argument('--output', type=Path)
args = parser.parse_args()
output = args.output.resolve() if args.output else root
output.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(root))
from sampler_numeric_evidence import NumericEvidence
from sampler_format_policy import ideal_alpha, evaluate, complete, store_control, negative_controls
stage = args.native_directory.resolve() if args.native_directory else root / 'precision-runtime' / 'runtimes' / 'win-x64' / 'native'
sys.path.insert(0, str(root / 'helpers'))
from resize_observation import Native, Scene, P, I


def hashes():
    return {p.relative_to(stage).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in stage.rglob('*') if p.is_file()}


before = hashes()
evidence = NumericEvidence(output)
evidence.save(runtimeBefore=before)
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
        ('glGetIntegerv', None, [U, C.POINTER(I)]), ('glGetBooleanv', None, [U, C.POINTER(C.c_ubyte)]),
        ('glIsEnabled', C.c_ubyte, [U]), ('glUniform4f', None, [I,F,F,F,F]),
        ('glGetFramebufferAttachmentParameteriv', None, [U,U,U,C.POINTER(I)]),
        ('glGetTexParameteriv', None, [U,U,C.POINTER(I)]),
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
    def gl_state():
        state = {'enabled': {}, 'integers': {}, 'framebufferAttachment': {}, 'texture': {}}
        for label, token in [('blend',0x0BE2),('dither',0x0BD0),('depth',0x0B71),('stencil',0x0B90),('scissor',0x0C11),('cull',0x0B44),('rasterizerDiscard',0x8C89),('sampleCoverage',0x80A0),('sampleAlphaToCoverage',0x809E)]:
            state['enabled'][label] = bool(gl.glIsEnabled(token))
        for label,token,count in [('subpixelBits',0x0D50,1),('viewport',0x0BA2,4),('currentProgram',0x8B8D,1),('drawFramebuffer',0x8CA6,1),('readFramebuffer',0x8CAA,1),('activeTexture',0x84E0,1),('texture2d',0x8069,1),('samplerBinding',0x8919,1),('packAlignment',0x0D05,1),('packRowLength',0x0D02,1),('packSkipRows',0x0D03,1),('packSkipPixels',0x0D04,1),('unpackAlignment',0x0CF5,1),('unpackRowLength',0x0CF2,1),('pixelPackBuffer',0x88ED,1),('blendSourceRgb',0x80C9,1),('blendDestinationRgb',0x80C8,1),('blendEquationRgb',0x8009,1)]:
            value=(I*count)();gl.glGetIntegerv(token,value);state['integers'][label]=list(value)
        mask=(C.c_ubyte*4)();gl.glGetBooleanv(0x0C23,mask);state['colorWriteMask']=list(mask)
        for label,token in [('componentType',0x8211),('redBits',0x8212),('greenBits',0x8213),('blueBits',0x8214),('alphaBits',0x8215)]:
            value=I();gl.glGetFramebufferAttachmentParameteriv(0x8D40,0x8CE0,token,C.byref(value));state['framebufferAttachment'][label]=value.value
        for label,token in [('minFilter',0x2801),('magFilter',0x2800),('wrapS',0x2802),('wrapT',0x2803),('baseLevel',0x813C),('maxLevel',0x813D)]:
            value=I();gl.glGetTexParameteriv(0x0DE1,token,C.byref(value));state['texture'][label]=value.value
        state['queryError']=gl.glGetError()
        return state

    evidence.save(renderer=renderer,vendor=gl.glGetString(0x1F00).decode(),version=gl.glGetString(0x1F02).decode(),extensions=extensions)
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

    def compile_fragment(source):
        shader = gl.glCreateShader(0x8B30)
        objects['shaders'].append(shader)
        pointer = C.c_char_p(source)
        gl.glShaderSource(shader, 1, C.byref(pointer), None)
        gl.glCompileShader(shader)
        status = I()
        gl.glGetShaderiv(shader, 0x8B81, C.byref(status))
        if not status.value:
            log = C.create_string_buffer(4096)
            gl.glGetShaderInfoLog(shader, len(log), None, log)
            raise AssertionError('Control fragment compile failed: '+log.value.decode())
        value = gl.glCreateProgram()
        objects['programs'].append(value)
        gl.glAttachShader(value, shaders[0])
        gl.glAttachShader(value, shader)
        gl.glLinkProgram(value)
        gl.glGetProgramiv(value, 0x8B82, C.byref(status))
        assert status.value, 'Control program link failed'
        return value

    fetch_source = b'''#version 300 es
    precision highp float; uniform highp sampler2D image; out highp vec4 color;
    void main(){color=texelFetch(image,ivec2(gl_FragCoord.xy),0);}'''
    fetch_program = compile_fragment(fetch_source)
    gl.glUseProgram(fetch_program)
    gl.glUniform1i(gl.glGetUniformLocation(fetch_program, b'image'), 0)
    constant_source = b'''#version 300 es
    precision highp float; uniform highp vec4 sourceColor; out highp vec4 color;
    void main(){color=sourceColor;}'''
    constant_program = compile_fragment(constant_source)
    gl.glUseProgram(program)
    gl.glUniform1f(gl.glGetUniformLocation(program, b'grid'), 1)
    gl.glViewport(0, 0, 256, 256)

    def draw_grid(name, source_texture, framebuffer, floating=False, blend=False):
        gl.glBindFramebuffer(0x8D40, framebuffer)
        gl.glBindTexture(0x0DE1, source_texture)
        gl.glClearColor(1, 1, 1, 1)
        gl.glClear(0x4000)
        (gl.glEnable if blend else gl.glDisable)(0x0BE2)
        gl.glBlendFunc(1, 0x0303)
        gl.glDrawArrays(4, 0, 3)
        values = np.empty((256, 256, 4), dtype=np.float32 if floating else np.uint8)
        gl.glReadPixels(0, 0, 256, 256, 0x1908, 0x1406 if floating else 0x1401, values.ctypes.data)
        assert gl.glGetError() == 0, name
        evidence.stage(name, values, gl_state())
        assert evidence.current['stages'][-1]['state']['queryError'] == 0
        return values

    pattern_rows, control_rows, negative_rows = [], [], []
    for bits in range(16):
        taps = np.array([(bits >> i) & 1 for i in range(4)], dtype=np.uint8).reshape(2, 2)
        ideal = ideal_alpha(bits)
        evidence.pattern(bits, taps, ideal)
        pixels = np.zeros((2, 2, 4), dtype=np.uint8)
        pixels[:, :, 3] = taps*255
        tex = texture(2, 2, pixels.ctypes.data)
        gl.glUseProgram(program)
        floating = draw_grid('float', tex, targets[0], True)
        unorm = draw_grid('unorm', tex, targets[1])
        white = draw_grid('white', tex, targets[1], blend=True)
        row = evaluate(bits, floating, unorm, white)
        pattern_rows.append(row)
        evidence.comparison('historicalUnormVersusFloat', floating, unorm,
                            np.abs(unorm[:, :, 3].astype(float)-floating[:, :, 3].astype(float)*255), .6)
        evidence.comparison('historicalWhiteVersusFloat', floating, white,
                            np.max(np.abs(white[:, :, :3].astype(float)-(255*(1-floating[:, :, 3].astype(float)))[:, :, None]), axis=2), .6)
        evidence.comparison('completeUnormVersusIndependentIdeal', ideal*255, unorm,
                            np.abs(unorm[:, :, 3].astype(float)-ideal*255), 1.6)
        evidence.comparison('completeWhiteVersusIndependentIdeal', 255*(1-ideal), white,
                            np.max(np.abs(white[:, :, :3].astype(float)-(255*(1-ideal))[:, :, None]), axis=2), 1.6)

        known = texture(256, 256, floating.ctypes.data, True)
        gl.glTexParameteri(0x0DE1, 0x2801, 0x2600)
        gl.glTexParameteri(0x0DE1, 0x2800, 0x2600)
        gl.glUseProgram(fetch_program)
        stored = draw_grid('knownFloatFetchUnorm', known, targets[1])
        store = store_control(stored, floating)
        gl.glUseProgram(program)
        gl.glBindTexture(0x0DE1, tex)
        gl.glTexParameteri(0x0DE1, 0x2801, 0x2600)
        gl.glTexParameteri(0x0DE1, 0x2800, 0x2600)
        nearest = draw_grid('nearestUnorm', tex, targets[1])
        nearest_float = draw_grid('nearestFloat', tex, targets[0], True)
        nearest_exact = bool(np.array_equal(nearest.astype(float), nearest_float.astype(float)*255))
        nearest_exact &= bool(np.isin(nearest[:, :, 3], taps*255).all())
        gl.glBindTexture(0x0DE1, tex)
        gl.glTexParameteri(0x0DE1, 0x2801, 0x2601)
        gl.glTexParameteri(0x0DE1, 0x2800, 0x2601)
        repeated = draw_grid('repeatUnorm', tex, targets[1])
        repeated_float = draw_grid('repeatFloat', tex, targets[0], True)
        repeat_exact = bool(np.array_equal(repeated, unorm) and np.array_equal(repeated_float, floating))

        worst = np.unravel_index(np.argmax(np.abs(unorm[:, :, 3].astype(float)-ideal*255)), ideal.shape)
        reference = floating[worst].copy()
        gl.glUseProgram(constant_program)
        gl.glUniform4f(gl.glGetUniformLocation(constant_program, b'sourceColor'), *map(float, reference))
        constant = draw_grid('constantUnorm', tex, targets[1])
        constant_check = store_control(constant, np.broadcast_to(reference, constant.shape))
        constant_white = draw_grid('constantWhite', tex, targets[1], blend=True)
        constant_white_error = float(np.max(np.abs(constant_white[:, :, :3].astype(float)-
                                                   255*(reference[:3].astype(float)+1-float(reference[3])))))
        gl.glUseProgram(program)
        if 'GL_OES_texture_float_linear' in extensions.split():
            float_pixels = pixels.astype(np.float32)/255
            float_tex = texture(2, 2, float_pixels.ctypes.data, True)
            float_source = draw_grid('floatSourceFloat', float_tex, targets[0], True)
            float_source_unorm = draw_grid('floatSourceUnorm', float_tex, targets[1])
            float_source_white = draw_grid('floatSourceWhite', float_tex, targets[1], blend=True)
            float_source_policy = evaluate(bits, float_source, float_source_unorm, float_source_white)
            float_source_control = {'status':'AVAILABLE', 'policy':float_source_policy}
        else:
            float_source_control = {'status':'UNAVAILABLE', 'reason':'GL_OES_texture_float_linear absent'}

        checks = {'patternBits':bits, 'knownFloatStore':store, 'nearestExact':nearest_exact,
                  'repeatedByteIdentical':repeat_exact, 'constantStore':constant_check,
                  'constantWhiteErrorUnits':constant_white_error, 'floatSource':float_source_control}
        checks['pass'] = (store['pass'] and constant_check['pass'] and nearest_exact and repeat_exact and
                          constant_white_error <= 1.6 and float_source_control['status'] == 'AVAILABLE' and
                          float_source_policy['policyFailures'] == 0)
        control_rows.append(checks)
        if bits == 1:
            negative_rows = negative_controls(bits, floating, unorm, white)
        evidence.save(completedFormatRows=pattern_rows, controls=control_rows, negatives=negative_rows)

    summary = complete(pattern_rows)
    controls_pass = all(row['pass'] for row in control_rows)
    negatives_pass = len(negative_rows) == 4 and all(row['failures'] > 0 for row in negative_rows)
    result = {'policy':summary, 'rows':pattern_rows, 'controls':control_rows, 'negativeControls':negative_rows,
              'controlsPass':controls_pass, 'negativeControlsPass':negatives_pass,
              'renderer':renderer, 'runtimeBefore':before,
              'historicalCrossDrawIsNotAnExactStoreReference':True,
              'shaders':{'vertex':vertex.decode(), 'sample':fragment.decode(),
                         'knownFloatFetch':fetch_source.decode(), 'constant':constant_source.decode()}}
    evidence.save(formatResult=result)
    assert summary['result'] == 'PASS' and controls_pass and negatives_pass, 'Aggregate actual-format policy/control failure'
finally:
    failure = sys.exc_info()[1]
    evidence.save(status='FAIL' if failure is not None else 'PASS',
                  failureType=type(failure).__name__ if failure is not None else None,
                  failure=str(failure) if failure is not None else None)
    scene.close()
    after = hashes()
    evidence.save(runtimeAfter=after, runtimeUnchanged=after == before)
assert after == before
result['runtimeUnchanged'] = True
destination = output/'sampler-format-probe.json'
temporary = destination.with_suffix('.tmp')
temporary.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n', encoding='utf-8')
temporary.replace(destination)
print(json.dumps({'result':summary, 'controlsPass':controls_pass, 'negativeControlsPass':negatives_pass,
                  'runtimeUnchanged':True}))
