# Runs tests/abi/canvas_state.py 30 times, one process each, against a frozen runtime; one PASS line per run.
# Usage: repeat30.sh <native directory> <output file>
set -e
: > "$2"
for i in $(seq 1 30); do
  python -I -X utf8 C:/wk/native-canvas-r04/tests/abi/canvas_paints.py --native-directory "$1" | grep 'PASS:' >> "$2"
done
sort "$2" | uniq -c
