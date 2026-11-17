"""Serialized, memory-guarded local vision/image jobs with model unload/recovery."""
import base64,collections,io,json,os,re,subprocess,sys,threading,time,uuid,warnings
from pathlib import Path
import psutil
from PIL import Image,ImageOps
from runtime_settings import gpu_info,read_settings
from image_quality import DEFAULT_NEGATIVE,visual_subject,simple_visual_translation
from text_training_runtime import active_training
ROOT=Path(__file__).resolve().parent
MEDIA=ROOT/'data/media';IMAGES=MEDIA/'images';JOBS=MEDIA/'jobs'

def save_upload(data_url):
    if not re.match(r'^data:image/(png|jpeg|webp);base64,',data_url):raise ValueError('PNG, JPEG, WebP 이미지만 지원합니다.')
    raw=base64.b64decode(data_url.split(',',1)[1],validate=True)
    if len(raw)>10*1024*1024:raise ValueError('이미지는 10MB 이하로 올려 주세요.')
    with warnings.catch_warnings():
        warnings.simplefilter('error',Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(raw)) as image:
            if image.width*image.height>16000000 or max(image.size)>8000:raise ValueError('이미지 크기가 너무 큽니다. 1,600만 픽셀 이하로 줄여 주세요.')
            if image.format not in ('PNG','JPEG','WEBP'):raise ValueError('지원하지 않는 이미지 형식입니다.')
            normalized=ImageOps.exif_transpose(image).convert('RGB');normalized.thumbnail((1280,1280))
            normalized.info.clear()
            image_id=uuid.uuid4().hex;IMAGES.mkdir(parents=True,exist_ok=True)
            normalized.save(IMAGES/(image_id+'.png'),format='PNG',optimize=True)
    return {'id':image_id,'url':'/media/'+image_id+'.png','width':normalized.width,'height':normalized.height}

def image_path(image_id):
    if not re.fullmatch('[a-f0-9]{32}',image_id):raise ValueError('올바르지 않은 이미지 ID입니다.')
    path=IMAGES/(image_id+'.png')
    if path.with_suffix('.blocked.json').is_file():raise ValueError('검열 설정에 따라 이 이미지 표시를 차단했습니다.')
    if not path.resolve().is_relative_to(IMAGES.resolve()):raise ValueError('허용된 이미지 경로가 아닙니다.')
    if not path.is_file():raise ValueError('이미지를 찾을 수 없습니다.')
    return path

