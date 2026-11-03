# Immutable preview12 Slim Recovery Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Qualify and export the five unchanged F native packages plus canonical F Interop and aggregate packages without rebuilding an engine or modifying the tag.

**Architecture:** A read-only controller H verifies the original four successful CI native jobs and the separate successful Mac F/H recovery. It runs only clean F's canonical managed packer, verifies all seven packages and actual compiled signatures, and emits receipts/artifacts. Export repeats provenance and payload admission against a separately reviewed successful qualification; Root owns trusted publication wiring.

**Tech Stack:** Python standard library, GitHub Actions, .NET SDK 10.0.403 metadata inspector.

**Spec:** Root's assigned Slim immutable-F recovery scope and native_acceptance's F/H, duplicate-member and exact-signature review requirements.

## Global Constraints

- Product F is d31c3631ed4bbe6520f7f5f7c7e7d34499c38122, version 0.1.1-preview.12, ABI64/349.
- Original Slim producer run is 41719479076; only four successful non-Mac native jobs supply original packages.
- Mac recovery supplies the fifth F package and independently bound H/helper/qualification proof.
- No engine build, source transplant, tag/version allocation, publication or build.yml edit.
- Policies remain unarmed with null actual artifact/package/qualification hashes until independently audited.
- Source, unsigned producer bytes and eventual signed public bytes must not be relabeled.

## Review Focus

- A successful job from another run, source, RID or workflow must reject.
- Duplicate/case-colliding/path-traversing ZIP members and incomplete native manifests must reject.
- A Mac package without successful independent native gates and matching unchanged-Host sidecars must reject.
- Compiled Interop must match all 349 signatures, marshalling and native-library identities; matching counts alone must reject.
- A stale/failed qualification, package mutation or public-native restore fallback must reject before export/authentication.

## Tasks

1. Add tests for disabled policy, original run/job/artifact admission, native payload/format tamper, Mac F/H/helper boundaries, aggregate dependency completeness, exact Interop signatures and qualification/export admission. Observe the missing-controller RED.
2. Implement `scripts/recover_preview12_slim.py` with `qualify` and `export`, safe immutable artifact acquisition, clean F/H source checks, owned bounded child groups, canonical F managed packaging and seven-package validation.
3. Add `tests/recovery/InteropMetadata` using System.Reflection.Metadata. Decode actual P/Invoke return/parameter types, marshalling and library/calling-convention metadata without loading native code; compare to F's canonical generator output.
4. Add an unarmed policy and separate read-only qualification workflow. Upload packages and complete failure evidence independently. Keep publisher integration outside this branch.
5. Run focused controls, compile the small inspector under an owned resource/lease admission if available, run the full Python suite, freeze source/evidence, request QA review and open a conventional focused PR. Cancel its redundant automatic native producer. Clean owned outputs after readers release.
