"""Separate float32 interpolation/address and fixed-conversion error budgets."""
from fractions import Fraction
import math

import numpy as np

GETTER_ORDER = [f'm{row}{column}' for column in range(1, 5) for row in range(1, 5)]


def gamma(count, unit):
    return count * unit / (1 - count * unit)


def address_budget(extent, precision_bits):
    unit = Fraction(1, 2 ** (precision_bits + 1))
    cross = gamma(3, unit)
    division = gamma(3, unit)
    weight = (cross + unit + division * (1 + cross)) / (1 - unit)
    attribute = 2 * weight + unit * (1 + 2 * weight)
    scale = unit * extent * (1 + attribute)
    half_offset = unit * (extent * (1 + attribute) * (1 + unit) + Fraction(1, 2))
    total = extent * attribute + scale + half_offset
    return {'unit': unit, 'crossNumeratorOverArea': cross, 'divisionRelative': division,
            'barycentricWeightAbsolute': weight, 'normalizedAttributeAbsolute': attribute,
            'scaledAttributeTexels': extent * attribute, 'samplerScaleFloatTexels': scale,
            'halfTexelSubtractFloatTexels': half_offset, 'arithmeticAddressTexels': total}


def coordinate_envelope(coordinate, arithmetic_error, minimum_bits=8, enumerated_bits=32):
    lower, upper = coordinate - arithmetic_error, coordinate + arithmetic_error
    candidates_lower, candidates_upper = [], []
    for bits in range(minimum_bits, enumerated_bits + 1):
        scale = 2**bits
        first = math.ceil(lower * scale - Fraction(3, 5))
        last = math.floor(upper * scale + Fraction(3, 5))
        if first <= last:
            candidates_lower.append(Fraction(first, scale))
            candidates_upper.append(Fraction(last, scale))
    tail_error = Fraction(3, 5 * 2**(enumerated_bits + 1))
    candidates_lower.append(lower - tail_error)
    candidates_upper.append(upper + tail_error)
    exact_lower, exact_upper = min(candidates_lower), max(candidates_upper)
    low, high = float(exact_lower), float(exact_upper)
    if Fraction.from_float(low) > exact_lower:
        low = math.nextafter(low, -math.inf)
    if Fraction.from_float(high) < exact_upper:
        high = math.nextafter(high, math.inf)
    return low, high


def projection_bound(coordinate, viewport, precision_bits):
    unit = Fraction(1, 2 ** (precision_bits + 1))
    position = Fraction.from_float(float(coordinate))
    coefficient = Fraction.from_float(float(np.float32(2 / viewport)))
    product = coefficient * position
    product_error = unit * abs(product)
    projected = product - 1
    projection_error = product_error + unit * (abs(projected) + product_error)
    half = Fraction(viewport, 2)
    screen_center = half * projected + half
    viewport_multiply_error = unit * half * (abs(projected) + projection_error)
    before_add_error = half * projection_error + viewport_multiply_error
    viewport_add_error = unit * (abs(screen_center) + before_add_error)
    result = abs(screen_center - position) + before_add_error + viewport_add_error
    return {'coordinate': float(position), 'viewport': viewport, 'projectionCoefficientFloat32': float(coefficient),
            'coefficientCenterScreenError': float(abs(screen_center - position)),
            'projectionArithmeticError': float(projection_error), 'viewportMultiplyError': float(viewport_multiply_error),
            'viewportAddError': float(viewport_add_error), 'totalScreenError': float(result),
            'exactTotalScreenErrorFraction': str(result)}


def uniform_cast_proof(raw_scale, extent):
    product = Fraction.from_float(raw_scale) * Fraction.from_float(extent)
    value = np.float32(extent)
    assert float(value) == extent
    previous = float(np.nextafter(value, np.float32(-math.inf)))
    following = float(np.nextafter(value, np.float32(math.inf)))
    half_bin = min(Fraction.from_float(extent) - Fraction.from_float(previous),
                   Fraction.from_float(following) - Fraction.from_float(extent)) / 2
    double_product_error = abs(product) / 2**53
    displacement = abs(product - Fraction.from_float(extent)) + double_product_error
    assert displacement < half_bin, 'model-view uniform does not round to the exact derived size'
    return {'rawScale': raw_scale, 'extent': extent, 'maximumDoubleProductDisplacement': float(displacement),
            'float32HalfRoundingBin': float(half_bin), 'uniformExtentExact': True}