class MediaJobs:
    def __init__(self,gate,unload,reload,text_task):
        self.gate=gate;self.unload=unload;self.reload=reload;self.text_task=text_task
        self.jobs=collections.OrderedDict();self.lock=threading.RLock();self.active=None
        self.cancel_event=threading.Event();self.process=None;self.children=[];self.closed=False;self.thread=None
        JOBS.mkdir(parents=True,exist_ok=True);IMAGES.mkdir(parents=True,exist_ok=True)
        for path in JOBS.glob('*.json'):
            if not re.fullmatch('[a-f0-9]{32}\\.json',path.name):continue
            try:
                old=json.loads(path.read_text(encoding='utf-8'))
                if old.get('state') in ('queued','running'):
                    old.update(state='error',phase='작업 중단됨',error='서버가 다시 시작되어 작업이 중단됐습니다.')
                    path.write_text(json.dumps(old,ensure_ascii=False,indent=2),encoding='utf-8')
            except (OSError,ValueError):pass
    def capabilities(self):
        return {'local_only':True,'vision_ready':all((ROOT/'models/media'/name).is_file() for name in ('vision.gguf','vision-mmproj.gguf')),
                'training_ready':(ROOT/'.training-venv/Scripts/python.exe').is_file() and (ROOT/'models/training/sd15/unet/diffusion_pytorch_model.fp16.safetensors').is_file(),
                'generation_ready':(ROOT/'models/media/sd15-q4.gguf').is_file() and (ROOT/'media-runtime/cpu/sd-cli.exe').is_file(),
                'vision_model':'Moondream2 Q4_K_M','generation_model':'Stable Diffusion 1.5 Q4_0','max_size':512,'active_job':self.active}
    def _persist(self,job):
        (JOBS/(job['id']+'.json')).write_text(json.dumps(job,ensure_ascii=False,indent=2),encoding='utf-8')
    def get(self,job_id):
        if not re.fullmatch('[a-f0-9]{32}',job_id):raise ValueError('올바르지 않은 작업 ID입니다.')
        with self.lock:
            if job_id in self.jobs:return json.loads(json.dumps(self.jobs[job_id]))
        path=JOBS/(job_id+'.json')
        if not path.is_file():raise ValueError('작업을 찾을 수 없습니다.')
        return json.loads(path.read_text(encoding='utf-8'))
    def start(self,kind,payload):
        if active_training():raise RuntimeError('코딩 모델 추가 학습 중에는 이미지 작업을 시작하지 않습니다.')
        ready=self.capabilities()
        if not ready['training_ready' if kind=='train' else 'vision_ready' if kind=='read' else 'generation_ready']:raise ValueError('로컬 이미지 모델 설치가 끝나지 않았습니다.')
        if kind=='read':image_path(payload['image_id'])
        if kind=='train':
            from training_store import dataset_path,adapter_path
            dataset_path(payload['dataset_id'])
            if payload.get('resume_adapter_id'):adapter_path(payload['resume_adapter_id'])
        from content_filter import reason,sanitize,settings
        moderation=payload.get('_moderation') or settings()
        blocked=reason(payload.get('prompt',''),moderation)
        if blocked:raise ValueError('검열: '+blocked)
        payload={**payload,'prompt':sanitize(payload.get('prompt',''),moderation)}
        if '<lora:' in payload['prompt'].lower():raise ValueError('LoRA는 목록에서 선택해 주세요.')
        if payload.get('adapter_id'):
            from training_store import adapter_path
            adapter_path(payload['adapter_id'])
        if not self.gate.acquire(blocking=False):raise RuntimeError('현재 작업을 완료하거나 중단한 뒤 실행해 주세요.')
        try:
            vm=psutil.virtual_memory()
            if vm.available/2**30<3 or vm.used/2**30>=13:raise ValueError('RAM 여유가 부족해 새 이미지 작업을 시작하지 않습니다.')
            if kind=='train' and vm.available/2**30<6:raise ValueError('사진 학습은 시작 전 6GiB 이상의 여유 RAM이 필요합니다.')
            with self.lock:
                job={'id':uuid.uuid4().hex,'kind':kind,'state':'queued','created':time.time(),'phase':'준비 중','local_only':True}
                if payload.get('_quality_notice'):job['quality_notice']=payload['_quality_notice']
                self.jobs[job['id']]=job;self.active=job['id'];self.cancel_event.clear()
                while len(self.jobs)>20:self.jobs.popitem(last=False)
                self._persist(job)
            self.thread=threading.Thread(target=self._work,args=(job,payload),daemon=True);self.thread.start()
            return self.get(job['id'])
        except Exception:self.gate.release();raise
    def cancel(self,job_id):
        with self.lock:
            if self.active==job_id:self.cancel_event.set()
        return {'ok':True}
    def _stop_process(self):
        p=self.process
        if p is None:return
        children=list(self.children)
        if p.poll() is None:
            try:
                for child in psutil.Process(p.pid).children(recursive=True):
                    if child not in children:children.append(child)
            except psutil.Error:pass
        for child in reversed(children):
            try:child.terminate()
            except psutil.Error:pass
        if p.poll() is None:
            p.terminate()
            try:p.wait(timeout=3)
            except subprocess.TimeoutExpired:p.kill();p.wait(timeout=3)
        _,alive=psutil.wait_procs(children,timeout=2)
        for child in alive:
            try:child.kill()
            except psutil.Error:pass
        psutil.wait_procs(alive,timeout=2);self.process=None;self.children=[]
    def _run(self,args,job,label,environment=None,cancelled=None):
        log=JOBS/(job['id']+'-'+label+'.log')
        with log.open('w',encoding='utf-8') as output:
            process=subprocess.Popen(args,cwd=ROOT,env=environment,stdout=output,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
            self.process=process
            self.children=[];started=time.monotonic()
            try:
                while process.poll() is None:
                    try:
                        for child in psutil.Process(process.pid).children(recursive=True):
                            if child not in self.children:self.children.append(child)
                    except psutil.Error:pass
                    vm=psutil.virtual_memory();used=vm.used/2**30;free=vm.available/2**30
                    job['peak_system_used_gib']=max(job.get('peak_system_used_gib',0),used)
                    job['minimum_available_gib']=min(job.get('minimum_available_gib',free),free)
                    if used>=13:job['memory_warning']=True
                    if self.cancel_event.is_set() or cancelled and cancelled():raise InterruptedError('작업을 중단했습니다.')
                    if used>=13.5 or free<2.5:raise RuntimeError('RAM 보호 기준에 도달해 이미지 작업을 중단했습니다.')
                    if label=='train':
                        progress=JOBS/(job['id']+'-progress.json')
                        try:job['phase']=json.loads(progress.read_text(encoding='utf-8'))['phase']
                        except (OSError,ValueError,KeyError):pass
                    if time.monotonic()-started>(3600 if label=='train' else 600):raise TimeoutError('이미지 작업 시간 제한을 초과했습니다.')
                    time.sleep(.4)
                return process.returncode,log
            finally:self._stop_process()
    def _work(self,job,payload):
        started=time.monotonic();error=None;result=None;terminal='error'
        try:
            job.update(state='running',phase='준비 중')
            prompt=payload.get('prompt','').strip()
            self.unload('로컬 이미지·번역 작업을 위한 모델 전환')
            env=os.environ.copy();env.update({'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','OMP_NUM_THREADS':str(read_settings()['cpu_threads']),'OPENBLAS_NUM_THREADS':str(read_settings()['cpu_threads']),'PYTHONUTF8':'1'})
            if payload.get('_moderation'):env['VIONA_MODERATION']=json.dumps(payload['_moderation'])
            if payload.get('translate',True) and re.search('[가-힣]',prompt):
                if job['kind']=='generate':
                    prompt=simple_visual_translation(prompt) or self._translate(visual_subject(prompt) or prompt,'en',job,env,visual=True)
                else:prompt=self._translate(prompt,'en',job,env)
            if job['kind']=='generate' and payload.get('translate',True) and re.search('[가-힣]',payload.get('negative_prompt','')):
                payload['negative_prompt']=self._translate(payload['negative_prompt'],'en',job,env,visual=True)
            job['prompt_used']=prompt
            if self.cancel_event.is_set():raise InterruptedError('작업을 중단했습니다.')
            if job['kind']=='train':
                job['phase']='사진 학습 준비 중';output=JOBS/(job['id']+'-training-result.json');request=JOBS/(job['id']+'-training-input.json')
                request.write_text(json.dumps({**payload,'id':job['id'],'result_path':str(output)}),encoding='utf-8')
                code,log=self._run([str(ROOT/'.training-venv/Scripts/python.exe'),str(ROOT/'train_lora_worker.py'),str(request)],job,'train',env)
                if code!=0 or not output.is_file():raise RuntimeError('사진 학습에 실패했습니다. 학습 로그를 확인해 주세요.')
                result=json.loads(output.read_text(encoding='utf-8'))
            elif job['kind']=='read':
                self._screen(image_path(payload['image_id']),job,env)
                job['phase']='이미지 읽는 중';output=JOBS/(job['id']+'-vision-result.json');request=JOBS/(job['id']+'-vision-input.json')
                request.write_text(json.dumps({'image_path':str(image_path(payload['image_id'])),'prompt':prompt or 'Describe the image briefly and accurately.','result_path':str(output)}),encoding='utf-8')
                code,log=self._run([sys.executable,str(ROOT/'vision_worker.py'),str(request)],job,'vision',env)
                if code!=0 or not output.is_file():raise RuntimeError('이미지 읽기에 실패했습니다. 작업 로그를 확인해 주세요.')
                result=json.loads(output.read_text(encoding='utf-8'));result['image_id']=payload['image_id'];result['image_url']='/media/'+payload['image_id']+'.png'
                if payload.get('translate',True) and result.get('text'):
                    result['text_original']=result['text']
                    result['text']=self._translate(result['text'],'ko',job,env)
            else:
                job['phase']='이미지 생성 중';output=IMAGES/(job['id']+'.png')
                output.with_suffix('.blocked.json').write_text('{"state":"pending"}',encoding='utf-8')
                for backend in ('cuda','cpu'):
                    executable=ROOT/'media-runtime'/backend/'sd-cli.exe'
                    if not executable.is_file():continue
                    local_env=env.copy();dlls=[str(ROOT/'.venv/Lib/site-packages/nvidia'/name/'bin') for name in ('cuda_runtime','cublas')]
                    local_env['PATH']=os.pathsep.join([str(executable.parent),*dlls,env.get('PATH','')])
                    cpu_threads=read_settings()['cpu_threads']
                    args=[str(executable),'-m',payload.get('_model_path') or str(ROOT/'models/media/sd15-q4.gguf'),'-p',prompt,'-o',str(output),'-W',str(payload['size']),'-H',str(payload['size']),'--steps',str(payload['steps']),'-s',str(payload['seed']),'-t',str(cpu_threads),'--sampling-method','dpm++2m','--scheduler','karras','--cfg-scale',str(payload.get('cfg_scale',6.5)),'--negative-prompt',payload.get('negative_prompt',DEFAULT_NEGATIVE),'--flash-attn','off','--batched-cfg','off']
                    job['generation_settings']={k:payload.get(k) for k in ('size','steps','seed','cfg_scale','negative_prompt','adapter_strength')}
                    job['generation_settings'].update(original_prompt=payload.get('prompt',''),prompt_used=prompt,sampler='dpm++2m',scheduler='karras',cpu_threads=cpu_threads)
                    args+=['--backend','te=cpu,vae=cpu,diffusion=cuda0','--offload-to-cpu','--max-vram','1.5'] if backend=='cuda' else ['--backend','cpu']
                    if payload.get('_adapter_path'):
                        adapter=Path(payload['_adapter_path'])
                        args[args.index('-p')+1]+='<lora:'+adapter.stem+':'+str(payload.get('adapter_strength',0.15))+'>'
                        args+=['--lora-model-dir',str(adapter.parent)]
                    elif payload.get('adapter_id'):
                        from training_store import LORAS
                        args[args.index('-p')+1]+='<lora:'+payload['adapter_id']+':'+str(payload.get('adapter_strength',0.15))+'>'
                        args+=['--lora-model-dir',str(LORAS)]
                    code,log=self._run(args,job,'generate-'+backend,local_env)
                    if code==0 and output.is_file():
                        with Image.open(output) as check:check.load()
                        result={'image_id':job['id'],'image_url':'/media/'+job['id']+'.png','backend':backend,'size':payload['size'],'seed':payload['seed'],'steps':payload['steps']};break
                    if self.cancel_event.is_set():raise InterruptedError('작업을 중단했습니다.')
                if result is None:raise RuntimeError('로컬 이미지 생성에 실패했습니다. 작업 로그를 확인해 주세요.')
                result['adapter_id']=Path(payload['_adapter_path']).stem if payload.get('_adapter_path') else payload.get('adapter_id') or None
                result['image_model_id']=payload.get('_selected_image_model')
                result['image_model_name']=payload.get('_selected_image_name')
                self._screen(output,job,env)
                output.with_suffix('.blocked.json').unlink(missing_ok=True)
        except InterruptedError as exc:result=None;error=str(exc);terminal='cancelled'
        except Exception as exc:result=None;error=str(exc);terminal='error'
        finally:
            self._stop_process();job['phase']='대화 모델 복구 중'
            try:
                with self.lock:
                    if not self.closed:
                        self.reload()
            except Exception as exc:
                job['restore_error']=str(exc);error='대화 모델 복구에 실패했습니다. 서버 상태를 확인해 주세요.';terminal='error'
            with self.lock:
                if result and job['kind']=='read':
                    from content_filter import filtered
                    for field in ('text','text_original'):
                        if result.get(field):result[field]=filtered(result[field],payload.get('_moderation'))
                self.gate.release()
                complete=bool(result) and not job.get('restore_error')
                job.update({'phase':'완료' if complete else error,'state':'done' if complete else terminal,'elapsed_seconds':time.monotonic()-started,'result':result,'error':error})
                self._persist(job);self.active=None
    def _translate(self,text,target,job,env,visual=False,cancelled=None):
        label='translate-'+target+'-'+str(len(job.get('translations',[])))
        request=JOBS/(job['id']+'-'+label+'-input.json');output=JOBS/(job['id']+'-'+label+'-result.json')
        request.write_text(json.dumps({'target':target,'texts':[text],'visual':visual,'result_path':str(output)}),encoding='utf-8')
        job['phase']='로컬 전용 모델 번역 중'
        code,_=self._run([str(ROOT/'.training-venv/Scripts/python.exe'),str(ROOT/'translation_worker.py'),str(request)],job,label,env,cancelled)
        if code or not output.is_file():raise RuntimeError('로컬 번역에 실패했습니다. 원문은 보존했으며 잘린 번역으로 계속하지 않습니다.')
        result=json.loads(output.read_text(encoding='utf-8'));job.setdefault('translations',[]).append(result)
        item=result['items'][0]
        if item['issues']:raise RuntimeError('번역의 수량·색상·부정 표현 등을 확인하지 못했습니다: '+', '.join(item['issues']))
        return item['text']

    def shutdown(self):
        with self.lock:self.closed=True;self.cancel_event.set()
        self._stop_process()
        if self.thread and self.thread.is_alive():self.thread.join(timeout=5)

    def _screen(self,image,job,env):
        from content_filter import settings
        config=json.loads(env['VIONA_MODERATION']) if env.get('VIONA_MODERATION') else settings()
        if not any(config[k] for k in ('sexual','violence')):return
        job['phase']='이미지 검열 검사 중';request=JOBS/(job['id']+'-screen-input.json');output=JOBS/(job['id']+'-screen-result.json')
        request.write_text(json.dumps({'images':[str(image)],'result_path':str(output),'config':config}),encoding='utf-8')
        code,_=self._run([str(ROOT/'.training-venv/Scripts/python.exe'),str(ROOT/'screen_images_worker.py'),str(request)],job,'screen',env)
        if code or not output.is_file():raise RuntimeError('로컬 이미지 검열 검사에 실패했습니다. 결과 표시를 보류합니다.')
        verdict=json.loads(output.read_text(encoding='utf-8'))[0];job['image_screen']=verdict
        if verdict['blocked']:
            image.with_suffix('.blocked.json').write_text(json.dumps(verdict,ensure_ascii=False),encoding='utf-8')
            raise RuntimeError('검열: '+verdict['blocked'])
