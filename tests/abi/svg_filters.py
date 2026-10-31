import argparse
import ctypes
import json
import math
from pathlib import Path
import re
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe
from utf8_inputs import Utf8


def verify(native_directory):
    with SvgProbe(native_directory, 500, 400) as p:
        p.load((Path(__file__).resolve().parents[1] / 'fixtures/svg-filters.svg').read_bytes())
        oracle = json.loads((Path(__file__).resolve().parents[1] / 'fixtures/svg-filter-member-oracle.json').read_text())
        roots = {'SVGAnimatedString':'svg_animated_string','SVGAnimatedNumber':'svg_animated_number','SVGAnimatedInteger':'svg_animated_integer','SVGAnimatedEnumeration':'svg_animated_enumeration','SVGAnimatedBoolean':'svg_animated_boolean','SVGAnimatedLength':'svg_animated_length','SVGAnimatedNumberList':'svg_animated_number_list','SVGAnimatedPreserveAspectRatio':'svg_animated_preserve_aspect_ratio'}
        scalar_types = {'SVGAnimatedNumber':p.single,'SVGAnimatedInteger':p.integer,'SVGAnimatedEnumeration':p.short,'SVGAnimatedBoolean':p.integer}
        nodes = {}
        properties = {}
        def node(identifier):
            if identifier not in nodes:
                nodes[identifier] = p.node(identifier)
            return nodes[identifier]
        def number_list(target):
            return [p.read('svg_number', p.object('rv_dom_svg_number_list_get_item', [p.pointer,p.unsigned], [target,index], 'svg_number'), 'value') for index in range(p.read('svg_number_list',target,'number_of_items',p.unsigned))]
        def current(root, target):
            if root in scalar_types:
                return p.read(roots[root], target, 'base_val', scalar_types[root])
            if root == 'SVGAnimatedString':
                return p.text('rv_dom_svg_animated_string_get_base_val',[p.pointer],target)
            if root == 'SVGAnimatedLength':
                return p.read('svg_length',p.property('svg_animated_length',target,'base_val','svg_length'),'value')
            if root == 'SVGAnimatedNumberList':
                return number_list(p.property('svg_animated_number_list',target,'base_val','svg_number_list'))
            base = p.property('svg_animated_preserve_aspect_ratio',target,'base_val','svg_preserve_aspect_ratio')
            return {field:p.read('svg_preserve_aspect_ratio',base,field,p.short) for field in ['align','meet_or_slice']}
        def compare(actual, expected, label):
            if isinstance(expected,list):
                p.close(actual,expected,label)
            elif isinstance(expected,dict):
                p.expect(actual['align']==expected['align'] and actual['meet_or_slice']==expected['meetOrSlice'],label)
            elif isinstance(expected,(int,float)):
                p.close([actual],[expected],label)
            else:
                p.expect(actual==expected,label)
        def write(root,target,value):
            if root in scalar_types:
                p.call('rv_dom_'+roots[root]+'_set_base_val',[p.pointer,scalar_types[root]],target,value)
            elif root == 'SVGAnimatedString':
                p.call('rv_dom_svg_animated_string_set_base_val',[p.pointer,Utf8],target,value.encode())
            elif root == 'SVGAnimatedLength':
                p.set_length(p.property('svg_animated_length',target,'base_val','svg_length'),value)
            elif root == 'SVGAnimatedNumberList':
                base=p.property('svg_animated_number_list',target,'base_val','svg_number_list')
                first=p.object('rv_dom_svg_number_list_get_item',[p.pointer,p.unsigned],[base,0],'svg_number')
                p.call('rv_dom_svg_number_set_value',[p.pointer,p.single],first,value[0])
            else:
                base=p.property('svg_animated_preserve_aspect_ratio',target,'base_val','svg_preserve_aspect_ratio')
                p.call('rv_dom_svg_preserve_aspect_ratio_set_align',[p.pointer,p.short],base,value['align'])
        def equivalent_serialization(got, want):
            left,right=re.split(r'[ ,]+',got),re.split(r'[ ,]+',want)
            try:
                numbers=[float(x.rstrip('%')) for x in left],[float(x.rstrip('%')) for x in right]
            except ValueError:
                return False
            return (len(left)==len(right) and all(abs(a-b)<=0.001 for a,b in zip(*numbers))
                    and [x.endswith('%') for x in left]==[x.endswith('%') for x in right])
        def compare_attributes(actual, expected, label):
            p.expect(actual.keys()==expected.keys(),label+' attribute names: '+str((actual,expected)))
            for name,want in expected.items():
                got=actual[name]
                p.expect(got==want or equivalent_serialization(got,want),label+' '+name+': '+repr((got,want)))
        for row in oracle['rows']:
            target = node(row['id'])
            root = row['root']
            animated = p.object(row['function'],[p.pointer],[target],roots[root])
            properties[(row['id'],row['member'])] = animated
            again = p.object(row['function'],[p.pointer],[target],roots[root])
            p.expect(again==animated,'real live filter property identity '+row['id']+'.'+row['member'])
            if row['state']=='NotExposed':
                p.expect(row['member']=='edgeMode','only documented blur native-only member')
                p.expect(current(root,animated)==3,'source-backed blur default EdgeModeType::None')
                write(root,animated,1)
                p.expect(current(root,animated)==1 and p.attribute(target,'edgeMode')=='duplicate','real native-only blur edgeMode edit')
                write(root,animated,3)
                p.exception('rv_dom_svg_animated_enumeration_set_base_val',[p.pointer,p.short],[animated,999],'TypeError')
                continue
            compare(current(root,animated),row['initial'],'independent browser initial '+row['id']+'.'+row['member'])
            if root == 'SVGAnimatedLength':
                readonly=p.property('svg_animated_length',animated,'anim_val','svg_length')
                p.exception('rv_dom_svg_length_set_value',[p.pointer,p.single],[readonly,99],'NoModificationAllowedError')
            elif root == 'SVGAnimatedNumberList':
                readonly=p.property('svg_animated_number_list',animated,'anim_val','svg_number_list')
                first=p.object('rv_dom_svg_number_list_get_item',[p.pointer,p.unsigned],[readonly,0],'svg_number')
                p.exception('rv_dom_svg_number_set_value',[p.pointer,p.single],[first,99],'NoModificationAllowedError')
            elif root == 'SVGAnimatedPreserveAspectRatio':
                readonly=p.property('svg_animated_preserve_aspect_ratio',animated,'anim_val','svg_preserve_aspect_ratio')
                p.exception('rv_dom_svg_preserve_aspect_ratio_set_align',[p.pointer,p.short],[readonly,1],'NoModificationAllowedError')
            write(root,animated,row['changed'])
            compare(current(root,animated),row['changed'],'actual filter parameter mutation '+row['id']+'.'+row['member'])
            actual_attributes = p.attributes(target)
            if row['id']=='blur' and 'edgeMode' not in row['afterAttributes']:
                actual_attributes.pop('edgeMode',None)
            compare_attributes(actual_attributes,row['afterAttributes'],'independent attribute mutation '+row['id']+'.'+row['member'])
            write(root,animated,row['initial'])
            if root == 'SVGAnimatedEnumeration':
                p.exception('rv_dom_svg_animated_enumeration_set_base_val',[p.pointer,p.short],[animated,999],'TypeError')
                compare(current(root,animated),row['initial'],'invalid filter enum preserves state')
        for row in oracle['methods']:
            target=node(row['id'])
            function='rv_dom_svgfe_'+('gaussian_blur' if row['id']=='blur' else 'drop_shadow')+'_element_set_std_deviation'
            args=[0,0]
            args[row['index']]={'NaN':math.nan,'Infinity':math.inf,'-Infinity':-math.inf}[row['input']]
            p.exception(function,[p.pointer,p.single,p.single],[target,*args],'TypeError')
            for field in ['stdDeviationX','stdDeviationY']:
                p.expect(current('SVGAnimatedNumber',properties[(row['id'],field)])==0,'nonfinite filter method preserves prior values')
        filter_node = p.node('filter')
        units = p.property('svg_filter_element', filter_node, 'filter_units', 'svg_animated_enumeration')
        p.expect(p.read('svg_animated_enumeration', units, 'base_val', p.short) == 1, 'real filter units producer')
        blur = p.node('blur')
        before = p.pixel(p.paint(), 415, 130)
        p.expect(before == [255, 255, 255, 255], 'unblurred source leaves exterior white')
        p.call('rv_dom_svgfe_gaussian_blur_element_set_std_deviation', [p.pointer, p.single, p.single], blur, 5, 0)
        after = p.pixel(p.paint(), 415, 130)
        p.expect(after[0] == 255 and after[1] < 250 and after[2] < 250, 'typed blur parameters change actual rendered paint')
        untouched=p.pointer(123)
        get_units=p.bind('rv_dom_svg_filter_element_get_filter_units',p.integer,[p.pointer,ctypes.POINTER(p.pointer)])
        p.expect(get_units(node('target'),ctypes.byref(untouched))==-11 and untouched.value==123,'filter subtype error preserves output')
        statuses=[]
        worker=threading.Thread(target=lambda:statuses.append(get_units(filter_node,ctypes.byref(untouched))))
        worker.start();worker.join()
        p.expect(statuses==[-2] and untouched.value==123,'filter off-thread error preserves output')
        kept = properties[('blur','stdDeviationX')]
        for identifier in ['root','filter','blur','funcR','funcG','funcB','funcA','distant','point','spot']:
            p.watch(node(identifier))
        for release,value in list(reversed(p.retained)):
            if value!=kept:
                p.bind(release,None,[p.pointer])(value)
                p.retained.remove((release,value))
        p.dispose_host()
        p.collect()
        p.expect_expired()
        p.expect(p.read('svg_animated_number',kept,'base_val')==5,'real filter parameter survives owner collection')
        p.call('rv_dom_svg_animated_number_set_base_val',[p.pointer,p.single],kept,2)
        p.expect(p.read('svg_animated_number',kept,'base_val')==2,'detached filter parameter remains safely mutable')
        assertions=p.assertions
    assertions += paint_effects(native_directory)
    assertions += convolve_cache_cases(native_directory)
    print(f'PASS SVG filters: {assertions} assertions', flush=True)
    return assertions


