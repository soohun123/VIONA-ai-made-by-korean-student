"""Offline CPU SD1.5 LoRA training, batch 1 and bounded resolution; original weights unchanged."""
import gc,hashlib,json,os,sys,time,random
from pathlib import Path
from runtime_settings import read_settings
TRAIN_THREADS=read_settings()['cpu_threads']
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',OMP_NUM_THREADS=str(TRAIN_THREADS),OPENBLAS_NUM_THREADS=str(TRAIN_THREADS))
import psutil,torch
from PIL import Image,ImageOps
from diffusers import AutoencoderKL,UNet2DConditionModel,DDPMScheduler
from diffusers.utils import convert_state_dict_to_kohya
from transformers import CLIPTextModel,CLIPTokenizer
from peft import LoraConfig
from peft.utils import get_peft_model_state_dict,set_peft_model_state_dict
from safetensors.torch import save_file,load_file
from training_store import adapter_metadata,adapter_path,collect_training_records,publish_adapter,ROOT,LORAS
torch.set_num_threads(TRAIN_THREADS);torch.set_num_interop_threads(1);torch.manual_seed(42)
request=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
job_id=request['id'];base=ROOT/'models/training/sd15';resolution=int(request['resolution']);steps=int(request['steps'])
if resolution not in (128,256) or not 1<=steps<=300:raise ValueError('Training limits exceeded')
parent_id=request.get('resume_adapter_id','');parent=adapter_metadata(parent_id) if parent_id else None
dataset,history=collect_training_records(request['dataset_id'],parent,request.get('replay_previous',True))
progress=ROOT/'data/media/jobs'/(job_id+'-progress.json');started=time.monotonic();peak_rss=0
def update(phase,**values):
    global peak_rss
    memory=psutil.virtual_memory();peak_rss=max(peak_rss,psutil.Process().memory_info().rss)
    if memory.available<2.5*2**30 or memory.used>=13.5*2**30:raise RuntimeError('RAM protection stopped training')
    data={'phase':phase,**values};temp=progress.with_suffix('.tmp');temp.write_text(json.dumps(data),encoding='utf-8')
    for _ in range(20):
        try:os.replace(temp,progress);break
        except PermissionError:time.sleep(.05)
def load(cls,folder):return cls.from_pretrained(base/folder,variant='fp16',torch_dtype=torch.float32,local_files_only=True,use_safetensors=True,low_cpu_mem_usage=True)
update('사진 인코딩 준비 중')
from screen_images_worker import screen
paths=[ROOT/r['image'] for r in dataset['records']]
verdicts=screen(paths,lambda n,total:update('학습 사진 검열 '+str(n)+'/'+str(total)))
blocked_count=sum(bool(v['blocked']) for v in verdicts)
dataset['records']=[r for r,v in zip(dataset['records'],verdicts) if not v['blocked']]
if not dataset['records']:raise ValueError('No photos passed content screening')
tokenizer=CLIPTokenizer.from_pretrained(base/'tokenizer',local_files_only=True)
encoder=load(CLIPTextModel,'text_encoder').eval().requires_grad_(False)
vae=load(AutoencoderKL,'vae').eval().requires_grad_(False)
cached=[]
for i,record in enumerate(dataset['records']):
    update('사진 준비 '+str(i+1)+'/'+str(len(dataset['records'])))
    path=ROOT/record['image']
    if not path.resolve().is_relative_to(ROOT.resolve()):raise ValueError('Image outside workspace')
    with Image.open(path) as im:
        im=ImageOps.fit(im.convert('RGB'),(resolution,resolution));import numpy as np
        pixels=torch.from_numpy(np.array(im).copy()).permute(2,0,1).unsqueeze(0).float()/127.5-1
    with torch.no_grad():
        latent=vae.encode(pixels).latent_dist.mean*vae.config.scaling_factor
        tokens=tokenizer(record['caption'],padding='max_length',max_length=tokenizer.model_max_length,truncation=True,return_tensors='pt').input_ids
        embedding=encoder(tokens)[0]
    cached.append((latent,embedding,record.get('split','train'),record['dataset_id']))
