// Actual writer source authorization, without creation/render/export.
import fs from 'node:fs/promises';
import {validateCarrier,authorizeSource,prepareMatrices} from './writer004.mjs';
try {
  const a=process.argv.slice(2);
  if(a.length!==4||a[0]!=='--carrier'||a[2]!=='--allowlist')throw new Error('USAGE');
  const cr=await fs.readFile(a[1]),ar=await fs.readFile(a[3]);
  if(cr.length>20*1024*1024||ar.length>256*1024)throw new Error('INPUT_SIZE_LIMIT');
  const c=JSON.parse(cr.toString('utf8')),allow=JSON.parse(ar.toString('utf8'));
  const counts=validateCarrier(c),source=await authorizeSource(c,allow),matrices=prepareMatrices(c);
  const label=matrices.review.find(row=>row[0]==='來源');
  console.log(JSON.stringify({status:'WRITER_SOURCE_AUTHORIZED_NO_EXPORT',counts,source,source_caption:label[1],source_check_caption:label[5],draft_schema:c.source.kind==='cached_xls'?'cps.cached-xls-research-draft.v1':'cps.cached-xlsx-research-draft.v1',exported:false,semantic_accuracy:null}));
}catch(e){console.error(JSON.stringify({status:'REJECTED',message:e.message}));process.exitCode=1;}
