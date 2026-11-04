import argparse
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(output, sdk, reference):
    if output.exists():
        raise ValueError('Require a fresh fixture output')
    compiler = sdk / 'Roslyn/bincore/csc.dll'
    references = sorted(reference.glob('*.dll'))
    if not compiler.is_file() or not references or reference.name != 'net10.0':
        raise ValueError('Require the installed SDK compiler and net10.0 reference assemblies')
    output.mkdir(parents=True)
    record = dict(compiler=dict(path=str(compiler), sha256=sha(compiler)),
                  references={str(path): sha(path) for path in references}, commands=[], fixtures={})

    def compile_source(name, sources, executable=False):
        directory = output / name
        directory.mkdir()
        assembly = directory / ('InteropMetadata.dll' if executable else 'Fixture.dll')
        response = directory / 'compiler.rsp'
        arguments = ['/nostdlib+', '/nologo', '/warnaserror+', '/nullable:enable', '/langversion:latest',
                     '/target:exe' if executable else '/target:library', '/out:' + str(assembly),
                     *('/reference:' + str(path) for path in references), *map(str, sources)]
        response.write_text('\n'.join('"' + value + '"' for value in arguments) + '\n')
        command = ['rtk', 'proxy', 'dotnet', compiler, '/noconfig', '@' + str(response)]
        subprocess.run(command, check=True)
        record['commands'].append(dict(arguments=list(map(str, command)), responseSha256=sha(response), exit=0))
        record['fixtures'][name] = dict(assemblySha256=sha(assembly), sources={str(path): sha(path) for path in sources})
        if executable:
            (directory / 'InteropMetadata.runtimeconfig.json').write_text(json.dumps(dict(runtimeOptions=dict(
                tfm='net10.0', framework=dict(name='Microsoft.NETCore.App', version='10.0.0')))))

    usings = output / 'GlobalUsings.cs'
    usings.write_text('global using System;\nglobal using System.IO;\nglobal using System.Linq;\nglobal using System.Collections.Generic;\n')
    compile_source('inspector', [ROOT / 'tests/recovery/InteropMetadata/Program.cs', usings], executable=True)
    for variant in ['baseline', 'return-marshal', 'reference-type', 'other-namespace', 'other-declaring-type', 'calling-convention']:
        namespace = 'Other' if variant == 'other-namespace' else 'Fixture'
        declaring = 'Different' if variant == 'other-declaring-type' else 'Native'
        kind = 'class' if variant == 'reference-type' else 'struct'
        convention = 'Cdecl' if variant == 'calling-convention' else 'Winapi'
        source = output / (variant + '.cs')
        lines = ['using System.Runtime.InteropServices;',
                 f'namespace {namespace} {{ public static class {declaring} {{ public {kind} Options {{ public int Value; }} }} }}',
                 'public static class Methods {']
        for index in range(349):
            if variant == 'return-marshal' and index == 0:
                lines.append('[return: MarshalAs(UnmanagedType.I1)]')
            lines.append(f'[DllImport("RanvierWebCoreHost", EntryPoint="rv_fixture_{index}", CallingConvention=CallingConvention.{convention})]')
            parameter = f'ref {namespace}.{declaring}.Options options' if index == 0 else ''
            lines.append(f'public static extern int Function{index}({parameter});')
        lines.append('}')
        source.write_text('\n'.join(lines) + '\n')
        compile_source(variant, [source])
    (output / 'fixture-build.json').write_text(json.dumps(record, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--sdk', required=True, type=Path)
    parser.add_argument('--reference', required=True, type=Path)
    arguments = parser.parse_args()
    build(arguments.output, arguments.sdk, arguments.reference)
