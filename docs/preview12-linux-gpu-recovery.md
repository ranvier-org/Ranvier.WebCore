# Preview12 Linux GPU test recovery

The immutable product source is `d31c3631ed4bbe6520f7f5f7c7e7d34499c38122`. Its
Linux GPU transition fixture still asserts ABI63, although that producer explicitly selects ABI64.
The corrected test source is `f2d5b2b4c0b0404586097696907dc36e83dc87b9`; it changes
no product code. Neither a tag move nor a replacement Host is part of this recovery.

The checked-in policy is unarmed. Once the actual automatic tag GPU producer has completed,
independent acceptance pins both original package artifacts, original complete probe summaries and
the exact guard failures. Qualification verifies the GitHub run/artifact digests, complete package
payloads and source equivalence. It retains every original passing probe and its one known failure,
then runs the corrected packaged GPU checks and the complete 349-declaration ABI catalogue,
including both actual managed driver modes and all 108 authored Python probes. Actual mapped Host
paths, hashes, process IDs and start ticks are captured. Every owned group is closed after execution.

The controller source and policy/workflow source are independently pinned, so a later policy commit
does not silently change the code that qualified the packages. No engine target is configured or
built by qualification; fetching the pinned upstream checkout supplies font and SVG test fixtures.

Publication requires a separately reviewed policy that pins the successful two-architecture
qualification run and both receipt artifacts. Pre-authentication export repeats origin, original
failure, package and qualification verification and copies the exact producer nupkg bytes. The
existing `build.yml` trusted publishing route performs authentication only after that export.
Fresh signed-public package auditing and issue-specific runtime evidence remain required afterward.
