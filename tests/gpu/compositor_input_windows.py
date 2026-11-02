import argparse,ctypes as C,hashlib,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'abi'))
from form_collections import Native,Case,P,I
from web_animations import Arena,animate,seek
from utf8_inputs import Utf8
parser=argparse.ArgumentParser();parser.add_argument('--native-directory',required=True);parser.add_argument('--report',required=True);parser.add_argument('--helper-library',required=True);args=parser.parse_args()
n=Native(args.native_directory)
helper=C.CDLL(args.helper_library)
for name,ret,params in [('gpu_readback_create',I,[P]),('gpu_readback_destroy',None,[P]),('gpu_readback_rgba',I,[P,P,P,C.c_uint64,C.c_uint32,C.c_uint32]),('native_input_create',I,[P,C.c_uint32,C.c_uint32,I,P]),('native_input_publish',I,[P,C.c_float,C.c_float,C.c_float,C.c_float]),('native_input_release',None,[P])]:
    f=getattr(helper,name);f.restype=ret;f.argtypes=params
helper.native_input_quadrants.argtypes=[P];helper.native_input_quadrants.restype=I
helper.native_input_removable.argtypes=[P,P,P];helper.native_input_removable.restype=I
helper.native_input_remove.argtypes=[P,P,P];helper.native_input_remove.restype=I
helper.native_input_removal_release.argtypes=[P];helper.native_input_removal_release.restype=None
device=P();assert helper.gpu_readback_create(C.byref(device))==0 and device.value
C.windll.kernel32.GetCurrentProcess.restype=P
C.windll.kernel32.GetProcessHandleCount.argtypes=[P,P]
def handles():
    count=C.c_uint32();assert C.windll.kernel32.GetProcessHandleCount(C.windll.kernel32.GetCurrentProcess(),C.byref(count));return count.value
PAGE='<style>html,body{margin:0;background:#123456}#clip{position:absolute;left:4px;top:4px;width:60px;height:40px;overflow:hidden}#slot{position:absolute;left:4px;top:4px;width:20px;height:20px;will-change:transform,opacity}#top{position:absolute;left:54px;top:8px;width:4px;height:20px;background:blue;z-index:2}</style><div id="clip"><div id="slot"></div><div style="width:160px;height:1px"></div></div><div id="top"></div>'
rows=[]
def publish(texture,color): assert helper.native_input_publish(texture,*color)==0
def acquire(page):
    n.ok('rv_host_update',[P],page.host);frame=P();status=n.call('rv_host_acquire_d3d11_frame',[P,P,P],page.host,device,C.byref(frame));return status,frame
def pixels(page,scale,label):
    status,frame=acquire(page);assert status==0 and frame.value,(label,status)
    try:
        texture,width,height,format_=P(),I(),I(),I()
        n.ok('rv_gpu_frame_info',[P,P,P,P,P],frame,C.byref(texture),C.byref(width),C.byref(height),C.byref(format_))
        assert [width.value,height.value,format_.value]==[int(101*scale),int(67*scale),1]
        data=(C.c_ubyte*(width.value*height.value*4))();assert helper.gpu_readback_rgba(device,texture,data,len(data),width.value,height.value)==0
        raw=bytes(data)
        at=lambda x,y:list(raw[(int(y*scale)*width.value+int(x*scale))*4:(int(y*scale)*width.value+int(x*scale))*4+4])
        row={'scale':scale,'label':label,'sha256':hashlib.sha256(raw).hexdigest(),'initial':at(16,16),'middle':at(36,16),'end':at(60,16),'clipped':at(66,16),'stack':at(55,16),'quadrants':[at(12,12),at(24,12),at(12,24),at(24,24)]};rows.append(row);return row
    finally:n.ok('rv_gpu_frame_release',[P],frame)
