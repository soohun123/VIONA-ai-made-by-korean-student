import argparse
from pathlib import Path
from huggingface_hub import hf_hub_download
p=argparse.ArgumentParser()
p.add_argument('--repo',default='Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF')
p.add_argument('--filename',default='qwen2.5-coder-1.5b-instruct-q4_k_m.gguf')
a=p.parse_args()
print('Downloading model. Check repository license and available filenames first.')
path=hf_hub_download(repo_id=a.repo,filename=a.filename,local_dir=str(Path(__file__).resolve().parent))
target=Path(__file__).resolve().parent/'model.gguf'
if Path(path).resolve()!=target.resolve():
 import shutil
 shutil.copyfile(path,target)
print('Model ready:',target)
