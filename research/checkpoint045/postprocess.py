"""Fail closed on completion. Preserve outer and compact bytes; expand only explicit references."""
import argparse,hashlib,json
from pathlib import Path
from strict_input import strict_load
from compact_expand import decode,expand,encode_bounded,LIMIT
from inline_null_profile import require_inline_null_reasons

def sha(b):return hashlib.sha256(b).hexdigest()

def check_events(raw):
    if len(raw)>LIMIT:raise ValueError('EVENT_SIZE_LIMIT')
    census={};messages=[];started=False;complete=False
    for line in raw.splitlines():
        if not line.strip():continue
        e=strict_load(line,LIMIT)
        if type(e) is not dict:raise ValueError('EVENT_OBJECT_REQUIRED')
        typ=e.get('type')
        if complete:raise ValueError('EVENT_AFTER_COMPLETION')
        if typ not in ('thread.started','turn.started','turn.completed','item.started','item.updated','item.completed'):raise ValueError('UNEXPECTED_EVENT_TYPE')
        census[typ]=census.get(typ,0)+1
        if typ=='turn.started':
            if started:raise ValueError('MULTIPLE_TURNS')
            started=True
        if typ.startswith('item.'):
            if not started:raise ValueError('ITEM_BEFORE_TURN')
            item=e.get('item')
            if type(item) is not dict or item.get('type') not in ('reasoning','agent_message'):raise ValueError('UNEXPECTED_TOOL_OR_ITEM_EVENT')
            census['item:'+item['type']]=census.get('item:'+item['type'],0)+1
            if typ=='item.completed' and item['type']=='agent_message':
                if type(item.get('text')) is not str:raise ValueError('MESSAGE_TEXT_REQUIRED')
                messages.append(item['text'])
        if typ=='turn.completed':
            if not started or len(messages)!=1:raise ValueError('INCOMPLETE_TURN')
            complete=True
    if census.get('thread.started')!=1 or not complete or len(messages)!=1:raise ValueError('SINGLE_COMPLETE_TURN_MESSAGE_REQUIRED')
    return census,messages[0]

def check_completion(result):
    if type(result) is not dict or result.get('timed_out') is not False or result.get('exit_code')!=0 or result.get('error') is not None or result.get('own_process_exited') is not True or result.get('capture_complete') is not True:
        raise ValueError('NORMAL_COMPLETION_REQUIRED')

def check_agreement(message,envelope):
    if strict_load(message.encode('utf-8'),LIMIT)!=strict_load(envelope,LIMIT):
        raise ValueError('EVENT_RESPONSE_ENVELOPE_MISMATCH')

def event_timings(raw,observations):
    result=[];offset=0
    lines=raw.splitlines(keepends=True)
    if len(lines)!=len(observations):raise ValueError('TIMING_LINE_COUNT_MISMATCH')
    previous=-1
    for line,ob in zip(lines,observations):
        end=offset+len(line)
        if ob.get('line_start')!=offset or ob.get('line_end')!=end:raise ValueError('TIMING_BYTE_RANGE_MISMATCH')
        ms=ob.get('observed_ms')
        if type(ms) is not int or ms<previous:raise ValueError('TIMING_NOT_MONOTONIC')
        previous=ms;offset=end
        e=strict_load(line,LIMIT)
        result.append({**ob,'type':e.get('type'),'item_type':e.get('item',{}).get('type')})
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);a=p.parse_args();d=Path(a.run).resolve(strict=True)
    check_completion(strict_load((d/'model.result.json').read_bytes(),LIMIT))
    env=(d/'response.json').read_bytes();raw=(d/'stdout.raw').read_bytes();census,message=check_events(raw)
    check_agreement(message,env)
    compact,c=decode(env)
    profile_check=require_inline_null_reasons(c)
    carrier,mapping=expand(c)
    encoded=encode_bounded(carrier)
    obs=[strict_load(x,LIMIT) for x in (d/'model.stdout-observations.jsonl').read_bytes().splitlines() if x.strip()]
    timeline=event_timings(raw,obs)
    for name,b in [('compact.json',compact),('carrier.json',encoded)]:
        with (d/name).open('xb') as f:f.write(b)
    receipt={'status':'COMPACT_EXPANDED_WITHOUT_MATERIAL_REPAIR','transport_profile':profile_check['profile'],'profile_check':profile_check,'response_sha256':sha(env),'compact_sha256':sha(compact),'carrier_sha256':sha(encoded),'event_census':census,'event_observations':timeline,'transformation':'JSON string decode, explicit model references copied and structural keys/headers supplied; no facts inferred','model_authored_items':len(c['items']),'expanded_items':len(carrier['items']),'model_authored_components':len(c['components']),'expanded_components':len(carrier['components']),'mapping':mapping,'structural_guard_required':True,'semantic_approval':False}
    with (d/'BOUNDARY_RESULT.json').open('x',encoding='utf-8') as f:json.dump(receipt,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in receipt.items() if k not in ('mapping','event_observations')}))
if __name__=='__main__':main()
