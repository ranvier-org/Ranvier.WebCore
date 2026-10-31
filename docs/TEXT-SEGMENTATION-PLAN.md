# T06 text segmentation plan

## Core and view state

- **Core primitives used:** none inside the native exports or the segmenter service. A view that segments text
  from state computes the segments in a memo (`createMemoWithComparer` with string equality on the text and the
  locale skips unchanged input), and a caret or selection that moves by grapheme or word reads those segments in
  an effect.
- **View-owned state:** none. Segmentation is a pure function of the text, the granularity and the locale; the
  engine's ICU holds the break rules and dictionaries, and a call returns an owned copy of the boundaries.

**Goal:** split text into graphemes, words (with `isWordLike`), sentences and line-break opportunities with the
engine's own ICU 77, the iterators WebKit uses for caret movement and line breaking, and compare them with
Chromium 156 (Ranvier.WebCore #76). A word, sentence or line boundary is always a grapheme boundary.

**Trees:** native `C:/wk/native-segment`, branch `codex/native-api-text-segmentation`, from H13's `d7e395c`;
D14 (Native34) merges before allocation. Reservation Native35/ABI43, DOM alpha.38, Views 0.1.28, backend
alpha.28; Views kinds start at 66.

## Measured RED (Native33 runtime ICU against Chromium 156.0.8078.4)

`C:/wk/t06-artifacts/red` holds 20 cases in nine locales: combining marks, ZWJ, flag and skin-tone emoji, CRLF,
Indic conjuncts, Hangul, Thai and CJK dictionary words, contractions, numbers, URLs, abbreviations and
right-to-left text.

- The runtime's ICU (`ubrk_*` in `icuuc77.dll`) agrees with `Intl.Segmenter` on graphemes 20/20 and sentences
  20/20, and on words 17/20. The three word differences are one rule: Chromium breaks at a full stop between
  letters (`p.m`, `a.b@c.example`, `Z.B`), where UAX #29 keeps one word.
- `Intl.Segmenter` has no line granularity. Chromium's `Intl.v8BreakIterator({type: 'line'})` wraps its ICU
  line iterator and is the line oracle: 20/20.
- .NET `StringInfo` agrees on graphemes 18/20: it splits both Indic conjuncts (UAX #29 GB9c). .NET has no word,
  sentence or line segmentation.
- The ABI has no segmentation export.

## Native surface (ABI43, hand-written, `rv_abi_has("text-segmentation")`)

`Intl.Segmenter` is JavaScript-runtime functionality, not WebCore IDL, so the export is hand-written in the host:
`rv_text_segment(granularity, locale, text, length, result)` takes UTF-16 text and a UTF-8 BCP 47 locale, and
returns an owned array of segment start offsets in UTF-16 code units with a word-like flag per segment, released
by `rv_text_segments_release`. Graphemes use WebKit's caret iterator (`TextBreakIterator::CaretMode`), lines its
line iterator (`LineMode`, default behaviour), and words and sentences ICU's iterators opened with the locale,
since WTF's shared word and sentence iterators ignore it.

## Scope

- Line-break opportunities are CSS `line-break: normal` only; `loose`, `strict` and `anywhere` are layout concerns
  outside T06.
- A locale that is not a well-formed BCP 47 tag raises a RangeError, as `Intl.Segmenter` does. A well-formed tag ICU
  does not know falls back to the root locale; the result reports ICU's valid locale, where Chromium reports its
  default (`en-GB` in the oracle). The Windows packages carry ICU 77 with every break-iterator rule and dictionary
  file (scripts/icu_data.py keeps the whole `brkitr` tree) and English locale resources only; the Linux and macOS
  packages carry no ICU and use the system's (config/wpe.cmake, config/mac.cmake), so `rv_text_segmentation_version`
  reports it and the probe checks exact results only on the ICU they were measured with.

## Proof

1. **RED:** `tests/abi/text_segmentation.py` fails on Native33 because the export is absent.
2. **Native GREEN** on `artifacts/native35-candidate-N`: every case at every granularity against the Chromium
   oracle, the grapheme-boundary invariant, null, length and locale errors, the wrong thread, and a result held past
   `rv_host_destroy`.
3. **Managed GREEN:** the shared conformance fixture runs on native JIT, NativeAOT and Chromium.
