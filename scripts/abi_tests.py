# Runs the F# ABI driver (tests/abi) against a staged runtime: the frames and events of every ABI version,
# then the teardown probes. The driver's P/Invoke declarations are checked against host/RanvierWebCoreAbi.h
# first. The staged libraries are copied next to the built driver, where .NET finds them on every platform.
#
#   abi_tests.py --stage DIR --source DIR    a directory build.py package staged, and the WebKit checkout
#                                            (the resources test serves its Ahem font)
import argparse, json, os, pathlib, shutil, subprocess, sys, tempfile

root = pathlib.Path(__file__).resolve().parents[1]
tests = root / 'tests' / 'abi'

parser = argparse.ArgumentParser()
parser.add_argument('--stage', required=True)
parser.add_argument('--source', required=True)
args = parser.parse_args()


def run(command, **kw):
    command = [str(c) for c in command]
    print('>', subprocess.list2cmdline(command), flush=True)
    subprocess.run(command, check=True, **kw)


run([sys.executable, '-I', tests / 'generate_native.py', 'check'])
stage = pathlib.Path(args.stage)
rid = json.loads((stage / 'manifest.json').read_text())['rid']
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
    out = pathlib.Path(temp) / 'driver'
    run(['dotnet', 'build', tests / 'RanvierWebCoreAbi.Driver.fsproj', '-c', 'Release', '--nologo', '-v', 'q', '-o', out])
    shutil.copytree(stage / 'runtimes' / rid / 'native', out, dirs_exist_ok=True)
    env = dict(os.environ, RANVIER_WEBKIT_SOURCE=args.source, RANVIER_WEBCORE_OUT=str(pathlib.Path(temp) / 'run'))
    driver = out / 'RanvierWebCoreAbi.Driver.dll'
    run(['dotnet', driver], env=env)
    run(['dotnet', driver], env=dict(env, RANVIER_WEBCORE_PROBE='teardown'))
print('abi tests passed', flush=True)
