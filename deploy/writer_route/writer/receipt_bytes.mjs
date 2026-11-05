// Shared actual helper transport guards; no executable/path comes from model data.
import {TextDecoder} from 'node:util';
export function boundedUtf8Collector(limit=1048576){
  let bytes=0;const chunks=[];
  return {
    add(chunk){const b=Buffer.from(chunk);if(bytes+b.length>limit)throw new Error('SOURCE_HELPER_OUTPUT_LIMIT');bytes+=b.length;chunks.push(b);},
    text(){return new TextDecoder('utf-8',{fatal:true}).decode(Buffer.concat(chunks,bytes));},
    get bytes(){return bytes;}
  };
}
export function assertSourceReceipt(verified,pin,expectedBytes){
  if(!verified||verified.path!==pin.path||verified.bytes!==expectedBytes||verified.sha256!==pin.sha256||verified.kind!==pin.kind)throw new Error('SOURCE_HELPER_RECEIPT_MISMATCH');
}
