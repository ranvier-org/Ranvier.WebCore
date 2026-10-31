"""Writes docs/event-detail-evidence/final-evidence.json for the I08 Native39/ABI47 proof from a frozen candidate, its full
batch, the event_details repeat logs and the previous lane's batch, and copies the records it cites into this directory.
usage: make_native39_evidence.py <native39-candidate-N> <baseline batch dir> <baseline catalogue commit>"""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

repo = Path('C:/wk/native-evdetail')
here = repo / 'docs/event-detail-evidence'
artifacts = repo / 'artifacts'
name = sys.argv[1]
candidate = artifacts / name
freeze = artifacts / (name + '-frozen')
batch = artifacts / (name + '-batch')
baseline = Path(sys.argv[2])
baseline_commit = sys.argv[3]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(*arguments, cwd=repo):
    return subprocess.run(['git', *arguments], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


for target, source in [('build_native39_candidate.py', artifacts / 'build_native39_candidate.py'),
                       ('source-patches.json', candidate / 'source-patches.json'),
                       ('runtime-receipt.json', freeze / 'runtime-receipt.json'),
                       ('batch-results.json', batch / 'results.json'),
                       ('event-details-report.json', artifacts / (name + '-event-details.json')),
                       ('event-details-repeats.log', artifacts / (name + '-event-details-30.log'))]:
    shutil.copyfile(source, here / target)

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

catalogue_base = git('show', baseline_commit + ':host/RanvierCapabilityCatalogue.inc')
catalogue_head = (repo / 'host/RanvierCapabilityCatalogue.inc').read_text()
names = lambda text: re.findall(r'^    "([^"]+)",$', text, re.M)
added = [entry for entry in names(catalogue_head) if entry not in names(catalogue_base)]
repeats = (here / 'event-details-repeats.log').read_text()
sweep = subprocess.run(['git', 'grep', '-n', '-E', r'ABI = 4[0-9]|== 4[0-9]\b|version 4[0-9]|return 4[0-9];|ABI version 4[0-9]', '--',
                        'host/RanvierWebCoreAbi.cpp', 'host/RanvierWebCoreAbi.h', 'tests/abi'], cwd=repo, capture_output=True, text=True).stdout.splitlines()
teardown = json.loads((batch / 'teardown/teardown-probes.json').read_text())
cases = json.loads((repo / 'tests/fixtures/event-details-cases.json').read_text())
oracle = json.loads((repo / 'tests/fixtures/event-details-oracle.json').read_text())
evidence = {
    'schemaVersion': 1,
    'group': 'I08 event detail adapters',
    'status': 'green (private Windows x64 slim; not accepted)',
    'issue': 'https://github.com/ranvier-org/Ranvier.WebCore/issues/105',
    'sourceHead': git('rev-parse', 'HEAD'),
    'nativeVersion': json.loads((repo / 'pins.json').read_text())['package']['version'],
    'abi': 47,
    'sourcePatches': {'receipt': 'source-patches.json', 'patches': sorted(json.loads((candidate / 'source-patches.json').read_text())['patches']),
                      'recompiledHere': 'host/dom/RanvierDomGlue.cpp only; every other WebCore object is the parent candidate\'s'},
    'runtime': {'receipt': 'runtime-receipt.json', 'sha256': json.loads((candidate / 'runtime-sha256.json').read_text())},
    'chromium': oracle['browser'],
    'batch': {'results': 'batch-results.json', 'rawAssertions': sum(item.get('assertions') or 0 for item in records),
              'teardownProbes': len(teardown), 'probes': len(records), 'allExit0': all(item['exitCode'] == 0 for item in records),
              'eventDetails': next(item.get('assertions') for item in records if item['name'] == 'event_details')},
    'baselineComparison': {'baseline': str(baseline), 'changes': changes,
                           'changeNotes': {'capabilities': 'more native checks for the 23 added catalogue entries',
                                           'frames': 'timing fields (servedMilliseconds, animationMilliseconds, fullMs) and process ids only; every other field is identical',
                                           'teardown': 'two added records: div and removed div, error event released after host destroy',
                                           'event_details': 'new probe'},
                           'catalogue': {'description': 'catalogue regenerated: +' + str(len(added)) + ' entries', 'entries': added}},
    'repeats': {'log': 'event-details-repeats.log', 'runs': len(repeats.splitlines()),
                'lines': {line: repeats.splitlines().count(line) for line in sorted(set(repeats.splitlines()))}},
    'assertionCount': '391 is the fixed count. An earlier 30x rehearsal read 404/405/406 (9/15/6 runs): it counted one expect() per run-loop iteration in the dispatched-step '
                      'drain; that drain is now an uncounted 10 s hang guard. No case was removed or merged.',
    'oracleDeterminism': {'log': 'oracle-repeats.log', 'finding': '30 consecutive recordings of tests/fixtures/event-details-oracle.json were byte-identical'}, 'teardown': 'teardown-probes.json',
    'qualified': json.loads((repo / 'tests/fixtures/event-details-qualified.json').read_text())['differences'],
    'deferred': cases['deferred'],
    'abiConstantSweep': sweep,
    'allocationAbsence': {'record': 'allocation-absence.json', 'sha256': digest(here / 'allocation-absence.json')},
    'teardownImageSettled': {'record': '../form-submission-evidence/teardown-image-settled.json', 'commit': '02d97a4'},
}
(here / 'final-evidence.json').write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
print('changes', [change['probe'] for change in changes], 'catalogue +', len(added), 'repeats', evidence['repeats']['runs'])
