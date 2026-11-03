"""Seal recovery evidence under one explicit artifact root."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def collect(evidence, work, flavor):
    evidence, work = evidence.resolve(), work.resolve()
    if flavor not in ['slim', 'gpu'] or evidence.is_relative_to(work) or work.is_relative_to(evidence):
        raise ValueError('Require separate owned producer and evidence roots and a known flavor')
    evidence.mkdir(parents=True, exist_ok=True)
    seal = evidence / 'artifact-members.json'
    if seal.exists():
        raise ValueError('The immutable proof root is already sealed')
    sources = []
    for label, source in [('probe-logs', work / 'probe-logs'),
                          ('mac-gpu-public-qualification', work / 'mac-gpu-public-qualification'),
                          ('symbols', work / 'out' / flavor / 'symbols')]:
        row = dict(source=str(source), destination='product-gates/' + label, present=source.exists())
        sources.append(row)
        if not row['present']:
            continue
        if source.is_symlink() or not source.is_dir() or any(path.is_symlink() for path in source.rglob('*')):
            raise ValueError('Require real owned gate output directories without external links')
        destination = evidence / row['destination']
        destination.parent.mkdir(exist_ok=True)
        shutil.copytree(source, destination)
    members = {}
    for path in sorted(evidence.rglob('*')):
        if path.is_symlink():
            raise ValueError('Do not follow links outside the sealed evidence root')
        if path.is_file():
            with path.open('rb') as stream:
                members[path.relative_to(evidence).as_posix()] = hashlib.file_digest(stream, 'sha256').hexdigest()
    result = dict(schemaVersion=1, layout='mac-recovery-proof-root-v1', sources=sources, members=members)
    seal.write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--flavor', choices=['slim', 'gpu'], required=True)
    args = parser.parse_args()
    result = collect(args.evidence, args.work, args.flavor)
    print(json.dumps(dict(layout=result['layout'], members=len(result['members']))))


if __name__ == '__main__':
    main()
