// CPS portable writer cross-check (NOT ADMITTED route). Runs the archived writer004
// prepareMatrices (validateCarrier + review-cell checks) on one carrier and prints exactly
// the EXPECTED_SAVED_VALUES.json text writer004 build() would save:
//   JSON.stringify({sheets:[...]}, null, 2) + '\n'
// with the sheet names writer004 gives to worksheets.add(). Never creates a workbook.
// Usage: node writer004_matrices.mjs --writer /abs/writer004.mjs --carrier /abs/carrier.json
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';

try {
  const args = process.argv.slice(2);
  if (args.length !== 4 || args[0] !== '--writer' || args[2] !== '--carrier' || !path.isAbsolute(args[1]) || !path.isAbsolute(args[3])) {
    throw Object.assign(new Error('Usage: node writer004_matrices.mjs --writer /abs/writer004.mjs --carrier /abs/carrier.json'), {code: 'USAGE'});
  }
  const {prepareMatrices} = await import(pathToFileURL(args[1]).href);
  const raw = await fs.readFile(args[3]);
  if (raw.length > 20 * 1024 * 1024) throw Object.assign(new Error('INPUT_SIZE_LIMIT'), {code: 'INPUT_SIZE_LIMIT'});
  // Same decoding as writer004 build(): raw.toString('utf8').replace(/^\ufeff/, '').
  const c = JSON.parse(raw.toString('utf8').replace(/^\ufeff/, ''));
  const {main, components, links, review} = prepareMatrices(c);
  // writer004: worksheets.add('未填研究草稿'), add('來源與審查'), add('組成參考'), add('組成連結');
  // EXPECTED_SAVED_VALUES order: ws, rs, cs, ls.
  const doc = {sheets: [{name: '未填研究草稿', values: main}, {name: '來源與審查', values: review},
                        {name: '組成參考', values: components}, {name: '組成連結', values: links}]};
  process.stdout.write(JSON.stringify(doc, null, 2) + '\n');
} catch (error) {
  process.stderr.write(JSON.stringify({status: 'REJECTED', code: error.code ?? 'ERROR', message: error.message}) + '\n');
  process.exitCode = 1;
}
