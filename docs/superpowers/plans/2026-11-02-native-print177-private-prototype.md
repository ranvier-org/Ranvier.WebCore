# Private native DOM printing prototype implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. This is an explicitly private test-only experiment.

**Goal:** Determine whether the existing live WebCore document can produce a real paginated PDF and restore its screen state through the existing PrintContext and Skia writer.

**Architecture:** A private embedder test unit accepts a retained native document on its owner thread. It synchronously enters print layout, computes page rectangles, paints pages to a bounded Skia PDF stream, leaves print mode, restores scroll, and publishes an independently owned byte result. There is no event-loop pumping during this operation, OS dialog, spooler, WebKit/WebFrame layer, new dependency, product ABI or package allocation.

**Tech Stack:** Existing pinned WebCore/Skia C++, Python ctypes, existing pypdf/Pillow and existing Poppler executable for independent output inspection.

**Spec:** WebCore177 retained native scope and `printing-native-boundary-gpu_apis.json` SHA a291684fe188377b32db02df26d3bc698a98eaa18e1a8a6686256762252dde8e in the external coordinator evidence directory.

## Global constraints

- Source base is exact36d2c786ce2e4d36e02595ad767372e304798e00, whose tested host lifecycle transaction is retained. Warm producer16ae and official P4 bytes are distinct provenance.
- No protected source, PCH, object, archive, configuration or official payload changes. Only private objects, response files, PDB/import library and DLL outputs may be written.
- Review unapplied source and exact recipe before a j1 compile/link window. Acquire and inspect an atomic native slot first, maximum three slots.
- Preserve all 26 official payload hashes before/after. Recompile the36 MutationGlue privately because the original official engine lacks its imports; append that object and the print fixture exactly once each, replace zero original objects, and retain the verified36 host DLL.
- This prototype requires valid private handles and a synchronous owner turn with no callback pumping. It does not establish production close/reentrancy safety or a public printing contract.

## Review focus

- Physical units: PDF page boxes use points. The initial code follows the existing WebKit print-layout sequence; the independently rendered96-CSS-pixel ruler must measure72 PDF points. A failure is a measured mapping gap, not permission to change the expectation.
- Live-state restoration: cancellation, output budget failure and success must all leave printing=false, identical screen pixels and scroll; reload and another print follow.
- Real PDF content: page markers remain extractable text, Ahem is embedded, the image remains blue and the ruler/vector content renders through an independent PDF consumer.
- Ownership: the result is released once, and retained bytes remain valid after host reload/destruction. Partial output from an aborted PDF is never exposed.
- Bounds: positive finite printable geometry, bounded pages/output/raster DPI and invalid options must fail without degenerate print layout or stale output.

### Task 1: Freeze a truthful runtime RED and the private test seam

**Files:** `tests/printing/print177_probe.h`, `tests/printing/print177_probe.py`.

**Interfaces:** Private `ranvier_print177_export(document, options, result**)`, `ranvier_print177_info`, `ranvier_print177_bytes`, `ranvier_print177_release`; not declared in any product header.

- [x] Write the fixture with literal three-page,576×720-point paper,36-point margins, one-inch ruler, text/font/image, cancellation and output-budget expectations.
- [x] Run against official P4. The first isolated-Python run failed before native binding because existing pypdf is in user site; preserve that as a harness failure.
- [x] Rerun with the recorded ordinary interpreter: exit1 at the missing private entry point, all26 official payload hashes unchanged. No printing success is inferred.

### Task 2: Prepare the unapplied source and exact private link

**Files:** `tests/printing/print177_probe.cpp`, `tests/printing/prepare_windows_trial.py`.

**Interfaces:** `Print177Options`/`Print177Info` are private C-layout records. Outcomes are0=complete,1=cancelled,2=output failure,3=invalid options/layout. Admission errors return-1; no result is published.

- [x] Implement a synchronous RAII PrintContext guard, bounded SkWStream, serial SkPDF metadata/JPEG callbacks, per-page paint and owned result bytes.
- [x] Prepare commands from the prior actual P4 producer receipt, preserving tool/flags/PCH. Redirect all outputs privately; append print and matching36 MutationGlue objects exactly once each.
- [ ] Root reviews the clean immutable source and unexecuted recipe before native tools run.

### Task 3: One bounded actual private compile/link and output experiment

- [ ] Capture every actual protected producer dependency and official payload hash after the owner grants the read-only window; distinguish historical3316 inputs from retired private proof paths.
- [ ] Acquire/inspect the own slot grant, then compile the two new objects sequentially and link the private WebCore. Any newly discovered uncaptured include stops before link and requires a new complete snapshot.
- [ ] Construct a private payload directory from the verified official package plus retained36 host and new private engine. Never overlay an official directory.
- [ ] Run the fixture with explicit native directory/bridge/source/output paths. Record every failed assertion and final nonzero status, not only the first visual gap.
- [ ] Independently parse and rasterize the PDF: three page boxes/markers, embedded font, images, ruler width, output abort semantics, state restoration, repeated export, deviceScale1/1.5/2 boxes and bytes after host close.
- [ ] Hash all protected inputs and26 official payloads afterward; preserve exact compiler/link/runtime commands and compact source/output proof. Release slot/borrow and retire disposable object/PDB/runtime copies after independent readers release.

No OS provider or production printing API is selected by this experiment. CSS page pseudo-classes, vertical writing, PDF links/tagging/accessibility, general font coverage and production reentrancy remain unqualified.
