import hashlib
import json
import math
from fractions import Fraction as Q
from pathlib import Path

import numpy as np

from mesa_precision import mesa_budget, integer_address_range

ROOT=Path(__file__).parent


def half_recovery():
    values=np.arange(256,dtype=np.float32)*np.float32(1/255)
    half=values.astype(np.float16)
    half=np.where(half.astype(np.float32)>values,np.nextafter(half,np.float16(0)),half).astype(np.float16)
    restored=half.astype(np.float32)*np.float32(255)
    complement=(np.float32(1)-half.astype(np.float32))*np.float32(255)
    assert np.array_equal(np.rint(restored).astype(int),np.arange(256))
    assert np.array_equal(np.rint(complement).astype(int),255-np.arange(256))
    margin=min(float(np.min(.5-np.abs(restored-np.arange(256)))),float(np.min(.5-np.abs(complement-(255-np.arange(256))))))
    assert margin>0.3
    return {'enumeratedInputBytes':256,'towardZeroHalfConversion':True,'allSourceAndComplementBytesRecovered':True,
            'minimumDistanceToWrongRoundBoundaryUnormUnits':margin,'additionalFloat32RoundErrorBoundUnits':255*2**-22,
            'source':'ActualIR UNORM8 normalize ->vcvtps2ph imm3 ->fpext. Half is only after sampler/address, not an interpolation operation.'}


def nearest_rect(rect,scale):
    x,y,w,h=map(np.float32,rect)
    return [math.floor(float(np.float32(v*scale))+.5)for v in [x,y,np.float32(x+w),np.float32(y+h)]]


def expectation(scale,inputs):
    assert scale in [1.5,2]
    profile=inputs['actualProfile']
    assert profile['version']=='OpenGL ES 3.2 Mesa 25.2.8-0ubuntu0.24.04.4'
    assert profile['renderer']=='llvmpipe (LLVM 20.1.2, 256 bits)' and profile['subpixelBits']==8
    assert inputs['localAndCiIrSha256']=='c8725b2468c0b5c87f138d0eb0cc8e171cbcd70ad8392a50f62e466f6aae8f1a'
    layout=lambda x:math.trunc(x*64)/64
    border=layout(float(np.float32(np.floor(np.float32(5*scale))/np.float32(scale))))
    css=[106.5+2*border,49.25+2*border]
    primary_origin=layout(math.floor(3*scale)/scale)
    primary_size=[layout((math.ceil((3+x)*scale)-math.floor(3*scale))/scale)for x in css]
    paint_origin=3-primary_origin
    paint=[paint_origin,paint_origin,*css]
    precise=[float(np.float32(paint_origin+math.floor(border*scale+.5)/scale+padding))for padding in [2,10]]+[100.5,33.25]
    outer=nearest_rect(paint,scale)
    inner=nearest_rect([paint_origin+border,paint_origin+border,css[0]-2*border,css[1]-2*border],scale)
    content=nearest_rect(precise,scale)
    quad_size=[float(np.float32(x*scale))for x in primary_size]
    origin=[(primary_origin+7.25)*scale,(primary_origin+11.5)*scale]
    texture_size=[math.ceil(x)for x in quad_size]
    width,height=int(800*scale),int(600*scale)
    arithmetic,proof=mesa_budget(origin,quad_size,texture_size,[width,height])
    left,top=map(lambda x:max(0,math.ceil(x-.5)),origin)
    right=min(width,math.ceil(origin[0]+quad_size[0]-.5))
    bottom=min(height,math.ceil(origin[1]+quad_size[1]-.5))
    ranges=[]
    for axis,(start,end)in enumerate([(left,right),(top,bottom)]):
        values=[]
        for pixel in range(start,end):
            ideal=(Q(2*pixel+1,2)-Q(origin[axis]))/Q(quad_size[axis])*texture_size[axis]-Q(1,2)
            values.append(integer_address_range(ideal,arithmetic[axis]))
        ranges.append(np.array(values,dtype=np.int64))
    qmin=np.full((bottom-top,right-left),255,dtype=np.int64)
    qmax=np.zeros_like(qmin)
    red_footprint=np.zeros(qmin.shape,dtype=bool)
    seen=np.zeros((*qmin.shape,256),dtype=bool)
    yy,xx=np.indices(qmin.shape)

    def taps(x,y,red):
        l,t,r,b=content if red else outer
        inside=(x>=l)&(x<r)&(y>=t)&(y<b)
        if not red:
            l,t,r,b=inner
            inside &= ~((x>=l)&(x<r)&(y>=t)&(y<b))
        return inside.astype(np.int64)*255

    def lerp(a,b,w):
        return a+((b-a)*w+128)//256

    for dx in range(int(np.max(ranges[0][:,1]-ranges[0][:,0]))+1):
        for dy in range(int(np.max(ranges[1][:,1]-ranges[1][:,0]))+1):
            kx,ky=np.meshgrid(ranges[0][:,0]+dx,ranges[1][:,0]+dy)
            valid=(kx<=ranges[0][:,1][None,:])&(ky<=ranges[1][:,1][:,None])
            fx,fy=kx&255,ky&255
            x0=np.clip(kx//256,0,texture_size[0]-1);x1=np.clip(kx//256+1,0,texture_size[0]-1)
            y0=np.clip(ky//256,0,texture_size[1]-1);y1=np.clip(ky//256+1,0,texture_size[1]-1)
            filtered=[]
            for red in [False,True]:
                a,b,c,d=[taps(x,y,red)for x,y in [(x0,y0),(x1,y0),(x0,y1),(x1,y1)]]
                filtered.append(lerp(lerp(a,b,fx),lerp(c,d,fx),fy))
            black,red=filtered
            assert not np.any(valid&(black>0)&(red>0))
            alpha=black+red
            qmin=np.where(valid,np.minimum(qmin,alpha),qmin)
            qmax=np.where(valid,np.maximum(qmax,alpha),qmax)
            red_footprint|=valid&(red>0)
            seen[yy[valid],xx[valid],alpha[valid]]=True
    assert np.all(np.count_nonzero(seen,axis=2)==qmax-qmin+1),'Noncontiguous allowed byte set requires explicit palette'
    low=np.full((height,width),255,dtype=np.uint8);high=low.copy()
    low[top:bottom,left:right]=(255-qmax).astype(np.uint8)
    high[top:bottom,left:right]=(255-qmin).astype(np.uint8)
    pink=np.zeros((height,width),dtype=bool);pink[top:bottom,left:right]=red_footprint
    result={'scale':scale,'pixels':width*height,'quad':[*origin,*quad_size],'backingSize':texture_size,
        'backingOuterRect':outer,'backingInnerRect':inner,'backingRedRect':content,
        'sourceGeometry':'Fixture CSS ->LayoutUnit/border device snap ->RenderLayerBacking enclosure ->tile allocation ->nonAA Skia clip; no Windows metadata or capturedRGBA input',
        'mesaFloat32Composition':proof,'filter':'ActualIR two sequential byte lerps a+floor(((b-a)*weight+128)/256), 8-bit integer weights, CLAMP_TO_EDGE',
        'halfOutputRecovery':half_recovery(),'filterErrorTolerance':None,'d3dRulesUsed':False,
        'exactSingleTuplePixels':int(np.count_nonzero(low==high)),'multipleAllowedTuplePixels':int(np.count_nonzero(low!=high))}
    return low,high,pink,result
