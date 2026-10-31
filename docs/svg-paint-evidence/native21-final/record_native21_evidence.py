import hashlib, json, re, subprocess
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
e = repo / 'docs/svg-paint-evidence/native21-final'


def h(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def lf(p):
    return hashlib.sha256((repo / p).read_bytes().replace(b'\r\n', b'\n')).hexdigest()


results = json.loads((e / 'batch/results.json').read_text())
counts = {}
for r in results:
    assert r['exitCode'] == 0, r['name']
    log = (e / 'batch' / Path(r['log']).name).read_text(encoding='utf-8', errors='replace')
    m = (re.search(r'PASS[^\n]*?(\d+) assertions', log) or re.search(r'CAPABILITIES_NATIVE_CHECKS=(\d+)', log)
         or re.search(r'SVG_VIEW_SELECTION_ASSERTIONS=(\d+)', log))
    counts[r['name']] = int(m.group(1)) if m else None
head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo, capture_output=True, text=True).stdout.strip()
model = json.loads((repo / 'gen/dom-api.json').read_text())
sources = ['gen/dom.json', 'gen/dom-api.json', 'gen/Ranvier.Dom.fs', 'host/RanvierWebCoreAbi.cpp', 'host/RanvierWebCoreAbi.h',
           'host/RanvierWebCoreDom.cpp', 'host/RanvierWebCoreDom.h', 'host/dom/RanvierDomGlue.cpp', 'host/dom/RanvierDomGlue.h',
           'host/RanvierCapabilityCatalogue.inc', 'host/RanvierSvgViewGlue.cpp', 'tests/abi/NativeDom.fs', 'tests/abi/Native.fs',
           'tests/abi/Program.fs', 'pins.json', 'patches/series', '.github/workflows/build.yml', 'scripts/abi_tests.py'] + [
    'patches/' + n for n in ['0027-svg-view-reset-target.patch', '0028-svg-convolve-structural-cache.patch',
                             '0029-svg-feimage-aspect-cache.patch', '0030-svg-symbol-view-box-instances.patch']]
receipt = json.loads((e / 'runtime-receipt.json').read_text())
evidence = {
    'status': 'private-win-x64-producer-verified (Native21/ABI29, unpublished)',
    'nativeVersion': '0.1.0-preview.21', 'abiVersion': 29, 'sourceHead': head, 'buildHead': receipt['buildHead'],
    'buildToHeadDelta': 'tests/evidence only: forward merge of Native20 4e7d904 (Native19 1d97ac4 svg_surfaces Linux quantum fix) and this evidence',
    'integrationParent': {'native20': '4e7d904525a1434db95defb0aba3511b175d1d68', 'native19': '1d97ac4f006ad44e4e13cebfd6351ce10289a7cc'},
    'allocation': 'native21-allocation/allocation-absence.json',
    'canonical': {'interfaces': len(model['interfaces']), 'functions': len(model['functions']), 'roots': 50, 'dictionaries': 22, 'stubs': 0,
                  'baselineNative19': {'interfaces': 205, 'functions': 2234}, 'newFunctions': len(model['functions']) - 2234},
    'counts': {'rawAssertionsByProbe': counts, 'rawAssertionTotal': sum(v for v in counts.values() if v), 'runs': len(results),
               'teardownCases': len(json.loads((e / 'batch/teardown-probes.json').read_text()))},
    'runtime': receipt['buildRuntimeSha256'],
    'compiledEngineScope': ['UnifiedSource-svg-4 (0028)', 'UnifiedSource-svg-5 (0029)', 'UnifiedSource-svg-13 (0024/0025/0027)',
                            'UnifiedSource-svg-14 (0030)', 'RanvierDomGlue', 'RanvierSvgViewGlue',
                            'four host translation units with RV_CAP flags; the other 50 WebCore replacement objects borrowed read-only from frozen Native19'],
    'sourceHashesLF': {p: lf(p) for p in sources},
    'groups': {'S08': '#85', 'S09': '#86', 'S10': '#87', 'S11': '#88'},
    'focusedReceipts': ['s08-evidence.json', 's09-green/receipt.json', 's10-green/receipt.json', 's11-green/receipt.json',
                        'symbol-viewbox-red', 'symbol-viewbox-green', 'convolve-red', 'convolve-green', 'feimage-red', 's10-red', 's11-red'],
    'qualifications': [
        'Chromium sweep 274 Available / 2 NotExposed: SVGFEGaussianBlurElement.edgeMode and SVGMarkerElement.orient are native-only',
        'SVGImageElement.decode has no native binding; H05 (#110) owned completion/decode remains a required S11 blocker; no Promise stub',
        'Both engines keep cached mask paint after a style-only mask-type change until child geometry changes',
        'Zero specularConstant: native transparent-over-white, Chromium opaque black',
        'Absent pattern viewBox needs authored initialization before typed edits affect paint (both engines)',
        'Native paints the broken-image placeholder for network errors and undecodable bytes where Chromium paints nothing',
        'SVGStringList.clear leaves systemLanguage="" natively; Chromium removes the attribute',
        'svg_filters assertion count varies 8941/8943 with image readiness polling; both are passing runs',
        'S11 resource proof uses the raw rv_host_set_resource_handler route; it does not deliver the H05 shared facade',
        'Private win-x64 only; official multi-RID CI/packages, shared consumers and group acceptance remain separate',
        'Lease deviation: one 3-case symbol diagnostic re-run for the GREEN log ran just after a test lease release'],
    'repositoryGates': {p.stem: p.read_text(encoding='utf-8', errors='replace').strip().splitlines()[-1] for p in sorted((e / 'gates').glob('*.log'))},
    'files': {p.relative_to(e).as_posix(): h(p) for p in sorted(e.rglob('*')) if p.is_file() and p.name != 'final-evidence.json'},
}
(e / 'final-evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
print(evidence['canonical'], evidence['counts']['rawAssertionTotal'], evidence['counts']['runs'], evidence['counts']['teardownCases'])
print('final-evidence.json', h(e / 'final-evidence.json'))