def paint_effects(native_directory):
    with SvgProbe(native_directory,500,400) as p:
        p.load((Path(__file__).resolve().parents[1]/'fixtures/svg-filters.svg').read_bytes())
        oracle=json.loads((Path(__file__).resolve().parents[1]/'fixtures/svg-filter-member-oracle.json').read_text())
        descriptors={(row['id'],row['member']):row for row in oracle['rows']}
        roots={'SVGAnimatedNumber':'svg_animated_number','SVGAnimatedEnumeration':'svg_animated_enumeration','SVGAnimatedString':'svg_animated_string','SVGAnimatedNumberList':'svg_animated_number_list','SVGAnimatedPreserveAspectRatio':'svg_animated_preserve_aspect_ratio'}
        nodes,properties={},{}
        def node(identifier):
            if identifier not in nodes:
                nodes[identifier]=p.node(identifier)
            return nodes[identifier]
        def prop(identifier,member):
            key=(identifier,member)
            if key not in properties:
                row=descriptors[key]
                properties[key]=p.object(row['function'],[p.pointer],[node(identifier)],roots[row['root']])
            return properties[key]
        def number(identifier,member,value):
            p.call('rv_dom_svg_animated_number_set_base_val',[p.pointer,p.single],prop(identifier,member),value)
        def enum(identifier,member,value):
            p.call('rv_dom_svg_animated_enumeration_set_base_val',[p.pointer,p.short],prop(identifier,member),value)
        def string(identifier,member,value):
            p.call('rv_dom_svg_animated_string_set_base_val',[p.pointer,Utf8],prop(identifier,member),value.encode())
        def numbers(identifier,member,values):
            base=p.property('svg_animated_number_list',prop(identifier,member),'base_val','svg_number_list')
            p.expect(p.read('svg_number_list',base,'number_of_items',p.unsigned)==len(values),'real filter numeric list shape')
            for index,value in enumerate(values):
                item=p.object('rv_dom_svg_number_list_get_item',[p.pointer,p.unsigned],[base,index],'svg_number')
                p.call('rv_dom_svg_number_set_value',[p.pointer,p.single],item,value)
        def style(identifier,property,value):
            declaration=p.property('svg_element',node(identifier),'style','css_style_declaration')
            p.call('rv_dom_css_style_declaration_set_property',[p.pointer,Utf8,Utf8,Utf8],declaration,property.encode(),value.encode(),b'')
        def wait_image(color):
            pixels=(ctypes.c_uint8*(500*400*4))()
            deadline=time.monotonic()+5
            while True:
                if p.bind('rv_host_update',p.integer,[p.pointer])(p.host)<0:
                    raise AssertionError('filter image update')
                if p.bind('rv_host_paint_rgba',p.integer,[p.pointer,p.pointer,p.integer])(p.host,pixels,len(pixels))!=0:
                    raise AssertionError('filter image paint')
                if p.pixel(pixels,30,230)==color:
                    break
                if time.monotonic()>deadline:
                    raise AssertionError('real filter image readiness: '+str(p.pixel(pixels,30,230)))
                if p.bind('rv_run_loop_cycle',p.integer,[p.integer])(10)<0:
                    raise AssertionError('filter image event cycle')
            p.expect(True,'actual filter image decode/paint readiness')
        red,blue,white=[255,0,0,255],[0,0,255,255],[255,255,255,255]
        wait_image(red)
        before=p.paint()
        specular_initial=p.pixel(before,30,330)
        print('SPECULAR_PROVIDER',{'initial':specular_initial},flush=True)
        p.expect(specular_initial[2]>200 and specular_initial[0]<50 and specular_initial[1]<50,'actual nonzero spot/specular lighting paints blue before edits')
        for x,y,want in [(30,30,red),(130,30,red),(230,30,[64,128,192,255]),(330,30,red),(430,30,red),(330,130,blue),(130,230,red),(130,330,red)]:
            p.close(p.pixel(before,x,y),want,'actual baseline filter output '+str((x,y)),tolerance=1)
        enum('blend','mode',2)
        p.expect(p.pixel(p.paint(),30,30)==[0,0,0,255],'blend mode changes actual paint')
        numbers('matrix','values',[0,0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,1,0])
        p.expect(p.pixel(p.paint(),130,30)==[0,255,0,255],'color matrix list changes actual paint')
        for identifier,intercept,want in [('funcR',1,[255,128,192,255]),('funcG',0,[255,0,192,255]),('funcB',1,[255,0,255,255]),('funcA',0.5,[255,128,255,255])]:
            number(identifier,'slope',0);number(identifier,'intercept',intercept)
            p.close(p.pixel(p.paint(),230,30),want,'real component-transfer channel '+identifier,tolerance=1)
        number('composite','k2',0);number('composite','k3',1)
        p.expect(p.pixel(p.paint(),330,30)==blue,'arithmetic composite parameters change actual paint')
        numbers('convolve','kernelMatrix',[0]*9);number('convolve','bias',0.5)
        p.close(p.pixel(p.paint(),430,30),[128,128,128,255],'convolve kernel/bias change actual paint',tolerance=1)
        number('distant','elevation',80)
        elevated=p.pixel(p.paint(),30,130)
        p.expect(elevated[0]>p.pixel(before,30,130)[0],'distant light changes actual diffuse lighting')
        number('diffuse','diffuseConstant',0)
        p.expect(p.pixel(p.paint(),30,130)==[0,0,0,255],'diffuse constant changes actual lighting')
        number('displacement','scale',20)
        displaced=p.paint()
        p.expect(p.pixel(displaced,145,115)==red and p.pixel(displaced,125,135)==white,'displacement channel/scale change actual source placement')
        number('shadow','dx',10);number('shadow','dy',10)
        p.close(p.pixel(p.paint(),245,145),[128,128,255,255],'drop-shadow offsets change actual paint',tolerance=1)
        style('flood','flood-color','rgb(0,255,0)')
        p.expect(p.pixel(p.paint(),330,130)==[0,255,0,255],'CSS flood color changes actual filter paint')
        p.call('rv_dom_svgfe_gaussian_blur_element_set_std_deviation',[p.pointer,p.single,p.single],node('blur'),5,0)
        blurred=p.pixel(p.paint(),415,130)
        p.expect(blurred[0]==255 and blurred[1]<250 and blurred[2]<250,'Gaussian blur method changes actual paint')
        aspect=p.property('svg_animated_preserve_aspect_ratio',prop('image','preserveAspectRatio'),'base_val','svg_preserve_aspect_ratio')
        p.expect(p.pixel(before,5,205)==white,'image aspect-ratio letterboxing is actual paint')
        p.call('rv_dom_svg_preserve_aspect_ratio_set_align',[p.pointer,p.short],aspect,1)
        p.expect(p.pixel(p.paint(),5,205)==red,'FEImage aspect-ratio edit changes actual paint')
        original=p.text('rv_dom_svg_animated_string_get_base_val',[p.pointer],prop('image','href'))
        string('image','href',original.replace("fill='red'","fill='blue'"))
        wait_image(blue)
        p.expect(p.pixel(p.paint(),30,230)==blue,'FEImage URI edit changes actual decoded paint')
        string('mergeNode','in1','blue')
        p.expect(p.pixel(p.paint(),130,230)==blue,'merge-node input changes actual graph output')
        enum('morphology','operator',2);number('morphology','radiusX',3);number('morphology','radiusY',3)
        p.expect(p.pixel(p.paint(),218,230)==red,'morphology dilation changes actual bounds')
        enum('morphology','operator',1)
        p.expect(p.pixel(p.paint(),220,230)==white,'morphology erosion changes actual bounds')
        number('offset','dx',10);number('offset','dy',10)
        moved=p.paint()
        p.expect(p.pixel(moved,345,245)==red and p.pixel(moved,325,225)==white,'offset parameters change actual source position')
        number('point','z',10)
        p.expect(p.pixel(p.paint(),430,230)[0]<p.pixel(before,430,230)[0],'point-light position changes actual lighting')
        number('spot','pointsAtX',100);number('spot','limitingConeAngle',5)
        p.expect(p.pixel(p.paint(),30,330)==white,'spot direction/cone change actual specular paint')
        number('spot','pointsAtX',30);number('spot','limitingConeAngle',90)
        number('specular','specularConstant',0)
        specular_zero=p.pixel(p.paint(),30,330)
        print('SPECULAR_PROVIDER',{'zeroConstant':specular_zero},flush=True)
        p.expect(specular_zero==white,'native specular zero is transparent over white (measured Chromium opaque black qualification)')
        string('tile','in1','blue')
        p.expect(p.pixel(p.paint(),130,330)==blue,'tile input changes actual tiled output')
        positions=[(x,y) for x in range(210,261,10) for y in range(310,361,10)]
        initial=[p.pixel(before,x,y) for x,y in positions]
        number('turbulence','seed',7)
        changed_pixels=p.paint();changed=[p.pixel(changed_pixels,x,y) for x,y in positions]
        p.expect(changed!=initial,'turbulence seed changes actual generated paint')
        number('turbulence','seed',0)
        repeated=p.paint()
        p.expect([p.pixel(repeated,x,y) for x,y in positions]==initial,'turbulence seed restores deterministic actual paint')
        return p.assertions


