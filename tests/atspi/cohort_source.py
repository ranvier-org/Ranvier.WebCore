"""Check the final hand-written ABI union and optionally record clean source identity; never qualify a binary."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
TAIL = ['rv_host_ime_surrounding', 'rv_host_ime_delete_surrounding', 'rv_ax_text_style_run']


def verify_abi(baseline, current, abi):
    if abi != 63:
        raise ValueError('The final union requires ABI63.')
    if len(current) != 347:
        raise ValueError('The final union requires exactly 347 hand-written ABI declarations.')
    if len(baseline) != 344 or current[:344] != baseline:
        raise ValueError('The original 344 signatures and order must remain unchanged.')
    if [row[0] for row in current[344:]] != TAIL:
        raise ValueError('The final tail order must be surrounding 344, delete 345, style 346.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref', required=True)
    parser.add_argument('--manifest', type=Path)
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{40}', args.baseline_ref):
        raise ValueError('Use an exact baseline commit, not a moving branch name.')
    header_path = 'host/RanvierWebCoreAbi.h'
    generator_path = 'tests/abi/generate_native.py'
    spec = importlib.util.spec_from_file_location('generate_native', ROOT / generator_path)
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    baseline = subprocess.check_output(['git', 'show', args.baseline_ref + ':' + header_path], cwd=ROOT, text=True)
    header = (ROOT / header_path).read_text(encoding='utf-8')
    declarations = generator.declarations(header)
    source = (ROOT / 'host/RanvierWebCoreAbi.cpp').read_text(encoding='utf-8')
    abi = int(re.search(r'rv_abi_version\(void\)\s*\{\s*return\s+(\d+);', source).group(1))
    verify_abi(generator.declarations(baseline), declarations, abi)
    result = dict(scope='source declaration contract only; no runtime qualification', abi=abi, functions=len(declarations),
        baseline=args.baseline_ref, tail=[[index, row[0]] for index, row in enumerate(declarations[344:], 344)])
    if args.manifest:
        if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
            raise ValueError('Commit the exact final generated/source tree before recording its manifest.')
        result.update(sourceCommit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            headerSha256NormalizedLF=hashlib.sha256(header.encode()).hexdigest(),
            generatorSha256NormalizedLF=hashlib.sha256((ROOT / generator_path).read_text(encoding='utf-8').encode()).hexdigest(),
            declarations=[dict(index=index, name=name, returns=returns, parameters=params)
                for index, (name, returns, params) in enumerate(declarations)])
        with args.manifest.open('x', encoding='utf-8') as output:
            json.dump(result, output, indent=2)
    print(json.dumps({key: value for key, value in result.items() if key != 'declarations'}))


if __name__ == '__main__':
    main()
