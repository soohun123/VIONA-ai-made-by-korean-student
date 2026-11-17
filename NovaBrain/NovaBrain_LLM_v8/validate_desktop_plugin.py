"""Operate only the non-activating NovaBrain test window using semantic UIA."""
import ctypes,json,time,urllib.request
from pathlib import Path
from validate_install import get
ROOT=Path(__file__).resolve().parent
token=get('/api/capabilities')['tool_token']
def tool(**payload):
    req=urllib.request.Request('http://127.0.0.1:8000/api/desktop',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','X-NovaBrain-Token':token})
    with urllib.request.urlopen(req,timeout=40) as response:
        data=json.load(response)
    if not data.get('ok'):raise RuntimeError(data.get('error'))
    return data
class Point(ctypes.Structure):_fields_=[('x',ctypes.c_long),('y',ctypes.c_long)]
user32=ctypes.windll.user32
user32.GetForegroundWindow.restype=ctypes.c_void_p
def input_state():
    point=Point();user32.GetCursorPos(ctypes.byref(point))
    return {'foreground':user32.GetForegroundWindow(),'pointer':[point.x,point.y]}
result={'physical_input_used':False,'clipboard_used':False}
try:
    windows=tool(operation='windows');result['cursor_overlay']=windows['cursor_overlay']
    assert windows['cursor_overlay']['ok'] and windows['cursor_overlay']['rendered']
    result['before']=input_state()
    target=next((w for w in windows['data'] if w['title']=='NovaBrain Plugin Test 20261114'),None)
    deadline=time.monotonic()+8
    while target is None and time.monotonic()<deadline:
        time.sleep(.2);windows=tool(operation='windows')
        target=next((w for w in windows['data'] if w['title']=='NovaBrain Plugin Test 20261114'),None)
    if target is None:raise RuntimeError('전용 테스트 창을 찾지 못했습니다. 다른 창에는 동작하지 않습니다.')
    snapshot=tool(operation='snapshot',window_id=target['id'],refresh=True)
    nodes=snapshot['data']['nodes'];result['node_count']=len(nodes)
    edit=next(n for n in nodes if n.get('name')=='NovaProbeInput')
    button=next(n for n in nodes if n.get('name')=='NovaProbeButton')
    value='NovaBrain semantic input '+str(time.time_ns())
    result['set_value']=tool(operation='set-value',ref=edit['ref_id'],value=value,confirmed=True)
    # Actions invalidate refs. Observe once more before the next action.
    nodes=tool(operation='snapshot',window_id=target['id'],refresh=True)['data']['nodes']
    button=next(n for n in nodes if n.get('name')=='NovaProbeButton')
    result['click']=tool(operation='click',ref=button['ref_id'],confirmed=True)
    deadline=time.monotonic()+3
    while not (ROOT/'plugin-probe-state.txt').exists() and time.monotonic()<deadline:time.sleep(.05)
    result['readback']=(ROOT/'plugin-probe-state.txt').read_text(encoding='utf-8-sig')
    assert result['readback']=='clicked:'+value
    result['after']=input_state();result['foreground_unchanged']=result['before']['foreground']==result['after']['foreground'];result['pointer_unchanged']=result['before']['pointer']==result['after']['pointer']
    assert result['foreground_unchanged'] and result['pointer_unchanged']
    result['passed']=True
finally:
    (ROOT/'plugin-probe-stop.txt').write_text('stop own probe',encoding='utf-8')
    (ROOT/'desktop-plugin-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=True,indent=2))
