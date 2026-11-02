# Native spelling-provider and editor integration

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task. Steps use checkbox syntax for tracking.

**Goal:** A native application obtains an optional OS spelling suggestion and replaces precisely the requested WebCore range while retaining composition, undo, cancellation and teardown safety.

**Architecture:** The application owns the OS spelling service and its UI. The renderer already supplies `rv_host_replace_range`, Range/selection handles, cancelable `insertReplacementText`, and undo/redo. Reuse that boundary; add no generic spelling service, Core facade, browser menu, dictionary engine or new public ABI. First qualify an optional Windows SDK adapter; unavailable language/provider results remain explicit on every platform.

**Tech stack:** Existing C++ host, WebCore editor, Windows `ISpellCheckerFactory`/`ISpellChecker`, SDK COM RAII, existing Python native ABI fixtures.

**Spec:** [WebCore172 current native delivery scope](https://github.com/ranvier-org/Ranvier.WebCore/issues/172). The current retained native scope supersedes the historical deferred/browser text.

## Global constraints

- No bundled NLP/LLM/writing-assistance framework, dictionary engine, browser-menu emulation or exact suggestion parity.
- Providers are optional; an unavailable provider/language is distinct from a successfully checked word.
- No dependency, package, ABI/version or kind allocation. SDK/Ole32 already belong to Windows host integration.
- All protected source/PCH/archive/build inputs are read-only. Native compilation uses owned outputs and an inspected max-three slot, j1 and aggregate8GiB/540second guard.
- Native text offsets are UTF-16; UTF-8 is only the existing C ABI transport. Preserve surrogate pairs and exact engine ranges.
- Keep existing renderer replacement behavior, public signatures and old tests except a demonstrated lifecycle/composition correction.

## Review focus

- A deferred suggestion must not overwrite a changed word or a replaced/destroyed document.
- Native `beforeinput` callbacks may cancel, replace the document or destroy the host.
- An active IME preedit must not be silently committed/cancelled by a spelling suggestion; decline application until composition ends.
- Provider errors and unsupported language must not be reported as correct spelling.
- COM objects, enumerated strings, request copies, range handles and callbacks must be released once.

## Task1: Prove the existing renderer boundary

**Files:** Create `tests/abi/spelling_replacement.py`; modify only `host/RanvierWebCoreAbi.cpp` if the RED proves a gap.

**Interfaces:** Existing `rv_host_replace_range`, generated Range/selection calls, `rv_host_ime_set_composition`/commit, `rv_host_edit` undo/redo and native input listeners.

- [ ] Add isolated cases for an emoji-prefixed misspelling, exact replacement, undo/redo, canceled `beforeinput`, stale document/range, active composition, callback document replacement and callback host destruction.
- [ ] Run the full fixture against immutable baseline63b; retain expected failures/crash exit and all passing controls. Each hazardous case runs in a child process.
- [ ] If confirmed, reuse existing host liveness/document-transaction and `handleInput`/`RvEditingScope` guards for range replacement. Decline active composition without changing preedit/history. Do not add a second editor/history implementation.
- [ ] Replay the unchanged full fixture and existing data-transfer/editing tests against one private host-only candidate. Commit the minimal proven fix separately.

## Task2: Qualify an optional Windows application provider

**Files:** Create `examples/NativeSpelling/WindowsSpellingProvider.h`, `tests/spelling/windows_provider.cpp` and its bounded SDK-only runner.

**Interfaces:** A copied UTF-16 check result carries availability, HRESULT failure, error start/length and bounded suggestions. No WebCore types or renderer linkage enter this adapter.

- [ ] Test actual installed language availability and unsupported language; check correct/misspelled text, suggestions, non-ASCII/UTF-16 offsets, repeated creation/release and provider failures. No fixed suggestion order is asserted.
- [ ] Implement with SDK `ISpellCheckerFactory`/`ISpellChecker`, balanced COM initialization, RAII interfaces and `CoTaskMemFree` for every returned string. Keep language/user dictionary ownership in the OS; do not modify dictionaries.
- [ ] Compile/run the SDK-only test privately; retain actual provider/language, HRESULTs, copied outputs and process cleanup.

## Task3: Exercise the real application action

**Files:** Extend `tests/abi/spelling_replacement.py`; add a concise `examples/NativeSpelling/README.md` and the existing probe route.

- [ ] Feed an actual OS result into app-owned native DOM suggestion UI. Apply the selected suggestion using the existing range edit and assert exact replacement, surrounding text and undo/redo. Browser context menus are not involved.
- [ ] Compare the copied expected word/current range text before applying; reject stale/cancelled requests and invalidate them on document replacement/close. Provider work owns no borrowed engine pointer across a thread or lifetime boundary.
- [ ] Run actual range/IME/cancellation/teardown regressions on Windows and Linux renderer candidates. Keep provider-unavailable paths explicit; do not infer Mac/Linux OS-provider qualification from Windows.
- [ ] Hand off exact source/runtime/SDK/proof hashes for independent review, then stop owned children/tools and archive/remove the owned tree and disposable outputs.

## Current evidence and review boundary

The host TextChecker is currently a no-op and continuous checking is disabled. That is not grounds to enable a general background checker. The existing C header already names range replacement as the spelling-correction boundary. `rv_host_replace_range` currently bypasses the existing editing scope; its composition/lifecycle behavior must be measured before any body change. Windows API references: [Check](https://learn.microsoft.com/en-us/windows/win32/api/spellcheck/nf-spellcheck-ispellchecker-check), [Suggest](https://learn.microsoft.com/en-us/windows/win32/api/spellcheck/nf-spellcheck-ispellchecker-suggest), [factory](https://learn.microsoft.com/en-us/windows/win32/api/spellcheck/nn-spellcheck-ispellcheckerfactory).

The OS adapter/app-owned UI choice is the coordinator/implementer proposal, not a claim of a user-mandated public API. Root reviews this bounded seam before product/provider edits. Native worktree tool rejected the external repository; the standing authorized Git fallback owns this isolated tree at405c25d.
