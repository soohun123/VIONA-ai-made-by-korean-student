"""Deterministic context reduction without spending model tokens on summaries."""
import json,re
PROFILES={'economy':(4800,512,3),'balanced':(9000,1024,6),'full':(0,16384,80)}

def compact_history(messages,profile='economy',notes=''):
    limit,_,max_turns=PROFILES[profile]
    history=[dict(role=m['role'],content=m['content']) for m in messages if m['role'] in ('user','assistant') and m['content'].strip()]
    groups=[]
    for message in history:
        if message['role']=='user':groups.append([message])
        elif groups:groups[-1].append(message)
    kept=[];size=0
    for group in reversed(groups):
        length=sum(len(m['content']) for m in group)
        # Always preserve the latest question and preceding exchange, including code.
        if len(kept)>=2 and (len(kept)>=max_turns or limit and size+length>limit):break
        kept.insert(0,group);size+=length
    reference_pinned=False;reference_missing=False
    latest=history[-1]['content'] if history else ''
    if re.search(r'아까|이전|앞서|처음|earlier|previous',latest,re.I):
        anchors=set(re.findall(r'\b[A-Za-z_]\w{2,}\b',latest))
        anchors-={'the','and','please','previous','earlier','function','code','fix','change'}
        for group in reversed(groups[:-len(kept)] if kept else groups):
            code='\n'.join(m['content'] for m in group if m['role']=='assistant')
            if not any(re.search(r'\b(?:def|function|class)\s+'+re.escape(name)+r'\b',code) for name in anchors):continue
            candidate=[group]+kept[-2:]
            length=sum(len(m['content']) for g in candidate for m in g)
            if not limit or length<=limit:
                kept=candidate;size=length;reference_pinned=True
            else:reference_missing=True
            break
    # Resolve explicit references to earlier user facts, not just function names.
    # Select the most recent matching user statement so corrections beat old values.
    if re.search(r'아까|이전|앞서|처음|기억',latest):
        keys=[key for key in ('이름','색','경로','목표','버전','예산','언어') if key in latest]
        if keys:
            for group in reversed(groups[:-1]):
                if not any(key in group[0]['content'] for key in keys):continue
                if any(group is g for g in kept):break
                candidate=[group]+kept[-2:]
                length=sum(len(m['content']) for g in candidate for m in g)
                if not limit or length<=limit:
                    kept=candidate;size=length;reference_pinned=True
                else:reference_missing=True
                break
    retained_ids={id(g) for g in kept}
    removed=[g for g in groups if id(g) not in retained_ids]
    facts=[]
    for group in removed:
        for line in group[0]['content'].splitlines():
            if re.search(r'이름|목표|선호|프로젝트|경로|기억|환경|버전|하지 마|원하지',line):facts.append(line.strip()[:160])
    memory='\n'.join(dict.fromkeys(facts[-6:]))[-640:]
    if notes.strip():memory='사용자가 고정한 기억:\n'+notes.strip()[:1200]+('\n이전 사용자 발언 일부:\n'+memory if memory else '')
    elif memory:memory='이전 사용자 발언 일부(새 요청 아님):\n'+memory
    if reference_missing:memory+='\n사용자가 참조한 이전 내용은 입력 예산에 들어가지 않았습니다. 내용을 추측하지 말고 필요한 원문을 요청하세요.'
    retained=[m for g in kept for m in g]
    return retained,memory,{'profile':profile,'original_messages':len(history),'kept_messages':len(retained),'removed_turns':len(removed),'original_chars':sum(len(m['content']) for m in history),'kept_chars':sum(len(m['content']) for m in retained),'memory_chars':len(memory),'reference_pinned':reference_pinned,'reference_missing':reference_missing}

def compact_desktop(value,profile='economy'):
    limit=1200 if profile=='economy' else 2800 if profile=='balanced' else 4500
    try:
        data=json.loads(value) if isinstance(value,str) else value
        rows=data if isinstance(data,list) else data.get('nodes',[])
        compact=[]
        for node in rows:
            row={k:node[k] for k in ('ref_id','role','name','available_actions') if k in node}
            if 'name' in row:row['name']=str(row['name'])[:100]
            candidate=json.dumps(compact+[row],ensure_ascii=False,separators=(',',':'))
            if len(candidate)>limit:break
            compact.append(row)
        return json.dumps(compact,ensure_ascii=False,separators=(',',':'))
    except (ValueError,TypeError,AttributeError):return str(value)[:limit]
