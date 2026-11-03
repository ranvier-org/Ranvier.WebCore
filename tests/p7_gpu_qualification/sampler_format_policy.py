import numpy as np


FILTER_UNITS = 1.0
STORE_UNITS = .6


def ideal_alpha(bits):
    y, x = np.mgrid[:256, :256]/256
    taps = [(bits >> i) & 1 for i in range(4)]
    return (1-x)*(1-y)*taps[0] + x*(1-y)*taps[1] + (1-x)*y*taps[2] + x*y*taps[3]


def evaluate(bits, floating, unorm, white):
    assert all(array.shape == (256, 256, 4) for array in (floating, unorm, white))
    ideal = ideal_alpha(bits)
    sample = floating[:, :, 3].astype(float)
    output = unorm[:, :, 3].astype(float)
    white_output = white[:, :, :3].astype(float)
    float_error = np.abs(sample-ideal)*255
    output_error = np.abs(output-ideal*255)
    white_error = np.max(np.abs(white_output-(255*(1-ideal))[:, :, None]), axis=2)
    valid = np.isfinite(floating).all(axis=2)
    valid &= float_error <= FILTER_UNITS
    valid &= output_error <= FILTER_UNITS+STORE_UNITS
    valid &= white_error <= FILTER_UNITS+STORE_UNITS
    valid &= (floating[:, :, :3] == 0).all(axis=2)
    valid &= (unorm[:, :, :3] == 0).all(axis=2)
    valid &= (white[:, :, 0] == white[:, :, 1]) & (white[:, :, 1] == white[:, :, 2])
    valid &= white[:, :, 3] == 255
    valid &= (sample >= 0) & (sample <= 1)
    if bits in (0, 15):
        expected = 255 if bits == 15 else 0
        valid &= (sample == expected/255) & (output == expected)
        valid &= (white_output == 255-expected).all(axis=2)
    historical = np.abs(output-sample*255)
    historical_white = np.max(np.abs(white_output-(255*(1-sample))[:, :, None]), axis=2)
    return {'patternBits':bits, 'samples':65536, 'policyFailures':int(np.count_nonzero(~valid)),
            'maximumFloatVsIdealUnits':float(np.max(float_error)),
            'maximumUnormVsIdealUnits':float(np.max(output_error)),
            'maximumWhiteVsIdealUnits':float(np.max(white_error)),
            'historicalCrossDrawFailures':int(np.count_nonzero((~np.isfinite(historical)) | (historical > STORE_UNITS))),
            'historicalWhiteCrossDrawFailures':int(np.count_nonzero((~np.isfinite(historical_white)) | (historical_white > STORE_UNITS))),
            'historicalMaximumCrossDrawErrorUnits':float(np.max(historical)),
            'historicalMaximumWhiteCrossDrawErrorUnits':float(np.max(historical_white))}


def store_control(unorm, known_float):
    error = np.abs(unorm.astype(float)-known_float.astype(float)*255)
    valid = np.isfinite(error) & (error <= STORE_UNITS)
    return {'pass':bool(np.all(valid)), 'failures':int(np.count_nonzero(~valid)),
            'maximumErrorUnits':float(np.max(error))}


def negative_controls(bits, floating, unorm, white):
    ideal = ideal_alpha(bits)
    rows = []
    for mutation in ('shift-half-texel', 'erase', 'recolor', 'beyond-bound'):
        changed = unorm.copy()
        if mutation == 'shift-half-texel': changed[:, 128:] = unorm[:, :-128]
        elif mutation == 'erase': changed[0, 0] = 0
        elif mutation == 'recolor': changed[0, 0, 0] = 1
        else: changed[32, 108, 3] = int(np.floor(ideal[32, 108]*255+FILTER_UNITS+STORE_UNITS))+1
        result = evaluate(bits, floating, changed, white)
        rows.append({'mutation':mutation, 'failures':result['policyFailures']})
    return rows


def complete(rows):
    coverage = len(rows) == 16 and {row['patternBits'] for row in rows} == set(range(16))
    samples = sum(row['samples'] for row in rows)
    failures = sum(row['policyFailures'] for row in rows)
    return {'result':'PASS' if coverage and samples == 1048576 and failures == 0 else 'FAIL',
            'completePatterns':coverage, 'samplesPerDestination':samples, 'policyFailures':failures,
            'filterUnits':FILTER_UNITS, 'storeUnits':STORE_UNITS,
            'historicalCrossDrawFailures':sum(row['historicalCrossDrawFailures'] for row in rows),
            'historicalWhiteCrossDrawFailures':sum(row['historicalWhiteCrossDrawFailures'] for row in rows),
            'historicalCrossDrawResult':'FAIL' if any(row['historicalCrossDrawFailures'] or row['historicalWhiteCrossDrawFailures'] for row in rows) else 'PASS',
            'scope':'Existing V3 one-quantum filter + .6 store tested-profile policy; no universal D3D numerical theorem'}
