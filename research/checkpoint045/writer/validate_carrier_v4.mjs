// Structural validation only. Run strict_input.py first. No PDF reads or export.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {validateCarrier} from './writer004.mjs';

try {
  const args = process.argv.slice(2);
  if (args.length !== 2 || args[0] !== '--carrier' || !path.isAbsolute(args[1])) {
    throw new Error('Usage: node validate_carrier.mjs --carrier absolute-carrier.json');
  }
  const raw = await fs.readFile(args[1]);
  if (raw.length > 20 * 1024 * 1024) throw new Error('INPUT_SIZE_LIMIT');
  const carrier = JSON.parse(raw.toString('utf8').replace(/^\uFEFF/, ''));
  const counts = validateCarrier(carrier);
  console.log(JSON.stringify({
    status: 'WRITER_STRUCTURAL_VALIDATION_ONLY',
    carrier_path: args[1],
    carrier_sha256: crypto.createHash('sha256').update(raw).digest('hex'),
    counts,
    source_read: false,
    export_authorized: false,
    semantic_approval: false
  }));
} catch (error) {
  console.error(JSON.stringify({status: 'REJECTED', code: error.code ?? 'ERROR', message: error.message}));
  process.exitCode = 1;
}
