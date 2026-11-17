"""One local image-reading job; explicit paths/data URI, no remote model code or image URLs."""
import base64,json,sys,time
from pathlib import Path
from cuda_runtime import initialize_cuda
ROOT=Path(__file__).resolve().parent
request=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
initialize_cuda()
from llama_cpp import Llama
from llama_cpp.llama_chat_format import MoondreamChatHandler
handler=MoondreamChatHandler(clip_model_path=str(ROOT/'models/media/vision-mmproj.gguf'),verbose=False)
model=Llama(model_path=str(ROOT/'models/media/vision.gguf'),chat_handler=handler,n_ctx=2048,n_gpu_layers=8,n_threads=6,n_threads_batch=6,n_batch=128,n_ubatch=64,verbose=False)
image_path=Path(request['image_path']).resolve()
if not image_path.is_relative_to((ROOT/'data/media/images').resolve()):raise ValueError('Image path outside local media')
image_url='data:image/png;base64,'+base64.b64encode(image_path.read_bytes()).decode('ascii')
started=time.monotonic()
answer=model.create_chat_completion(messages=[{'role':'user','content':[{'type':'image_url','image_url':{'url':image_url}},{'type':'text','text':request.get('prompt') or 'Describe the image briefly and accurately.'}]}],max_tokens=192,temperature=.1,repeat_penalty=1.1,seed=42)
result={'text':answer['choices'][0]['message'].get('content') or '','usage':answer.get('usage',{}),'inference_seconds':time.monotonic()-started}
Path(request['result_path']).write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
