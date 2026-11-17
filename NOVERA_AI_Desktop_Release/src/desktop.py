"""NOVERA desktop: local-only native window, isolated inference, no cloud keys."""
import argparse,base64,ctypes,hashlib,json,logging,os,queue,re,socket,subprocess,sys,threading,time,uuid
from pathlib import Path
import psutil

BUNDLE=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
APP=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]
DATA=Path(os.environ.get('NOVERA_DATA_DIR',str(Path(os.environ.get('LOCALAPPDATA',str(APP)))/'NOVERA AI Desktop')))
DATA.mkdir(parents=True,exist_ok=True)
(DATA/'logs').mkdir(exist_ok=True)
LOG=DATA/'logs/desktop.log'
logging.basicConfig(filename=LOG,encoding='utf-8',level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
HIDDEN=getattr(subprocess,'CREATE_NO_WINDOW',0)

def digest(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()

def atomic(p,d):
    tmp=p.with_suffix('.'+uuid.uuid4().hex+'.tmp');tmp.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(tmp,p)

def command(*args):
    return ([sys.executable] if getattr(sys,'frozen',False) else [sys.executable,str(Path(__file__).resolve())])+list(args)

def terminate(p):
    if p is None:return
    try:
        root=psutil.Process(p.pid);children=root.children(recursive=True)
        for child in reversed(children):
            try:child.terminate()
            except psutil.Error:pass
        if p.poll() is None:root.terminate()
        _,alive=psutil.wait_procs(children+[root],timeout=4)
        for item in alive:
            try:item.kill()
            except psutil.Error:pass
        p.wait(timeout=4)
    except (psutil.Error,subprocess.TimeoutExpired):pass

def gpu():
    try:
        r=subprocess.run(['nvidia-smi','--query-gpu=name,memory.total,memory.free,memory.used,utilization.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=4,creationflags=HIDDEN)
        a=r.stdout.strip().splitlines()[0].split(',');return dict(name=a[0].strip(),total_mib=int(a[1]),free_mib=int(a[2]),used_mib=int(a[3]),utilization=int(a[4]))
    except Exception:return {'name':'CPU only','free_mib':0}

def worker(config):
    for stream in [sys.stdin,sys.stdout,sys.stderr]:
        if stream and hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8',errors='strict')
    c=json.loads(Path(config).read_text(encoding='utf-8'));os.environ.update(OMP_NUM_THREADS=str(c['threads']),OPENBLAS_NUM_THREADS=str(c['threads']),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
    dlls=[]
    nvidia=BUNDLE/'nvidia'
    if not nvidia.exists() and not getattr(sys,'frozen',False):nvidia=APP.parent/'NovaBrain/NovaBrain_LLM_v8/.venv/Lib/site-packages/nvidia'
    for folder in nvidia.glob('*/bin') if nvidia.exists() else []:
        dlls.append(os.add_dll_directory(str(folder)));os.environ['PATH']=str(folder)+os.pathsep+os.environ['PATH']
    for package,name in [('cuda_runtime','cudart64_12.dll'),('cublas','cublasLt64_12.dll'),('cublas','cublas64_12.dll')]:
        path=nvidia/package/'bin'/name
        if not path.exists():path=BUNDLE/name
        if path.exists():dlls.append(ctypes.CDLL(str(path)))
    # llama.cpp and stable-diffusion.cpp ship different DLLs with identical
    # basenames. Preload the text engine's exact pair before importing bindings.
    import importlib.util
    package=Path(next(iter(importlib.util.find_spec('llama_cpp').submodule_search_locations)))
    backend_dir=package/'lib';dlls.append(os.add_dll_directory(str(backend_dir)))
    dlls.append(ctypes.CDLL(str(backend_dir/'ggml-base.dll')))
    native_ggml=ctypes.CDLL(str(backend_dir/'ggml.dll'));dlls.append(native_ggml)
    import llama_cpp
    from llama_cpp import Llama,llama_supports_gpu_offload
    from gguf_metadata import read_metadata
    from generation_resources import release_generation
    meta=read_metadata(c['model']);limit=next((int(v) for k,v in meta.items() if k.endswith('.context_length')),0)
    if not limit or c['context']>limit:raise ValueError('컨텍스트가 모델 한계를 넘습니다.')
    layers=c['gpu_layers'] if llama_supports_gpu_offload() else 0
    kw=dict(model_path=c['model'],n_ctx=c['context'],n_threads=c['threads'],n_threads_batch=c['threads'],n_gpu_layers=layers,n_batch=128,n_ubatch=128,use_mmap=True,verbose=True,lora_path=c.get('text_adapter') or None,lora_scale=1.0)
    try:llm=Llama(**kw)
    except Exception:
        if not layers:raise
        kw['n_gpu_layers']=0;layers=0;llm=Llama(**kw)
    print(json.dumps({'ready':True,'gpu_layers':layers,'context_limit':limit,'text_adapter_loaded':bool(c.get('text_adapter'))}),flush=True)
    for line in sys.stdin:
        chunks=None
        try:
            req=json.loads(line);started=time.monotonic();parts=[];finish_reason=None
            from qwen_guard import budget
            if req.get('guards',True):messages,output_limit,budget_info=budget(req['messages'],llm.tokenize,c['context'],req.get('max_tokens',512))
            else:messages,output_limit,budget_info=req['messages'],req.get('max_tokens',512),{}
            chunks=llm.create_chat_completion(messages=messages,max_tokens=output_limit,temperature=.15 if req.get('coding') else .35,stream=True,seed=42)
            for chunk in chunks:
                if chunk['choices'][0].get('finish_reason'):finish_reason=chunk['choices'][0]['finish_reason']
                token=chunk['choices'][0].get('delta',{}).get('content') or ''
                if token:parts.append(token);print(json.dumps({'token':token},ensure_ascii=False),flush=True)
            n=len(llm.tokenize(''.join(parts).encode(),add_bos=False));elapsed=time.monotonic()-started
            print(json.dumps({'done':True,'tokens':n,'elapsed':elapsed,'tokens_per_second':n/max(elapsed,.001),'finish_reason':finish_reason,'budget':budget_info}),flush=True)
        except Exception as e:print(json.dumps({'error':str(e)}),flush=True)
        finally:release_generation(llm,chunks)

class Controller:
    def __init__(self):
        self._window=None;self.proc=None;self.image_proc=None;self.lock=threading.Lock();self.stopping=False;self.loaded=None;self.q=queue.Queue();self.phase='시작 준비';self.peak_rss=0;self.peak_used=0;self.last_error='';self.restarts=0
        manifest=BUNDLE/'assets/model-sources.json'
        self.models=json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {'models':[],'adapters':[]}
        config=DATA/'settings.json'
        self.settings=json.loads(config.read_text(encoding='utf-8')) if config.exists() else {'mode':'cpu','threads':4,'context':8192,'model':'qwen-viona','adapter':'viona-image15','strength':.3,'text_lora':True}
        extra=DATA/'extra-models.json'
        if extra.exists():self.models['models']+=json.loads(extra.read_text(encoding='utf-8'))
        self.hash_cache={}
        self.web_release=None
        if self.settings.get('follow_web',True):
            try:self._sync_web(False)
            except Exception as e:logging.warning('Website sync unavailable; retain local choices: %s',e)
        threading.Thread(target=self.monitor,daemon=True).start()

    def _sync_web(self,verify=True):
        from website_sync import read_release
        config=json.loads((BUNDLE/'assets/website-source.json').read_text(encoding='utf-8'))
        release=read_release(config['project_root'])
        if verify:
            for row in release['models']+release['adapters']:
                self.verified(row)
                if row.get('text_adapter'):self.verified(row['text_adapter'])
        self.stop_model()
        self.models['models']=[m for m in self.models['models'] if not m['id'].startswith('web-')]+release['models']
        self.models['adapters']=[m for m in self.models['adapters'] if not m['id'].startswith('web-')]+release['adapters']
        text=[m for m in release['models'] if m['kind']=='text'];image=[m for m in release['models'] if m['kind']=='image']
        if text:
            if self.settings['model'] not in {m['id'] for m in text}:self.settings['model']=text[0]['id']
            self.settings['text_lora']=bool(next(m for m in text if m['id']==self.settings['model']).get('text_adapter'))
        if image:
            if self.settings.get('image_model') not in {m['id'] for m in image}:self.settings['image_model']=image[0]['id']
            self.settings['adapter']=next(m for m in image if m['id']==self.settings['image_model']).get('adapter_id','')
        self.settings['follow_web']=True;self.web_release={'id':release['id'],'name':release['name']};logging.info('WEBSITE deployment connected %s',self.web_release)
        return self.web_release

    def sync_web(self):
        if not self.lock.acquire(False):return {'error':'현재 작업 완료 후 배포를 가져와 주세요.'}
        try:
            self.phase='웹 배포 파일·해시 확인 중';result=self._sync_web(True);atomic(DATA/'settings.json',self.settings);self.phase='웹 배포 연결 완료';return {'ok':True,'release':result,'bootstrap':self.bootstrap()}
        except Exception as e:self.phase='배포 연결 오류';return {'error':str(e)}
        finally:self.lock.release()

    def emit(self,kind,**values):
        if self._window:
            try:self._window.evaluate_js('window.dispatchEvent(new CustomEvent("novera",{detail:'+json.dumps({'kind':kind,**values},ensure_ascii=False)+'}))')
            except Exception:pass

    def path(self,row):
        for p in [DATA/row.get('relative','__none__'),APP/'model-pack'/row.get('relative','__none__'),Path(row.get('source','__missing__'))]:
            if p.is_file():return p
        raise ValueError('모델을 찾지 못했습니다. 설정에서 모델을 추가해 주세요: '+row.get('name',''))

    def verified(self,row):
        p=self.path(row);key=(str(p),p.stat().st_mtime_ns,p.stat().st_size)
        if key not in self.hash_cache:self.hash_cache[key]=digest(p)
        if row.get('sha256') and self.hash_cache[key]!=row['sha256']:raise ValueError('모델 해시가 다릅니다: '+p.name)
        logging.info('MODEL verified path=%s sha256=%s',p,self.hash_cache[key]);return p

    def selected(self,kind):
        if kind=='text':
            return next((m for m in self.models['models'] if m['id']==self.settings['model'] and m['kind']=='text'),None)
        return next((m for m in self.models['models'] if m['kind']=='image' and m['id']==self.settings.get('image_model')),None) or next((m for m in self.models['models'] if m['kind']=='image'),None)

    def status(self):
        m=psutil.virtual_memory();g=gpu()
        return {'phase':self.phase,'ready':self.proc is not None and self.proc.poll() is None and self.loaded is not None,'loaded':self.loaded,'free_gib':round(m.available/2**30,2),'used_gib':round(m.used/2**30,2),'gpu':g,'error':self.last_error,'peak_rss_gib':round(self.peak_rss/2**30,3),'peak_system_gib':round(self.peak_used/2**30,3),'restarts':self.restarts}

    def monitor(self):
        while not self.stopping:
            vm=psutil.virtual_memory();self.peak_used=max(self.peak_used,vm.used)
            for p in [self.proc,self.image_proc]:
                if p and p.poll() is None:
                    try:
                        tree=[psutil.Process(p.pid)]+psutil.Process(p.pid).children(recursive=True);rss=sum(x.memory_info().rss for x in tree);self.peak_rss=max(self.peak_rss,rss)
                        if vm.available<2.5*2**30 or vm.used>=13.5*2**30:
                            self.last_error='RAM 보호: 모델을 중단했습니다. 다른 앱의 메모리 사용량을 확인해 주세요.';terminate(p);self.loaded=None;self.phase='메모리 보호 중단';logging.error(self.last_error)
                    except psutil.Error:pass
            if self.proc and self.proc.poll() is not None and self.loaded:
                self.loaded=None;self.last_error='AI 엔진이 종료됐습니다. 다음 요청에서 다시 로드합니다.';self.phase='엔진 종료 감지';self.restarts+=1;logging.error(self.last_error)
            time.sleep(.5)

    def stop_model(self):
        self.loaded=None;terminate(self.proc);self.proc=None

    def load_model(self):
        if self.proc and self.proc.poll() is None and self.loaded:return
        self.stop_model();vm=psutil.virtual_memory()
        if vm.available<5.2*2**30 or vm.used>=13*2**30:raise ValueError('모델 시작에 필요한 여유 RAM이 부족합니다 (최소 5.2GiB).')
        self.phase='모델 파일·해시 확인 중';self.emit('phase',text=self.phase)
        row=self.selected('text')
        if not row:raise ValueError('대화 모델을 선택해 주세요.')
        model=self.verified(row);adapter='';adapter_hash=None
        if self.settings.get('text_lora') and row.get('text_adapter'):
            a=row['text_adapter']
            try:self.path(a);available=True
            except ValueError:available=False
            if available:
                if digest(model)!=a['base_sha256']:raise ValueError('텍스트 LoRA와 베이스 모델이 다릅니다.')
                adapter=str(self.verified(a));adapter_hash=digest(adapter)
            else:logging.warning('Private text LoRA unavailable; loading base only, adapter_loaded=false')
        g=gpu();layers=0
        if self.settings['mode']=='gpu' and g['free_mib']>=1600:layers=min(14,max(0,(g['free_mib']-1000)//50))+1
        config={'model':str(model),'text_adapter':adapter,'threads':self.settings['threads'],'context':self.settings['context'],'gpu_layers':layers}
        cfg=DATA/'worker-config.json';atomic(cfg,config);self.q=queue.Queue();q=self.q
        log=(DATA/'logs/worker.log').open('a',encoding='utf-8');self.phase='모델 로딩 중';self.emit('phase',text=self.phase)
        self.proc=subprocess.Popen(command('--worker',str(cfg)),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,encoding='utf-8',bufsize=1,creationflags=HIDDEN,env={**os.environ,'PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8'});log.close()
        def read(p):
            try:
                for line in p.stdout:
                    try:q.put(json.loads(line))
                    except ValueError:logging.warning('worker non-JSON: %s',line[:200])
            finally:q.put({'error':'모델 프로세스가 종료됐습니다.'})
        threading.Thread(target=read,args=(self.proc,),daemon=True).start()
        try:r=q.get(timeout=180)
        except queue.Empty:self.stop_model();raise RuntimeError('모델 로딩 시간 초과')
        if not r.get('ready'):self.stop_model();raise RuntimeError(r.get('error','모델 로딩 실패'))
        self.loaded={**r,'model_path':str(model),'model_sha256':digest(model),'text_adapter_path':adapter,'text_adapter_sha256':adapter_hash};self.phase='준비됨';self.last_error='';logging.info('ENGINE loaded %s',json.dumps(self.loaded));self.emit('phase',text=self.phase)

    def bootstrap(self):
        from auto_update import current_version
        return {'settings':self.settings,'models':[{'id':x['id'],'name':x['name'],'kind':x['kind']} for x in self.models['models']],'adapters':[{'id':x['id'],'name':x['name']} for x in self.models['adapters']],'status':self.status(),'history':self.history(),'web_release':self.web_release,'app_version':current_version(APP)}

    def chat(self,messages,max_tokens=512,guards=True):
        if not self.lock.acquire(False):return {'error':'현재 작업을 먼저 완료하거나 중단해 주세요.'}
        try:
            if not isinstance(messages,list) or len(messages)>100:raise ValueError('메시지 수가 너무 많습니다.')
            self.load_model();self.phase='응답 생성 중';parts=[]
            from qwen_guard import system_message,coding_request,inspect_python,html_request
            messages=[{'role':m['role'],'content':str(m['content'])} for m in messages if m['role'] in ('user','assistant')]
            prompt=next((m['content'] for m in reversed(messages) if m['role']=='user'),'');coding=coding_request(prompt)
            if guards and html_request(prompt):max_tokens=max(int(max_tokens),1536)
            system=system_message(prompt,(self.selected('text') or {}).get('instructions','')) if guards else 'You are VIONA, a helpful AI assistant in NOVERA AI Desktop. Answer in Korean when asked in Korean. Write correct Python code when requested.'
            request={'messages':[{'role':'system','content':system}]+messages,'max_tokens':min(2048,max(1,int(max_tokens))),'guards':guards,'coding':bool(guards and coding)}
            attempts=[];best=None
            for attempt in range(2 if guards and coding else 1):
                parts=[];self.proc.stdin.write(json.dumps(request,ensure_ascii=False)+'\n');self.proc.stdin.flush()
                while True:
                    r=self.q.get(timeout=180)
                    if r.get('error'):raise RuntimeError(r['error'])
                    if r.get('token'):parts.append(r['token']);self.emit('token',text=r['token'])
                    if r.get('done'):break
                reply=''.join(parts);check=inspect_python(reply,prompt,r.get('finish_reason')) if guards else {'checked':False,'issues':[],'executed':False};attempts.append({'metrics':r,'checks':check})
                score=(bool(check.get('syntax_valid')), -len(check['issues']))
                if best is None or score>best[0]:best=(score,reply,check,r)
                if not check['issues'] or attempt:break
                if check.get('syntax_valid') and check['issues']==['출력 토큰 한도로 답변이 잘렸습니다.']:break
                self.emit('phase',text='코드 정적 검사에서 발견한 문제를 수정 중');self.emit('replace',text='')
                request['messages'] = [{'role':'system','content':system},{'role':'user','content':prompt+'\nReturn one complete Python code block. Address these static issues: '+'; '.join(check['issues'])}]
            _,reply,check,r=best
            self.phase='준비됨';logging.info('CHAT review %s',attempts);return {'text':reply,'metrics':r,'code_checks':check,'attempts':attempts}
        except Exception as e:self.last_error=str(e);self.phase='오류';logging.exception('chat');self.stop_model();return {'error':str(e)}
        finally:self.lock.release()

    def image(self,prompt,steps=12,seed=42):
        if not self.lock.acquire(False):return {'error':'현재 작업이 진행 중입니다.'}
        try:
            self.stop_model();self.phase='이미지 모델·LoRA 확인';self.emit('phase',text=self.phase)
            if psutil.virtual_memory().available<5.5*2**30:raise ValueError('이미지 생성에 필요한 RAM이 부족합니다 (최소 5.5GiB).')
            row=self.selected('image');model=self.verified(row);a=next((x for x in self.models['adapters'] if x['id']==self.settings['adapter']),None)
            adapter=None
            if a:
                if a['base_sha256']!=digest(model):raise ValueError('LoRA 베이스 모델 SHA-256이 일치하지 않습니다.')
                adapter=self.verified(a)
            backend='cuda' if self.settings['mode']=='gpu' and gpu()['free_mib']>=1800 else 'cpu'
            runtime=BUNDLE/'media-runtime'
            if not runtime.exists() and not getattr(sys,'frozen',False):runtime=APP.parent/'NovaBrain/NovaBrain_LLM_v8/media-runtime'
            exe=runtime/backend/'sd-cli.exe';output=DATA/'images'/(uuid.uuid4().hex+'.png');output.parent.mkdir(exist_ok=True)
            text=str(prompt)[:1800]
            if '<lora:' in text.lower():raise ValueError('LoRA는 설정 목록에서 선택해 주세요.')
            if adapter:text+='<lora:'+adapter.stem+':'+str(self.settings['strength'])+'>'
            args=[str(exe),'-m',str(model),'-p',text,'-o',str(output),'-W','256','-H','256','--steps',str(min(30,max(2,int(steps)))),'--seed',str(int(seed)),'-t',str(self.settings['threads']),'--sampling-method','euler','--cfg-scale','6.5','--flash-attn','off','--batched-cfg','off']
            args+=['--backend','te=cpu,vae=cpu,diffusion=cuda0','--offload-to-cpu','--max-vram','1.5'] if backend=='cuda' else ['--backend','cpu']
            if adapter:args+=['--lora-model-dir',str(adapter.parent)]
            env=os.environ.copy()
            env['PATH']=str(BUNDLE)+os.pathsep+os.pathsep.join(str(p) for p in (BUNDLE/'nvidia').glob('*/bin'))+os.pathsep+env.get('PATH','')
            logpath=DATA/'logs'/('image-'+output.stem+'.log');self.phase='이미지 생성 중';self.emit('phase',text=self.phase)
            logging.info('IMAGE base=%s base_hash=%s adapter=%s adapter_hash=%s strength=%s backend=%s',model,digest(model),adapter,digest(adapter) if adapter else None,self.settings['strength'],backend)
            with logpath.open('w',encoding='utf-8') as log:
                self.image_proc=subprocess.Popen(args,stdout=log,stderr=log,env=env,creationflags=HIDDEN)
                try:code=self.image_proc.wait(timeout=900)
                except subprocess.TimeoutExpired:terminate(self.image_proc);raise RuntimeError('이미지 생성 시간 초과')
            native=logpath.read_text(encoding='utf-8',errors='replace')
            if code or not output.exists():raise RuntimeError('이미지 엔진 실패: '+str(logpath))
            from PIL import Image
            with Image.open(output) as im:im.load()
            # Native success messages must name LoRA loading, not merely echo its prompt.
            evidence=[line for line in native.splitlines() if re.search(r'(lora.*(loaded|applied|apply|loading)|(?:load|apply).*lora)',line,re.I) and '<lora:' not in line]
            counts=re.findall(r'\(\s*(\d+)\s*/\s*(\d+)\s*\)\s*LoRA tensors have been applied',native,re.I)
            applied=bool(adapter and self.settings['strength']>0 and any(int(a)==int(b) and int(a)>0 for a,b in counts))
            self.phase='이미지 완료';return {'image':'data:image/png;base64,'+base64.b64encode(output.read_bytes()).decode(),'file':str(output),'adapter_requested':str(adapter) if adapter else None,'adapter_loading_evidence':evidence,'adapter_applied':applied,'native_log':str(logpath),'backend':backend}
        except Exception as e:self.last_error=str(e);self.phase='오류';logging.exception('image');return {'error':str(e)}
        finally:self.image_proc=None;self.lock.release()

    def configure(self,values):
        if not self.lock.acquire(False):return {'error':'작업 완료 후 설정을 변경해 주세요.'}
        try:
            if values.get('mode') not in ('cpu','gpu'):raise ValueError('CPU 또는 GPU를 선택해 주세요.')
            s={**self.settings,**{k:values[k] for k in ['mode','threads','context','model','image_model','adapter','strength','text_lora','follow_web'] if k in values}}
            s['threads']=min(6,max(1,int(s['threads'])));s['context']=min(32768,max(512,int(s['context'])));s['strength']=min(1.5,max(0,float(s['strength'])))
            self.stop_model();self.settings=s;atomic(DATA/'settings.json',s);return {'ok':True}
        except Exception as e:return {'error':str(e)}
        finally:self.lock.release()

    def history(self):
        p=DATA/'conversations.json';return json.loads(p.read_text(encoding='utf-8')) if p.exists() else []

    def save_history(self,items):
        if not isinstance(items,list) or len(json.dumps(items))>10_000_000:return {'error':'기록 용량 초과'}
        atomic(DATA/'conversations.json',items);return {'ok':True}

    def logs(self):return LOG.read_text(encoding='utf-8',errors='replace')[-30000:]

    def export_html(self,reply):
        from html_artifacts import save_html
        try:return {'ok':True,**save_html(reply,DATA/'exports')}
        except ValueError as e:return {'error':str(e)}

    def add_model(self):
        import webview
        files=self._window.create_file_dialog(webview.FileDialog.OPEN,file_types=('GGUF (*.gguf)',))
        if not files:return {'cancelled':True}
        p=Path(files[0]);from gguf_metadata import read_metadata
        meta=read_metadata(p);arch=meta.get('general.architecture')
        if not arch or not any(k.endswith('.context_length') for k in meta):return {'error':'지원되는 대화 GGUF가 아닙니다.'}
        row={'id':'user-'+uuid.uuid4().hex,'name':p.stem,'kind':'text','source':str(p),'relative':'models/'+p.name,'sha256':digest(p),'size':p.stat().st_size}
        path=DATA/'extra-models.json';old=json.loads(path.read_text()) if path.exists() else [];old.append(row);atomic(path,old);self.models['models'].append(row);return {'ok':True,'model':row}

    def cancel(self):
        self.stop_model();terminate(self.image_proc);return {'ok':True}

    def close(self,*args):
        self.stopping=True;self.cancel();logging.info('CLOSED owned processes cleaned')

class Bridge:
    """Expose actions only, never process objects or native-window internals."""
    def __init__(self,controller):
        from local_accounts import Accounts
        from social_login import Settings,SocialLogin
        self._controller=controller;self._accounts=Accounts(DATA,BUNDLE/'assets/developer-account.json');self._user=None
        self._auth_lock=threading.RLock()
        self._social_settings=Settings(DATA);self._social=SocialLogin(self._social_settings,self._social_identity)
    def _social_identity(self,provider,profile):
        self._user=self._accounts.social(provider,profile)
    def _guard(self,developer=False):
        if not self._user:return {'error':'로그인이 필요합니다.','code':'login_required'}
        if developer and self._user['role']!='developer':return {'error':'개발자 계정에서만 사용할 수 있습니다.','code':'developer_required'}
    def auth_status(self):
        try:providers=self._social_settings.public()
        except Exception:providers={name:{'configured':False,'client_id':''} for name in ('google','naver')}
        return {'authenticated':bool(self._user),'user':self._user,'providers':providers,**self._social.status()}
    def begin_social(self,provider):
        if self._user:return {'error':'다른 계정으로 로그인하려면 먼저 로그아웃해 주세요.'}
        if self._controller.lock.locked():return {'error':'현재 작업을 먼저 중지해 주세요.'}
        return self._social.start(provider)
    def cancel_login(self):self._social.cancel();return {'ok':True}
    def login(self,login,password):
        with self._auth_lock:
            if self._controller.lock.locked():return {'error':'현재 작업을 먼저 중지한 뒤 로그인해 주세요.'}
            if str(login).strip().lower()!='soo_dev':return {'error':'개발자 계정을 확인해 주세요. 일반 사용자는 Google 또는 네이버로 로그인하세요.'}
            self._social.cancel()
            result=self._accounts.login(login,password)
            if result.get('ok'):self._user=result['user']
            return result
    def logout(self):
        with self._auth_lock:
            self._social.cancel();self._controller.cancel();self._user=None
            return {'ok':True}
    def configure_login(self,provider,client_id,client_secret):
        error=self._guard(True)
        if error:return error
        try:self._social_settings.save(provider,client_id,client_secret);return {'ok':True,'providers':self._social_settings.public()}
        except Exception:return {'error':'설정을 저장하지 못했습니다. Client ID·Secret과 Windows 계정의 저장 권한을 확인해 주세요.'}
    def bootstrap(self):
        if not self._user:return self.auth_status()
        data=self._controller.bootstrap();path=self._accounts.history_path(self._user)
        if not path.exists() and self._user['role']=='developer':atomic(path,data['history'])
        data['history']=json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
        data.update(self.auth_status());return data
    def status(self):
        if not self._user:return {'phase':'로그인이 필요합니다.','ready':False}
        result=self._controller.status()
        if self._user['role']!='developer' and result.get('loaded'):
            result['loaded']={k:v for k,v in result['loaded'].items() if not k.endswith('_path')}
        return result
    def chat(self,messages,max_tokens=512):return self._guard() or self._controller.chat(messages,max_tokens)
    def image(self,prompt,steps=12,seed=42):return self._guard() or self._controller.image(prompt,steps,seed)
    def configure(self,values):
        error=self._guard()
        if error:return error
        if self._user['role']!='developer' and set(values)-{'mode','threads','context'}:return {'error':'모델 변경은 개발자 계정에서만 가능합니다.','code':'developer_required'}
        return self._controller.configure(values)
    def save_history(self,items):
        with self._auth_lock:
            error=self._guard()
            if error:return error
            if not isinstance(items,list) or len(json.dumps(items))>10_000_000:return {'error':'기록 용량 초과'}
            atomic(self._accounts.history_path(self._user),items);return {'ok':True}
    def logs(self):return self._guard(True) or self._controller.logs()
    def add_model(self):return self._guard(True) or self._controller.add_model()
    def cancel(self):return self._guard() or self._controller.cancel()
    def sync_web(self):
        error=self._guard(True)
        if error:return error
        result=self._controller.sync_web()
        if result.get('ok'):result['bootstrap']=self.bootstrap()
        return result
    def export_html(self,reply):return self._guard() or self._controller.export_html(reply)
    def check_updates(self):
        from auto_update import check
        result=check(APP,BUNDLE,DATA)
        previous=DATA/'updates/apply-result.json'
        if result.get('ok') and result.get('available') and previous.exists():
            old=json.loads(previous.read_text(encoding='utf-8'))
            if not old.get('ok'):
                previous.rename(previous.with_name('failed-'+uuid.uuid4().hex+'.json'))
                result['status']='다음 앱 시작 시 업데이트를 다시 시도합니다.'
        return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--worker');parser.add_argument('--self-test',action='store_true');parser.add_argument('--gui-smoke',action='store_true');parser.add_argument('--test-image',action='store_true');parser.add_argument('--test-gpu',action='store_true');args=parser.parse_args()
    if args.worker:
        if getattr(sys,'frozen',False):
            import msvcrt
            from ctypes import wintypes
            get_handle=ctypes.windll.kernel32.GetStdHandle;get_handle.argtypes=[wintypes.DWORD];get_handle.restype=wintypes.HANDLE
            for name,number,flags,mode in [('stdin',-10,os.O_RDONLY,'r'),('stdout',-11,os.O_WRONLY,'w'),('stderr',-12,os.O_WRONLY,'w')]:
                handle=get_handle(number & 0xffffffff)
                if handle and handle!=wintypes.HANDLE(-1).value:
                    setattr(sys,name,os.fdopen(msvcrt.open_osfhandle(handle,flags),mode,encoding='utf-8',buffering=1))
        try:worker(args.worker)
        except Exception as e:print(json.dumps({'error':str(e)}),flush=True);logging.exception('worker fatal')
        return
    if not args.self_test and getattr(sys,'frozen',False):
        from auto_update import at_start
        if at_start(APP,BUNDLE,DATA,smoke=args.gui_smoke):return
    ctl=Controller()
    if args.self_test:
        if args.test_gpu:ctl.settings['mode']='gpu'
        results={}
        try:
            r=ctl.chat([{'role':'user','content':'한국어로 한 문장으로 인사해 주세요.'}],96);results['korean']=r;results['loaded']=ctl.loaded
            r=ctl.chat([{'role':'user','content':'Write only a Python function add(a,b) that returns their sum.'}],96);results['python']=r
            results['resources']=ctl.status();pid=ctl.proc.pid if ctl.proc else None;ctl.stop_model();results['closed_worker_gone']=not pid or not psutil.pid_exists(pid)
            if args.test_image:
                chosen=ctl.settings['adapter'];ctl.settings['adapter']=''
                baseline=ctl.image('a photograph of an open human hand, five fingers, white background',4,42);baseline.pop('image',None);results['image_baseline']=baseline
                ctl.settings['adapter']=chosen
                r=ctl.image('a photograph of an open human hand, five fingers, white background',4,42);r.pop('image',None);results['image']=r
                if baseline.get('file') and r.get('file'):
                    from PIL import Image,ImageChops,ImageStat
                    with Image.open(baseline['file']) as x,Image.open(r['file']) as y:
                        x=x.convert('RGB');y=y.convert('RGB');results['image_comparison']={'different_pixels':x.tobytes()!=y.tobytes(),'mean_absolute_difference':ImageStat.Stat(ImageChops.difference(x,y)).mean}
            ctl.load_model();results['relaunch']=ctl.loaded;ctl.close()
            results['passed']=bool(results['korean'].get('text') and re.search('[가-힣]',results['korean']['text']) and 'return' in results['python'].get('text','') and results['closed_worker_gone'] and results['relaunch'])
            if args.test_image:results['passed']=results['passed'] and bool(results.get('image_comparison',{}).get('different_pixels') and results.get('image',{}).get('adapter_applied'))
        except Exception as e:results['error']=str(e);results['passed']=False;logging.exception('self-test')
        finally:ctl.close();atomic(DATA/'self-test.json',results)
        return
    if sys.stderr is None:sys.stderr=(DATA/'logs/gui-runtime.log').open('a',encoding='utf-8',buffering=1)
    if sys.stdout is None:sys.stdout=(DATA/'logs/gui-runtime.log').open('a',encoding='utf-8',buffering=1)
    import webview
    import msvcrt
    instance=(DATA/'instance.lock').open('a+b');instance.seek(0,2)
    if not instance.tell():instance.write(b'0');instance.flush()
    instance.seek(0)
    try:msvcrt.locking(instance.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:return
    # Each instance has a private loopback UI server; no externally listening AI API.
    bridge=Bridge(ctl)
    from ui_assets import prepare_ui
    page=prepare_ui(BUNDLE/'assets',DATA/'ui')
    window=webview.create_window('NOVERA AI Desktop',str(page),js_api=bridge,width=1180,height=800,min_size=(760,560),background_color='#0b1020',focus=not args.gui_smoke,hidden=args.gui_smoke,text_select=True)
    def logged_out_on_close(*args):bridge.logout()
    ctl._window=window;window.events.closed+=logged_out_on_close;window.events.closed+=ctl.close
    def smoke():
        try:
            if not window.events.loaded.wait(90):raise RuntimeError('WebView2 page loading exceeded 90 seconds')
            time.sleep(1)
            r=window.evaluate_js('JSON.stringify({title:document.title,chat:!!document.querySelector("#messages"),settings:!!document.querySelector("#settings"),width:innerWidth,overflow:document.documentElement.scrollWidth>innerWidth})')
            result={'dom':json.loads(r),'runtime':'WebView2','ok':True}
            result['auth_dom']=window.evaluate_js('({present:!!document.getElementById("authScreen"),signedOut:document.body.classList.contains("signed-out"),googleDisabled:document.getElementById("googleLogin")?.disabled,naverDisabled:document.getElementById("naverLogin")?.disabled})')
            if not any(p['configured'] for p in bridge.auth_status()['providers'].values()):
                window.evaluate_js("window.pywebview.api.begin_social('google').then(r=>window.__authPackagingCheck=r).catch(()=>window.__authPackagingCheck={error:'bridge failure'}); true")
                for _ in range(50):
                    check=window.evaluate_js('window.__authPackagingCheck||null')
                    if check:break
                    time.sleep(.1)
                result['auth_library_check']=check
            try:
                from System import Action
                from System.IO import MemoryStream
                from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat
                stream=MemoryStream();tasks=[];view=window.native.webview
                view.Invoke(Action(lambda:tasks.append(view.CoreWebView2.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png,stream))))
                if not tasks[0].Wait(10000):raise RuntimeError('Capture timed out')
                (DATA/'desktop-preview.png').write_bytes(bytes(stream.ToArray()));stream.Dispose();result['screenshot']='desktop-preview.png'
            except Exception as e:result['screenshot_error']=str(e)
            window.evaluate_js("show('settings')")
            result['settings_dom']=window.evaluate_js('({visible:!document.querySelector("#settings").hidden, chatHidden:document.querySelector("#chat").hidden, modelOptions:document.querySelector("#model").options.length})')
            atomic(DATA/'gui-smoke.json',result)
        except Exception as e:atomic(DATA/'gui-smoke.json',{'ok':False,'error':str(e)})
        window.destroy()
    try:webview.start(smoke if args.gui_smoke else None,gui='edgechromium',private_mode=False,storage_path=str(DATA/'webview'),debug=False)
    except Exception:
        logging.exception('GUI startup');ctypes.windll.user32.MessageBoxW(None,'실행 실패. Microsoft Edge WebView2 Runtime 설치 여부와 로그를 확인해 주세요.\n'+str(LOG),'NOVERA AI Desktop',16)
    finally:ctl.close()

if __name__=='__main__':main()
