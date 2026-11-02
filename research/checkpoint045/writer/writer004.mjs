import fs from 'node:fs/promises';
import {spawn} from 'node:child_process';
import {boundedUtf8Collector,assertSourceReceipt} from './receipt_bytes.mjs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {Workbook, SpreadsheetFile} from '@oai/artifact-tool';

export const HEADERS = Object.freeze(['盤體名稱','盤體規格','材料名稱','規格','單位','數量','單價','複價','型號','廠牌','訂購廠商','工程編號','訂購客戶','使用客戶','需要日期','需要數量','合約價']);
export const COLS = Object.freeze(Array.from({length:17},(_,i)=>String.fromCharCode(65+i)));
export const ROOT = path.dirname(fileURLToPath(import.meta.url));
const sha = b=>crypto.createHash('sha256').update(b).digest('hex');
const fail = (code,location)=>{throw Object.assign(new Error(`${code}: ${location}`),{code,location});};
const obj = (v,p)=>{if(!v || typeof v!=='object' || Array.isArray(v))fail('OBJECT_REQUIRED',p);};
const keys = (v,ks,p)=>{obj(v,p);const a=Object.keys(v).sort(),b=[...ks].sort();if(JSON.stringify(a)!==JSON.stringify(b))fail('EXACT_KEYS_REQUIRED',p);};
const str = (v,p,empty=false)=>{if(typeof v!=='string' || (!empty&&!v.trim()) || v.length>30000 || /[\u0000-\u0008\u000b\u000c\u000e-\u001f]/u.test(v))fail('STRING_REQUIRED',p);};
const maybeText=(v,p)=>{if(v!==null)str(v,p,true);};
const strings=(v,p)=>{if(!Array.isArray(v)||v.length>500)fail('STRING_ARRAY_REQUIRED',p);v.forEach((s,i)=>str(s,`${p}[${i}]`));};
const id=(v,p)=>{str(v,p);if(!/^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$/.test(v))fail('ID_REQUIRED',p);};
function address(a){if(typeof a!=='string'||!/^([A-Z]{1,3})([1-9][0-9]{0,6})$/.test(a))fail('CELL_ADDRESS','location');const m=a.match(/^([A-Z]+)([0-9]+)$/);let c=0;for(const x of m[1])c=c*26+x.charCodeAt(0)-64;const r=Number(m[2]);if(c>16384||r>1048576)fail('CELL_BOUNDS','location');return[c,r];}
function bounds(s){if(typeof s!=='string')fail('RANGE_REQUIRED','source');const a=s.split(':');if(a.length<1||a.length>2)fail('RANGE_REQUIRED','source');const lo=address(a[0]),hi=address(a.at(-1));if(lo[0]>hi[0]||lo[1]>hi[1])fail('RANGE_ORDER','source');return[lo,hi];}
function locator(v,source,p){keys(v,['sheet','cells','views'],p);str(v.sheet,p);if(!Array.isArray(v.cells)||!v.cells.length||v.cells.length>1000||!Array.isArray(v.views)||!v.views.length||v.views.length>1000||new Set(v.cells).size!==v.cells.length||new Set(v.views).size!==v.views.length)fail('LOCATION_SHAPE',p);const bb=v.views.map(n=>{if(!Number.isInteger(n)||n<1||n>source.views.length)fail('VIEW_BOUNDS',p);const view=source.views[n-1];if(view.sheet!==v.sheet)fail('SHEET_VIEW_MISMATCH',p);return bounds(view.range);});const cc=v.cells.map(address);for(const[c,r]of cc)if(!bb.some(([lo,hi])=>lo[0]<=c&&c<=hi[0]&&lo[1]<=r&&r<=hi[1]))fail('CELL_OUTSIDE_VIEWS',p);for(const[lo,hi]of bb)if(!cc.some(([c,r])=>lo[0]<=c&&c<=hi[0]&&lo[1]<=r&&r<=hi[1]))fail('UNRELATED_VIEW',p);}

