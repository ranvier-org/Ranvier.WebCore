# Pinned burn harness

Use the tracked `scripts/burn.sh` when a diagnostic needs a bounded Windows load run or CPU-pinned child:

```bash
. scripts/burn.sh
PIN=1 AFF=3 pinned ./Native.exe --dialogs-only
status=$?
```

Pinned launch creates the child suspended, applies the requested affinity mask, and resumes it.
The child s exact Windows exit DWORD is emitted as `BURN_CHILD_EXIT_CODE=<unsigned-decimal>`.
The Bash function also returns the child status (Bash exposes the low byte); callers that need the
full Windows code should record the marker. Unpinned calls execute directly and retain normal
shell status.

Load generators are capped at six. Each burner exits after 1,500 seconds, and `start_burners`
registers `stop_burners` for exit and signal cleanup. Diagnostics should still call
`stop_burners` after each run so they do not rely on the timeout.

The original flake diagnostic copies were kept read-only at
`C:/wk/flake1-artifacts/burn.sh` and `C:/wk/flake3-artifacts/burn.sh`. Their source hashes and
consumer paths are recorded in `docs/issue213-source-provenance.json`.
