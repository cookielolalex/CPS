// Run the real writer004 prepareMatrices (validateCarrier + review-cell checks) on many carriers.
// Usage: node parity_batch.mjs /abs/writer004.mjs /abs/carriers.json  -> JSON array of 'PASS' or error code
import fs from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
const [writerPath, inPath] = process.argv.slice(2);
const {prepareMatrices} = await import(pathToFileURL(writerPath).href);
const carriers = JSON.parse(await fs.readFile(inPath, 'utf8'));
console.log(JSON.stringify(carriers.map(c => { try { prepareMatrices(c); return 'PASS'; } catch (e) { return e.code ?? ('ERROR:' + e.message); } })));
