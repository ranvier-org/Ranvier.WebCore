"""Download only pinned artifacts and invoke the independent P7 Linux verifier."""
import argparse
from pathlib import Path
import subprocess
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--work', type=Path, required=True)
args = parser.parse_args()
work = args.work.resolve()
work.mkdir(parents=True, exist_ok=False)
artifacts = [
    (41514646288, 'package-linux-x64-gpu', 'x64-package'),
    (41514646288, 'manifest-linux-x64-gpu', 'x64-manifest'),
    (41514646288, 'probe-logs-linux-x64-gpu', 'x64-probe'),
    (41514646288, 'package-linux-arm64-gpu', 'arm64-package'),
    (41514646288, 'manifest-linux-arm64-gpu', 'arm64-manifest'),
    (41514646288, 'probe-logs-linux-arm64-gpu', 'arm64-probe'),
    (41514646288, 'clipping-report-linux-x64-gpu', 'original'),
    (41535027181, 'p7-linux-artifact-profile', 'qualification'),
]
for run_id, name, directory in artifacts:
    subprocess.run(['gh', 'run', 'download', str(run_id), '--repo', 'ranvier-org/Ranvier.WebCore',
                    '--name', name, '--dir', str(work / directory)], check=True, timeout=180)
command = [sys.executable, '-I', str(Path(__file__).with_name('recover_preview7_linux_gpu.py')),
    '--x64-package', str(work / 'x64-package/Ranvier.WebCore.Native.Gpu.linux-x64.0.1.1-preview.7.nupkg'),
    '--x64-manifest', str(work / 'x64-manifest/manifest.json'), '--x64-summary', str(work / 'x64-probe/summary.txt'),
    '--arm64-package', str(work / 'arm64-package/Ranvier.WebCore.Native.Gpu.linux-arm64.0.1.1-preview.7.nupkg'),
    '--arm64-manifest', str(work / 'arm64-manifest/manifest.json'), '--arm64-summary', str(work / 'arm64-probe/summary.txt'),
    '--original-report', str(work / 'original/background-content-clipping-regression.json'),
    '--qualification-dir', str(work / 'qualification'), '--export', str(work / 'export')]
subprocess.run(command, check=True, timeout=90)
