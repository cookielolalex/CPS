import fs from 'node:fs/promises';
import path from 'node:path';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const args=Object.fromEntries(process.argv.slice(2).reduce((rows,v,i,a)=>i%2===0?[...rows,[v,a[i+1]]]:rows,[]));
const input=args['--input'],out=args['--output'];
if(!input||!out) throw new Error('Usage: export_workbooks.mjs --input generated_run --output fresh_folder');
await fs.mkdir(out,{recursive:true});
const receipt=JSON.parse(await fs.readFile(path.join(input,'BATCH_RECEIPT.json'),'utf8'));
const audit=[];
const font='Microsoft JhengHei';
function table(wb,name,rows,widths){
  const s=wb.worksheets.add(name);s.showGridLines=false;
  s.getRangeByIndexes(0,0,rows.length,rows[0].length).values=rows.map(r=>r.map(v=>typeof v==='string'&&v.startsWith('=')?"'"+v:v));
  const used=s.getRangeByIndexes(0,0,rows.length,rows[0].length);
  used.format.font={name:font,size:10,color:'#243247'};used.format.verticalAlignment='top';used.format.wrapText=true;used.format.rowHeight=28;
  const header=s.getRangeByIndexes(0,0,1,rows[0].length);
  header.format.fill='#314B66';header.format.font={name:font,size:10,bold:true,color:'#FFFFFF'};header.format.rowHeight=36;
  widths.forEach((width,i)=>s.getRangeByIndexes(0,i,rows.length,1).format.columnWidth=width);
  for(let i=1;i<rows.length;i++){
    const lines=Math.max(...rows[i].map((v,j)=>String(v??'').split(/\r?\n/).reduce((n,x)=>n+Math.max(1,Math.ceil(x.replace(/[^\u0000-\u00ff]/g,'xx').length/Math.max(8,widths[j]-2))),0)));
    s.getRangeByIndexes(i,0,1,rows[i].length).format.rowHeight=Math.min(409,Math.max(28,lines*16+8));
  }
  s.freezePanes.freezeRows(1);return s;
}
for(const item of receipt.outputs){
  const data=JSON.parse(await fs.readFile(path.join(input,item.case_id+'.json'),'utf8'));
  const wb=Workbook.create();
  const rows=[data.headers,...data.rows.map(r=>r.values)];
  const s=table(wb,'未填',rows,[30,30,56,60,9,12,12,14,20,20,20,14,20,20,16,12,16]);
  for(const col of ['F','G','H','P','Q']) if(rows.length>1)s.getRange(`${col}2:${col}${rows.length}`).setNumberFormat('General');
  const notes=[['項目','內容'],['工程編號',item.case_id],['狀態',data.status==='blocked'?'來源不足：未產生材料列':'待核對草稿：尚未達自動部署標準'],
    ['用途','合約轉未填供料草稿；後續沿用格式整理。'],['來源範圍','只使用允許合約；未知資料留空。'],['需要核對','有效版本、供料範圍、盤體歸屬、分析倍率及未識別欄位。'],
    ['說明','G/H採購價格留空；Q僅於已建立材料單價來源角色時填列。'],
    ...data.sources.map(x=>['來源檔案',x.path]),...data.sources.map(x=>['來源SHA256',x.sha256])];
  const check=table(wb,'核對事項',notes,[24,105]);
  wb.recalculate();
  const inspection=await wb.inspect({kind:'table',range:`'未填'!A1:Q${Math.min(rows.length,4)}`,include:'values,formulas',tableMaxRows:4,tableMaxCols:17,maxChars:1200});
  const basename=`${item.case_id}_CPS未填草稿`;
  // One preview for each sheet; complete saved-value parity is checked separately.
  for(const [name,range] of [['未填',`A1:F${Math.min(rows.length,6)}`],['核對事項','A1:B7']]){
    const preview=await wb.render({sheetName:name,range,scale:1,format:'png'});
    await fs.writeFile(path.join(out,`${basename}_${name}.png`),new Uint8Array(await preview.arrayBuffer()));
  }
  const file=await SpreadsheetFile.exportXlsx(wb);await file.save(path.join(out,basename+'.xlsx'));
  audit.push({case_id:item.case_id,rows:data.rows.length,filename:basename+'.xlsx',inspection:inspection.ndjson,status:data.status});
}
await fs.writeFile(path.join(out,'EXPORT_RECEIPT.json'),JSON.stringify(audit,null,2));
console.log(JSON.stringify({exported:audit.length,output:out}));
