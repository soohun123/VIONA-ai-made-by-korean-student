import json,time
from pathlib import Path
from runtime_settings import gpu_info
samples=[];start=time.time()
while time.time()-start<700:
    samples.append({'time':time.time(),**gpu_info()})
    Path('media-soak-gpu-samples.json').write_text(json.dumps(samples,ensure_ascii=False,indent=2),encoding='utf-8')
    try:
        if 'passed' in json.loads(Path('media-hybrid-stability-validation.json').read_text(encoding='utf-8')):break
    except (OSError,ValueError):pass
    time.sleep(2)
print('gpu_samples',len(samples))
