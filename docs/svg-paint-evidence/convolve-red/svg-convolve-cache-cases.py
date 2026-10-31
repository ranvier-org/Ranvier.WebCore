import ctypes
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests/abi'))
from svg_paint_probe import SvgProbe

rows=[]
for route in ['input','order']:
    with SvgProbe(sys.argv[1],100,100) as p:
        p.load('''<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><defs><filter id="filter" filterUnits="userSpaceOnUse" x="0" y="0" width="80" height="80" color-interpolation-filters="sRGB"><feFlood flood-color="blue" result="blue"/><feConvolveMatrix id="convolve" in="SourceGraphic" order="3" kernelMatrix="0 0 0 0 1 0 0 0 0" divisor="1" bias="0.25" targetX="1" targetY="1" preserveAlpha="true"/></filter></defs><rect x="20" y="20" width="20" height="20" fill="red" filter="url(#filter)"/></svg>''')
        target=p.node('convolve')
        before=p.pixel(p.paint(),30,30)
        if route=='input':
            value=p.property('svgfe_convolve_matrix_element',target,'in1','svg_animated_string')
            p.call('rv_dom_svg_animated_string_set_base_val',[p.pointer,ctypes.c_char_p],value,b'blue')
        else:
            value=p.property('svgfe_convolve_matrix_element',target,'order_x','svg_animated_integer')
            p.call('rv_dom_svg_animated_integer_set_base_val',[p.pointer,p.integer],value,2)
        rows.append(dict(route=route,before=before,after=p.pixel(p.paint(),30,30),attributes=p.attributes(target)))
Path(sys.argv[2]).write_text(json.dumps(rows,indent=2)+'\n')
print(json.dumps(rows))
