# Footguns

Each entry: what happens, why, and what to do instead.

## GitHub and merging

### Closing keywords close issues even in a negative sentence

- **What happens:** a PR body saying "can't close #211" closed #211 on merge.
- **Why:** GitHub matches `close`, `fix` and `resolve` (and their variants) followed by `#N`, ignoring the sentence around them.
- **Do instead:** write `close`, `fix` or `resolve` before `#N` only when the merge should close the issue. Write
  "refs #211" or "relates to #211" otherwise.

### An unreviewed commit can land with a merge

- **What happens:** a push after review changes what `gh pr merge` merges.
- **Why:** the merge takes the branch head at merge time.
- **Do instead:** `gh pr merge <n> --match-head-commit <reviewed sha>`; the merge fails if the head moved.

## Workflows and tests

### Text-matching a workflow `if:` breaks when guards are wrapped

- **What happens:** a test asserting that an `if:` starts with a given prefix fails after a harmless wrapper such as
  `!cancelled() && (...)` is added.
- **Why:** the test matches serialization, not meaning.
- **Do instead:** evaluate the condition for each input combination in the test.

### The AT-SPI tests need `at-spi2-core` on the runner

- **What happens:** `atspi (linux-x64)` fails before any assertion; the `v0.1.1-rc.1` tag run published nothing.
- **Why:** `tests/atspi/run.py` starts `/usr/libexec/at-spi2-registryd`, which the GitHub Ubuntu images omit.
- **Do instead:** install `at-spi2-core` in every job that runs the AT-SPI tests. `test_release.py` checks
  `build.yml` and `atspi-provider.yml` for it.

### Pinned versions in CI break on the next release

- **What happens:** a workflow or test carrying `63`, `0.1.1-preview.12` or a source commit fails or silently
  checks the old release after a bump.
- **Why:** the number is a copy of a value with a source of truth elsewhere.
- **Do instead:** read the ABI from `host/RanvierWebCoreAbi.cpp`, the version from `pins.json` or the tag, and a
  dependency's commit from its published nuspec. Verify a pinned value by its published hash, never by a literal.

### A failing step skips every later step in a job

- **What happens:** a new test placed after a known-red step never runs, and the job looks the same as before.
- **Why:** later steps run only on success unless marked `if: always()`.
- **Do instead:** put new tests before known-red steps or give them their own step condition. `package-contract`
  lists its test files explicitly in `build.yml`, so a new test file must be added there to run in CI.

### Push-triggered workflows on deleted branches rot silently

- **What happens:** a workflow triggered by `push` to a branch that no longer exists never fires, and its drift goes unnoticed.
- **Why:** nothing exercises it.
- **Do instead:** delete the workflow with its branch, or run it from `workflow_dispatch` on `main`.

### A job without `if:` has an implicit `success()`

- **What happens:** a job skips when a `needs` job failed or was skipped, although it declares no condition.
- **Why:** an omitted `if:` means `success()`. Removing a condition that is always true is therefore equivalent to
  keeping it.
- **Do instead:** write `!cancelled()` plus explicit `needs.<job>.result` checks when the job should run after a
  skip or failure.

### The Cocoa replay wrapper and controller come from different checkouts

- **What happens:** the replay runs a controller that differs from `main`.
- **Why:** the wrapper runs from the main checkout, and the controller from the pinned `controllerSource`.
- **Do instead:** re-check `main` before each dispatch. `collect-owner` always ends red by design; read its output
  rather than its status.

### A cleanup misses files loaded by a computed path

- **What happens:** a file looks unreferenced and is deleted, then a release job fails to open it.
- **Why:** `Path(__file__).parent / 'cases.json'` never contains the file's repository path, so a search for the
  path finds nothing. `tests/p7_gpu_qualification/cases.json` survived the CI cleanup (#338) only through review.
- **Do instead:** before deleting a data file, search for its bare filename as well as its path, and run every
  `build.yml` job that could load it.

## Hashes and packages

### Hash-pinned JSON depends on exact bytes

- **What happens:** a pinned sha256 stops matching after a rewrite.
- **Why:** the sha covers one serialization, `json.dumps(obj, indent=2) + '\n'`. On Windows, text mode translates
  `\n` to `\r\n`.
- **Do instead:** write with `newline='\n'`. Write embedded text that is pinned by sha (for example `ownerProofText`,
  `auditText`) back byte for byte, including its own line endings.

### Signing a package adds one member

- **What happens:** a sidecar manifest sealed against the unsigned stage names the wrong package sha.
- **Why:** signing a `.nupkg` adds only `.signature.p7s`. Helper sidecars built against the unsigned stage stay
  valid, but the seal must name the signed package sha. `_rels/.rels` is in both packages but absent from the
  producer stage tree.
- **Do instead:** compare the native payload of the signed and unsigned packages, then seal against the signed
  package sha. Do not rebuild helpers for a signature.

## Probes and ABI

### ABI-version asserts in probes go stale on every bump

- **What happens:** a probe with `assert rv_abi_version == 63` fails or blocks after the ABI moves to 64.
- **Why:** the number is copied into the probe.
- **Do instead:** compare against the manifest's `abi`, or the value read from `host/RanvierWebCoreAbi.cpp`. After
  each bump, `git grep -n "rv_abi_version"` in `tests/`.

### macOS strips `DYLD_*` under `/usr/bin/xcrun`

- **What happens:** `xcrun lldb` (or any tool launched through `/usr/bin/xcrun`) starts without `DYLD_*` variables,
  and helpers built with absolute rpaths to the producer runner can fail to load.
- **Why:** System Integrity Protection strips `DYLD_*` from protected binaries' children.
- **Do instead:** locate the tool with `xcrun --find` and run it directly, or build helpers with rpaths valid on the
  machine that loads them.

## Windows shell

### Heredocs, `xargs` and `-F -` misbehave

- **What happens:** inline Python in a heredoc loses backslashes; `xargs` passes CRLF into paths; `rtk git commit -F -`
  does not forward stdin.
- **Why:** the shell layers rewrite the text between you and the program.
- **Do instead:** write scripts and commit messages to files and pass the file path (`python -I script.py`,
  `git commit -F message.txt`).

### Git Bash rewrites `rev:path` arguments

- **What happens:** `git show origin/main:path/to/file` fails or reads the wrong file.
- **Why:** MSYS converts arguments that look like POSIX paths into Windows paths.
- **Do instead:** `export MSYS_NO_PATHCONV=1` before the command.