def convolve_cache_cases(native_directory):
    assertions=0
    for route in ['input','order']:
        with SvgProbe(native_directory,100,100) as p:
            p.load('''<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><defs><filter filterUnits="userSpaceOnUse" x="0" y="0" width="80" height="80" color-interpolation-filters="sRGB" id="filter"><feFlood flood-color="blue" result="blue"/><feConvolveMatrix id="convolve" in="SourceGraphic" order="3" kernelMatrix="0 0 0 0 1 0 0 0 0" divisor="1" bias="0.25" targetX="1" targetY="1" preserveAlpha="true"/></filter></defs><rect x="20" y="20" width="20" height="20" fill="red" filter="url(#filter)"/></svg>''')
            target=p.node('convolve')
            p.close(p.pixel(p.paint(),30,30),[255,64,64,255],'convolve cached initial effect',tolerance=1)
            if route=='input':
                value=p.property('svgfe_convolve_matrix_element',target,'in1','svg_animated_string')
                p.call('rv_dom_svg_animated_string_set_base_val',[p.pointer,Utf8],value,b'blue')
                p.close(p.pixel(p.paint(),30,30),[64,64,255,255],'input graph change preserves actual convolve effect',tolerance=1)
            else:
                value=p.property('svgfe_convolve_matrix_element',target,'order_x','svg_animated_integer')
                p.call('rv_dom_svg_animated_integer_set_base_val',[p.pointer,p.integer],value,2)
                p.expect(p.pixel(p.paint(),30,30)==[255,255,255,255],'order change discards stale effect when kernel dimensions become invalid')
                p.call('rv_dom_svg_animated_integer_set_base_val',[p.pointer,p.integer],value,3)
                p.close(p.pixel(p.paint(),30,30),[255,64,64,255],'valid order restores actual effect',tolerance=1)
            assertions+=p.assertions
    return assertions


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    verify(parser.parse_args().native_directory)
