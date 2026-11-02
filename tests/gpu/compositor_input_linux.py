"""Native GLES producer -> EGLImage -> DOM layer -> shared GPU output, without host CPU painting."""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from linux_view_transition_pixels import Consumer, Native, Case, P, I, U
from web_animations import Arena, animate, seek
from utf8_inputs import Utf8

PAGE = '<style>html,body{margin:0;background:#123456}#clip{position:absolute;left:4px;top:4px;width:60px;height:40px;overflow:hidden}#slot{position:absolute;left:4px;top:4px;width:20px;height:20px;will-change:transform,opacity}#top{position:absolute;left:54px;top:8px;width:4px;height:20px;background:blue;z-index:2}</style><div id="clip"><div id="slot"></div><div style="width:160px;height:1px"></div></div><div id="top"></div>'


class InputConsumer(Consumer):
    def __init__(self, native):
        super().__init__(native)
        get_proc = self.bind(self.egl, 'eglGetProcAddress', P, [C.c_char_p])
        self.create_image = C.CFUNCTYPE(P, P, P, U, P, P)(get_proc(b'eglCreateImageKHR'))
        self.destroy_image = C.CFUNCTYPE(U, P, P)(get_proc(b'eglDestroyImageKHR'))

    def source(self, page, target, width=32, height=24, flip=False):
        self.activate()
        texture, framebuffer = U(), U()
        self.bind(self.gl, 'glGenTextures', None, [I,P])(1,C.byref(texture))
        self.bind(self.gl, 'glBindTexture', None, [U,U])(0x0DE1,texture)
        self.bind(self.gl, 'glTexImage2D', None, [U,I,I,I,I,I,U,U,P])(0x0DE1,0,0x1908,width,height,0,0x1908,0x1401,None)
        self.bind(self.gl, 'glGenFramebuffers', None, [I,P])(1,C.byref(framebuffer))
        self.bind(self.gl, 'glBindFramebuffer', None, [U,U])(0x8D40,framebuffer)
        self.bind(self.gl, 'glFramebufferTexture2D', None, [U,U,U,U,I])(0x8D40,0x8CE0,0x0DE1,texture,0)
        assert self.bind(self.gl, 'glCheckFramebufferStatus', U, [U])(0x8D40) == 0x8CD5
        self.publish(framebuffer,(1,0,0,1))
        self.bind_image(page,target,texture,flip)
        return texture,framebuffer

    def bind_image(self, page, target, texture, flip=False):
        self.activate()
        image = self.create_image(self.display,self.context,0x30B1,P(texture.value),(I*3)(0x30D2,1,0x3038))
        assert image, 'producer EGLImage creation'
        try:
            self.n.ok('rv_host_bind_egl_image',[P,P,P,I],page.host,target,image,int(flip))
        finally:
            assert self.destroy_image(self.display,image), 'caller releases EGLImage handle after binding'

    def quadrants(self, framebuffer):
        self.activate()
        self.bind(self.gl,'glBindFramebuffer',None,[U,U])(0x8D40,framebuffer)
        self.bind(self.gl,'glEnable',None,[U])(0x0C11)
        try:
            for x,y,color in [(0,0,(1,0,0,1)),(16,0,(0,1,0,1)),(0,12,(0,0,1,1)),(16,12,(1,1,0,1))]:
                self.bind(self.gl,'glScissor',None,[I,I,I,I])(x,y,16,12)
                self.bind(self.gl,'glClearColor',None,[C.c_float]*4)(*color)
                self.bind(self.gl,'glClear',None,[U])(0x4000)
        finally:
            self.bind(self.gl,'glDisable',None,[U])(0x0C11)
        self.bind(self.gl,'glFinish',None,[])()
        assert self.bind(self.gl,'glGetError',U,[])() == 0

    def publish(self, framebuffer, color):
        self.activate()
        self.bind(self.gl,'glBindFramebuffer',None,[U,U])(0x8D40,framebuffer)
        self.bind(self.gl,'glClearColor',None,[C.c_float]*4)(*color)
        self.bind(self.gl,'glClear',None,[U])(0x4000)
        self.bind(self.gl,'glFinish',None,[])()
        assert self.bind(self.gl,'glGetError',U,[])() == 0

    def delete_source(self, texture, framebuffer):
        self.activate()
        self.bind(self.gl,'glDeleteFramebuffers',None,[I,P])(1,C.byref(framebuffer))
        self.bind(self.gl,'glDeleteTextures',None,[I,P])(1,C.byref(texture))

    def capture(self, host, scale, label):
        self.n.ok('rv_host_update',[P],host)
        self.activate()
        frame = P()
        self.n.ok('rv_host_acquire_egl_frame',[P,P],host,C.byref(frame))
        assert frame.value
        texture,framebuffer = U(),U()
        try:
            image,width,height,format_ = P(),I(),I(),I()
            self.n.ok('rv_gpu_frame_info',[P,P,P,P,P],frame,C.byref(image),C.byref(width),C.byref(height),C.byref(format_))
            assert (width.value,height.value,format_.value) == (int(101*scale),int(67*scale),1)
            self.bind(self.gl,'glGenTextures',None,[I,P])(1,C.byref(texture))
            self.bind(self.gl,'glBindTexture',None,[U,U])(0x0DE1,texture)
            self.target(0x0DE1,image)
            self.bind(self.gl,'glGenFramebuffers',None,[I,P])(1,C.byref(framebuffer))
            self.bind(self.gl,'glBindFramebuffer',None,[U,U])(0x8D40,framebuffer)
            self.bind(self.gl,'glFramebufferTexture2D',None,[U,U,U,U,I])(0x8D40,0x8CE0,0x0DE1,texture,0)
            assert self.bind(self.gl,'glCheckFramebufferStatus',U,[U])(0x8D40) == 0x8CD5
            pixels = (C.c_ubyte*(width.value*height.value*4))()
            self.bind(self.gl,'glReadPixels',None,[I,I,I,I,U,U,P])(0,0,width.value,height.value,0x1908,0x1401,pixels)
            raw = bytes(pixels)
            at = lambda x,y:list(raw[(int(y*scale)*width.value+int(x*scale))*4:(int(y*scale)*width.value+int(x*scale))*4+4])
            return dict(label=label,scale=scale,sha256=hashlib.sha256(raw).hexdigest(),initial=at(16,16),middle=at(36,16),end=at(60,16),clipped=at(66,16),stack=at(55,16),quadrants=[at(12,12),at(24,12),at(12,24),at(24,24)])
        finally:
            self.delete_source(texture,framebuffer)
            self.bind(self.gl,'glFinish',None,[])()
            self.n.ok('rv_gpu_frame_release',[P],frame)

    def close(self):
        self.current(self.display,None,None,None)
        assert self.bind(self.egl,'eglDestroyContext',U,[P,P])(self.display,self.context)


