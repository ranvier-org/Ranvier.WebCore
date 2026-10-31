# Runs tests/abi/cascade_diagnostics.py 30 times, one process each, against a frozen runtime, and the Chromium oracle
# 30 times; one line per run. Usage: repeat30.sh <native directory> <probe output file> <oracle output file>
set -e
: > "$2"
: > "$3"
for i in $(seq 1 30); do
  python -I -X utf8 C:/wk/native-cascade/tests/abi/cascade_diagnostics.py --native-directory "$1" | grep PASS >> "$2"
  node C:/wk/native-cascade/tests/abi/cascade_diagnostics_browser.mjs > /dev/null
  echo "$i $(sha256sum C:/wk/native-cascade/tests/fixtures/cascade-diagnostics-oracle.json | cut -d' ' -f1)" >> "$3"
done
sort "$2" | uniq -c
cut -d' ' -f2 "$3" | sort | uniq -c