def complete_budget(inputs, record, quad_origin, quad_size, texture_size):
    precisions = inputs['shaderPrecision']['shaderPrecision']
    bits = min(value['fractionBits'] for shader in precisions.values() for value in shader.values())
    assert bits == 23
    assert inputs['matrixGetterOrder'] == GETTER_ORDER
    matrix = dict(zip(GETTER_ORDER, record['promotedTexture']['matrix']))
    casts = [uniform_cast_proof(matrix['m11'], quad_size[0]), uniform_cast_proof(matrix['m22'], quad_size[1])]
    viewport = [int(record['viewportCss'][0] * record['scale']), int(record['viewportCss'][1] * record['scale'])]
    raster = [projection_bound(position, viewport[axis], bits)
              for axis in range(2) for position in [quad_origin[axis], quad_origin[axis] + quad_size[axis]]]
    for index, row in enumerate(raster):
        mirror_error = Fraction(viewport[index // 2], 2 ** (bits + 1))
        bound = Fraction(row['exactTotalScreenErrorFraction']) + mirror_error
        row['mirrorAdditionalViewportAddError'] = float(mirror_error)
        row['mirrorSafeTotalScreenError'] = float(bound)
        row['exactTotalScreenErrorFraction'] = str(bound)
    exclusion_limit = Fraction(2, 5) / 256
    assert all(Fraction(row['exactTotalScreenErrorFraction']) < exclusion_limit for row in raster)
    axes = [address_budget(extent, bits) for extent in texture_size]
    serial = [{key: float(value) for key, value in axis.items()} for axis in axes]
    proof = {'fractionBits': bits, 'unitRoundoff': float(Fraction(1, 2**(bits+1))),
             'matrixGetterOrder': GETTER_ORDER, 'translationGetterIndices': {'m41': 3, 'm42': 7},
             'uniformCastProof': casts, 'rasterProjectionViewport': raster,
             'rasterUniqueSnapThresholdPixels': float(exclusion_limit), 'rasterSnapExact': True,
             'separateArithmeticBudget': serial, 'fixedConversionTexels': 0.6 / 256,
             'totalCoordinateRadiusTexels': [float(axis['arithmeticAddressTexels']) + 0.6 / 256 for axis in axes],
             'unormConversionUnits': 0.6,
             'fixedLatticeComposition': {'minimumFractionBits':8,'enumeratedThroughBits':32,
                 'higherPrecisionTailErrorTexels':float(Fraction(3,5*2**33)),
                 'rule':'For eachk>=8, integerj must satisfy ceil((ideal-B_arith)*2^k-0.6)<=j<=floor((ideal+B_arith)*2^k+0.6). Union exactlattices, not a blind continuous .6/256 expansion.'},
             'rules': {
                 'vertexAttributes': 'Unitrect andidentitypatternproduceexact0/1; sparsemodelviewuniforms/verticesexactaftercheckedfloatcast.',
                 'projection': 'One coefficient cast plusmultiply/add projection andmultiply/add viewport; rational forwarderror isbelow0.4/256, so0.6LSB fixedposition conversioncannotchooseneighbor.',
                 'interpolation': 'Positivearea rectangulartriangles; exactfixedgrid coordinate differences. Crossnumerator abs<=gamma3*A; area relative<=u; reciprocal+multiply relative<=gamma3. Weight absbound=(gamma3+u+gamma3*(1+gamma3))/(1-u). Sumtwo0/1weightedattributes adds2weightError+u*(1+2weightError).',
                 'samplerAddress': 'Multiply normalizedattribute bydimension andsubtracthalftexel with separate float32 errors; add fixedconversionerror onlyafterthese.',
                 'precisionPrimary': 'D3D11.3 sections3.1.3.1-2,15.16,15.16.2,3.2.4.1,7.18.16.1. No arbitrary operationcount or doublecounted fixedpoint bound.'}}
    return [axis['arithmeticAddressTexels'] for axis in axes], proof
