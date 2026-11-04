// Test-only parity probe, independent of writer004_matrices.mjs: run the archived writer004
// prepareMatrices on each carrier file and return the EXPECTED_SAVED_VALUES.json text writer004
// would save, or writer004's refusal code.
// Usage: node parity_matrices.mjs /abs/writer004.mjs /abs/carrier-paths.json
import fs from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
const [writerPath, listPath] = process.argv.slice(2);
const {prepareMatrices} = await import(pathToFileURL(writerPath).href);
const paths = JSON.parse(await fs.readFile(listPath, 'utf8'));
const out = [];
for (const p of paths) {
  try {
    const c = JSON.parse((await fs.readFile(p)).toString('utf8').replace(/^\ufeff/, ''));
    const m = prepareMatrices(c);
    const doc = {sheets: [{name: '未填研究草稿', values: m.main}, {name: '來源與審查', values: m.review},
                          {name: '組成參考', values: m.components}, {name: '組成連結', values: m.links}]};
    out.push({ok: true, text: JSON.stringify(doc, null, 2) + '\n'});
  } catch (e) { out.push({ok: false, code: e.code ?? 'ERROR', message: e.message}); }
}
process.stdout.write(JSON.stringify(out));
