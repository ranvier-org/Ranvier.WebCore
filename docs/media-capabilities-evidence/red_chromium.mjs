// RED survey of navigator.mediaCapabilities in Chromium over media-cases.json: writes red-chromium.json next to this file.
import {createRequire} from 'node:module';
import {readFileSync, writeFileSync} from 'node:fs';
const here = new URL('.', import.meta.url);
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
const cases = JSON.parse(readFileSync(new URL('../../tests/fixtures/media-capabilities-cases.json', here), 'utf8'));
const browser = await chromium.launch({headless: true});
const out = {browser: browser.version()};
try {
  const tab = await browser.newPage();
  await tab.setContent('<!doctype html><body>');
  out.members = await tab.evaluate(() => ({mediaCapabilities: 'mediaCapabilities' in navigator,
    decodingInfo: typeof navigator.mediaCapabilities?.decodingInfo, encodingInfo: typeof navigator.mediaCapabilities?.encodingInfo}));
  out.results = await tab.evaluate(async cases => {
    const config = (c) => {
      const r = {type: c.type};
      if ('video' in c) r.video = {contentType: c.video, ...cases.video, ...(c.framerate !== undefined ? {framerate: c.framerate} : {}),
        ...(c.hdrMetadataType ? {hdrMetadataType: c.hdrMetadataType} : {}), ...(c.colorGamut ? {colorGamut: c.colorGamut} : {}),
        ...(c.transferFunction ? {transferFunction: c.transferFunction} : {})};
      if ('audio' in c) { r.audio = {contentType: c.audio};
        if (c.channels !== undefined) r.audio.channels = c.channels; if (c.audioBitrate !== undefined) r.audio.bitrate = c.audioBitrate;
        if (c.samplerate !== undefined) r.audio.samplerate = c.samplerate; if (c.spatialRendering !== undefined) r.audio.spatialRendering = c.spatialRendering; }
      return r;
    };
    const run = async (kind, list) => { const rows = [];
      for (const c of list) { try { const i = await navigator.mediaCapabilities[kind](config(c));
          rows.push({name: c.name, supported: i.supported, smooth: i.smooth, powerEfficient: i.powerEfficient}); }
        catch (e) { rows.push({name: c.name, error: e.name}); } }
      return rows; };
    return {decoding: await run('decodingInfo', cases.decoding), encoding: await run('encodingInfo', cases.encoding)};
  }, cases);
} finally { await browser.close(); }
writeFileSync(new URL('red-chromium.json', here), JSON.stringify(out, null, 1));
console.log(JSON.stringify(out, null, 1));
