"""Source-matched float32 plane/address bounds for the recorded llvmpipe profile."""
from fractions import Fraction as Q
import math

from precision_budget import projection_bound


def interval_gradient(width, height, width_error, height_error, axis):
    unit=Q(1,2**24)
    w=(width-width_error,width+width_error)
    h=(height-height_error,height+height_error)
    w=(w[0]*(1-unit),w[1]*(1+unit))
    h=(h[0]*(1-unit),h[1]*(1+unit))
    area=(w[0]*h[0]*(1-unit),w[1]*h[1]*(1+unit))
    reciprocal=((1-unit)/area[1],(1+unit)/area[0])
    opposite=h if axis==0 else w
    gradient=(opposite[0]*reciprocal[0]*(1-unit),opposite[1]*reciprocal[1]*(1+unit))
    return gradient


def mesa_budget(quad_origin,quad_size,texture_size,viewport):
    unit=Q(1,2**24)
    positions=[[projection_bound(quad_origin[axis]+end*quad_size[axis],viewport[axis],23)
                for end in [0,1]]for axis in [0,1]]
    errors=[[Q(row['exactTotalScreenErrorFraction'])for row in axis]for axis in positions]
    # Mirroring the projection changes the viewport addition from y to H-y.
    # Its magnitude can grow by at most H; retain that extra u*H term.
    errors[1]=[error+unit*viewport[1] for error in errors[1]]
    for row,error in zip(positions[1],errors[1]):
        row['mirrorSafeTotalScreenError']=float(error)
        row['mirrorAdditionalViewportAddError']=float(unit*viewport[1])
    assert all(e<Q(2,5*256)for axis in errors for e in axis)
    sizes=list(map(Q,quad_size))
    gradients=[interval_gradient(*sizes,sum(errors[0]),sum(errors[1]),axis)for axis in [0,1]]
    proofs=[];bounds=[]
    for axis in [0,1]:
        ideal_gradient=1/sizes[axis]
        gmin,gmax=gradients[axis]
        gradient_error=max(abs(gmin-ideal_gradient),abs(gmax-ideal_gradient))
        orientations=[]
        for flipped in ([False] if axis==0 else [False,True]):
            origin=Q(quad_origin[axis]) if not flipped else Q(viewport[axis])-Q(quad_origin[axis])
            origin_error=errors[axis][0]
            center=origin-Q(1,2)
            max_fragment=max(abs(origin),abs(origin+(-1 if flipped else 1)*sizes[axis]))+1
            coefficient_error=unit*gmax*(abs(center)+origin_error)
            interpolation_multiply=unit*gmax*max_fragment
            interpolation_add=unit*(gmax*max_fragment+gmax*(abs(center)+origin_error)
                                    +coefficient_error+interpolation_multiply)
            normalized=(gradient_error*sizes[axis]+gmax*origin_error
                        +coefficient_error+interpolation_multiply+interpolation_add)
            sampler=texture_size[axis]*normalized+unit*texture_size[axis]*(1+normalized)
            orientations.append({'flipped':flipped,'origin':float(origin),
                'gradientInputAndArithmeticError':float(gradient_error*sizes[axis]),
                'originContribution':float(gmax*origin_error),'coefficientMultiply':float(coefficient_error),
                'interpolationMultiply':float(interpolation_multiply),'interpolationAdd':float(interpolation_add),
                'normalizedError':float(normalized),'addressTexels':float(sampler),'exactAddressTexels':str(sampler)})
        bound=max(Q(row['exactAddressTexels'])for row in orientations)
        bounds.append(bound)
        proofs.append({'axis':axis,'gradientInterval':[float(gmin),float(gmax)],
                       'orientations':orientations,'arithmeticTexels':float(bound)})
    return bounds,{'renderer':'Mesa25.2.8 llvmpipeLLVM20.1.2','unitRoundoff':float(unit),
        'rasterBits':8,'rasterUniqueSnap':True,'vertexBounds':positions,'axes':proofs,
        'source':'lp_state_setup.c calc_coef4/emit_tri_coef; actual compiledfs157/159/160 IR float32 interpolation and address',
        'orthogonalGradient':'Each zero cross-gradient subtracts identical shared products or multiplies zero; exact for the two rectilinear fan triangles',
        'filterAddress':'Actual IR multiplies normalizedfloat32 byextent*256, rounds to integer, then subtracts128. No floating half-texel subtraction.',
        'notUsed':'D3D precision rules or reportedmediump10 treatedas23'}


def integer_address_range(coordinate,error):
    return math.ceil((coordinate-error)*256-Q(1,2)),math.floor((coordinate+error)*256+Q(1,2))
