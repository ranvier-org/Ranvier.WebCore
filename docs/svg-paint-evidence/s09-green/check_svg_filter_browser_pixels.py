import json
from pathlib import Path
from PIL import Image

assertions=0
samples=[]
def pixel(phase,x,y):
    value=list(Image.open('artifacts/svg-filter-paint-'+phase+'.png').convert('RGBA').getpixel((x,y)))
    samples.append(dict(phase=phase,x=x,y=y,rgba=value))
    return value
def expect(value,label):
    global assertions
    assertions+=1
    assert value,label
def close(actual,want,label):
    expect(all(abs(a-b)<=1 for a,b in zip(actual,want)),label+': '+str(actual))
red,blue,white=[255,0,0,255],[0,0,255,255],[255,255,255,255]
for x,y,want in [(30,30,red),(130,30,red),(230,30,[64,128,192,255]),(330,30,red),(430,30,red),(330,130,blue),(130,230,red),(130,330,red),(30,330,blue)]:
    close(pixel('initial',x,y),want,'real filter baseline')
for phase,x,y,want in [('blend',30,30,[0,0,0,255]),('matrix',130,30,[0,255,0,255]),('funcR',230,30,[255,128,192,255]),('funcG',230,30,[255,0,192,255]),('funcB',230,30,[255,0,255,255]),('funcA',230,30,[255,128,255,255]),('composite',330,30,blue),('convolve',430,30,[128,128,128,255]),('diffuse',30,130,[0,0,0,255]),('displacement',145,115,red),('shadow',245,145,[128,128,255,255]),('flood',330,130,[0,255,0,255]),('imageAspect',5,205,red),('imageBlue',30,230,blue),('merge',130,230,blue),('morphDilate',218,230,red),('morphErode',220,230,white),('offset',345,245,red),('spotCone',30,330,white),('specularZero',30,330,[0,0,0,255]),('tile',130,330,blue)]:
    close(pixel(phase,x,y),want,phase+' actual filter paint')
expect(pixel('distant',30,130)[0]>pixel('initial',30,130)[0],'distant lighting effect')
expect(pixel('point',430,230)[0]<pixel('initial',430,230)[0],'point lighting effect')
blurred=pixel('blur',415,130);expect(blurred[0]==255 and blurred[1]<250 and blurred[2]<250,'blur exterior effect')
expect(pixel('initial',5,205)==white,'initial actual image letterbox')
crop=lambda phase:Image.open('artifacts/svg-filter-paint-'+phase+'.png').convert('RGBA').crop((200,300,280,380)).tobytes()
expect(crop('turbSeed7')!=crop('initial'),'seed changes actual turbulence')
expect(crop('turbSeed0')==crop('initial'),'seed restores deterministic actual turbulence')
Path('artifacts/svg-filter-browser-pixels.json').write_text(json.dumps(dict(assertions=assertions,samples=samples,qualification='Specular constant zero is opaque black in measured Chromium; pinned native is transparent over white. Both nonzero baselines are blue.'),indent=2)+'\n')
print('PASS SVG filter browser paint:',assertions,'assertions across27capturedphases')
