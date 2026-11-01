"""A11 snapshots and animation pixels through strict native EGLImage frames."""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'abi'))
from form_collections import Native, Case, P, I, U
from view_transitions import UPDATE, Options, SETTLED
from web_animations import Animations, Time


class Consumer:
    def __init__(self, native):
        self.n = native
        self.egl = C.CDLL('libEGL.so.1')
        self.gl = C.CDLL('libGLESv2.so.2')
        self.bind = lambda lib, name, result, params: self._bind(lib, name, result, params)
        self.current = self.bind(self.egl, 'eglMakeCurrent', U, [P, P, P, P])
        self.display = self.bind(self.egl, 'eglGetDisplay', P, [P])(None)
        assert self.bind(self.egl, 'eglInitialize', U, [P, P, P])(self.display, None, None)
        assert self.bind(self.egl, 'eglBindAPI', U, [U])(0x30A0)
        config, count = P(), I()
        attributes = (I * 11)(0x3033, 1, 0x3040, 4, 0x3024, 8, 0x3023, 8, 0x3022, 8, 0x3038)
        assert self.bind(self.egl, 'eglChooseConfig', U, [P, P, P, I, P])(
            self.display, attributes, C.byref(config), 1, C.byref(count)) and count.value
        self.context = self.bind(self.egl, 'eglCreateContext', P, [P, P, P, P])(
            self.display, config, None, (I * 3)(0x3098, 2, 0x3038))
        self.activate()
        native.ok('rv_configure_egl_display', [P], self.display)
        self.target = C.CFUNCTYPE(None, U, P)(self.bind(self.egl, 'eglGetProcAddress', P, [C.c_char_p])(
            b'glEGLImageTargetTexture2DOES'))
        self.frames = 0

    @staticmethod
    def _bind(library, name, result, parameters):
        function = getattr(library, name)
        function.restype, function.argtypes = result, parameters
        return function

    def activate(self):
        assert self.context and self.current(self.display, None, None, self.context)

    def pixels(self, host, label):
        self.n.ok('rv_host_update', [P], host)
        self.activate()
        assert self.bind(self.gl, 'glGetError', U, [])() == 0, 'consumer GL error before native acquire'
        frame = P()
        self.n.ok('rv_host_acquire_egl_frame', [P, C.POINTER(P)], host, C.byref(frame))
        assert frame.value, 'strict EGL acquire returned no frame'
        texture, framebuffer = U(), U()
        try:
            image, width, height, format_ = P(), I(), I(), I()
            self.n.ok('rv_gpu_frame_info', [P, P, P, P, P], frame, C.byref(image), C.byref(width), C.byref(height), C.byref(format_))
            assert image.value and (width.value, height.value, format_.value) == (96, 64, 1)
            self.bind(self.gl, 'glGenTextures', None, [I, P])(1, C.byref(texture))
            self.bind(self.gl, 'glBindTexture', None, [U, U])(0x0DE1, texture)
            self.target(0x0DE1, image)
            assert self.bind(self.gl, 'glGetError', U, [])() == 0
            self.bind(self.gl, 'glGenFramebuffers', None, [I, P])(1, C.byref(framebuffer))
            self.bind(self.gl, 'glBindFramebuffer', None, [U, U])(0x8D40, framebuffer)
            self.bind(self.gl, 'glFramebufferTexture2D', None, [U, U, U, U, I])(0x8D40, 0x8CE0, 0x0DE1, texture, 0)
            assert self.bind(self.gl, 'glCheckFramebufferStatus', U, [U])(0x8D40) == 0x8CD5
            pixels = (C.c_ubyte * (96 * 64 * 4))()
            self.bind(self.gl, 'glReadPixels', None, [I, I, I, I, U, U, P])(0, 0, 96, 64, 0x1908, 0x1401, pixels)
            self.frames += 1
            output = bytes(pixels)
            at = lambda x, y: list(output[(y * 96 + x) * 4:(y * 96 + x) * 4 + 4])
            sample = {'label': label, 'box': at(20, 20), 'background': at(80, 50), 'sha256': hashlib.sha256(output).hexdigest()}
            print(json.dumps(sample), flush=True)
            return sample
        finally:
            self.bind(self.gl, 'glFinish', None, [])()
            self.bind(self.gl, 'glDeleteFramebuffers', None, [I, P])(1, C.byref(framebuffer))
            self.bind(self.gl, 'glDeleteTextures', None, [I, P])(1, C.byref(texture))
            self.n.ok('rv_gpu_frame_release', [P], frame)


PAGE = '''<style>
html,body{margin:0;background:rgb(17,34,51)}
:root{view-transition-name:root}
#box{position:absolute;left:8px;top:8px;width:40px;height:32px;background:rgb(255,0,0);transform:translateZ(0)}
::view-transition-group(root){animation:none}
::view-transition-old(root){animation:none;opacity:1}
::view-transition-new(root){animation:reveal 100s linear both;mix-blend-mode:normal}
@keyframes reveal{from{opacity:0}to{opacity:1}}
</style><div id="box"></div>'''


