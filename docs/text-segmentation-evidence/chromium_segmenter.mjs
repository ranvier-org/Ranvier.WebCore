// Records Chromium's Intl.Segmenter output for C:/wk/t06-artifacts/red/cases.json.
import {createRequire} from 'node:module';
import {readFileSync, writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
const cases = JSON.parse(readFileSync(process.argv[2], 'utf8')).cases;
const browser = await chromium.launch({headless: true});
const tab = await (await browser.newContext()).newPage();
const result = await tab.evaluate(cases => {
  const run = (locale, granularity, text) =>
    [...new Intl.Segmenter(locale, {granularity}).segment(text)].map(s => granularity === 'word' ? [s.index, s.segment, s.isWordLike] : [s.index, s.segment]);
  return {
    icu: typeof Intl.v8BreakIterator === 'function' ? 'v8' : null,
    resolved: new Intl.Segmenter('th', {granularity: 'word'}).resolvedOptions(),
    // Line breaks: Intl.Segmenter has no line granularity; Chromium's non-standard Intl.v8BreakIterator wraps ICU's line iterator.
    line: null,
    cases: cases.map(([locale, text]) => {
      const lines = [];
      const iterator = new Intl.v8BreakIterator([locale], {type: 'line'});
      iterator.adoptText(text);
      let start = iterator.first();
      for (let end = iterator.next(); end !== -1; end = iterator.next()) { lines.push([start, text.slice(start, end)]); start = end; }
      return {locale, text, grapheme: run(locale, 'grapheme', text), word: run(locale, 'word', text), sentence: run(locale, 'sentence', text), line: lines};
    }),
  };
}, cases);
writeFileSync(process.argv[3], JSON.stringify({browser: browser.version(), ...result}, null, 1));
await browser.close();
