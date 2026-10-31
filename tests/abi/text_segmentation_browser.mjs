// Chromium oracle for tests/abi/text_segmentation.py: writes tests/fixtures/text-segmentation-oracle.json.
// Records Intl.Segmenter graphemes, words (with isWordLike) and sentences, and the line-break opportunities of
// Chromium's non-standard Intl.v8BreakIterator, since Intl.Segmenter has no line granularity. Also records how each
// locale of the fixture resolves, or the error it raises.
import {createRequire} from 'node:module';
import {readFileSync, writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

const fixtures = new URL('../fixtures/', import.meta.url);
const input = JSON.parse(readFileSync(new URL('text-segmentation-cases.json', fixtures), 'utf8'));

function record({cases, locales}) {
  const segments = (locale, granularity, text) =>
    [...new Intl.Segmenter(locale, {granularity}).segment(text)].map(s => granularity === 'word' ? [s.index, s.segment, s.isWordLike] : [s.index, s.segment]);
  const lines = (locale, text) => {
    const out = [];
    const iterator = new Intl.v8BreakIterator([locale], {type: 'line'});
    iterator.adoptText(text);
    let start = iterator.first();
    for (let end = iterator.next(); end !== -1; end = iterator.next()) { out.push([start, text.slice(start, end)]); start = end; }
    return out;
  };
  const attempt = f => { try { return f(); } catch (e) { return {error: e.name}; } };
  return {
    defaultLocale: new Intl.Segmenter().resolvedOptions().locale,
    cases: cases.map(([locale, text]) => ({locale, text, grapheme: segments(locale, 'grapheme', text), word: segments(locale, 'word', text),
                                           sentence: segments(locale, 'sentence', text), line: lines(locale, text)})),
    locales: locales.map(locale => ({locale, resolved: attempt(() => new Intl.Segmenter(locale, {granularity: 'word'}).resolvedOptions().locale),
                                     words: attempt(() => segments(locale, 'word', 'a.b c'))})),
  };
}

const browser = await chromium.launch({headless: true});
try {
  const tab = await (await browser.newContext()).newPage();
  const result = await tab.evaluate(record, input);
  writeFileSync(new URL('text-segmentation-oracle.json', fixtures), JSON.stringify({browser: browser.version(), ...result}, null, 1) + '\n');
  console.log('text segmentation oracle', browser.version(), result.cases.length, 'cases', result.locales.length, 'locales');
} finally {
  await browser.close();
}
