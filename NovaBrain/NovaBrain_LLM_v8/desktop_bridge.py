"""Allowlisted semantic desktop bridge. Never uses a shell or physical input."""
import json,re,subprocess,threading,time
from pathlib import Path
BIN=Path('D:/수혀니당/CodexTools/AgentDesktop/agent-desktop.exe')
class DesktopBridge:
    def __init__(self):
        self.session=None;self.lock=threading.Lock();self.refs={};self.window=None
        self.cached_snapshot=None
        self.last_overlay=None
    def run(self,args):
        cmd=[str(BIN)]+(['--session',self.session] if self.session else [])+args
        try:
            p=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',timeout=25,creationflags=subprocess.CREATE_NO_WINDOW)
            return json.loads(p.stdout)
        except subprocess.TimeoutExpired:return {'ok':False,'error':{'code':'TIMEOUT','message':'데스크톱 도구 응답 시간 초과. 상태를 다시 읽어 주세요.'}}
        except (OSError,ValueError):return {'ok':False,'error':{'code':'UNAVAILABLE','message':'agent-desktop을 실행할 수 없습니다.'}}
    def activate(self):
        if not BIN.is_file():return {'ok':False,'error':{'message':'agent-desktop 설치가 필요합니다.'}}
        if not self.session:
            status=self.run(['status'])
            if not status.get('ok'):return status
            started=self.run(['session','start','--name','VIONA Desktop'])
            if not started.get('ok'):return started
            self.session=started['data']['session_id']
        overlay=self.run(['cursor-overlay','enable','--label','VIONA','--size','1.4'])
        if not overlay.get('ok') or not overlay.get('data',{}).get('rendered'):
            return {'ok':False,'error':{'code':'CURSOR_UNAVAILABLE','message':'표시 커서를 렌더링할 수 없어 데스크톱 작업을 중단했습니다.'}}
        self.last_overlay={'ok':True,'rendered':True,'label':'VIONA'}
        return None
    def windows(self):
        with self.lock:
            error=self.activate()
            if error:return error
            result=self.run(['list-windows']);result['cursor_overlay']=self.last_overlay
            return result
    def snapshot(self,window_id,root=None,refresh=False):
        with self.lock:
            error=self.activate()
            if error:return error
            key=(window_id,root)
            if not refresh and self.cached_snapshot and self.cached_snapshot[0]==key and time.monotonic()-self.cached_snapshot[1]<2:
                result=json.loads(json.dumps(self.cached_snapshot[2]));result['data']['cached']=True;return result
            args=['snapshot','--compact','-i','--max-depth','4','--timeout-ms','8000']
            if root:
                if root not in self.refs:return {'ok':False,'error':{'message':'대상을 다시 읽어 주세요.'}}
                args+=['--root',root]
            else:
                if not re.fullmatch(r'w-[0-9]+',window_id or ''):return {'ok':False,'error':{'message':'올바른 창을 선택해 주세요.'}}
                args+=['--window-id',window_id,'--skeleton']
            result=self.run(args)
            if result.get('ok'):
                if not root:self.refs={};self.window=window_id
                nodes=[]
                def visit(node,depth=0):
                    ref=node.get('ref_id');states=node.get('states',[])
                    if ref:
                        clean={k:node[k] for k in ('name','role','ref_id','available_actions','children_count','states') if k in node}
                        clean['available_actions']=[a for a in node.get('available_actions',[]) if a!='SetFocus']
                        if 'value' in node and not any(re.search('password|protected',str(s),re.I) for s in states):clean['value']=str(node['value'])[:160]
                        self.refs[ref]={'node':clean,'time':time.monotonic()};nodes.append(clean)
                    for child in node.get('children',[]):visit(child,depth+1)
                visit(result['data']['tree'])
                result['data']['nodes']=nodes[:60]
                result['data']['omitted_nodes']=max(0,len(nodes)-60)
                result['data'].pop('tree',None)
                self.cached_snapshot=(key,time.monotonic(),json.loads(json.dumps(result)))
            return result
    def action(self,action,ref,value,confirmed):
        with self.lock:
            if action not in ('click','set-value','check','uncheck') or not confirmed:
                return {'ok':False,'error':{'code':'POLICY_DENIED','message':'대상과 동작 확인이 필요합니다.'}}
            entry=self.refs.get(ref)
            if not entry or time.monotonic()-entry['time']>180:
                return {'ok':False,'error':{'code':'STALE_REF','message':'대상 정보가 오래됐습니다. 다시 읽어 주세요.'}}
            node=entry['node']
            if re.search(r'닫기|종료|삭제|제거|포맷|close|exit|delete|remove|format',node.get('name',''),re.I):
                return {'ok':False,'error':{'code':'POLICY_DENIED','message':'종료·삭제 동작은 이 도구에서 허용하지 않습니다.'}}
            expected={'click':'Click','set-value':'SetValue','check':'Toggle','uncheck':'Toggle'}[action]
            if expected not in node.get('available_actions',[]):
                return {'ok':False,'error':{'code':'ACTION_NOT_SUPPORTED','message':'이 요소에는 해당 semantic 동작이 없습니다. 물리 입력으로 전환하지 않습니다.'}}
            error=self.activate()
            if error:return error
            result=self.set_value(ref,value) if action=='set-value' else self.run([action,ref])
            self.refs={}
            self.cached_snapshot=None
            # No retries: delivered_unverified is explicitly surfaced to the user.
            return result
    def set_value(self,ref,value):
        try:
            p=subprocess.run([str(BIN),'--session',self.session,'set-value',ref,'--stdin'],input=value,capture_output=True,text=True,encoding='utf-8',timeout=25,creationflags=subprocess.CREATE_NO_WINDOW)
            return json.loads(p.stdout)
        except (OSError,ValueError,subprocess.TimeoutExpired):return {'ok':False,'error':{'message':'입력 결과를 확인할 수 없습니다. 다시 읽은 후 상태를 확인해 주세요.'}}

desktop=DesktopBridge()