del encoder,vae,pixels,embedding,latent;gc.collect()
update('LoRA 모델 준비 중')
low_memory=psutil.virtual_memory().available<8*2**30
unet=UNet2DConditionModel.from_pretrained(base/'unet',variant='fp16',torch_dtype=torch.bfloat16 if low_memory else torch.float32,local_files_only=True,use_safetensors=True,low_cpu_mem_usage=True);unet.requires_grad_(False)
unet.add_adapter(LoraConfig(r=2,lora_alpha=2,init_lora_weights='gaussian',target_modules=['to_k','to_q','to_v','to_out.0']))
# Keep the small trainable adapter in full precision, including restored weights.
for parameter in unet.parameters():
    if parameter.requires_grad:parameter.data=parameter.data.float()
if low_memory:
    # Frozen layers use compact storage and float32 CPU arithmetic. Keep the
    # trainable LoRA modules untouched so optimizer state stays in full precision.
    from types import MethodType
    def compact_linear(module,value):
        return torch.nn.functional.linear(value,module.weight.float(),module.bias.float() if module.bias is not None else None)
    def compact_conv(module,value):
        return module._conv_forward(value,module.weight.float(),module.bias.float() if module.bias is not None else None)
    for module in unet.modules():
        direct=list(module.parameters(recurse=False))
        if direct and not any(p.requires_grad for p in direct) and not list(module.children()):
            if isinstance(module,(torch.nn.Linear,torch.nn.Conv1d,torch.nn.Conv2d,torch.nn.Conv3d)):
                module.forward=MethodType(compact_linear if isinstance(module,torch.nn.Linear) else compact_conv,module)
            else:module.float()
resume_format=None
if parent:
    update('이전 학습 가중치 복원 중')
    checkpoint=LORAS/(parent_id+'.training.safetensors')
    if checkpoint.is_file():
        restored={k.removeprefix('unet.'):v for k,v in load_file(str(checkpoint)).items()};resume_format='peft'
    else:
        from diffusers.utils.state_dict_utils import StateDictType
        saved=load_file(str(adapter_path(parent_id)));restored={}
        for key,value in get_peft_model_state_dict(unet).items():
            conversion=convert_state_dict_to_kohya({'unet.'+key:value},original_type=StateDictType.PEFT)
            name=next(k for k in conversion if k.endswith('.weight'))
            if name not in saved or saved[name].shape!=value.shape:raise ValueError('기존 LoRA 구조를 복원할 수 없습니다.')
            restored[key]=saved[name]
        resume_format='legacy_kohya';del saved
    expected=get_peft_model_state_dict(unet)
    if set(restored)!=set(expected) or any(restored[k].shape!=expected[k].shape for k in expected):raise ValueError('LoRA 체크포인트 구조 불일치')
    outcome=set_peft_model_state_dict(unet,restored)
    if outcome.unexpected_keys:raise ValueError('LoRA 체크포인트에 알 수 없는 가중치가 있습니다.')
    del restored,expected
unet.enable_gradient_checkpointing();unet.train()
parameters=[p for p in unet.parameters() if p.requires_grad]
optimizer=torch.optim.AdamW(parameters,lr=1e-4)
scheduler=DDPMScheduler.from_pretrained(base/'scheduler',local_files_only=True)
def weights():return {'unet.'+k:v.detach().cpu().contiguous() for k,v in get_peft_model_state_dict(unet).items()}

def predict(latent,timestep,embedding):
    return unet(latent,timestep,embedding).sample
def digest(state):
    h=hashlib.sha256()
    for key,tensor in sorted(state.items()):h.update(key.encode());h.update(tensor.numpy().tobytes())
    return h.hexdigest()
