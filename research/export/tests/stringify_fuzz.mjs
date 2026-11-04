// Test-only: JSON.stringify(v) and JSON.stringify(v, null, 2) for each value of a JSON array file.
// Usage: node stringify_fuzz.mjs /abs/values.json
import fs from 'node:fs/promises';
const values = JSON.parse(await fs.readFile(process.argv[2], 'utf8'));
process.stdout.write(JSON.stringify(values.map(v => [JSON.stringify(v), JSON.stringify(v, null, 2)])));
