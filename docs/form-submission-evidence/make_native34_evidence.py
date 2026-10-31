"""Writes docs/form-submission-evidence/final-evidence.json for the D14 Native34/ABI42 proof from the frozen runtime,
the full batch, the repeat log, the characterSet measurement, the RED and GREEN unload records and the Native33
baseline batch, and copies the records it cites into this directory."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

repo = Path('C:/wk/native-formsubmit')
here = repo / 'docs/form-submission-evidence'
artifacts = repo / 'artifacts'
candidate = artifacts / 'native34-candidate-10'
freeze = artifacts / 'native34-frozen-2'
batch = artifacts / 'native34-batch-2'
baseline = Path('C:/wk/native-url/artifacts/native33-batch-2')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(*arguments, cwd=repo):
    return subprocess.run(['git', *arguments], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


for name, source in [('red-unload-candidate4.json', artifacts / 'd14-unload-red-candidate4.json'),
                     ('green-unload-candidate8.json', artifacts / 'd14-unload-green-candidate8.json'),
                     ('unload_red.py', artifacts / 'unload_red.py'),
                     ('build_native34_candidate.py', artifacts / 'build_native34_candidate_0037b.py'),
                     ('source-patches.json', candidate / 'source-patches.json'),
                     ('runtime-receipt.json', freeze / 'runtime-receipt.json'),
                     ('batch-results.json', batch / 'results.json'),
                     ('form-submission-report.json', artifacts / 'd14-final-report.json')]:
    shutil.copyfile(source, here / name)

records = json.loads((batch / 'results.json').read_text())
before = {item['name']: item for item in json.loads((baseline / 'results.json').read_text())}


def normalized(text):
    text = re.sub(r'\d+(\.\d+)?\s*(ms|s)\b', 'T', text)
    text = re.sub(r'"[A-Za-z]*Milliseconds":[\d.]+', '"Milliseconds":T', text)
    text = re.sub(r'[0-9a-f]{40,}', 'HASH', text)
    return re.sub(r'[A-Za-z]:[\\/][^\s"]*', 'PATH', text)


changes = []
for item in records:
    old = before.get(item['name'])
    if old is None:
        changes.append({'probe': item['name'], 'change': 'new', 'assertions': item.get('assertions')})
        continue
    same_count = old.get('assertions') == item.get('assertions') or old.get('assertions') is None
    same_log = normalized(Path(old['log']).read_text(errors='replace')) == normalized(Path(item['log']).read_text(errors='replace'))
    if not (same_count and same_log):
        changes.append({'probe': item['name'], 'assertions': [old.get('assertions'), item.get('assertions')],
                        'logLines': [line for line in normalized(Path(item['log']).read_text(errors='replace')).splitlines()
                                     if line not in normalized(Path(old['log']).read_text(errors='replace')).splitlines()][:3]})

catalogue_base = git('show', '3c7e8d4:host/RanvierCapabilityCatalogue.inc')
catalogue_head = (repo / 'host/RanvierCapabilityCatalogue.inc').read_text()
names = lambda text: re.findall(r'^    "([^"]+)",$', text, re.M)
added = [name for name in names(catalogue_head) if name not in names(catalogue_base)]
repeats = (here / 'form-submission-repeats-native34.log').read_text()
sweep = subprocess.run(['git', 'grep', '-n', '-E', r'ABI = 4[0-9]|== 4[0-9]\b|version 4[0-9]|return 4[0-9];|ABI version 4[0-9]', '--',
                        'host/RanvierWebCoreAbi.cpp', 'host/RanvierWebCoreAbi.h', 'tests/abi'], cwd=repo, capture_output=True, text=True).stdout.splitlines()
evidence = {
    'schemaVersion': 1,
    'group': 'D14 form submission',
    'status': 'green (private Windows x64 slim; not accepted)',
    'issue': 'https://github.com/ranvier-org/Ranvier.WebCore/issues/23',
    'sourceHead': git('rev-parse', 'HEAD'),
    'nativeVersion': json.loads((repo / 'pins.json').read_text())['package']['version'],
    'abi': 42,
    'stackedOn': 'H13 3c7e8d4 (Native33/ABI41, U+0000 fix), G09 fb87eb0 / a215ef9, H11 6610b57',
    'sourcePatches': {'applied': ['0035', '0037'], 'unused': ['0036'], 'receipt': 'source-patches.json',
                      'recompiledUnits': len(json.loads((candidate / 'source-patches.json').read_text())['recompiledUnits'])},
    'runtime': {'receipt': 'runtime-receipt.json', 'sha256': json.loads((candidate / 'runtime-sha256.json').read_text())},
    'red': {'record': 'red-unload-candidate4.json',
            'finding': 'pagehide and unload fire on the first submission, and later submit and formdata events reach no listener'},
    'green': {'record': 'green-unload-candidate8.json', 'finding': 'no unload events; both forms deliver their events'},
    'batch': {'results': 'batch-results.json', 'rawAssertions': sum(item.get('assertions') or 0 for item in records),
              'teardownProbes': 84, 'probes': len(records), 'allExit0': all(item['exitCode'] == 0 for item in records),
              'formSubmission': next(item.get('assertions') for item in records if item['name'] == 'form_submission')},
    'baselineComparison': {'baseline': str(baseline), 'changes': changes,
                           'catalogue': {'description': 'catalogue regenerated: +' + str(len(added)) + ' entries', 'entries': added}},
    'characterSet': json.loads((here / 'character-set.json').read_text()),
    'repeats': {'log': 'form-submission-repeats-native34.log', 'runs': repeats.count('run '),
                'pass': len(re.findall(r'^PASS form_submission: 418 assertions', repeats, re.M)), 'fail': repeats.count('FAIL')},
    'qualified': json.loads((repo / 'tests/fixtures/form-submission-qualified.json').read_text())['differences'],
    'abiConstantSweep': sweep,
    'measuredVariation': {'record': 'teardown-image-missing-file-reruns.json',
                          'finding': 'the batch teardown run read references 0 and 1 after one cycle for "image with a missing file '
                                     'source"; six reruns of the same driver read -1 and -1, and every run reads -1 after collection'},
    'allocationAbsence': {'record': 'allocation-absence.json', 'sha256': digest(here / 'allocation-absence.json')},
}
(here / 'final-evidence.json').write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
print('changes', [change['probe'] for change in changes], 'catalogue +', len(added), 'repeats', evidence['repeats'])
