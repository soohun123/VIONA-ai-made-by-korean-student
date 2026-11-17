import json,sys,traceback,time,re
import engine
from generation_resources import release_generation
engine.startup()
print(json.dumps({'kind':'ready','ready':engine.llm is not None,'error':engine.load_error,'limit':engine.model_limit,'gpu_layers':engine.effective_gpu_layers,'gpu_fallback':engine.gpu_fallback,'placement':engine.placement,'text_adapter':engine.text_adapter}),flush=True)
for line in sys.stdin:
    chunks=None
    try:
        data=json.loads(line)
        req=engine.ChatRequest(**data)
        msgs=engine.prepare(req)
        start=time.perf_counter();first=None;parts=[];finish_reason=None
        chunks=engine.llm.create_chat_completion(messages=msgs,max_tokens=req.max_tokens,temperature=req.temperature,top_p=req.top_p,repeat_penalty=req.repeat_penalty,frequency_penalty=req.frequency_penalty,stream=True,seed=42)
        for chunk in chunks:
            if chunk['choices'][0].get('finish_reason'):finish_reason=chunk['choices'][0]['finish_reason']
            delta=chunk['choices'][0].get('delta',{}).get('content') or ''
            if delta:
                if first is None:first=time.perf_counter()
                finished_code=False
                if req.code_only:
                    previous=''.join(parts);combined=previous+delta
                    opening=re.match(r'^\s*```[\w.+-]*\r?\n',combined)
                    if opening:
                        closing=re.search(r'(?m)^```[ \t]*(?:\r?\n|$)',combined[opening.end():])
                        if closing:
                            end_code=opening.end()+closing.end()
                            delta=combined[len(previous):end_code];finished_code=True
                parts.append(delta)
                print(json.dumps({'token':delta},ensure_ascii=False),flush=True)
                if finished_code:
                    finish_reason='code_fence'
                    chunks.close();break
        end=time.perf_counter()
        count=len(engine.llm.tokenize(''.join(parts).encode('utf-8'),add_bos=False))
        release_generation(engine.llm,chunks);chunks=None
        print(json.dumps({'done':True,'metrics':{'finish_reason':finish_reason or 'unknown','input_proxy_tokens':engine.last_input_proxy_tokens,'input_count_method':'JSON tokenizer + message reserve; not exact chat-template usage','context_messages':len(msgs),'output_tokens':count,'token_count_method':'retokenized output, no EOS','elapsed_seconds':end-start,'ttft_seconds':first-start if first else None,'tokens_per_second':count/max(end-start,.001),'decode_tokens_per_second':max(0,count-1)/max(end-(first or start),.001)}}),flush=True)
    except Exception as e:
        print(json.dumps({'error':str(e)},ensure_ascii=False),flush=True)
    finally:
        release_generation(engine.llm,chunks)
