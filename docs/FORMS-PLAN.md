# D13 form collections and events plan

## Core and view state

- **Core primitives used:** none. D13 is a WebCore producer change: generated C functions over the engine's own form
  collections and events, plus their managed P/Invoke declarations.
- **View-owned state:** none. The Views wrappers and the shared conformance fixture consume these functions in
  Ranvier.View; that lane's spec carries its own section.

**Goal:** Expose HTMLFormControlsCollection, HTMLOptionsCollection, SubmitEvent, FormDataEvent and FormData through the
pinned engine, and prove named and indexed form/option lookup, a typed submitter and collected form data against a
measured browser, including duplicate names and removed controls. Tracking issue: Ranvier.WebCore #22, engine route.

**Tree:** `C:/wk/native-forms`, branch `codex/native-api-forms`, from #137 `e58aa24` (Native25/ABI33). Reserved:
Native28/ABI36 after I12 (Native26) and G02/G12 (Native27); the G02/G12 branch is forward-merged before allocation.

## Pinned source scope

- `html/HTMLFormControlsCollection.idl`: indexed getter (from HTMLCollection) and `namedItem(name) -> (RadioNodeList or
  Element)?`. Reached through the existing `HTMLFormElement.elements` getter.
- `html/HTMLOptionsCollection.idl`: `length` (read/write), indexed setter, `add(element, before)`, `remove(index)`,
  `selectedIndex` (read/write), `item`, `namedItem`. Reached through `HTMLSelectElement.options`.
- `html/SubmitEvent.idl`: `submitter`; constructor with `SubmitEventInit.submitter`.
- `dom/FormDataEvent.idl`: `formData`; constructor with a required `FormDataEventInit.formData`.
- `html/DOMFormData.idl` (`FormData`): constructor `(form, submitter)`, `append`/`set` (string and Blob overloads),
  `delete`, `get`, `getAll`, `has`, and a key/value iterable. Entry values are `(File or USVString)`.

A trial generation with the five interfaces in scope emits 17 functions. Constructors need `constructors` entries.
`get`, `getAll`, the Blob overloads and the iterable need `File`/`Blob`, which are out of scope (H11).

## Engine-fired events

`HTMLFormElement.requestSubmit(submitter)` and `submit()` are excluded today as navigation. In the pinned engine,
`requestSubmit` validates the submitter, fires a trusted, cancelable SubmitEvent with the submitter, and builds the entry
list, which fires FormDataEvent. It then hands the navigation to `FrameLoader::submitForm`. The host's
`EmptyFrameLoaderClient::dispatchDecidePolicyForNavigationAction` never answers the policy check, so the document is
not replaced. `new FormData(form, submitter)` also fires FormDataEvent synchronously.

## Proof

1. RED: the collection, event and FormData functions are absent in Native25.
2. A Chromium oracle over one form fixture records:
   - indexed and named lookup with duplicate names (RadioNodeList), id-versus-name priority, and controls that are
     removed, moved, form-associated by the `form` attribute, or inside fieldsets;
   - options collection edits: `add` before an element or an index, `remove`, the `length` setter (truncate and grow),
     the indexed setter, `selectedIndex`, and named lookup;
   - SubmitEvent submitter for `requestSubmit(button)`, `requestSubmit()` and a constructed event, plus requestSubmit
     errors (a non-submit button, or a button of another form);
   - FormDataEvent from requestSubmit and from `new FormData(form, submitter)`, with the entry list (including the
     submitter's name/value, disabled and removed controls, and duplicates), and with edits made in the listener.
3. Native: `tests/abi/form_collections.py` must match the oracle exactly, plus null/thread/subtype errors.
4. Teardown cases: collections, a FormData and a held SubmitEvent released after host destroy.
5. Final batch, gates, absence check, Native28/ABI36 and evidence; no push until root releases the lane.

## Decisions (root, 2026-10-31)

1. Host glue answers the navigation policy check with Ignore, explicitly and synchronously (not C:/wk/src), and
   `HTMLFormElement.requestSubmit` and `submit` are unexcluded. Probe: `submit()` fires no submit event but does fire
   formdata; `requestSubmit()` fires a cancelable SubmitEvent with the submitter, and preventDefault stops formdata;
   two requestSubmit calls in a row each fire; an invalid submitter throws; the document is never replaced. Rerun the
   full existing batch to show that the Ignore answer changes no other probe.
2. FormData entries: a generator mapping for `File or USVString` in which each entry carries a kind tag (String or
   File). String entries read normally; only reading a File entry's contents returns RV_ERR_UNSUPPORTED until H11.
   `get`, `getAll` and an entries snapshot (`iterableBindings`) work on mixed lists. The managed side models
   FormDataEntryValue as a union whose File case is opaque until H11; recorded as a qualification.
3. SubmitEvent and FormDataEvent constructors through generated `constructors` entries; I02's RvEventInit unchanged.
4. Scope: the whole group (WebCore producer, Core contract and browser provider, Views native provider, shared
   conformance fixture; managed29 / Views 0.1.19) on JIT, NativeAOT and Chromium. Managed work stacks on I02's Core
   #277 (88e75d3f) and Views #33 (b5dc03e9), forward-merging the I12 and G02/G12 managed branches when root sends them.
   Everything stays local until root releases pushes.
