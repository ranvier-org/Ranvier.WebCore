import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utf8_inputs import Utf8, bind as bind_utf8


def verify(directory,evidence_json=None):
    directory=Path(directory).resolve()
    before={str(p.relative_to(directory)):hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
    print('RUNTIME_BEFORE='+json.dumps(before,sort_keys=True),flush=True)
    search=os.add_dll_directory(str(directory)) if sys.platform=='win32' else None
    filename={'win32':'RanvierWebCoreHost.dll','darwin':'libRanvierWebCoreHost.dylib'}.get(sys.platform,'libRanvierWebCoreHost.so')
    library=ctypes.CDLL(str(directory/filename))
    has=library.rv_abi_has
    has.restype=ctypes.c_int32
    has.argtypes=[ctypes.c_char_p]
    retained=[]
    assertions=0
    host=None
    stages=[]
    passed=False
    def expect(condition,message):
        nonlocal assertions
        assertions+=1
        if not condition: raise AssertionError(message)
    def bind(name,result,arguments):
        return bind_utf8(library, name, result, arguments)
    pointer,integer,single=ctypes.c_void_p,ctypes.c_int32,ctypes.c_float
    try:
        expect(has(b'svg-view-selection') == 1, 'S06 requires an actual current SVG document view-selection provider')
        select=bind('rv_host_select_svg_view',integer,[pointer,ctypes.c_char_p,ctypes.POINTER(integer)])
        host=bind('rv_host_create',pointer,[integer,integer])(200,120)
        expect(bool(host),'Host creation')
        sentinel=integer(42)
        expect(select(host,b'zoom',ctypes.byref(sentinel)) == -9 and sentinel.value == 42,'HTML document rejected before mutation')
        markup=(Path(__file__).resolve().parents[1]/'fixtures/svg-view-selection.svg').read_bytes()
        load=bind('rv_host_load_svg',integer,[pointer,Utf8])
        expect(load(host,markup) == 0,'Load SVG document')
        document=bind('rv_host_document',pointer,[pointer])(host)
        retained.append(('rv_node_release',document))
        root=bind('rv_node_relative',pointer,[pointer,integer])(document,1)
        retained.append(('rv_node_release',root))
        expect(bool(root),'Main SVG root')
        red=bind('rv_document_get_element_by_id',pointer,[pointer,Utf8])(host,b'red')
        retained.append(('rv_node_release',red))
        def use_current():
            value=integer(42)
            expect(bind('rv_dom_svgsvg_element_get_use_current_view',integer,[pointer,ctypes.POINTER(integer)])(root,ctypes.byref(value)) == 0,'useCurrentView query')
            return value.value
        def handle(name,target,release):
            value=pointer()
            expect(bind(name,integer,[pointer,ctypes.POINTER(pointer)])(target,ctypes.byref(value)) == 0 and bool(value.value),'Handle '+name)
            retained.append((release,value.value))
            return value.value
        current=handle('rv_dom_svgsvg_element_get_current_view',root,'rv_dom_svg_view_spec_release')
        animated=handle('rv_dom_svg_view_spec_get_view_box',current,'rv_dom_svg_animated_rect_release')
        rectangle=handle('rv_dom_svg_animated_rect_get_base_val',animated,'rv_dom_svg_rect_release')
        def view_box():
            result=[]
            for field in ['x','y','width','height']:
                value=single(42)
                expect(bind('rv_dom_svg_rect_get_'+field,integer,[pointer,ctypes.POINTER(single)])(rectangle,ctypes.byref(value)) == 0,'Live current view '+field)
                result.append(value.value)
            return result
        def choose(fragment,expected):
            value=integer(42)
            expect(select(host,fragment,ctypes.byref(value)) == 0 and value.value == expected,'Engine fragment selection '+repr(fragment))
        def paint():
            rgba=(ctypes.c_uint8*(200*120*4))()
            expect(bind('rv_host_paint_rgba',integer,[pointer,pointer,integer])(host,rgba,len(rgba)) == 0,'Paint current view')
            return bytes(rgba)
        def applied_state(name,pixels):
            state={'name':name,'paintSha256':hashlib.sha256(pixels).hexdigest(),'viewSpec':view_box(),'useCurrentView':use_current()}
            for method in ['ctm','screen_ctm']:
                matrix=handle('rv_dom_svg_graphics_element_get_'+method,red,'rv_dom_svg_matrix_release')
                values=[]
                for field in ['a','b','c','d','e','f']:
                    value=ctypes.c_double()
                    expect(bind('rv_dom_svg_matrix_get_'+field,integer,[pointer,ctypes.POINTER(ctypes.c_double)])(matrix,ctypes.byref(value)) == 0,'Applied '+method+'.'+field)
                    values.append(value.value)
                state[method]=values
            bounds=handle('rv_dom_element_get_bounding_client_rect',red,'rv_dom_dom_rect_read_only_release')
            values=[]
            for field in ['x','y','width','height']:
                value=ctypes.c_double()
                expect(bind('rv_dom_dom_rect_read_only_get_'+field,integer,[pointer,ctypes.POINTER(ctypes.c_double)])(bounds,ctypes.byref(value)) == 0,'Applied bounds '+field)
                values.append(value.value)
            state['redBounds']=values
            stages.append(state)
            return state
        baseline=paint()
        choose(b'zoom',1)
        expect(use_current() == 1 and view_box() == [0,0,50,100],'Named view changes retained live currentView geometry')
        selected_paint=paint()
        expect(selected_paint != baseline,'Named view changes actual rendered pixels')
        selected_state=applied_state('named',selected_paint)
        active_view=bind('rv_document_get_element_by_id',pointer,[pointer,Utf8])(host,b'zoom')
        retained.append(('rv_node_release',active_view))
        expect(bind('rv_element_set_attribute',integer,[pointer,ctypes.c_char_p,Utf8])(active_view,b'viewBox',b'20 20 20 20') == 0,'Edit live active view')
        expect(use_current() == 1 and view_box() == [20,20,20,20],'Pinned WebCore actively selected view edits update retained currentView')
        expect(bind('rv_host_update',integer,[pointer])(host) >= 0,'Normal update after active view edit')
        edited_paint=paint()
        edited_state=applied_state('active-edit-after-update-paint',edited_paint)
        choose(b'zoom',1)
        reselected_paint=paint()
        applied_state('explicit-reselect',reselected_paint)
        expect(reselected_paint != selected_paint,'Explicit reselect applies changed named view to actual rendering')
        choose(b'other',1)
        expect(view_box() == [50,0,50,100],'Repeated named selection replaces geometry')
        choose(b'svgView(viewBox(10,20,30,40))',1)
        expect(use_current() == 1 and view_box() == [10,20,30,40],'Explicit svgView fragment')
        choose(b'zoom',1)
        choose(b'',0)
        expect(use_current() == 0,'Empty fragment resets active view')
        cleared_paint=paint()
        expect(cleared_paint == baseline,'Reset restores actual default pixels')
        view=bind('rv_document_get_element_by_id',pointer,[pointer,Utf8])(host,b'zoom')
        retained.append(('rv_node_release',view))
        expect(bind('rv_element_set_attribute',integer,[pointer,ctypes.c_char_p,Utf8])(view,b'viewBox',b'30 30 25 25') == 0,'Edit formerly active view after reset with a distinct value')
        expect(use_current() == 0,'Cleared former view edit must not reactivate currentView')
        expect(paint() == baseline,'Cleared former view edit must not change default paint')
        for fragment in [b'no-such-view',b'svgView(viewBox(bad))']:
            choose(b'zoom',1)
            choose(fragment,0)
            expect(use_current() == 0,'Missing/malformed fragments reset to unselected')
        before_error=paint()
        for target,fragment,output,expected in [(None,b'zoom',ctypes.byref(sentinel),-1),(host,None,ctypes.byref(sentinel),-1),(host,b'zoom',None,-1),(host,b'\xff',ctypes.byref(sentinel),-9)]:
            expect(select(target,fragment,output) == expected,'Invalid input status')
            expect(sentinel.value == 42,'Invalid input preserves selected output')
        expect(paint() == before_error,'Invalid input preserves rendered state')
        wrong=[]
        def background():
            value=integer(42)
            wrong.append((select(host,b'zoom',ctypes.byref(value)),value.value))
        thread=threading.Thread(target=background);thread.start();thread.join()
        expect(wrong == [(-2,42)],'Wrong thread rejects before state/output mutation')
        choose(b'zoom',1)
        expect(bind('rv_node_remove',integer,[pointer])(active_view) == 0,'Remove active view before clearing')
        choose(b'',0)
        expect(use_current() == 0 and paint() == baseline,'Clearing after active-view removal restores default rendering')
        expect(load(host,markup) == 0,'Replacement SVG document')
        choose(b'other',1)
        expect(bind('rv_host_load_html',integer,[pointer,Utf8])(host,b'<body>replacement') == 0,'Replacement HTML document')
        expect(select(host,b'zoom',ctypes.byref(sentinel)) == -9 and sentinel.value == 42,'Queries use current document after replacement')
        for release,value in reversed(retained):
            if value: bind(release,None,[pointer])(value)
        retained.clear()
        expired=host
        bind('rv_host_destroy',None,[pointer])(host)
        host=None
        expect(select(expired,b'zoom',ctypes.byref(sentinel)) == -9 and sentinel.value == 42,'Expired host rejects before dereference and preserves output')
        print('SVG_VIEW_SELECTION_ASSERTIONS='+str(assertions),flush=True)
        passed=True
    finally:
        for release,value in reversed(retained):
            if value: bind(release,None,[pointer])(value)
        if host: bind('rv_host_destroy',None,[pointer])(host)
        after={str(p.relative_to(directory)):hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
        assert before==after,'Executed runtime changed'
        if evidence_json:
            Path(evidence_json).write_text(json.dumps({'passed':passed,'assertions':assertions,'fixtureSha256':hashlib.sha256(markup).hexdigest(),'stages':stages,'runtime':before},indent=2))
        if search: search.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--native-directory',required=True)
    parser.add_argument('--evidence-json')
    arguments=parser.parse_args()
    verify(arguments.native_directory,arguments.evidence_json)
