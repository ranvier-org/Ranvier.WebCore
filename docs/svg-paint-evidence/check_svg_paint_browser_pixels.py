import json
from pathlib import Path
from PIL import Image

count = 0
records = []
def pixel(phase, x, y):
    value = list(Image.open('artifacts/svg-paint-full-' + phase + '.png').convert('RGBA').getpixel((x,y)))
    records.append(dict(phase=phase,x=x,y=y,rgba=value))
    return value
def expect(value, label):
    global count
    count += 1
    assert value, label
red, blue, white = [255,0,0,255], [0,0,255,255], [255,255,255,255]
for x in [25,325]:
    value=pixel('initial',x,50);expect(value[0]>value[2],'initial actual gradient')
for x in [75,375]:
    expect(pixel('linear50',x,50)==blue,'typed gradient coordinate effect')
expect(pixel('gradientTranslate',50,50)[0]>pixel('linear50',50,50)[0],'gradient transform effect')
expect(all(abs(a-b)<=1 for a,b in zip(pixel('spreadRepeat',25,50),pixel('spreadRepeat',75,50))),'repeat spread effect')
value=pixel('gradientObjectUnits',75,50);expect(value[0]>240 and value[2]<10,'gradient object units')
expect(pixel('missingGradient',325,50)==white,'missing actual gradient')
expect(pixel('radialMoved',225,55)[0]>240 and pixel('radialMoved',200,55)==blue,'radial center/radius effect')
expect(pixel('radialFocal',230,55)[0]>pixel('radialMoved',230,55)[0],'focal radius effect')
expect(pixel('stopGreen',10,50)==[0,255,0,255],'stop offset/color effect')
value=pixel('stopOpacity',10,50);expect(value[1]==255 and 120<=value[0]<=135 and 120<=value[2]<=135,'stop opacity effect')
for phase,x,y,want in [('patternMoved',7,122,red),('patternMoved',17,122,white),('patternMoved',7,135,white),('patternMovedY',7,122,white),('patternMovedY',7,127,red),('patternTransform',10,131,red),('patternTransform',15,131,blue),('patternViewBox',15,131,red),('patternObjectUnits',2,122,red),('patternObjectUnits',12,122,white),('patternContentUnits',12,122,red),('patternTests',2,122,red),('patternMissing',202,122,white)]:
    expect(pixel(phase,x,y)==want,phase+' actual paint')
Path('artifacts/svg-paint-browser-pixels.json').write_text(json.dumps(dict(assertions=count,samples=records),indent=2)+'\n')
print('PASS SVG browser paint:',count,'pixel assertions')