initial_hash=digest(weights())
if parent and initial_hash!=parent['final_weight_hash']:raise ValueError('이전 종료 가중치와 누적 학습 시작 가중치가 일치하지 않습니다.')
train=[x for x in cached if x[2]=='train'];validation=[x for x in cached if x[2]=='validation'][:4]
random.Random(42).shuffle(train)
new_indices=[i for i,x in enumerate(train) if x[3]==request['dataset_id']]
old_indices=[i for i,x in enumerate(train) if x[3]!=request['dataset_id']]
if not train:raise ValueError('No training photos')
def evaluate():
    if not validation:return None
    losses=[];generator=torch.Generator().manual_seed(914)
    unet.eval()
    with torch.no_grad():
        for latent,embedding,_,_ in validation:
            noise=torch.randn(latent.shape,generator=generator);timestep=torch.tensor([400])
            prediction=predict(scheduler.add_noise(latent,noise,timestep),timestep,embedding)
            losses.append(torch.nn.functional.mse_loss(prediction.float(),noise.float()).item())
    unet.train();return sum(losses)/len(losses)
before=evaluate();losses=[];seen=set();seen_datasets={}
for step in range(steps):
    update('사진 학습 '+str(step+1)+'/'+str(steps),step=step,total=steps)
    if new_indices and old_indices:
        pool=new_indices if step%2==0 else old_indices;index=pool[(step//2)%len(pool)]
    else:index=step%len(train)
    latent,embedding,_,identifier=train[index]
    if index not in seen:seen.add(index);seen_datasets[identifier]=seen_datasets.get(identifier,0)+1
    noise=torch.randn_like(latent);timestep=torch.randint(0,scheduler.config.num_train_timesteps,(1,))
    prediction=predict(scheduler.add_noise(latent,noise,timestep),timestep,embedding)
    loss=torch.nn.functional.mse_loss(prediction.float(),noise.float())
    if not torch.isfinite(loss):raise RuntimeError('Non-finite training loss')
    loss.backward();torch.nn.utils.clip_grad_norm_(parameters,1.0);optimizer.step();optimizer.zero_grad(set_to_none=True);losses.append(loss.item())
after=evaluate();state=weights();final_hash=digest(state)
if final_hash==initial_hash:raise RuntimeError('LoRA weights did not change')
LORAS.mkdir(parents=True,exist_ok=True);temp=LORAS/(job_id+'.native.tmp');training_temp=LORAS/(job_id+'.training.tmp')
save_file(convert_state_dict_to_kohya(state),str(temp),metadata={'base_model':'SD1.5','dataset':dataset['id'],'format':'pt'})
save_file(state,str(training_temp),metadata={'format':'pt','base_model':'SD1.5','rank':'2'})
result={'adapter_id':job_id,'name':request.get('name') or (parent['name'] if parent else dataset['name']),'dataset_id':dataset['id'],'source':dataset.get('source',''),'steps':steps,'resolution':resolution,'rank':2,'device':'cpu','train_images':len(train),'seen_train_images':len(seen),'seen_dataset_counts':seen_datasets,'blocked_training_images':blocked_count,'held_out_images':sum(x[2]=='validation' for x in cached),'validation_images_measured':len(validation),'validation_loss_before':before,'validation_loss_after':after,'initial_weight_hash':initial_hash,'final_weight_hash':final_hash,'adapter_file_sha256':hashlib.sha256(temp.read_bytes()).hexdigest(),'losses':losses,'trainable_parameters':sum(p.numel() for p in parameters),'elapsed_seconds':time.monotonic()-started,'peak_worker_rss_gib':peak_rss/2**30,'dataset_ids':history,'parent_adapter_id':parent_id or None,'parent_version_id':parent.get('version_id',parent_id) if parent else None,'version':parent.get('version',1)+1 if parent else 1,'total_steps':(parent.get('total_steps',parent['steps']) if parent else 0)+steps,'resume_format':resume_format,'keep_previous':request.get('keep_previous',True),'replay_previous':request.get('replay_previous',True),'optimizer_restarted':True}
result['frozen_weight_dtype']='bfloat16' if low_memory else 'float32'
publish_adapter(job_id,parent_id,request.get('keep_previous',True),result,temp,training_temp)
Path(request['result_path']).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');update('학습 완료')
