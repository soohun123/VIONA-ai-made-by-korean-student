"""Standalone native placement evidence; run only with this server stopped."""
import psutil,socket
from pathlib import Path
from cuda_runtime import initialize_cuda
from generation_resources import release_generation
with socket.socket() as sock:
    if sock.connect_ex(('127.0.0.1',8000))==0:raise SystemExit('Server must be stopped first; no process was stopped.')
vm=psutil.virtual_memory()
if vm.available<5*2**30 or vm.used>10*2**30:raise SystemExit('Insufficient safe RAM headroom')
initialize_cuda()
from llama_cpp import Llama
llm=Llama(model_path=str(Path(__file__).resolve().parent/'model.gguf'),n_ctx=8192,n_threads=6,n_threads_batch=6,n_gpu_layers=27,n_batch=128,n_ubatch=128,verbose=True)
try:
    result=llm.create_chat_completion(messages=[{'role':'user','content':'Return only the sum: 19 + 23.'}],max_tokens=16,temperature=0,seed=42)
    print('ACTUAL_COMPLETION',result['choices'][0]['message']['content'],flush=True)
finally:
    release_generation(llm);llm.close()
