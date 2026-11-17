"""Actual early stream close, WASI-only code check, then unrelated chat."""
import json,re,urllib.request
from pathlib import Path
from validate_install import chat,get
from sandbox_eval import Sandbox
payload={'messages':[{'role':'user','content':'Write only one fenced Python code block defining add(a,b) that returns a+b. No explanation.'}],'max_tokens':256,'temperature':0,'top_p':1,'code_only':True}
req=urllib.request.Request('http://127.0.0.1:8000/chat/stream',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
events=[]
with urllib.request.urlopen(req,timeout=120) as response:
    for line in response:events.append(json.loads(line))
assert not any(e.get('error') for e in events),events
assert any(e.get('done') for e in events),events
text=''.join(e.get('token','') for e in events)
match=re.fullmatch(r'\s*```(?:python)?\s*\n(.*?)\n```\s*',text,re.S);assert match,text
sandbox=Sandbox().run(match[1]+"\nassert add(19,23)==42\nassert add(-2,2)==0\nprint('PASS')",5)
assert sandbox['passed'],sandbox
following=chat([{'role':'user','content':'Return only the sum: 19 + 23.'}],32)
assert '42' in following['reply'],following
result={'code':text,'events':events,'wasi_result':sandbox,'following_chat':following,'status':get('/status')}
Path('sampler-code-only-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=True,indent=2))
