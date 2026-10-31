import ctypes
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests/abi'))
from svg_paint_probe import SvgProbe

with SvgProbe('artifacts/svg-paint-candidate/runtime',100,100) as p:
    p.load('''<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><defs><filter id="filter" filterUnits="userSpaceOnUse" x="0" y="0" width="80" height="80"><feImage id="image" preserveAspectRatio="xMidYMid meet" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='40' height='20'%3E%3Crect width='40' height='20' fill='red'/%3E%3C/svg%3E"/></filter></defs><rect x="20" y="20" width="20" height="20" filter="url(#filter)"/></svg>''')
    image=p.node('image')
    animated=p.property('svgfe_image_element',image,'preserve_aspect_ratio','svg_animated_preserve_aspect_ratio')
    base=p.property('svg_animated_preserve_aspect_ratio',animated,'base_val','svg_preserve_aspect_ratio')
    deadline=time.monotonic()+5
    while p.pixel(p.paint(),30,30)!=[255,0,0,255]:
        if time.monotonic()>deadline:
            raise AssertionError('FEImage red resource readiness')
        p.bind('rv_run_loop_cycle',p.integer,[p.integer])(10)
    rows=[]
    for phase in ['initial','typedNone','authoredNone']:
        if phase=='typedNone':
            p.call('rv_dom_svg_preserve_aspect_ratio_set_align',[p.pointer,p.short],base,1)
        if phase=='authoredNone':
            p.call('rv_dom_element_set_attribute',[p.pointer,ctypes.c_char_p,ctypes.c_char_p],image,b'preserveAspectRatio',b'none')
        rgba=p.paint()
        rows.append(dict(phase=phase,attribute=p.attribute(image,'preserveAspectRatio'),align=p.read('svg_preserve_aspect_ratio',base,'align',p.short),corner=p.pixel(rgba,5,5),center=p.pixel(rgba,30,30)))
Path('artifacts/svg-feimage-native-oracle.json').write_text(json.dumps(rows,indent=2)+'\n')
print(json.dumps(rows))
