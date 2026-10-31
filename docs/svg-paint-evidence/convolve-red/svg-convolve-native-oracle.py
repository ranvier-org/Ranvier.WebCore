import ctypes
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests/abi'))
from svg_paint_probe import SvgProbe

rows=[]
with SvgProbe('artifacts/svg-paint-candidate/runtime',500,400) as p:
    p.load(Path('tests/fixtures/svg-filters.svg').read_bytes())
    convolve=p.node('convolve')
    animated=p.property('svgfe_convolve_matrix_element',convolve,'kernel_matrix','svg_animated_number_list')
    base=p.property('svg_animated_number_list',animated,'base_val','svg_number_list')
    items=[p.object('rv_dom_svg_number_list_get_item',[p.pointer,p.unsigned],[base,i],'svg_number') for i in range(9)]
    bias=p.property('svgfe_convolve_matrix_element',convolve,'bias','svg_animated_number')
    for phase in ['initial','typedKernel','bias','authoredKernel']:
        if phase=='typedKernel':
            for item in items:
                p.call('rv_dom_svg_number_set_value',[p.pointer,p.single],item,0)
        if phase=='bias':
            p.call('rv_dom_svg_animated_number_set_base_val',[p.pointer,p.single],bias,0.5)
        if phase=='authoredKernel':
            p.call('rv_dom_element_set_attribute',[p.pointer,ctypes.c_char_p,ctypes.c_char_p],convolve,b'kernelMatrix',b'0 0 0 0 0 0 0 0 0')
        rows.append(dict(phase=phase,kernel=[p.read('svg_number',item,'value') for item in items],attribute=p.attribute(convolve,'kernelMatrix'),bias=p.read('svg_animated_number',bias,'base_val'),pixel=p.pixel(p.paint(),430,30)))
Path('artifacts/svg-convolve-native-oracle.json').write_text(json.dumps(rows,indent=2)+'\n')
print(json.dumps(rows))
