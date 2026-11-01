# Runs tests/abi/snapshot_options.py 30 times, one process each, against a frozen runtime; one PASS line per run.
# Usage: repeat30.sh <native directory> <output file>
set -e
here="$(cd "$(dirname "$0")/../.." && pwd)"
: > "$2"
for i in $(seq 1 30); do
  python -I -X utf8 "$here/tests/abi/snapshot_options.py" --native-directory "$1" | grep 'PASS' >> "$2"
done
sort "$2" | uniq -c
