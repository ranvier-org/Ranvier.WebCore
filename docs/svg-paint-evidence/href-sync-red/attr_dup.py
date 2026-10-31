import json, runpy, sys, os, ctypes
sys.path.insert(0, 'tests/abi'); sys.path.insert(0, 'artifacts')
import svg_paint_probe
from diagnose_href_enumeration import raw, named, names
original = svg_paint_probe.SvgProbe.attributes
found = []
def attributes(self, target):
    first = raw(self, target)
    if len(first) != len(set(first)):
        found.append({'raw': first, 'named': named(self, target), 'rawAfterNamed': raw(self, target), 'names': names(self, target)})
        print('DUPLICATE', json.dumps(found[-1]), flush=True)
    return original(self, target)
svg_paint_probe.SvgProbe.attributes = attributes
sys.argv = ['svg_filters.py', '--native-directory', sys.argv[1]]
runpy.run_path('tests/abi/svg_filters.py', run_name='__main__')
