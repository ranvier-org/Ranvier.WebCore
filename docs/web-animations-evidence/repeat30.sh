# Runs web_animations 30 times on a frozen runtime and prints each PASS line. Usage: repeat30.sh <runtime dir>
R=${1:?runtime}
for i in $(seq 1 30); do
  python -I -X utf8 tests/abi/web_animations.py --native-directory "$R" 2>&1 | tail -1 | sed "s/^/run $i: /"
done
