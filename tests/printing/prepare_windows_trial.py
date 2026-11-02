"""Create a reviewable private-print compile/link recipe without invoking tools."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def normalize(value):
    return value.replace('\\', '/').casefold()


def main(args):
    source = args.source_root.resolve()
    build = args.build_root.resolve()
    work = args.output.resolve()
    work.mkdir(parents=True, exist_ok=False)
    baseline = json.loads(args.producer_receipt.read_text())
    host = json.loads(args.host_receipt.read_text())
    assert baseline['producerSource'] == '16ae55818db049bf4b70079a2e91e6895e8b5b40'
    assert host['source'] == '36d2c786ce2e4d36e02595ad767372e304798e00'
    assert len(host['officialDependencyHashes']) == 26
    source_head = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    subprocess.run(['git', '-C', str(source), 'merge-base', '--is-ancestor', host['source'], source_head], check=True)
    archive = Path(host['dllZip']['path'])
    assert sha(archive) == host['dllZip']['sha256']
    old_root = 'C:/wk/project2/mutation157/production-trial-1/source'

    def compile_command(input_path, name):
        command = baseline['command'].copy()
        for i, argument in enumerate(command):
            if normalize(old_root) in normalize(argument):
                argument = argument.replace(old_root.replace('/', '\\'), str(source)).replace(old_root, str(source))
            if argument.startswith('/Fo'):
                argument = '/Fo' + str(work / (name + '.obj'))
            if argument.startswith('/Fd'):
                argument = '/Fd' + str(work / (name + '.pdb'))
            command[i] = argument
        assert command[-2] == '--'
        command[-1] = str(input_path)
        assert sum(x.startswith('/Fo') for x in command) == 1
        assert sum(x.startswith('/Fd') for x in command) == 1
        assert '/showIncludes' in command
        assert not any(normalize(old_root) in normalize(x) for x in command)
        for argument in command:
            if argument.startswith(('/Fo', '/Fd')):
                assert Path(argument[3:]).is_relative_to(work)
        return command

    commands = {
        'print177': compile_command(source / 'tests/printing/print177_probe.cpp', 'print177'),
        'mutation36': compile_command(source / 'host/RanvierMutationGlue.cpp', 'mutation36'),
    }
    link = baseline['originalLinkCommand'].copy()
    original_inputs = list(link)
    outputs = {'/out:': work / 'native/WebCore.dll', '/implib:': work / 'WebCore.lib', '/pdb:': work / 'WebCore.pdb'}
    output_counts = dict.fromkeys(outputs, 0)
    for i, argument in enumerate(link):
        for prefix, destination in outputs.items():
            if argument.casefold().startswith(prefix):
                link[i] = prefix + str(destination)
                output_counts[prefix] += 1
        assert not argument.casefold().startswith(('/ilk:', '/pdbstripped:', '/map:', '/manifestfile:'))
    assert all(count == 1 for count in output_counts.values())
    for name in commands:
        path = str(work / (name + '.obj'))
        assert not any(normalize(x) == normalize(path) for x in original_inputs)
        link.append(path)
    assert len(link) == len(original_inputs) + 2
    assert not any('RanvierMutationGlue' in x for x in original_inputs)
    response = work / 'WebCore-link.rsp'
    response.write_text('\n'.join(subprocess.list2cmdline([x]) for x in link[1:]) + '\n')
    historical = json.loads(args.host_transaction_receipt.read_text())['protectedAfter']
    protected = {}
    retired = []
    for path, digest in historical.items():
        candidate = Path(path)
        if normalize(old_root) in normalize(path):
            candidate = source / path.replace('\\', '/').split('/source/', 1)[1]
        if candidate.is_file():
            protected[str(candidate)] = {'historicalPath': path, 'historicalSha256': digest}
        else:
            retired.append(path)
    assert len(historical) == 3316
    assert len(retired) == 2 and all(normalize(x).endswith(('/webcore.lib', '/native/webcore.dll')) for x in retired)
    extra = [source / 'tests/printing/print177_probe.h', source / 'tests/printing/print177_probe.cpp',
             source / 'tests/printing/print177_probe.py', source / 'host/RanvierMutationGlue.cpp',
             build / 'CMakeCache.txt', build / 'build.ninja',
             Path('C:/wk/src/Source/WebCore/page/PrintContext.h'),
             Path('C:/wk/src/Source/WebCore/page/PrintContext.cpp')]
    for directory in ['C:/wk/src/Source/ThirdParty/skia/include', 'C:/wk/src/Source/WebCore/platform/graphics/skia']:
        extra += list(Path(directory).rglob('*.h'))
    for path in extra:
        assert path.is_file(), path
        protected.setdefault(str(path), {'historicalPath': None, 'historicalSha256': None})
    recipe = {
        'scope': 'Unexecuted private test-only synchronous print prototype; no public ABI or production lifecycle claim',
        'source': source_head, 'hostSource': host['source'], 'producerSource': baseline['producerSource'],
        'workingDirectory': str(build), 'commands': commands, 'originalLinkCommand': original_inputs,
        'privateLinkCommand': link, 'privateLinkResponse': str(response),
        'originalObjectReplacements': 0, 'printObjectAppendCount': 1, 'mutation36ObjectAppendCount': 1,
        'hostRelinked': False, 'hostDllFromVerifiedArchive': host['dllZip'],
        'hostDllSha256': host['privateHostSha256'],
        'officialPayloadHashes': host['officialDependencyHashes'],
        'officialPackageSha256': '914ebc2f6c9c907d7f4e7b6481271dd92079effdc43d95fd2ca523e43f0980a0',
        'protectedHistoricalCount': len(historical), 'protectedInputs': protected,
        'retiredPrivateProofInputsNotConsumed': retired,
        'preconditions': [
            'Root review and explicit read-only producer/PCH window before compile or link.',
            'Acquire and inspect own atomic native slot grant, maximum three; j1 compilation.',
            'Hash every actual protected producer input and all 26 official payloads before tools and after completion.',
            'Original 3316 receipt includes retired private image/import-library paths; these are not current producer inputs. Exact 200 private source paths map to owned immutable36-based checkout; record source hashes honestly.',
            'Only /Fo and /Fd outputs plus redirected DLL/import library/PDB/response are writable in owned work directory.',
            'Capture /showIncludes; any newly discovered uncaptured dependency stops before link and requires a hash-complete corrective window.',
            'Copy official payloads privately; use verified36 host DLL and new private WebCore only. Do not relabel either as official P4.',
            'Final runtime test is one owner turn without pumping, script reentrancy or OS dialog during PrintContext lifetime.',
        ],
    }
    (work / 'recipe.json').write_text(json.dumps(recipe, indent=2) + '\n')
    print(json.dumps({'recipe': str(work / 'recipe.json'), 'sha256': sha(work / 'recipe.json'),
                      'protectedCandidates': len(protected), 'nativeToolsInvoked': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ['source-root', 'build-root', 'producer-receipt', 'host-receipt', 'host-transaction-receipt', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    main(parser.parse_args())
