"""Consumer-only native texture input and physical-DPI compositor regression."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from windows_view_transition_pixels import build_helper


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--compiler-environment', type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    consumer = Path(tempfile.mkdtemp(prefix='consumer-', dir=args.output)).resolve()
    try:
        library = build_helper(consumer, args.compiler_environment, texture_input=True)
        failures = []
        pipeline = subprocess.run([sys.executable, '-I', str(Path(__file__).with_name('frame_pipeline.py')),
                                   str(args.native_directory.resolve()), str(library)], timeout=120)
        if pipeline.returncode:
            failures.append(('frame_pipeline', pipeline.returncode))
        for name in ['compositor_dpi_windows', 'compositor_input_windows', 'compositor_fractional_edges']:
            result = subprocess.run([
                sys.executable, '-I', str(Path(__file__).with_name(name + '.py')),
                '--native-directory', str(args.native_directory.resolve()),
                '--helper-library', str(library), '--report', str((args.output / (name + '.json')).resolve())],
                timeout=120)
            if result.returncode:
                failures.append((name, result.returncode))
        for name in ['host_tracing', 'host_errors', 'host_error_lifetime']:
            result = subprocess.run([
                sys.executable, '-I', str(Path(__file__).resolve().parents[1] / 'abi' / (name + '.py')),
                str(args.native_directory.resolve()), str(library)], timeout=120)
            if result.returncode:
                failures.append((name, result.returncode))
        assert not failures, failures
    finally:
        assert consumer.parent == args.output.resolve()
        shutil.rmtree(consumer)


if __name__ == '__main__':
    main()
