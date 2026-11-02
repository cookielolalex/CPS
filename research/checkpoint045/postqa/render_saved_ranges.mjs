// Read/reopen/render only, adapted from frozen render_saved.mjs. Never export or edit.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const args=process.argv.slice(2);
if(args.length!==4||args[0]!=='--output'||args[2]!=='--dest'||!path.isAbsolute(args[1])||!path.isAbsolute(args[3]))throw new Error('Usage --output absolute-workbook-output --dest new-owned-visual-directory');
const d=args[1],dir=args[3];
const expected=JSON.parse(await fs.readFile(path.join(d,'EXPECTED_SAVED_VALUES.json'),'utf8'));
const book=path.join(d,'research-draft.xlsx'),before=await fs.readFile(book),hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(book));
await fs.mkdir(dir,{recursive:false});
const ranges=[];
for(let s=0;s<expected.sheets.length;s++){
  const sheet=expected.sheets[s],n=sheet.values.length;
  if(sheet.name==='未填研究草稿'||sheet.name==='組成參考'){
    const prefix=sheet.name==='未填研究草稿'?'main':'components';
    for(let start=1;start<=n;start+=12){
      const end=Math.min(n,start+11),tag=String(start).padStart(4,'0');
      ranges.push({sheet:sheet.name,range:`A${start}:H${end}`,name:`${prefix}-left-${tag}.png`,coverage:`complete-${prefix}`},
                  {sheet:sheet.name,range:`I${start}:Q${end}`,name:`${prefix}-right-${tag}.png`,coverage:`complete-${prefix}`});
    }
  }else if(sheet.name==='組成連結'){
    for(let start=1;start<=n;start+=12)ranges.push({sheet:sheet.name,range:`A${start}:H${Math.min(n,start+11)}`,name:`links-${String(start).padStart(4,'0')}.png`,coverage:'complete-links'});
  }else if(sheet.name==='來源與審查'){
    const starts=[...new Set([1,Math.max(1,Math.floor(n/2)-5),Math.max(1,n-11)])].sort((a,b)=>a-b);
    for(const start of starts)ranges.push({sheet:sheet.name,range:`A${start}:G${Math.min(n,start+11)}`,name:`review-sample-${String(start).padStart(4,'0')}.png`,coverage:'sampled-review-first-middle-last'});
  }else throw new Error('UNKNOWN_SAVED_SHEET');
}
for(const r of ranges){const b=await wb.render({sheetName:r.sheet,range:r.range,scale:1,format:'png'});await fs.writeFile(path.join(dir,r.name),new Uint8Array(await b.arrayBuffer()),{flag:'wx'});}
if(hash(await fs.readFile(book))!==hash(before))throw new Error('SAVED_WORKBOOK_CHANGED_DURING_READONLY_RENDER');
await fs.writeFile(path.join(dir,'RENDER_MANIFEST.json'),JSON.stringify({status:'RENDERED_AWAITING_VISUAL_INSPECTION',xlsx_sha256:hash(before),saved_workbook_reopened:true,main_17_columns_all_rows:true,components_17_columns_all_rows:true,links_all_rows:true,review_sheet_coverage:'Sampled first/middle/last up to12rows each; not complete review-sheet visual QA',ranges},null,2),{flag:'wx'});
console.log(JSON.stringify({status:'RENDERED_AWAITING_VISUAL_INSPECTION',main_ranges:ranges.filter(r=>r.coverage==='complete-main').length,component_ranges:ranges.filter(r=>r.coverage==='complete-components').length,link_ranges:ranges.filter(r=>r.coverage==='complete-links').length,review_sample_ranges:ranges.filter(r=>r.coverage==='sampled-review-first-middle-last').length,actual_visual_inspection_complete:false}));
