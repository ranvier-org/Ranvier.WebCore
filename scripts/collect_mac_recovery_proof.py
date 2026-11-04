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
        if source.is_symlink() or not source.is_dir() or not source.resolve(strict=True).is_relative_to(work):
            raise ValueError('Require real owned gate output directories: ' + str(source))
        aliases = []
        for path in source.rglob('*'):
            if not path.is_symlink():
                continue
            try:
                target = path.resolve(strict=True)
            except (OSError, RuntimeError) as error:
                raise ValueError('Broken or cyclic gate output alias: ' + str(path)) from error
            if not target.is_file() or not target.is_relative_to(source.resolve(strict=True)):
                raise ValueError('External or directory gate output alias: ' + str(path) + ' -> ' + str(target))
            aliases.append(dict(path=path.relative_to(source).as_posix(), target=target.relative_to(source).as_posix(),
                                sha256=hashlib.sha256(target.read_bytes()).hexdigest(), copiedAs='regular-file-bytes'))
        row['fileAliases'] = aliases
        destination = evidence / row['destination']
        destination.parent.mkdir(exist_ok=True)
        shutil.copytree(source, destination)
        for alias in aliases:
            copied = destination / alias['path']
            if (copied.is_symlink() or hashlib.sha256(copied.read_bytes()).hexdigest() != alias['sha256']
                    or hashlib.sha256((source / alias['target']).read_bytes()).hexdigest() != alias['sha256']):
                raise ValueError('Gate output alias changed while copying: ' + alias['path'])
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
