// Chromium oracle for tests/abi/binary_values.py: writes tests/fixtures/binary-values-oracle.json.
// Records Blob and File construction, type normalization, line endings, slicing, UTF-8 decoding, data URLs,
// FileReader abort, FileList through a file input and FormData File entries.
import {createRequire} from 'node:module';
import {writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

// Runs in the page. Every case returns plain JSON; bytes are lowercase hex strings.
const measure = async () => {
  const hex = async blob => [...new Uint8Array(await blob.arrayBuffer())].map(b => b.toString(16).padStart(2, '0')).join('');
  const describe = async blob => ({size: blob.size, type: blob.type, bytes: await hex(blob),
    ...(blob instanceof File ? {name: blob.name, lastModified: blob.lastModified} : {})});
  const bytes = list => new Uint8Array(list);
  const cases = {};
  cases.parts = await describe(new Blob(['h\u00e9llo', bytes([0, 1, 255]), new Blob(['ab']), '\ud800x'], {type: 'Text/Plain'}));
  cases.empty = await describe(new Blob());
  cases.emptyParts = await describe(new Blob([], {type: 'a/b'}));
  cases.view = await describe(new Blob([bytes([1, 2, 3, 4, 5]).subarray(1, 4)]));
  cases.types = {};
  for (const type of ['Text/Plain', 'text/\u00e9', 'a\u007fb', '  ', 'text/plain;charset=UTF-8', ''])
    cases.types[JSON.stringify(type)] = new Blob([], {type}).type;
  cases.endings = {};
  for (const endings of ['transparent', 'native'])
    cases.endings[endings] = await hex(new Blob(['a\nb\r\nc\rd'], {endings}));
  const source = new Blob(['0123456789'], {type: 'text/plain'});
  const slices = [[], [1, 3], [-2], [0, -1], [3, 1], [undefined, undefined, 'X/Y'], [100, 200], [-100], [2, 8, 'text/\u00e9'], [1.9, 4.2]];
  cases.slices = [];
  for (const args of slices)
    cases.slices.push({args: args.map(a => a === undefined ? null : a), ...(await describe(source.slice(...args)))});
  cases.sliceOfSlice = await describe(source.slice(2, 8).slice(1, -1));
  cases.file = await describe(new File(['abc'], 'a/b.txt', {type: 'TEXT/X', lastModified: 1234}));
  cases.fileNegative = await describe(new File([], 'n', {lastModified: -5}));
  const before = Date.now();
  const now = new File([], 'now');
  cases.fileDefaultLastModifiedNow = now.lastModified >= before && now.lastModified <= Date.now();
  cases.fileOfFile = await describe(new File([new File(['xy'], 'inner', {lastModified: 1})], 'outer', {lastModified: 2}));
  cases.text = {};
  for (const [name, list] of Object.entries({bom: [0xef, 0xbb, 0xbf, 0x41], invalid: [0xff, 0x41], truncated: [0xe2, 0x82],
    surrogate: [0xed, 0xa0, 0x80], ascii: [0x68, 0x69]}))
    cases.text[name] = await new Blob([bytes(list)]).text();
  const reader = (blob, method, ...args) => new Promise(resolve => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = () => resolve({error: r.error && r.error.name});
    r[method](blob, ...args);
  });
  cases.dataUrl = {
    typed: await reader(new Blob(['hi'], {type: 'text/plain'}), 'readAsDataURL'),
    untyped: await reader(new Blob(['hi']), 'readAsDataURL'),
    empty: await reader(new Blob([]), 'readAsDataURL'),
    params: await reader(new Blob(['hi'], {type: 'text/plain;charset=utf-8'}), 'readAsDataURL'),
  };
  cases.abort = await new Promise(resolve => {
    const r = new FileReader();
    const events = [];
    for (const type of ['loadstart', 'progress', 'load', 'abort', 'error', 'loadend'])
      r.addEventListener(type, () => events.push(type));
    r.readAsArrayBuffer(new Blob([new Uint8Array(1 << 20)]));
    const during = r.readyState;
    r.abort();
    setTimeout(() => resolve({during, after: r.readyState, result: r.result, error: r.error && r.error.name, events}), 50);
  });
  const big = new Uint8Array(1 << 20);
  for (let i = 0; i < big.length; i++) big[i] = (i * 31 + 7) & 255;
  const bigBlob = new Blob([big]);
  const bigBack = new Uint8Array(await bigBlob.arrayBuffer());
  let sum = 0;
  for (const b of bigBack) sum = (sum * 33 + b) >>> 0;
  cases.big = {size: bigBlob.size, checksum: sum};

  const form = document.createElement('form');
  const input = document.createElement('input');
  input.type = 'file';
  input.name = 'upload';
  form.append(input);
  document.body.append(form);
  const emptyEntry = new FormData(form).get('upload');
  cases.emptyFileInput = {files: input.files.length, entry: await describe(emptyEntry), isFile: emptyEntry instanceof File,
    lastModifiedNow: Math.abs(emptyEntry.lastModified - Date.now()) < 60000};
  delete cases.emptyFileInput.entry.lastModified;
  const transfer = new DataTransfer();
  transfer.items.add(new File(['one'], 'one.txt', {type: 'text/plain', lastModified: 10}));
  transfer.items.add(new File([bytes([9, 8])], 'two.bin', {lastModified: 20}));
  input.files = transfer.files;
  const list = input.files;
  cases.fileList = {length: list.length, item0: await describe(list.item(0)), item1: await describe(list.item(1)),
    item2: list.item(2), same: list.item(0) === list.item(0)};
  const formEntries = [];
  for (const [name, value] of new FormData(form))
    formEntries.push({name, value: typeof value === 'string' ? value : await describe(value)});
  cases.formFromInput = formEntries;
  const data = new FormData();
  const plain = new Blob(['p'], {type: 'text/p'});
  data.append('a', plain);
  data.append('b', plain, 'named.txt');
  data.append('c', list.item(0));
  data.append('d', list.item(0), 'renamed');
  data.set('e', new Blob([]));
  const converted = data.get('a');
  cases.formData = {};
  for (const name of ['a', 'b', 'c', 'd', 'e']) {
    const value = data.get(name);
    cases.formData[name] = {...(await describe(value)), isFile: value instanceof File, sameAsInput: value === list.item(0)};
    delete cases.formData[name].lastModified;
  }
  cases.formData.convertedLastModifiedNow = Math.abs(converted.lastModified - Date.now()) < 60000;
  cases.formData.copiedLastModified = data.get('d').lastModified;
  return cases;
};

if (import.meta.url === `file:///${process.argv[1].replaceAll('\\', '/')}`) {
  const browser = await chromium.launch({headless: true});
  try {
    const tab = await (await browser.newContext()).newPage();
    await tab.setContent('<!doctype html><body></body>');
    const cases = await tab.evaluate(measure);
    const result = {browser: browser.version(), headless: 'new', cases};
    writeFileSync(new URL('../fixtures/binary-values-oracle.json', import.meta.url), JSON.stringify(result, null, 2) + '\n');
    console.log(JSON.stringify(result, null, 2));
  } finally {
    await browser.close();
  }
}
