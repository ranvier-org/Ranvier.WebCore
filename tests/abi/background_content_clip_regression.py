"""Require exact #230 content-red masks for twelve fixed controls.
All 54 controls also forbid per-pixel RGBA error increases against reviewed port baselines.
Remaining Chromium differences are reported; baseline generation is a separate command.
"""
import argparse
import base64
import contextlib
import ctypes
import hashlib
import json
from pathlib import Path
import platform
import sys
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
from background_content_clip_capture import capture_samples, FIXTURES, Native, I

BASELINES = FIXTURES / 'background-content-clip-baselines'
FIXED = {'bordered-half-phase', 'negative-origin', 'nested-offset', 'always-composited'}
PROFILES = {'linux-x64': 'linux', 'win-x64': 'win32'}


def unique_entries(entries, expected):
    result = {(entry['name'], entry['scale']): entry for entry in entries}
    assert len(result) == len(entries) == 54 and set(result) == expected, 'Incomplete or duplicate 54-case coverage'
    return result


def decode(entry):
    raw = zlib.decompress(base64.b64decode(entry['rgbaZlibBase64']))
    assert len(raw) == entry['width'] * entry['height'] * 4
    assert hashlib.sha256(raw).hexdigest() == entry['rgbaSha256']
    return raw


def solid_red(raw):
    return bytes(r > 250 and g < 5 and b < 5 and a > 250
                 for r,g,b,a in zip(raw[0::4], raw[1::4], raw[2::4], raw[3::4]))


def pixel_policy(before, after, chrome):
    assert len(before) == len(after) == len(chrome) and len(before) % 4 == 0
    changed = {index // 4 for index, (left,right) in enumerate(zip(before,after)) if left != right}
    worse, lost, improved, delta = [], 0, 0, 0
    for pixel in sorted(changed):
        at = pixel * 4
        previous = sum(abs(a-b) for a,b in zip(before[at:at+4],chrome[at:at+4]))
        current = sum(abs(a-b) for a,b in zip(after[at:at+4],chrome[at:at+4]))
        if current > previous:
            worse.append(pixel)
        lost += previous == 0 and current != 0
        improved += current < previous
        delta += current - previous
    return dict(changedPixels=len(changed), worsePixels=worse, previouslyExactPixelsLost=lost,
                improvedPixels=improved, totalL1ErrorDelta=delta)


def json_identity(value):
    canonical = json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')
    return hashlib.sha256(canonical).hexdigest()


def load_inputs(rid, fixtures=None, baselines=None):
    fixtures = fixtures if fixtures is not None else FIXTURES
    baselines = baselines if baselines is not None else BASELINES
    profile = json.loads((baselines / (rid + '-gpu.json')).read_text(encoding='utf-8'))
    assert profile['rid'] == rid and profile['flavor'] == 'gpu'
    identity = profile['fixtureIdentity']
    assert identity['format'] == 'canonical-json-v1'
    inputs = {}
    for name,path in [('cases',fixtures / 'background-content-clip-cases.json'),
                      ('oracle',fixtures / 'background-content-clip-oracle.json'),
                      ('chrome',baselines / 'chromium-rgba.json')]:
        value = json.loads(path.read_text(encoding='utf-8'))
        assert json_identity(value) == identity['sha256'][name], 'Fixture JSON identity mismatch: ' + name
        inputs[name] = value
    cases = inputs['cases']
    expected = {(test['name'],scale) for scale in cases['scales'] for test in cases['cases']}
    before = unique_entries(profile['results'],expected)
    targets = unique_entries(inputs['chrome']['results'],expected)
    return profile,cases,expected,before,targets


def verify(directory, rid):
    assert rid in PROFILES and sys.platform == PROFILES[rid], 'Unproven native platform/RID'
    assert platform.machine().lower() in ['amd64', 'x86_64'], 'No ARM baseline has been qualified'
    manifest = json.loads((Path(directory).resolve().parents[2] / 'manifest.json').read_text())
    assert (manifest['rid'],manifest['flavor'],manifest['abi']) == (rid,'gpu',60), 'Unproven package profile'
    native = Native(directory)
    assert native.bind('rv_abi_version', I, [])() == 60
    assert native.call('rv_abi_has', [ctypes.c_char_p], b'compositing') == 1, 'Only the GPU profile is qualified'
    profile,cases,expected,before,targets = load_inputs(rid)
    results, seen = [], set()
    with contextlib.closing(capture_samples(directory,cases)) as samples:
        for name,scale,width,height,raw in samples:
            key = name,scale
            assert key in expected and key not in seen
            seen.add(key)
            prior, target = before[key],targets[key]
            assert (width,height) == (prior['width'],prior['height']) == (target['width'],target['height'])
            old, chrome = decode(prior),decode(target)
            policy = pixel_policy(old,raw,chrome)
            mask_difference = sum(a != b for a,b in zip(solid_red(raw),solid_red(chrome)))
            entry = dict(name=name,scale=scale,strictFixedCase=name in FIXED,
                         contentMaskDifference=mask_difference,rgbaMatchesChrome=raw == chrome,
                         rgbaSha256=hashlib.sha256(raw).hexdigest(),**policy)
            if policy['worsePixels'] or (name in FIXED and mask_difference):
                entry['rgbaZlibBase64'] = base64.b64encode(zlib.compress(raw,6)).decode()
            results.append(entry)
    assert seen == expected and len(results) == 54
    fixed = [entry for entry in results if entry['strictFixedCase']]
    assert len(fixed) == 12
    failures = [entry for entry in results if entry['worsePixels'] or (entry['strictFixedCase'] and entry['contentMaskDifference'])]
    return dict(result='FAIL' if failures else 'PASS',rid=rid,flavor='gpu',completeKeys=54,
                strictContentMaskKeys=12,results=results,failures=failures,
                residualContentMaskDifferences=[entry for entry in results if entry['contentMaskDifference']],
                baselineSource=profile['source'],baselineRuntime=profile['runtime'],
                scopes='Strict complete content-red masks for 12 fixed keys; full RGBA pointwise no-regression for 54 controls; no whole-image Chrome-perfection claim')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--rid', choices=sorted(PROFILES), required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.native_directory,args.rid)
    args.report.write_text(json.dumps(result,indent=2)+'\n')
    print(f"{result['result']} content clipping: 54 controls, 12 strict masks, {len(result['residualContentMaskDifferences'])} residual mask differences")
    assert not result['failures'], 'Content clipping mask or pointwise RGBA regression; see report'
