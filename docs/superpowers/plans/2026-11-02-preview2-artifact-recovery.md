# Preview2 artifact recovery implementation plan

> Execution: Codex acceptance implements directly; root independently reviews the source checkpoint before any dispatch or publication.

**Goal:** Qualify and publish the exact Windows GPU package already produced from 05ba, without rebuilding or changing its immutable tag.

**Architecture:** An explicit recovery dispatch in build.yml skips the seven ordinary jobs. A read-only Windows job downloads only the fixed package and manifest, runs the immutable reviewed test checkout's full 101 probes and packed checks, and audits the seven existing public packages. A separate OIDC job can publish only the exact verified package after that job succeeds. Orchestrator, test, and product commits are recorded separately.

**Spec:** Root's authorized artifact-only recovery ruling, retained in C:/wk/project2/integration-recipe.md and diagnostic-ci/independent-audit.json.

## Constraints

- Product source05ba023551aaf58946cbc0ca7099ca65d9860e14; ABI60; version0.1.1-preview.2.
- Original run41356950088; package SHA9a4015a5eaf3581fa9481146ded5b6dbee8d6e63cf1e5b13ed5e24522a8ad243.
- The reviewed negative fixture's test commit is pinned before the recovery path becomes usable.
- No configure, native build, tag rewrite, repack, or policy edit.
- The seven published signed packages must match the retained exact public audit.
- Default job guards, normal concurrency and automatic cohort behavior remain unchanged when recovery=false.

## Tasks

- [x] Write and run RED package, manifest, source, catalogue and public-package corruption controls.
- [x] Implement strict package verification and bounded asset-only staging; run focused GREEN tests.
- [x] Add the explicit recovery workflow and isolated publication gate. Test graph decisions for ordinary/tag/recovery/failure/cancel cases.
- [x] Pin the independently reviewed fixture, five font assets and their hashes. Run full Python suite and source checks.
- [ ] Push immutable source checkpoint for root review. Dispatch or publish only after that review and the full proof succeeds.

## Review focus

Reject mismatched product and test provenance, missing/extra/failed catalogue groups, modified payloads, missing public packages, and unbounded subprocess cleanup. Check that NuGet login fails closed if the actual private policy rejects the main workflow token; public documentation alone is not a policy readback.