def run(directory, report, scales=(1,1.5,2)):
    native = Native(directory)
    assert native.call('rv_abi_has',[C.c_char_p],b'texture-input-egl') == 1
    consumer = InputConsumer(native)
    rows,lifetimes = [],[]
    try:
        for scale in scales:
            page = Case(native,PAGE)
            texture,framebuffer,animation,held = U(),U(),None,P()
            try:
                native.ok('rv_host_resize',[P,I,I],page.host,101,67)
                native.ok('rv_host_set_device_scale',[P,C.c_float],page.host,scale)
                native.ok('rv_host_set_accelerated_compositing',[P,I],page.host,1)
                target = page.node('slot')
                texture,framebuffer = consumer.source(page,target)
                def capture(label):
                    row = consumer.capture(page.host,scale,label)
                    rows.append(row)
                    report.write_text(json.dumps(dict(status='RUNNING',rows=rows,assertions=native.assertions),indent=2)+'\n')
                    print(json.dumps(dict(scale=scale,label=label,sha256=row['sha256'])),flush=True)
                    assert row['clipped']==[18,52,86,255] and row['stack']==[0,0,255,255],row
                    return row
                assert capture('native GPU red after EGLImage handle release')['initial']==[255,0,0,255]
                consumer.publish(framebuffer,(0,1,0,1))
                native.ok('rv_host_native_texture_changed',[P,P],page.host,target)
                assert capture('native GPU update')['initial']==[0,255,0,255]
                consumer.quadrants(framebuffer)
                row=capture('top-row-first native input')
                assert row['quadrants']==[[255,0,0,255],[0,255,0,255],[0,0,255,255],[255,255,0,255]],row
                consumer.bind_image(page,target,texture,True)
                row=capture('bottom-row-first native input')
                assert row['quadrants']==[[0,0,255,255],[255,255,0,255],[255,0,0,255],[0,255,0,255]],row
                consumer.bind_image(page,target,texture,False)
                consumer.publish(framebuffer,(0.5,0,0,0.5))
                row=capture('premultiplied input alpha')
                assert all(abs(a-b)<=1 for a,b in zip(row['initial'],[137,26,43,255])),row
                arena = Arena()
                status,animation=animate(native,page,'animate',target,[{'props':{'transform':'translateX(0px)','opacity':'1'}},{'props':{'transform':'translateX(40px)','opacity':'0.5'}}],{'duration':1000,'fill':'both'},arena)
                assert status==0 and animation
                native.ok('rv_dom_web_animation_pause',[P],animation)
                for tick,point,expected in [(0,'initial',[255,0,0,255]),(500,'middle',[196,13,22,255]),(1000,'end',[137,26,43,255])]:
                    seek(native,animation,tick)
                    consumer.publish(framebuffer,(1,0,0,1))
                    row=capture('animated native input '+str(tick))
                    assert all(abs(a-b)<=1 for a,b in zip(row[point],expected)),row
                native.ok('rv_dom_web_animation_cancel',[P],animation)
                native.bind('rv_event_target_release',None,[P])(animation)
                animation=None
                native.ok('rv_host_set_accelerated_compositing',[P,I],page.host,0)
                native.ok('rv_host_update',[P],page.host)
                native.ok('rv_host_set_accelerated_compositing',[P,I],page.host,1)
                consumer.publish(framebuffer,(0,1,0,1))
                assert capture('backing rebuilt')['initial']==[0,255,0,255]
                clip=page.node('clip')
                native.ok('rv_element_set_style',[P,C.c_char_p,P,I,I],target,b'left',b'84px',4,0)
                native.ok('rv_element_set_style',[P,C.c_char_p,P,I,I],clip,b'overflow',b'auto',4,0)
                native.ok('rv_host_update',[P],page.host)
                native.ok('rv_dom_element_set_scroll_left',[P,I],clip,80)
                assert native.integer('rv_dom_element_get_scroll_left',clip)==80
                assert capture('scrolled input')['initial']==[0,255,0,255]
                consumer.delete_source(texture,framebuffer)
                texture,framebuffer=U(),U()
                assert capture('host sibling survives producer texture deletion')['initial']==[0,255,0,255]
                native.ok('rv_host_bind_egl_image',[P,P,P,I],page.host,target,None,0)
                assert capture('unbound')['initial']==[18,52,86,255]
                native.ok('rv_host_load_html',[P,Utf8],page.host,PAGE.encode())
                texture,framebuffer=consumer.source(page,page.node('slot'),48,40)
                assert capture('resized replacement input')['initial']==[255,0,0,255]
                native.ok('rv_host_load_html',[P,Utf8],page.host,PAGE.encode())
                assert capture('bound image revoked by document replacement')['initial']==[18,52,86,255]
                consumer.delete_source(texture,framebuffer)
                texture,framebuffer=consumer.source(page,page.node('slot'))
                assert capture('new document accepts a fresh native input')['initial']==[255,0,0,255]
                native.ok('rv_node_remove_child',[P,P],page.node('clip'),page.node('slot'))
                assert capture('removed element')['initial']==[18,52,86,255]
                native.ok('rv_host_load_html',[P,Utf8],page.host,PAGE.encode())
                consumer.delete_source(texture,framebuffer)
                texture,framebuffer=consumer.source(page,page.node('slot'))
                assert capture('bound input before host destruction')['initial']==[255,0,0,255]
                native.ok('rv_host_update',[P],page.host)
                consumer.activate()
                native.ok('rv_host_acquire_egl_frame',[P,P],page.host,C.byref(held))
                assert held.value
            finally:
                if animation:
                    native.ok('rv_dom_web_animation_cancel',[P],animation)
                    native.bind('rv_event_target_release',None,[P])(animation)
                page.close()
                consumer.delete_source(texture,framebuffer)
                if held.value:
                    consumer.activate()
                    try:
                        image,width,height,format_=P(),I(),I(),I()
                        native.ok('rv_gpu_frame_info',[P,P,P,P,P],held,C.byref(image),C.byref(width),C.byref(height),C.byref(format_))
                        assert image.value and (width.value,height.value,format_.value)==(int(101*scale),int(67*scale),1)
                        lifetimes.append(dict(scale=scale,heldOutputSurvivedHostAndBoundInput=True))
                    finally:
                        native.ok('rv_gpu_frame_release',[P],held)
    finally:
        consumer.close()
        report.write_text(json.dumps(dict(rows=rows,lifetimes=lifetimes,assertions=native.assertions,hostCpuPaintCalls=0,transport='native GLES texture/EGLImage -> DOM -> EGLImage output'),indent=2)+'\n')
    print('PASS Linux native texture DOM input',len(rows),'frames',native.assertions,'assertions')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-directory',required=True)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--scale',type=float,choices=[1,1.5,2],help='Run one scale in an isolated diagnostic process')
    args=parser.parse_args()
    run(args.native_directory,args.report,[args.scale] if args.scale is not None else (1,1.5,2))