def animations(n, document):
    result = Animations()
    n.ok('rv_dom_document_get_animations', [P, P], document, C.byref(result))
    handles = [n.bind('rv_event_target_retain', P, [P])(result.items[i]) for i in range(result.count)]
    n.bind('rv_dom_sequence_web_animation_release', None, [P])(C.byref(result))
    return handles


def run(directory):
    n = Native(directory)
    assert n.bind('rv_abi_version', I, [])() == 60
    assert n.call('rv_abi_has', [C.c_char_p], b'view-transitions')
    consumer = Consumer(n)
    page = Case(n, PAGE)
    transition, observer, callback = P(), P(), None
    controlled = []
    events = []
    try:
        n.ok('rv_host_resize', [P, I, I], page.host, 96, 64)
        n.ok('rv_host_set_accelerated_compositing', [P, I], page.host, 1)
        old = consumer.pixels(page.host, 'old red DOM')
        assert old['box'] == [255, 0, 0, 255], old
        box = page.node('box')

        def change(_):
            n.ok('rv_element_set_style', [P, C.c_char_p, C.c_char_p, I, I], box, b'background', b'rgb(0,0,255)', 12, 0)
            return 0

        update = UPDATE(change)
        callback = n.bind('rv_view_transition_update_callback_create', P, [P, UPDATE, P, P])(page.host, update, None, None)
        options = Options(C.sizeof(Options), callback, None)
        n.ok('rv_dom_document_start_view_transition', [P, P, P], page.document, C.byref(options), C.byref(transition))
        sink = SETTLED(lambda _, kind, error: events.append((kind, error.decode() if error else None)))
        n.ok('rv_view_transition_observe', [P, P, SETTLED, P, P], page.host, transition, sink, None, C.byref(observer))
        deadline = time.monotonic() + 5
        while (1, None) not in events and time.monotonic() < deadline:
            n.ok('rv_host_update', [P], page.host)
            n.call('rv_run_loop_cycle', [I], 1)
        assert (1, None) in events, events
        controlled = animations(n, page.document)
        names = []
        for animation in controlled:
            effect = n.handle('rv_dom_web_animation_get_effect', [P], animation)
            names.append(n.text('rv_dom_keyframe_effect_get_pseudo_element', [P], effect))
            n.bind('rv_dom_animation_effect_release', None, [P])(effect)
            n.ok('rv_dom_web_animation_pause', [P], animation)
            n.ok('rv_dom_web_animation_set_current_time', [P, P], animation, C.byref(Time(1, 1, 50000.0, None)))
        print(json.dumps({'events': events, 'controlled_pseudos': names}), flush=True)
        assert controlled and '::view-transition-new(root)' in names, names
        changed = n.text('rv_element_computed_style', [P, C.c_char_p], box, b'background-color')
        assert changed == 'rgb(0, 0, 255)', changed
        for milliseconds, color in [(0, [255, 0, 0, 255]), (50000, [128, 0, 128, 255]), (100000, [0, 0, 255, 255])]:
            for animation in controlled:
                n.ok('rv_dom_web_animation_set_current_time', [P, P], animation, C.byref(Time(1, 1, milliseconds, None)))
            sample = consumer.pixels(page.host, f'in flight at {milliseconds}ms; live DOM is blue')
            assert all(abs(actual - expected) <= 2 for actual, expected in zip(sample['box'], color)), sample
        for animation in controlled:
            n.ok('rv_dom_web_animation_finish', [P], animation)
        deadline = time.monotonic() + 5
        while (2, None) not in events and time.monotonic() < deadline:
            n.ok('rv_host_update', [P], page.host)
            n.call('rv_run_loop_cycle', [I], 1)
        assert (2, None) in events, events
        final = consumer.pixels(page.host, 'finished blue DOM')
        assert final['box'] == [0, 0, 255, 255], final
        assert not n.handle('rv_dom_document_get_active_view_transition', [P], page.document)
        leftover = animations(n, page.document)
        assert not leftover, 'transition pseudo animations survived completion'

        n.bind('rv_view_transition_observer_release', None, [P])(observer)
        observer = P()
        n.bind('rv_dom_view_transition_release', None, [P])(transition)
        transition = P()
        n.bind('rv_dom_view_transition_update_callback_release', None, [P])(callback)
        callback = None
        for animation in controlled:
            n.bind('rv_event_target_release', None, [P])(animation)
        controlled = []

        # A second transition is interrupted after a real composited midpoint.
        events.clear()
        reverse = UPDATE(lambda _: n.call('rv_element_set_style', [P, C.c_char_p, C.c_char_p, I, I],
                                          box, b'background', b'rgb(255,0,0)', 12, 0))
        callback = n.bind('rv_view_transition_update_callback_create', P, [P, UPDATE, P, P])(page.host, reverse, None, None)
        options = Options(C.sizeof(Options), callback, None)
        n.ok('rv_dom_document_start_view_transition', [P, P, P], page.document, C.byref(options), C.byref(transition))
        n.ok('rv_view_transition_observe', [P, P, SETTLED, P, P], page.host, transition, sink, None, C.byref(observer))
        deadline = time.monotonic() + 5
        while (1, None) not in events and time.monotonic() < deadline:
            n.ok('rv_host_update', [P], page.host)
            n.call('rv_run_loop_cycle', [I], 1)
        assert (1, None) in events, events
        controlled = animations(n, page.document)
        assert controlled
        for animation in controlled:
            n.ok('rv_dom_web_animation_pause', [P], animation)
            n.ok('rv_dom_web_animation_set_current_time', [P, P], animation, C.byref(Time(1, 1, 50000.0, None)))
        interrupted = consumer.pixels(page.host, 'reverse transition before skip at 50%')
        assert all(abs(actual - expected) <= 2 for actual, expected in zip(interrupted['box'], [128, 0, 128, 255])), interrupted
        n.ok('rv_dom_view_transition_skip_transition', [P], transition)
        deadline = time.monotonic() + 5
        while (2, None) not in events and time.monotonic() < deadline:
            n.ok('rv_host_update', [P], page.host)
            n.call('rv_run_loop_cycle', [I], 1)
        assert (2, None) in events, events
        skipped = consumer.pixels(page.host, 'skip cleans pseudo tree; live DOM red')
        assert skipped['box'] == [255, 0, 0, 255], skipped
        assert not n.handle('rv_dom_document_get_active_view_transition', [P], page.document)
        assert not animations(n, page.document), 'skip left pseudo animations'

        n.bind('rv_view_transition_observer_release', None, [P])(observer)
        observer = P()
        n.bind('rv_dom_view_transition_release', None, [P])(transition)
        transition = P()
        n.bind('rv_dom_view_transition_update_callback_release', None, [P])(callback)
        callback = None
        for animation in controlled:
            n.bind('rv_event_target_release', None, [P])(animation)
        controlled = []
        events.clear()
        callback = n.bind('rv_view_transition_update_callback_create', P, [P, UPDATE, P, P])(page.host, update, None, None)
        options = Options(C.sizeof(Options), callback, None)
        n.ok('rv_dom_document_start_view_transition', [P, P, P], page.document, C.byref(options), C.byref(transition))
        n.ok('rv_view_transition_observe', [P, P, SETTLED, P, P], page.host, transition, sink, None, C.byref(observer))
        deadline = time.monotonic() + 5
        while (1, None) not in events and time.monotonic() < deadline:
            n.ok('rv_host_update', [P], page.host)
            n.call('rv_run_loop_cycle', [I], 1)
        assert (1, None) in events, events
        controlled = animations(n, page.document)
        assert controlled
        for animation in controlled:
            n.ok('rv_dom_web_animation_pause', [P], animation)
            n.ok('rv_dom_web_animation_set_current_time', [P, P], animation, C.byref(Time(1, 1, 50000.0, None)))
        replacing = consumer.pixels(page.host, 'transition before document replacement at 50%')
        assert all(abs(actual - expected) <= 2 for actual, expected in zip(replacing['box'], [128, 0, 128, 255])), replacing
        replacement = PAGE.replace('rgb(255,0,0)', 'rgb(0,255,0)').encode()
        n.ok('rv_host_load_html', [P, C.c_char_p, I], page.host, replacement, len(replacement))
        n.ok('rv_host_set_accelerated_compositing', [P, I], page.host, 1)
        replaced = consumer.pixels(page.host, 'replacement document green; old transition interrupted')
        assert replaced['box'] == [0, 255, 0, 255], replaced
        new_document = n.bind('rv_host_document', P, [P])(page.host)
        try:
            assert not n.handle('rv_dom_document_get_active_view_transition', [P], new_document)
            assert not animations(n, new_document), 'replacement kept pseudo animations'
        finally:
            n.bind('rv_node_release', None, [P])(new_document)
        print(json.dumps({'result': 'PASS', 'transport': 'EGLImage', 'gpu_frames': consumer.frames,
                          'cpu_paint_api_calls': 0, 'events': events, 'pseudo_animations_after': len(leftover),
                          'controlled_times_ms': [0, 50000, 100000], 'skip_cleanup': True, 'replacement_cleanup': True}))
    finally:
        for animation in controlled:
            n.bind('rv_event_target_release', None, [P])(animation)
        if observer.value:
            n.bind('rv_view_transition_observer_release', None, [P])(observer)
        if transition.value:
            n.bind('rv_dom_view_transition_release', None, [P])(transition)
        if callback:
            n.bind('rv_dom_view_transition_update_callback_release', None, [P])(callback)
        page.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    run(parser.parse_args().native_directory)