try:
    for scale in [1,1.5,2]:
        page=Case(n,PAGE);texture=P();invalid=P();removable=P();removal=P();animation=None;callerOwnsTexture=True;retained=None
        try:
            n.ok('rv_host_resize',[P,I,I],page.host,101,67);n.ok('rv_host_set_accelerated_compositing',[P,I],page.host,1);n.ok('rv_host_set_device_scale',[P,C.c_float],page.host,scale)
            target=page.node('slot')
            assert helper.native_input_create(device,32,24,1,C.byref(texture))==0
            n.ok('rv_host_bind_d3d11_texture',[P,P,P],page.host,target,texture)
            start=time.monotonic();status,frame=acquire(page)
            control={'scale':scale,'label':'unpublished input','status':status,'frame':bool(frame.value),'seconds':time.monotonic()-start};rows.append(control);print(json.dumps(control),flush=True)
            if frame.value:n.ok('rv_gpu_frame_release',[P],frame)
            assert status==-5 and not frame.value and control['seconds']<1,'unpublished input bounded paint failure'
            publish(texture,(1,0,0,1));row=pixels(page,scale,'native GPU red')
            assert row['initial']==[255,0,0,255],row
            assert helper.native_input_create(device,32,24,0,C.byref(invalid))==0
            assert n.call('rv_host_bind_d3d11_texture',[P,P,P],page.host,target,invalid)==-9,'missing sharing flags rejected'
            publish(texture,(0,1,0,1));row=pixels(page,scale,'native GPU green after rejected replacement')
            assert row['initial']==[0,255,0,255],row
            assert helper.native_input_quadrants(texture)==0
            row=pixels(page,scale,'GPU four quadrants orientation')
            assert row['quadrants']==[[255,0,0,255],[0,255,0,255],[0,0,255,255],[255,255,0,255]],row
            publish(texture,(0.5,0,0,0.5));row=pixels(page,scale,'premultiplied input alpha')
            assert all(abs(a-b)<=1 for a,b in zip(row['initial'],[137,26,43,255])),row
            arena=Arena();status,animation=animate(n,page,'animate',target,[{'props':{'transform':'translateX(0px)','opacity':'1'}},{'props':{'transform':'translateX(40px)','opacity':'0.5'}}],{'duration':1000,'fill':'both'},arena);assert status==0
            n.ok('rv_dom_web_animation_pause',[P],animation)
            for tick,point,expected in [(0,'initial',[255,0,0,255]),(500,'middle',[196,13,22,255]),(1000,'end',[137,26,43,255])]:
                seek(n,animation,tick);publish(texture,(1,0,0,1));row=pixels(page,scale,'native input animated '+str(tick))
                assert all(abs(a-b)<=1 for a,b in zip(row[point],expected)),row
                assert row['clipped']==[18,52,86,255] and row['stack']==[0,0,255,255],row
            n.ok('rv_host_bind_d3d11_texture',[P,P,P],page.host,target,None)
            row=pixels(page,scale,'unbound')
            assert row['end']==[18,52,86,255],row
            n.ok('rv_dom_web_animation_cancel',[P],animation);n.bind('rv_event_target_release',None,[P])(animation);animation=None
            n.ok('rv_host_bind_d3d11_texture',[P,P,P],page.host,target,texture)
            n.ok('rv_host_set_accelerated_compositing',[P,I],page.host,0)
            n.ok('rv_host_update',[P],page.host)
            n.ok('rv_host_set_accelerated_compositing',[P,I],page.host,1)
            publish(texture,(0,1,0,1));row=pixels(page,scale,'backing rebuilt GPU off then on')
            assert row['initial']==[0,255,0,255],row
            clip=page.node('clip')
            for node,name,value in [(target,b'left',b'84px'),(clip,b'overflow',b'auto')]:
                n.ok('rv_element_set_style',[P,C.c_char_p,P,I,I],node,name,value,len(value),0)
            n.ok('rv_host_update',[P],page.host)
            n.ok('rv_dom_element_set_scroll_left',[P,I],clip,80)
            assert n.integer('rv_dom_element_get_scroll_left',clip)==80,'actual scroll offset'
            publish(texture,(1,0,0,1));row=pixels(page,scale,'scrolled native input')
            assert row['initial']==[255,0,0,255],row
            n.ok('rv_node_remove_child',[P,P],clip,target)
            row=pixels(page,scale,'removed input element')
            assert row['initial']==[18,52,86,255],row
            n.ok('rv_host_load_html',[P,Utf8],page.host,PAGE.encode())
            row=pixels(page,scale,'replaced document has no old input')
            assert row['initial']==[18,52,86,255],row
            assert helper.native_input_removable(device,C.byref(removable),C.byref(removal))==0
            n.ok('rv_host_bind_d3d11_texture',[P,P,P],page.host,page.node('slot'),removable)
            publish(removable,(0,1,0,1));row=pixels(page,scale,'healthy removable native input')
            assert row['initial']==[0,255,0,255],row
            reasons=(I*4)();assert helper.native_input_remove(removal,removable,reasons)==0
            control={'scale':scale,'label':'input device removal','reasons':list(reasons),'attempts':[]};rows.append(control)
            assert list(reasons)[:2]==[0,0] and all(r<0 for r in list(reasons)[2:]),control
            control['handlesBefore']=handles()
            for attempt in range(25):
                status,frame=acquire(page);control['attempts'].append({'status':status,'frame':bool(frame.value)})
                if frame.value:n.ok('rv_gpu_frame_release',[P],frame)
                assert status==-5 and not frame.value,control
            control['handlesAfter']=handles();assert control['handlesAfter']<=control['handlesBefore']+4,control
            n.ok('rv_host_bind_d3d11_texture',[P,P,P],page.host,page.node('slot'),None)
            helper.native_input_release(removable);removable=P();helper.native_input_removal_release(removal);removal=P()
            helper.native_input_release(texture);texture=P()
            assert helper.native_input_create(device,48,40,1,C.byref(texture))==0
            n.ok('rv_host_bind_d3d11_texture',[P,P,P],page.host,page.node('slot'),texture)
            helper.native_input_release(texture);callerOwnsTexture=False
            publish(texture,(0,1,0,1));row=pixels(page,scale,'resized texture with only host COM ownership')
            assert row['initial']==[0,255,0,255],row
            publish(texture,(1,0,0,1));status,retained=acquire(page);assert status==0 and retained.value
        finally:
            if animation:n.ok('rv_dom_web_animation_cancel',[P],animation);n.bind('rv_event_target_release',None,[P])(animation)
            page.close()
            if callerOwnsTexture:helper.native_input_release(texture)
            helper.native_input_release(invalid)
            helper.native_input_release(removable);helper.native_input_removal_release(removal)
            if retained:
                out,w,h,fmt=P(),I(),I(),I()
                n.ok('rv_gpu_frame_info',[P,P,P,P,P],retained,C.byref(out),C.byref(w),C.byref(h),C.byref(fmt))
                assert [w.value,h.value,fmt.value]==[int(101*scale),int(67*scale),1]
                n.ok('rv_gpu_frame_release',[P],retained)
finally:
    helper.gpu_readback_destroy(device)
    Path(args.report).write_text(json.dumps({'rows':rows,'assertions':n.assertions,'production':'native D3D GPU render target -> NTshared ANGLE EGLImage -> DOM platform layer -> GPU shared output','hostCpuPaintCalls':0},indent=2)+'\n')
print('PASS native D3D texture DOM input',sum('sha256' in r for r in rows),'frames',n.assertions,'assertions')
