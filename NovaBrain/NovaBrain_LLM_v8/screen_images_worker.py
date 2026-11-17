"""Offline CLIP-based sexual/graphic-violence screening in an isolated CPU process."""
import gc,json,os,sys
from pathlib import Path
from runtime_settings import read_settings
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',OMP_NUM_THREADS=str(read_settings()['cpu_threads']))
from content_filter import settings,image_reason
ROOT=Path(__file__).resolve().parent
def screen(paths,progress=None,config=None):
    config=config or settings()
    if not config['sexual'] and not config['violence']:return [{'scores':{},'blocked':None} for _ in paths]
    import torch
    from transformers import CLIPModel,CLIPProcessor
    from PIL import Image
    torch.set_num_threads(read_settings()['cpu_threads'])
    base=ROOT/'models/moderation/clip'
    model=CLIPModel.from_pretrained(base,local_files_only=True,weights_only=True).eval()
    processor=CLIPProcessor.from_pretrained(base,local_files_only=True,use_fast=False)
    safe_labels=['a normal photograph of everyday objects','a normal photograph of scenery or animals','a fully clothed person in an ordinary photograph','a diagram or a clean illustration',
                 'a photograph of an airplane or aircraft at an airport','a photograph of a car or vehicle',
                 'a photograph of mechanical parts of a vehicle','a photograph of a logo or emblem']
    labels=safe_labels+['a photograph of explicit sexual activity','a close-up photograph of naked genitals','a photograph of severe graphic violence with blood and gore']
    sexual_start=len(safe_labels)
    results=[]
    for start in range(0,len(paths),4):
        images=[]
        for path in paths[start:start+4]:
            if not Path(path).resolve().is_relative_to(ROOT):raise ValueError('Image outside workspace')
            with Image.open(path) as im:images.append(im.convert('RGB'))
        with torch.no_grad():
            inputs=processor(text=labels,images=images,return_tensors='pt',padding=True)
            probabilities=model(**inputs).logits_per_image.softmax(dim=-1)
        for values in probabilities:
            scores={'sexual':float(values[sexual_start:sexual_start+2].sum()),'violence':float(values[sexual_start+2])};results.append({'scores':scores,'blocked':image_reason(scores,config)})
        if progress:progress(min(start+4,len(paths)),len(paths))
    del model,processor,images;gc.collect();return results
if __name__=='__main__':
    request=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    results=screen(request['images'],config=request.get('config'))
    Path(request['result_path']).write_text(json.dumps(results),encoding='utf-8')
