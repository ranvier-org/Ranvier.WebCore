import json
from pathlib import Path
from PIL import Image

checks=[('initial',(25,25),(255,0,0,255)),('initial',(75,25),(255,255,255,255)),('initial',(175,25),(0,0,255,255)),('initial',(225,25),(255,255,255,255)),('initial',(235,200),(0,255,0,255)),('maskExtension',(175,25),(0,0,255,255)),('maskLanguage',(175,25),(0,0,255,255)),('maskBlack',(175,25),(255,255,255,255)),('maskAlpha',(175,25),(255,255,255,255)),('maskAlphaRepaint',(175,25),(0,0,255,255)),('markerNone',(223,205),(0,255,0,255)),('markerMeet',(223,205),(255,255,255,255))]
rows=[]
for phase,point,expected in checks:
 actual=Image.open('artifacts/svg-clip-'+phase+'.png').convert('RGBA').getpixel(point)
 assert actual==expected,(phase,point,actual,expected)
 rows.append(dict(phase=phase,point=point,actual=actual))
Path('artifacts/svg-clip-browser-pixels.json').write_text(json.dumps(rows,indent=2))
print('PASS SVG clip/mask/marker browser pixels:',len(rows))
