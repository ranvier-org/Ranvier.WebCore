# Future public Cocoa CPU contracts

This is disabled source preparation. `public_cocoa_policy.json` has no allocated Native version, public
package/source hashes or owner-proof admission. Consumer execution is unarmed, and this controller
builds no engine. The accepted private2a proofs remain separate: motion135, scoped contrast83 in both fresh
orders, and the exact-runtime contextual eight-mode timer result.

## Runtime and source binding

After the matching public cohort exists, QA supplies one reviewed policy with exact Native package ID,
version, clean source, package and public audit SHA256; matching Interop package/header hashes; the
producer-built sidecar manifest hash; and the controller commit. The Native manifest must identify
ABI64/osx-arm64 and all four Slim or six GPU dylibs plus every resource. The Interop header must contain
all 349 canonical declarations. The controller verifies every package payload, the package signature,
and actual ARM64 Mach-O headers before execution. It copies the original package bytes into its own
`baseline-native` directory and never replaces the Host or an engine.

The audit hash is the independently reviewed public-feed/signature/payload receipt, not a caller's
unverified source label. It must establish that these exact nupkg bytes came from the public feed.
No private2a package, derivative Host, old owner address or broad contrast hook is an admissible substitute.

## Matching sidecars, built once beside the producer

The native producer invokes `build_cocoa_sidecars.py` immediately after staging its package and retains
a separate `cocoa-sidecars-osx-arm64-<flavor>` artifact. Its immutable `producer-sidecars.json` binds
the unsigned package, complete native payload, helper binaries and consumed input archives. After
publication, QA seals a separate consumer manifest against the signed nupkg only after proving its
native payload identical. Signing the nupkg requires no helper rebuild. The raw producer receipt is
retained unchanged, and the checked-in consumer policy remains unarmed.

Mac configure explicitly enables `CMAKE_EXPORT_COMPILE_COMMANDS` and requires exactly one usable
`RanvierWebCoreAbi.cpp` compiler stanza before the native build. Package and manifest artifacts upload
before sidecar compilation, so a helper failure does not discard the already staged package. Timer/page
and AppKit dependency capsules are byte-verified and written after dependency scanning, before compiling
the helper; their receipts and archives remain available when compilation or strict linking fails.

An external corrected controller checkout may use `--producer-root "$PRODUCER_ROOT"`. That producer
checkout must be tracked-clean at exactly the staged manifest's source commit and supply the canonical
349-declaration header plus all C++/AppKit probe sources. The controller and Python builder remain in
their separate tracked-clean checkout. The receipt records both Git identities, both roots and the
controller/builder hashes, then rechecks both sources and every native payload after the attempt. This
permits a metadata-only recovery without editing or relabeling the immutable producer source.

The existing public ABI deliberately initializes motion/contrast to Off and maps media preference0 to
no preference, not `ForcedAccessibilityValue::System`. It also does not expose the per-page vector
painter setting. The old fixture reached those controls through a private Host replacement. This route
uses `cocoa_page_sidecar.cpp` instead. It obtains a retained Document through existing `rv_host_document`,
uses the matching generated inline Settings accessors and calls the existing exported Page invalidators.
It includes no Host implementation, changes no registry and allocates no public ABI. Its test-only
precondition is a live host on an idle owner turn; fixtures restore the painter before host teardown.
It is not an application API for stale/reentrant host calls.

Static feasibility was checked against retained2a generated Settings.h and externally defined Page
invalidator symbols. Actual new-cohort compile/link is still required. The exact new producer's existing
build/configuration/forwarding headers must still be available. Do not regenerate an SDK or borrow an
older header set to satisfy this preparation.

Use the existing `build_cocoa_timer_contract.py` against that completed producer and an extracted,
hash-verified signed runtime. This performs only private helper compilation, using the captured Host
command and full dependency scan; it invokes no engine target:

```sh
python3 -I tests/abi/build_cocoa_timer_contract.py \
  --build "$PRODUCER_BUILD" --webkit-source "$PINNED_WEBKIT" \
  --runtime "$SIGNED_NATIVE" --runtime-hashes "$SIGNED_HASHES" \
  --probe-source tests/abi/cocoa_timer_contract.cpp --output "$OWN/timer" --public-sidecar
python3 -I tests/abi/build_cocoa_timer_contract.py \
  --build "$PRODUCER_BUILD" --webkit-source "$PINNED_WEBKIT" \
  --runtime "$SIGNED_NATIVE" --runtime-hashes "$SIGNED_HASHES" \
  --probe-source tests/controls/cocoa_page_sidecar.cpp --output "$OWN/page" \
  --public-sidecar --link-webcore
```

The explicit public-sidecar mode uses the proven TestWebCore allowable-client install name, strict
undefined-symbol resolution, then the final helper ID and ad-hoc codesign. It records compiler/profile,
configuration, dependencies, consumed header bytes and native before/after hashes. The ordinary legacy
helper mode is unchanged. Any missing header/export or new unresolved symbol is a retained failure;
there is no dynamic lookup, stub, copied definition or system-engine fallback.

Build `cocoa_progress_motion.mm` and `cocoa_contrast_scoped_override.mm` as separate process-local AppKit
helpers with the same actual SDK/deployment target: `xcrun clang++ -std=c++20 -fobjc-arc -dynamiclib
-mmacosx-version-min=26.0 -framework AppKit -framework Foundation`. Record their compiler/SDK, exact
argv/source/dependency hashes and ad-hoc signatures. They add no renderer package dependency.

Seal a sidecar manifest with boundary `public-Host-unchanged-sidecars-v1`, ABI64/349, Native package SHA
and source, complete identical `nativeBefore/nativeAfter` maps, `hostReplaced/headerReconstruction/
engineCompilation=false`, strictLink and reviewed source equivalence, all compiler/configuration/input
archive hashes, and the relative path/SHA of timer, page, motion and scoped contrast helpers. This
manifest is independently reviewed and hash-pinned by the policy before any consumer activation.

## Compile-free consumer and owner proof

`public_cocoa_contracts.py --plan-only` verifies the policy/package/header/sidecar/source admission and
prints the exact commands. Execution has no build path. It runs independent bounded child groups, with
an 8 GiB resident tree limit, 360-second group deadline and process-group cleanup. A failed output group
does not skip the other admitted groups:

- The existing eight timer modes, plus fairness at 0.01/0.1/1 ms. The original 1 ns trap remains historical,
  with no new blanket interpretation.
- The complete 135 motion checks, using a separately loaded page sidecar. The assertions are unchanged.
- Both 83-check scoped contrast orders, unknown-caller forwarding and positive System getter attribution,
  then the existing full-image paired-order validator. All original assertions remain.
- A fresh LLDB destructor inspection against the actually loaded JSC. It finds the current symbol and
  isCurrent conditional dynamically, observes false ownership and records the actual fatal instruction;
  it contains no reused address.

The first consumer has no reviewed owner proof and therefore cannot claim complete acceptance. It
retains the actual failures/signals, all independent groups and fresh debugger data. After independent
review, a second compile-free replay may pin that exact-runtime proof SHA. Existing `cocoa_timer_contract`
still validates the native identity and same-helper fatal reference. Any accepted Mac SIGKILL remains
contextual evidence for this exact runtime, not direct attribution of every future signal. No timeout
or memory-limit kill qualifies as an ownership assertion.

The final receipt requires unchanged public/native/helper bytes, all original counts, both contrast
orders and reviewed exact-runtime owner admission. This is CPU implementation evidence for the signed
cohort; it does not qualify Metal presentation, second-host composition or public View package graphs.
