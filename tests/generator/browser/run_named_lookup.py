"""Exercise compiled F# named lookups against Chromium DOM objects."""

import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('--browser', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
output = args.output.resolve()
assert (output / 'NamedLookupBrowser.js').is_file(), 'Compile NamedLookupBrowser.fsproj first'
shutil.copyfile(Path(__file__).with_name('NamedLookupTests.js'), output / 'NamedLookupTests.js')
page = output / 'named-lookup.html'
page.write_text('<!doctype html><html><body><script type="module" src="NamedLookupTests.js"></script></body></html>', encoding='utf-8')
with tempfile.TemporaryDirectory(prefix='ranvier-named-lookup-') as profile:
    result = subprocess.run([str(args.browser.resolve()), '--headless=new', '--disable-gpu',
                             '--no-first-run', '--no-default-browser-check', '--allow-file-access-from-files',
                             '--user-data-dir=' + profile, '--virtual-time-budget=5000', '--dump-dom', page.as_uri()],
                            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=45)
    (output / 'named-lookup-result.html').write_text(result.stdout, encoding='utf-8')
    (output / 'named-lookup-stderr.log').write_text(result.stderr, encoding='utf-8')
    assert result.returncode == 0, result.stderr[-4000:]
    assert 'data-result="NAMED_LOOKUP_PASS"' in result.stdout, result.stdout[-6000:] + result.stderr[-2000:]
    assert 'data-assertions="121"' in result.stdout, result.stdout[-6000:]
print('NAMED_LOOKUP PASS: 121 assertions for document IDs, cross-realm facades, live mutations, shadow isolation and SVG/MathML datasets')