const numeric=(v,p)=>{if(typeof v!=='number'||!Number.isFinite(v)||Math.abs(v)>Number.MAX_SAFE_INTEGER)fail('FINITE_SAFE_NUMBER_REQUIRED',p);};
const numericRaw=(v,p)=>{str(v,p);const t=v.trim();if(!/^[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?$/.test(t))fail('UNSUPPORTED_NUMERIC_TEXT',p);const n=Number(t.replaceAll(',',''));numeric(n,p);return n;};
const formulaLike=s=>typeof s==='string'&&/^[\s\uFEFF]*[=+@-]/u.test(s);
const forbiddenPath=p=>/(?:未填|已填|電機圖|板金|鈑金|歷史|(?:^|[\\/_. -])(?:ok|targets?|reserved|drawings?|histor(?:y|ical|ies))(?=[\\/_. -]|$))/iu.test(p);
function sourceShape(s,p){
  keys(s,['kind','path','sha256','views'],p);if(!['cached_xlsx','cached_xls'].includes(s.kind))fail('SOURCE_KIND',p);str(s.path,`${p}.path`);
  if(s.path.length>2048||s.path.normalize('NFC')!==s.path)fail('NONCANONICAL_UNICODE_PATH',p);
  if(!/^[A-Z]:\\/.test(s.path)||s.path.includes('/'))fail('CANONICAL_LOCAL_ABSOLUTE_PATH_REQUIRED',p);
  const parts=s.path.slice(3).split('\\');
  if(!parts.length||parts.some(x=>!x||x==='.'||x==='..'||/[ .]$/.test(x)||/[<>:"|?*\x00-\x1f]/.test(x)||/^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)/i.test(x)))fail('NONCANONICAL_PATH_COMPONENT',p);
  if(path.win32.normalize(s.path)!==s.path||path.win32.extname(s.path).toLowerCase()!==(s.kind==='cached_xls'?'.xls':'.xlsx'))fail('SOURCE_KIND_EXTENSION_MISMATCH',p);
  if(forbiddenPath(s.path))fail('FORBIDDEN_SOURCE_PATH',p);
  if(!/^[a-f0-9]{64}$/.test(s.sha256))fail('SHA256_REQUIRED',p);
  if(!Array.isArray(s.views)||s.views.length<1||s.views.length>1000)fail('VIEWS_REQUIRED',p);s.views.forEach((v,i)=>{keys(v,['id','sheet','range'],p);if(v.id!==i+1)fail('VIEW_ID',p);str(v.sheet,p);bounds(v.range);});
}
function metadataData(v,p='metadata',depth=0){
  if(depth>12)fail('METADATA_TOO_DEEP',p);
  if(v===null||typeof v==='boolean')return;
  if(typeof v==='number'){numeric(v,p);return;}
  if(typeof v==='string'){
    str(v,p,true);
    if(/(?:[A-Za-z]:[\\/]|\\\\|file:\/\/|https?:\/\/)/i.test(v))fail('EXTRA_SOURCE_REFERENCE',p);
    return;
  }
  if(Array.isArray(v)){if(v.length>1000)fail('METADATA_TOO_LARGE',p);v.forEach((x,i)=>metadataData(x,`${p}[${i}]`,depth+1));return;}
  obj(v,p);
  for(const [k,x]of Object.entries(v)){
    if(/^(?:paths?|files?|uris?|urls?|callbacks?|scripts?|formulas?|sources?|source_path|source_file|source_url|source_uri|annex|annexes|attachments?)$/i.test(k))fail('EXTRA_SOURCE_REFERENCE',`${p}.${k}`);
    metadataData(x,`${p}.${k}`,depth+1);
  }
}

/** Structural/evidence validation only. It does not certify the transcription against the original cached XLSX. */
export function validateCarrier(c){
  keys(c,['schema','headers','case_id','family_id','source','metadata','groups','items','components','nonitems','limitations'],'carrier');
  if(c.schema!==(c.source?.kind==='cached_xls'?'cps.cached-xls-research-carrier.v1':'cps.cached-xlsx-research-carrier.v1'))fail('SCHEMA_MISMATCH','schema');
  if(JSON.stringify(c.headers)!==JSON.stringify(HEADERS))fail('EXACT_HEADERS_REQUIRED','headers');
  id(c.case_id,'case_id');id(c.family_id,'family_id');sourceShape(c.source,'source');obj(c.metadata,'metadata');metadataData(c.metadata);strings(c.limitations,'limitations');
  if(!Array.isArray(c.groups)||c.groups.length>2000)fail('GROUPS_REQUIRED','groups');
  if(!Array.isArray(c.items)||c.items.length<1||c.items.length>2000)fail('ITEMS_REQUIRED','items');
  if(!Array.isArray(c.nonitems)||c.nonitems.length>5000)fail('NONITEMS_REQUIRED','nonitems');
  if(!Array.isArray(c.components)||c.components.length>2000)fail('COMPONENTS_REQUIRED','components');
  const all=[...c.items,...c.components];const groups=new Map(),seen=new Set(),covered=new Set();
  for(const [i,g]of c.groups.entries()){
    const p=`groups[${i}]`;keys(g,['id','name','specification','location','anchor','quantity_basis','limitations'],p);id(g.id,`${p}.id`);
    if(groups.has(g.id))fail('DUPLICATE_GROUP_ID',g.id);
    maybeText(g.name,`${p}.name`);maybeText(g.specification,`${p}.specification`);locator(g.location,c.source,p);g.location.views.forEach(v=>covered.add(v));
    str(g.anchor,`${p}.anchor`);str(g.quantity_basis,`${p}.quantity_basis`);strings(g.limitations,`${p}.limitations`);
    if(g.name===null&&g.limitations.length===0)fail('UNRESOLVED_GROUP_REASON_REQUIRED',p);
    groups.set(g.id,g);
  }
  for(const [i,r]of all.entries()){
    const p=`items[${i}]`;keys(r,['id','group_id','location','anchor','raw','values','evidence','null_reasons','status','review_reasons',...(i>=c.items.length?['composition']:[])],p);id(r.id,`${p}.id`);
    if(seen.has(r.id))fail('DUPLICATE_ITEM_ID',r.id);seen.add(r.id);
    if(r.group_id!==null&&!groups.has(r.group_id))fail('UNKNOWN_GROUP_ID',p);
    locator(r.location,c.source,p);r.location.views.forEach(v=>covered.add(v));str(r.anchor,`${p}.anchor`);
    keys(r.raw,['description','unit','quantity','unit_price','amount','remarks'],`${p}.raw`);
    for(const [k,v]of Object.entries(r.raw))maybeText(v,`${p}.raw.${k}`);
    if(!Array.isArray(r.values)||r.values.length!==17)fail('SEVENTEEN_VALUES_REQUIRED',p);
    if(!['research_draft','held'].includes(r.status))fail('REVIEW_STATUS_REQUIRED',p);strings(r.review_reasons,`${p}.review_reasons`);
    if(r.status==='held'&&!r.review_reasons.length)fail('HELD_REASON_REQUIRED',p);
    if(r.values[2]===null&&r.status!=='held')fail('UNRESOLVED_ITEM_MUST_BE_HELD',p);
    obj(r.evidence,`${p}.evidence`);obj(r.null_reasons,`${p}.null_reasons`);
    const requiredEvidence=[],requiredNulls=[];
    r.values.forEach((v,j)=>{
      const col=COLS[j],vp=`${p}.values.${col}`;
      if(v===null){requiredNulls.push(col);str(r.null_reasons[col],`${p}.null_reasons.${col}`);return;}
      if([6,7].includes(j))fail('PURCHASE_PRICE_MUST_BE_BLANK',vp);
      if([5,15,16].includes(j))numeric(v,vp);else str(v,vp);
      if(formulaLike(v))fail('FORMULA_STRING_FORBIDDEN',vp);
      requiredEvidence.push(col);const e=r.evidence[col];obj(e,`${p}.evidence.${col}`);
      if(Object.hasOwn(e,'selection_evidence')){
        if(col!=='L')fail('SELECTION_ONLY_ENGINEERING_ID',vp);
        keys(e,['selection_evidence','transformation'],`${p}.evidence.${col}`);str(e.selection_evidence,`${vp}.selection_evidence`);str(e.transformation,`${vp}.transformation`);
        if(/(?:[A-Za-z]:[\\/]|\\\\|file:\/\/|https?:\/\/)/i.test(e.selection_evidence))fail('EXTRA_SOURCE_REFERENCE',vp);
      }else{
        keys(e,['location','anchor','raw_text','transformation'],`${p}.evidence.${col}`);locator(e.location,c.source,vp);str(e.anchor,`${vp}.anchor`);str(e.raw_text,`${vp}.raw_text`);str(e.transformation,`${vp}.transformation`);
        if([5,15,16].includes(j)&&numericRaw(e.raw_text,vp)!==v)fail('NUMERIC_EVIDENCE_MISMATCH',vp);
      }
    });
    keys(r.evidence,requiredEvidence,`${p}.evidence`);keys(r.null_reasons,requiredNulls,`${p}.null_reasons`);
    if(r.group_id===null&&(r.values[0]!==null||r.values[1]!==null))fail('UNGROUPED_AB_MUST_BE_BLANK',p);
    if(r.values[5]!==null&&numericRaw(r.raw.quantity,`${p}.raw.quantity`)!==r.values[5])fail('SOURCE_QUANTITY_MISMATCH',p);
    if(r.values[16]!==null&&numericRaw(r.raw.unit_price,`${p}.raw.unit_price`)!==r.values[16])fail('SOURCE_UNIT_PRICE_MISMATCH',p);
    if(r.values[4]!==null&&r.values[4]!==r.raw.unit)fail('SOURCE_UNIT_MISMATCH',p);
  }
  const detailIds=new Set(c.items.map(r=>r.id));
  for(const r of c.components){const x=r.composition;keys(x,['parent_id','basis_quantity','basis_unit','basis_location','basis_raw'],'composition');id(x.parent_id,'composition');if(!detailIds.has(x.parent_id)||x.parent_id===r.id)fail('COMPONENT_PARENT_MUST_BE_DETAIL',r.id);numeric(x.basis_quantity,r.id);if(x.basis_quantity<=0||numericRaw(x.basis_raw,r.id)!==x.basis_quantity)fail('POSITIVE_LITERAL_BASIS_REQUIRED',r.id);str(x.basis_unit,r.id);if(formulaLike(x.basis_unit))fail('FORMULA_STRING_FORBIDDEN',r.id);locator(x.basis_location,c.source,r.id);}
  for(const [i,n]of c.nonitems.entries()){
    const p=`nonitems[${i}]`;keys(n,['location','kind','anchor','text','reason'],p);locator(n.location,c.source,p);n.location.views.forEach(v=>covered.add(v));
    for(const k of ['kind','anchor','reason'])str(n[k],`${p}.${k}`);str(n.text,`${p}.text`,true);
  }
  for(let p=1;p<=c.source.views.length;p++)if(!covered.has(p))fail('VIEW_SCOPE_UNACCOUNTED',String(p));
  return {items:c.items.length,components:c.components.length,groups:c.groups.length,nonitems:c.nonitems.length,held_items:all.filter(r=>r.status==='held').length,views_represented:covered.size};
}

export async function authorizeSource(c,a){
  keys(a,['schema','sources'],'allowlist');if(!['cps.source-allowlist.v1','cps.source-allowlist.v2'].includes(a.schema))fail('ALLOWLIST_SCHEMA','allowlist');
  if(!Array.isArray(a.sources)||a.sources.length<1||a.sources.length>20)fail('ALLOWLIST_SOURCES','allowlist');
  const pins=new Set();for(const s of a.sources){sourceShape(s,'allowlist.sources');if(a.schema==='cps.source-allowlist.v1'&&s.kind!=='cached_xlsx')fail('LEGACY_REQUIRES_ALLOWLIST_V2','allowlist');const k=path.normalize(s.path).toLowerCase();if(pins.has(k))fail('DUPLICATE_SOURCE_PIN',k);pins.add(k);}
  const pin=a.sources.find(s=>s.path===c.source.path&&s.sha256===c.source.sha256&&JSON.stringify(s.views)===JSON.stringify(c.source.views)&&s.kind===c.source.kind);
  if(!pin)fail('SOURCE_NOT_PINNED','source');
  const real=await fs.realpath(pin.path);
  if(path.normalize(real).toLowerCase()!==path.normalize(pin.path).toLowerCase()||forbiddenPath(real))fail('SOURCE_REDIRECTION_FORBIDDEN','source');
  const stat=await fs.stat(real);if(!stat.isFile()||stat.size>100*1024*1024)fail('SOURCE_FILE_LIMIT','source');
  const bytes=await fs.readFile(real);if(sha(bytes)!==pin.sha256)fail('SOURCE_HASH_MISMATCH','source');
  const verified=await verifyOriginalSource(pin);
  assertSourceReceipt(verified,pin,bytes.length);
  return {...verified,reconstructed_view_count:pin.views.length};
}

function reviewRows(c){
  // JSON string encoding prevents source text such as '=...' from becoming formulas.
  // Source cells contain a lossless JSON string/value, with exact unencoded data in source-carrier.json.
  const rows=[['狀態','整份研究稿',null,null,'held','來源語義及正式用途尚待獨立審查','held'],['來源',c.source.kind==='cached_xls'?'選定原始 XLS（BIFF8）':'選定原始 XLSX',null,null,JSON.stringify(c.source),c.source.kind==='cached_xls'?'核對允許原始路徑、SHA256、OLE Workbook 與 BIFF8 記錄；未重算來源公式':'核對允許原始路徑、SHA256 與 ZIP 標頭；未重算來源公式','held']];
  for(const [k,v]of Object.entries(c.metadata))rows.push(['識別資料',JSON.stringify(k),null,null,JSON.stringify(v),'保留輸入識別與限制','held']);
  c.limitations.forEach((v,i)=>rows.push(['全案限制',String(i+1),null,null,JSON.stringify(v),'原載限制','held']));
  c.groups.forEach(g=>rows.push(['群組',g.id,JSON.stringify(g.location),JSON.stringify(g.anchor),JSON.stringify(g),'群組不推導實體箱數或分配','held']));
  [...c.items,...c.components].forEach((r,i)=>{
    rows.push(['項目',r.id,JSON.stringify(r.location),JSON.stringify(r.anchor),JSON.stringify({group_id:r.group_id,sheet:i<c.items.length?'未填研究草稿':'組成參考',saved_row:i<c.items.length?i+2:i-c.items.length+2,composition:r.composition??null,values:r.values}),JSON.stringify(r.review_reasons),r.status]);
    for(const [k,v]of Object.entries(r.raw))rows.push(['原文',`${r.id}.${k}`,JSON.stringify(r.location),JSON.stringify(r.anchor),JSON.stringify(v),'JSON 字串保留原文與換行',r.status]);
    for(const [k,v]of Object.entries(r.evidence))rows.push(['欄位依據',`${r.id}.${k}`,v.location?JSON.stringify(v.location):null,JSON.stringify(v.anchor??'已核對工程選取'),JSON.stringify(v),JSON.stringify(v.transformation),r.status]);
    for(const [k,v]of Object.entries(r.null_reasons))rows.push(['空白原因',`${r.id}.${k}`,JSON.stringify(r.location),JSON.stringify(r.anchor),JSON.stringify(v),'空白不等於零或抽取成功',r.status]);
    r.review_reasons.forEach((v,j)=>rows.push(['待確認',`${r.id}.${j+1}`,JSON.stringify(r.location),JSON.stringify(r.anchor),JSON.stringify(v),'保留受阻列',r.status]));
  });
  c.nonitems.forEach((n,i)=>rows.push([`非材料：${n.kind}`,String(i+1),JSON.stringify(n.location),JSON.stringify(n.anchor),JSON.stringify(n.text),JSON.stringify(n.reason),'held']));
  return rows;
}
function formatSheet(sheet,rows,cols,widths){
  const all=sheet.getRangeByIndexes(0,0,rows,cols);all.format.font={name:'Arial',size:11,color:'#172033'};all.format.verticalAlignment='top';all.format.wrapText=true;all.format.rowHeight=32;
  const h=sheet.getRangeByIndexes(0,0,1,cols);h.format.fill='#29445D';h.format.font={name:'Arial',size:11,bold:true,color:'#FFFFFF'};h.format.horizontalAlignment='center';h.format.verticalAlignment='center';h.format.rowHeight=36;
  widths.forEach((w,j)=>sheet.getRangeByIndexes(0,j,rows,1).format.columnWidth=w);
  sheet.showGridLines=false;sheet.freezePanes.freezeRows(1);sheet.freezePanes.freezeColumns(Math.min(cols,3));
  all.format.autofitRows();h.format.rowHeight=36;
}
async function saveJson(p,v){await fs.writeFile(p,JSON.stringify(v,null,2)+'\n',{flag:'wx'});}

export function prepareMatrices(c){
  validateCarrier(c);
    const main=[HEADERS,...c.items.map(r=>r.values)];
    const components=[HEADERS,...c.components.map(r=>r.values)];
    const links=[['組成識別','組成表列','主項識別','主表列','基準數量','基準單位','基準來源','組成來源'],...c.components.map((r,i)=>[r.id,i+2,r.composition.parent_id,c.items.findIndex(x=>x.id===r.composition.parent_id)+2,r.composition.basis_quantity,r.composition.basis_unit,JSON.stringify(r.composition.basis_location),JSON.stringify(r.location)])];
    const review=[['類型','識別／欄位','工作表／儲存格／重建視圖','來源定位','原文／資料（JSON）','處理／審查原因','狀態'],...reviewRows(c)];
    for(const [i,row]of review.entries())for(const [j,v]of row.entries())if(typeof v==='string'&&(v.length>32767||formulaLike(v)))fail('REVIEW_CELL_UNSAFE_OR_TOO_LONG',`${i+1}:${j+1}`);
    return {main,components,links,review};
}

export async function build(carrierPath,allowlistPath,out){
  for(const [p,k]of [[carrierPath,'carrier'],[allowlistPath,'allowlist'],[out,'out']])if(!path.isAbsolute(p))fail('ABSOLUTE_CLI_PATH_REQUIRED',k);
  const dest=path.resolve(out),rel=path.relative(ROOT,dest);if(!rel||rel.startsWith('..')||path.isAbsolute(rel))fail('OUTPUT_OUTSIDE_WRITER_SCOPE','out');
  const parent=await fs.realpath(path.dirname(dest));const realRoot=await fs.realpath(ROOT);const parentRel=path.relative(realRoot,parent);if(parentRel.startsWith('..')||path.isAbsolute(parentRel))fail('OUTPUT_REDIRECTION_FORBIDDEN','out');
  const raw=await fs.readFile(carrierPath);const allowRaw=await fs.readFile(allowlistPath);if(raw.length>20*1024*1024||allowRaw.length>256*1024)fail('INPUT_SIZE_LIMIT','inputs');
  const c=JSON.parse(raw.toString('utf8').replace(/^\uFEFF/,'')),a=JSON.parse(allowRaw.toString('utf8').replace(/^\uFEFF/,''));
  const counts=validateCarrier(c),source=await authorizeSource(c,a);
  await fs.mkdir(dest,{recursive:false});
  const started=new Date().toISOString();
  await fs.writeFile(path.join(dest,'source-carrier.json'),raw,{flag:'wx'});
  await saveJson(path.join(dest,'INPUT_PINS.json'),{carrier:{path:carrierPath,sha256:sha(raw)},allowlist:{path:allowlistPath,sha256:sha(allowRaw)},source,writer_sha256:sha(await fs.readFile(fileURLToPath(import.meta.url))),started});
  try{
    const {main,components,links,review}=prepareMatrices(c);
    const wb=Workbook.create();const ws=wb.worksheets.add('未填研究草稿'),rs=wb.worksheets.add('來源與審查');ws.tabColor='#29445D';const cs=wb.worksheets.add('組成參考'),ls=wb.worksheets.add('組成連結');
    cs.getRangeByIndexes(0,0,components.length,17).values=components;ls.getRangeByIndexes(0,0,links.length,8).values=links;
    formatSheet(cs,components.length,17,[18,30,38,48,9,12,12,12,20,18,22,18,24,24,18,12,14]);formatSheet(ls,links.length,8,[24,12,24,12,12,12,65,65]);
    ws.getRangeByIndexes(0,0,main.length,17).values=main;rs.getRangeByIndexes(0,0,review.length,7).values=review;
    formatSheet(ws,main.length,17,[18,30,38,48,9,12,12,12,20,18,22,18,24,24,18,12,14]);
    formatSheet(rs,review.length,7,[18,23,38,38,88,62,18]);
    for(const j of [5,15,16]){const r=ws.getRangeByIndexes(1,j,c.items.length,1);r.setNumberFormat('General');r.format.horizontalAlignment='right';}
    ws.getRangeByIndexes(1,6,c.items.length,2).format.fill='#F1F3F5';
    // No formulas are authored; neither source nor output is recalculated.
    const inspection=await wb.inspect({kind:'table',range:`未填研究草稿!A1:Q${Math.min(main.length,12)}`,include:'values,formulas',tableMaxRows:12,tableMaxCols:17,maxChars:18000});
    await fs.writeFile(path.join(dest,'INSPECTION.ndjson'),inspection.ndjson,{flag:'wx'});
    const errors=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:300},summary:'literal error scan; raw source may intentionally contain error text'});
    await fs.writeFile(path.join(dest,'ERROR_SCAN.ndjson'),errors.ndjson,{flag:'wx'});
    const file=await SpreadsheetFile.exportXlsx(wb);await file.save(path.join(dest,'research-draft.xlsx'));
    const renders=[['main-left.png','未填研究草稿',`A1:H${Math.min(main.length,15)}`],['main-right.png','未填研究草稿',`I1:Q${Math.min(main.length,15)}`],['source-review.png','來源與審查',`A1:G${Math.min(review.length,12)}`]];
    for(const [name,sheetName,range]of renders){const b=await wb.render({sheetName,range,scale:1,format:'png'});await fs.writeFile(path.join(dest,name),new Uint8Array(await b.arrayBuffer()),{flag:'wx'});}
    const draft={schema:c.source.kind==='cached_xls'?'cps.cached-xls-research-draft.v1':'cps.cached-xlsx-research-draft.v1',status:'held',headers:HEADERS,carrier:c,writer:{kind:'data-only worksheet assembly',counts,source,formulas:false,arithmetic:false,semantic_source_validation:false,native_excel_validation:false,required_review:'Independent complete source semantic comparison; assembly and source eligibility do not establish correctness.'}};
    await saveJson(path.join(dest,'research-draft.json'),draft);
    await saveJson(path.join(dest,'EXPECTED_SAVED_VALUES.json'),{sheets:[{name:ws.name,values:main},{name:rs.name,values:review},{name:cs.name,values:components},{name:ls.name,values:links}]});
    const result={status:'ASSEMBLED_REVIEW_HELD',counts,source,started,ended:new Date().toISOString(),xlsx_sha256:sha(await fs.readFile(path.join(dest,'research-draft.xlsx'))),native_excel_validation:false,render_review:'pending independent visual inspection'};
    await saveJson(path.join(dest,'BUILD_RESULT.json'),result);return result;
  }catch(e){await saveJson(path.join(dest,'BUILD_FAILURE.json'),{status:'FAILED_PARTIAL_OUTPUT_PRESERVED',message:e.message,stack:e.stack,ended:new Date().toISOString()});throw e;}
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  try{
    const args=process.argv.slice(2);if(args.length!==6||args[0]!=='--carrier'||args[2]!=='--allowlist'||args[4]!=='--out')fail('USAGE','node writer.mjs --carrier absolute.json --allowlist absolute.json --out new-directory');
    console.log(JSON.stringify(await build(args[1],args[3],args[5])));
  }catch(e){console.error(JSON.stringify({status:'REJECTED_OR_FAILED',code:e.code??'ERROR',message:e.message}));process.exitCode=1;}
}

// Fixed implementation helper, never selected by carrier/model arguments.
async function verifyOriginalSource(source) {
  const helper=path.resolve(ROOT,'../source_verify.py');
  if(sha(await fs.readFile(helper))!=="b745adf64e23cb7b96868193de21a98183d6509cd9e3668c9b26adb20d09b87c")fail('SOURCE_HELPER_BINDING_CHANGED','source');
  const executable=String.raw`C:\CPS_LOCAL_USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`;
  return await new Promise((resolve,reject)=>{
    const child=spawn(executable,['-I','-X','utf8','-B',helper,'--source-stdin'],{shell:false,windowsHide:true,stdio:['pipe','pipe','pipe']});
    const out=boundedUtf8Collector(),err=boundedUtf8Collector();let done=false;
    const finish=(error,value)=>{if(done)return;done=true;clearTimeout(timer);error?reject(error):resolve(value);};
    const timer=setTimeout(()=>{child.kill();finish(new Error('SOURCE_HELPER_TIMEOUT'));},10000);
    child.on('error',e=>finish(e));
    child.stdout.on('data',b=>{try{out.add(b);}catch(e){child.kill();finish(e);}});
    child.stderr.on('data',b=>{try{err.add(b);}catch(e){child.kill();finish(e);}});
    child.stdin.on('error',e=>finish(e));
    child.on('close',code=>{try{if(code!==0)return finish(new Error('SOURCE_HELPER_REJECTED:'+err.text()));finish(null,JSON.parse(out.text()));}catch(e){finish(e);}});
    child.stdin.end(JSON.stringify(source));
  });
}
