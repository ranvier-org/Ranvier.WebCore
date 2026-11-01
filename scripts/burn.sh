#!/usr/bin/env bash
# Shared pinned-process harness for bounded native diagnostics.
BURN_SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
BURN_PIDS=""
BURN_PIDS_FILE="${BURN_PIDS_FILE:-${TMPDIR:-/tmp}/ranvier-burners-${BASHPID:-$$}.pids}"

start_burners() {
  local n="${1:-0}"
  case "$n" in
    (""|*[!0-9]*) echo "start_burners expects an integer count" >&2; return 2 ;;
  esac
  [ "$n" -gt 6 ] && n=6
  [ "$n" -eq 0 ] && return 0

  local burner
  burner=$(cygpath -w "$BURN_SCRIPT_DIR/burner.js") || return
  BURN_PIDS=$(BURNER_JS_PATH="$burner" BURNER_COUNT="$n" BURNER_AFFINITY="${AFF:-3}" powershell.exe -NoProfile -Command '
    $count = [int]$env:BURNER_COUNT
    $maskText = $env:BURNER_AFFINITY
    if ($maskText.StartsWith("0x", [System.StringComparison]::OrdinalIgnoreCase)) {
      $mask = [Convert]::ToInt64($maskText.Substring(2), 16)
    } else {
      $mask = [Int64]$maskText
    }
    1..$count | ForEach-Object {
      $process = Start-Process -FilePath node -ArgumentList @($env:BURNER_JS_PATH) -WindowStyle Hidden -PassThru
      $process.ProcessorAffinity = [IntPtr]$mask
      $process.Id
    }
  ' | tr -d '\r' | tr '\n' ' ')
  [ -n "$BURN_PIDS" ] || { echo "failed to start load generators" >&2; return 1; }
  printf '%s\n' "$BURN_PIDS" > "$BURN_PIDS_FILE"
  trap stop_burners EXIT INT TERM
}

stop_burners() {
  local pid
  for pid in $BURN_PIDS; do
    taskkill //F //PID "$pid" > /dev/null 2>&1 || true
  done
  BURN_PIDS=""
  : > "$BURN_PIDS_FILE"
}

# Pinned children are started suspended, assigned AFF, then resumed.
# The runner emits the exact Windows exit DWORD and returns the child code.
pinned() {
  if [ -n "${PIN:-}" ]; then
    [ "$#" -gt 0 ] || { echo "pinned requires a command" >&2; return 127; }
    python -I "$BURN_SCRIPT_DIR/pinned-run.py" "${AFF:-3}" "$@"
  else
    "$@"
  fi
}
