import argparse
import ctypes
import json
from pathlib import Path
import sys
import threading

sys.path.insert(0,str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe
from utf8_inputs import Utf8


def verify(native_directory):
    with SvgProbe(native_directory,400,300) as p:
        p.load((Path(__file__).resolve().parents[1]/'fixtures/svg-clip-mask-marker.svg').read_bytes())
        oracle=json.loads((Path(__file__).resolve().parents[1]/'fixtures/svg-clip-mask-marker-oracle.json').read_text())
        root,clip,mask,marker=(p.node(name) for name in ['root','clip','mask','marker'])
        node_map={'clip':clip,'mask':mask,'marker':marker}
        roots={'SVGAnimatedLength':'svg_animated_length','SVGAnimatedEnumeration':'svg_animated_enumeration','SVGAnimatedAngle':'svg_animated_angle','SVGAnimatedRect':'svg_animated_rect','SVGAnimatedPreserveAspectRatio':'svg_animated_preserve_aspect_ratio','SVGAnimatedTransformList':'svg_animated_transform_list','SVGStringList':'svg_string_list'}
        properties={}
        for function,target in [('rv_dom_svg_clip_path_element_get_clip_path_units',clip),('rv_dom_svg_mask_element_get_mask_units',mask),('rv_dom_svg_marker_element_get_marker_units',marker)]:
            untouched=p.pointer(123)
            getter=p.bind(function,p.integer,[p.pointer,ctypes.POINTER(p.pointer)])
            p.expect(getter(root,ctypes.byref(untouched))==-11 and untouched.value==123,'node subtype rejection preserves output')
            p.expect(getter(None,ctypes.byref(untouched))==-1 and untouched.value==123,'null node rejection preserves output')
            statuses=[]
            worker=threading.Thread(target=lambda:statuses.append(getter(target,ctypes.byref(untouched))))
            worker.start();worker.join()
            p.expect(statuses==[-2] and untouched.value==123,'off-thread node rejection preserves output')
        def transform(base,x,y):
            value=p.object('rv_dom_svgsvg_element_create_svg_transform',[p.pointer],[root],'svg_transform')
            p.call('rv_dom_svg_transform_set_translate',[p.pointer,p.single,p.single],value,x,y)
            return p.object('rv_dom_svg_transform_list_append_item',[p.pointer,p.pointer],[base,value],'svg_transform')
        for row in oracle['rows']:
            target=node_map[row['id']]
            if row['state']=='NotExposed':
                p.expect(row['member']=='orient' and p.text(row['function'],[p.pointer],target)=='0','source-backed native-only marker orient')
                continue
            kind=row['root'];value=p.object(row['function'],[p.pointer],[target],roots[kind])
            properties[(row['id'],row['member'])]=value
            p.expect(p.object(row['function'],[p.pointer],[target],roots[kind])==value,'live clip/mask/marker property identity')
            if kind=='SVGAnimatedEnumeration':
                p.expect(p.read(roots[kind],value,'base_val',p.short)==row['initial'],'independent enum initial '+row['member'])
                p.call('rv_dom_svg_animated_enumeration_set_base_val',[p.pointer,p.short],value,row['changed'])
                p.expect(p.read(roots[kind],value,'base_val',p.short)==row['changed'],'typed enum mutation '+row['member'])
                p.call('rv_dom_svg_animated_enumeration_set_base_val',[p.pointer,p.short],value,row['initial'])
                p.exception('rv_dom_svg_animated_enumeration_set_base_val',[p.pointer,p.short],[value,999],'TypeError')
            elif kind in ['SVGAnimatedLength','SVGAnimatedAngle']:
                child='svg_length' if kind=='SVGAnimatedLength' else 'svg_angle'
                base=p.property(roots[kind],value,'base_val',child)
                readonly=p.property(roots[kind],value,'anim_val',child)
                p.close([p.read(child,base,'value')],[row['initial']],'independent coordinate/angle initial '+row['member'])
                p.exception('rv_dom_'+child+'_set_value',[p.pointer,p.single],[readonly,99],'NoModificationAllowedError')
                p.call('rv_dom_'+child+'_set_value',[p.pointer,p.single],base,row['changed'])
                p.close([p.read(child,base,'value')],[row['changed']],'typed coordinate/angle mutation '+row['member'])
                p.call('rv_dom_'+child+'_set_value',[p.pointer,p.single],base,row['initial'])
            elif kind=='SVGAnimatedRect':
                base=p.property(roots[kind],value,'base_val','svg_rect');readonly=p.property(roots[kind],value,'anim_val','svg_rect')
                p.close([p.read('svg_rect',base,key) for key in ['x','y','width','height']],row['initial'],'independent marker viewBox')
                p.exception('rv_dom_svg_rect_set_width',[p.pointer,p.single],[readonly,99],'NoModificationAllowedError')
                p.call('rv_dom_svg_rect_set_width',[p.pointer,p.single],base,row['changed'][2])
                p.close([p.read('svg_rect',base,key) for key in ['x','y','width','height']],row['changed'],'typed marker viewBox mutation')
                p.call('rv_dom_svg_rect_set_width',[p.pointer,p.single],base,row['initial'][2])
            elif kind=='SVGAnimatedPreserveAspectRatio':
                base=p.property(roots[kind],value,'base_val','svg_preserve_aspect_ratio');readonly=p.property(roots[kind],value,'anim_val','svg_preserve_aspect_ratio')
                p.expect(p.read('svg_preserve_aspect_ratio',base,'align',p.short)==row['initial']['align'],'independent marker aspect ratio')
                p.exception('rv_dom_svg_preserve_aspect_ratio_set_align',[p.pointer,p.short],[readonly,6],'NoModificationAllowedError')
                p.call('rv_dom_svg_preserve_aspect_ratio_set_align',[p.pointer,p.short],base,row['changed']['align'])
                p.expect(p.read('svg_preserve_aspect_ratio',base,'align',p.short)==row['changed']['align'],'typed marker aspect mutation')
                p.call('rv_dom_svg_preserve_aspect_ratio_set_align',[p.pointer,p.short],base,row['initial']['align'])
            elif kind=='SVGAnimatedTransformList':
                base=p.property(roots[kind],value,'base_val','svg_transform_list');readonly=p.property(roots[kind],value,'anim_val','svg_transform_list')
                p.expect(p.read('svg_transform_list',base,'number_of_items',p.unsigned)==0,'initial clip transform list')
                p.exception('rv_dom_svg_transform_list_clear',[p.pointer],[readonly],'NoModificationAllowedError')
                item=transform(base,3,4);matrix=p.property('svg_transform',item,'matrix','svg_matrix')
                p.close([p.read('svg_matrix',matrix,key,p.double) for key in ['a','b','c','d','e','f']],row['changed'],'independent clip transform matrix')
                p.call('rv_dom_svg_transform_list_clear',[p.pointer],base)
            elif kind=='SVGStringList':
                p.expect(p.read('svg_string_list',value,'number_of_items',p.unsigned)==0,'initial mask SVGTests list')
                p.expect(p.text('rv_dom_svg_string_list_append_item',[p.pointer,Utf8],value,b'zz')=='zz','real mask SVGTests append')
                p.expect(p.text('rv_dom_svg_string_list_get_item',[p.pointer,p.unsigned],value,0)=='zz','real mask SVGTests item')
                p.call('rv_dom_svg_string_list_clear',[p.pointer],value)
        units=p.property('svg_clip_path_element',clip,'clip_path_units','svg_animated_enumeration')
        p.expect(p.read('svg_animated_enumeration',units,'base_val',p.short)==1,'actual clipPath unit producer')
        before=p.paint()
        p.expect(p.pixel(before,25,25)==[255,0,0,255] and p.pixel(before,75,25)==[255,255,255,255],'actual initial clipping')
        geometry=p.node('clipGeometry')
        _,width=p.length('svg_rect_element',geometry,'width')
        p.set_length(width,80)
        p.expect(p.pixel(p.paint(),75,25)==[255,0,0,255],'typed clip geometry changes actual paint')
        transforms=p.property('svg_animated_transform_list',properties[('clip','transform')],'base_val','svg_transform_list')
        transform(transforms,30,0)
        translated=p.paint()
        p.expect(p.pixel(translated,15,25)==[255,255,255,255] and p.pixel(translated,95,25)==[255,0,0,255],'clip transform changes actual clipping')
        p.call('rv_dom_svg_transform_list_clear',[p.pointer],transforms)
        _,clip_height=p.length('svg_rect_element',geometry,'height')
        p.set_length(width,0.5);p.set_length(clip_height,1)
        p.call('rv_dom_svg_animated_enumeration_set_base_val',[p.pointer,p.short],units,2)
        p.expect(p.pixel(p.paint(),25,25)==[255,0,0,255],'clip objectBoundingBox units scale actual geometry')
        p.call('rv_dom_svg_animated_enumeration_set_base_val',[p.pointer,p.short],units,1)
        p.expect(p.pixel(p.paint(),25,25)==[255,255,255,255],'clip user-space units preserve actual tiny geometry')
        mask_geometry=p.node('maskGeometry')
        p.expect(p.pixel(before,175,25)==[0,0,255,255] and p.pixel(before,225,25)==[255,255,255,255],'actual initial mask output')
        for member in ['requiredExtensions','systemLanguage']:
            values=properties[('mask',member)]
            p.expect(p.text('rv_dom_svg_string_list_append_item',[p.pointer,Utf8],values,b'zz')=='zz','actual mask test list state')
            p.expect(p.pixel(p.paint(),175,25)==[0,0,255,255],'measured mask test lists do not suppress actual paint')
            p.call('rv_dom_svg_string_list_clear',[p.pointer],values)
        p.call('rv_dom_element_set_attribute',[p.pointer,Utf8,Utf8],mask_geometry,b'fill',b'black')
        p.expect(p.pixel(p.paint(),175,25)==[255,255,255,255],'luminance mask black removes actual paint')
        style=p.property('svg_element',mask,'style','css_style_declaration')
        p.call('rv_dom_css_style_declaration_set_property',[p.pointer,Utf8,Utf8,Utf8],style,b'mask-type',b'alpha',b'')
        p.expect(p.text('rv_dom_css_style_declaration_get_property_value',[p.pointer,Utf8],style,b'mask-type')=='alpha','actual mask alpha style reflection')
        p.expect(p.pixel(p.paint(),175,25)==[255,255,255,255],'shared native/Chrome cached mask output after style-only change')
        p.call('rv_dom_element_set_attribute',[p.pointer,Utf8,Utf8],mask_geometry,b'x',b'151')
        p.expect(p.pixel(p.paint(),175,25)==[0,0,255,255],'alpha mask uses opacity after actual child geometry invalidation')
        mask_lengths={field:p.length('svg_mask_element',mask,field)[1] for field in ['x','y','width','height']}
        geom_lengths={field:p.length('svg_rect_element',mask_geometry,field)[1] for field in ['x','y','width','height']}
        for field,value in [('x',0),('y',0),('width',0.5),('height',1)]:
            p.set_length(geom_lengths[field],value)
        p.call('rv_dom_svg_animated_enumeration_set_base_val',[p.pointer,p.short],properties[('mask','maskContentUnits')],2)
        relative_mask=p.paint()
        p.expect(p.pixel(relative_mask,175,25)==[0,0,255,255] and p.pixel(relative_mask,225,25)==[255,255,255,255],'mask content units change actual child scale')
        for field,value in [('x',0),('y',0),('width',1),('height',1)]:
            p.set_length(mask_lengths[field],value)
        p.call('rv_dom_svg_animated_enumeration_set_base_val',[p.pointer,p.short],properties[('mask','maskUnits')],2)
        p.expect(p.pixel(p.paint(),175,25)==[0,0,255,255],'mask object units apply actual target region')
        p.call('rv_dom_svg_animated_enumeration_set_base_val',[p.pointer,p.short],properties[('mask','maskUnits')],1)
        p.expect(p.pixel(p.paint(),175,25)==[255,255,255,255],'mask user-space region clips actual target')
        p.expect(p.pixel(before,235,200)==[0,255,0,255] and p.pixel(before,220,215)==[255,255,255,255],'actual initial marker paint')
        angle=p.object('rv_dom_svgsvg_element_create_svg_angle',[p.pointer],[root],'svg_angle')
        p.call('rv_dom_svg_angle_set_value',[p.pointer,p.single],angle,90)
        p.call('rv_dom_svg_marker_element_set_orient_to_angle',[p.pointer,p.pointer],marker,angle)
        turned=p.paint()
        p.expect(p.pixel(turned,235,200)==[255,255,255,255] and p.pixel(turned,220,215)==[0,255,0,255],'explicit marker angle changes actual orientation')
        p.expect(p.read('svg_animated_enumeration',properties[('marker','orientType')],'base_val',p.short)==2,'real explicit marker orientation type')
        p.expect(p.text('rv_dom_svg_marker_element_get_orient',[p.pointer],marker)=='90','native-only actual orient text')
        p.call('rv_dom_svg_marker_element_set_orient_to_auto',[p.pointer],marker)
        p.expect(p.pixel(p.paint(),235,200)==[0,255,0,255],'automatic orientation follows actual line direction')
        p.expect(p.text('rv_dom_svg_marker_element_get_orient',[p.pointer],marker)=='auto','native-only actual auto orient text')
        p.expect(p.bind('rv_dom_svg_marker_element_set_orient_to_angle',p.integer,[p.pointer,p.pointer])(marker,None)==-1,'null angle rejected')
        p.expect(p.read('svg_animated_enumeration',properties[('marker','orientType')],'base_val',p.short)==1,'null angle preserves orientation')
        p.call('rv_dom_svg_animated_enumeration_set_base_val',[p.pointer,p.short],properties[('marker','markerUnits')],2)
        p.expect(p.pixel(p.paint(),255,200)==[0,255,0,255],'stroke-width marker units change actual marker size')
        p.call('rv_dom_svg_animated_enumeration_set_base_val',[p.pointer,p.short],properties[('marker','markerUnits')],1)
        marker_lengths={field:p.length('svg_marker_element',marker,field)[1] for field in ['ref_x','ref_y','marker_width','marker_height']}
        p.set_length(marker_lengths['marker_width'],10);p.set_length(marker_lengths['marker_height'],10)
        p.expect(p.pixel(p.paint(),235,200)==[255,255,255,255],'marker dimensions change actual paint')
        p.set_length(marker_lengths['marker_width'],20);p.set_length(marker_lengths['marker_height'],20)
        p.set_length(marker_lengths['ref_x'],5)
        p.expect(p.pixel(p.paint(),235,200)==[255,255,255,255],'marker reference point shifts actual placement')
        p.set_length(marker_lengths['ref_x'],0);p.set_length(marker_lengths['ref_y'],0)
        p.expect(p.pixel(p.paint(),225,215)==[0,255,0,255],'marker refY shifts actual vertical placement')
        p.set_length(marker_lengths['ref_y'],5)
        view_box=p.property('svg_animated_rect',properties[('marker','viewBox')],'base_val','svg_rect')
        p.call('rv_dom_svg_rect_set_width',[p.pointer,p.single],view_box,20)
        p.expect(p.pixel(p.paint(),235,200)==[255,255,255,255],'marker viewBox changes actual content scale')
        aspect=p.property('svg_animated_preserve_aspect_ratio',properties[('marker','preserveAspectRatio')],'base_val','svg_preserve_aspect_ratio')
        none_paint=p.pixel(p.paint(),223,205)
        p.call('rv_dom_svg_preserve_aspect_ratio_set_align',[p.pointer,p.short],aspect,6)
        p.expect(none_paint==[0,255,0,255] and p.pixel(p.paint(),223,205)==[255,255,255,255],'marker aspect ratio changes actual content scale')
        p.call('rv_dom_svg_rect_set_width',[p.pointer,p.single],view_box,10)
        p.call('rv_dom_svg_preserve_aspect_ratio_set_align',[p.pointer,p.short],aspect,1)
        p.call('rv_node_remove',[p.pointer],marker)
        p.expect(p.pixel(p.paint(),235,200)==[255,255,255,255],'removed marker reference clears actual output')
        p.call('rv_node_append_child',[p.pointer,p.pointer],p.node('definitions'),marker)
        p.expect(p.pixel(p.paint(),235,200)==[0,255,0,255],'restored real marker reference restores actual output')
        kept=p.property('svg_animated_angle',properties[('marker','orientAngle')],'base_val','svg_angle')
        for owner in [root,clip,mask,marker]:
            p.watch(owner)
        for release,value in list(reversed(p.retained)):
            if value!=kept:
                p.bind(release,None,[p.pointer])(value);p.retained.remove((release,value))
        p.dispose_host();p.collect();p.expect_expired()
        p.call('rv_dom_svg_angle_set_value',[p.pointer,p.single],kept,37)
        p.expect(p.read('svg_angle',kept,'value')==37,'retained marker angle remains safely mutable after owner collection')
        print(f'PASS SVG clip/mask/marker: {p.assertions} assertions',flush=True)
        return p.assertions


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--native-directory',required=True)
    verify(parser.parse_args().native_directory)
