import json,os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
CONFIG=ROOT/'runtime-settings.json'
def read_settings():
    try:
        data=json.loads(CONFIG.read_text(encoding='utf-8'))
        blocks=data.get('gpu_blocks',14)
        threads=data.get('cpu_threads',6)
        return {'gpu_mode':data.get('gpu_mode') if data.get('gpu_mode') in ('cpu','auto','hybrid') else 'auto','gpu_blocks':blocks if isinstance(blocks,int) and 1<=blocks<=26 else 14,'cpu_threads':threads if type(threads) is int and 1<=threads<=6 else 6}
    except (OSError,ValueError):return {'gpu_mode':'auto','gpu_blocks':14,'cpu_threads':6}
def save_settings(mode,gpu_blocks=None,cpu_threads=None):
    if mode not in ('cpu','auto','hybrid'):raise ValueError('지원하지 않는 GPU 모드')
    blocks=read_settings()['gpu_blocks'] if gpu_blocks is None else gpu_blocks
    if not 1<=blocks<=26:raise ValueError('GPU 계산 블록은 1~26 범위여야 합니다.')
    threads=read_settings()['cpu_threads'] if cpu_threads is None else cpu_threads
    if type(threads) is not int or not 1<=threads<=6:raise ValueError('CPU 스레드는 1~6 범위여야 합니다.')
    temp=CONFIG.with_suffix('.tmp');temp.write_text(json.dumps({'gpu_mode':mode,'gpu_blocks':blocks,'cpu_threads':threads}),encoding='utf-8');os.replace(temp,CONFIG)
def gpu_info():
    try:
        p=subprocess.run(['nvidia-smi','--query-gpu=name,memory.total,memory.free,memory.used,utilization.gpu,temperature.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=4,creationflags=subprocess.CREATE_NO_WINDOW)
        row=p.stdout.strip().splitlines()[0].split(',')
        return {'available':True,'name':row[0].strip(),'total_mib':int(row[1]),'free_mib':int(row[2]),'used_mib':int(row[3]),'utilization_percent':int(row[4]),'temperature_c':int(row[5])}
    except (OSError,ValueError,IndexError,subprocess.TimeoutExpired):return {'available':False}
def layers_for_mode(mode):
    if mode=='cpu':return 0
    gpu=gpu_info()
    if not gpu.get('available'):return 0
    free=gpu['free_mib']
    # This pinned backend counts the output layer too: 15 = 14 blocks + output.
    if mode=='hybrid':
        # Keep at least two transformer blocks on CPU and startup VRAM headroom.
        capacity=min(26,max(0,int((free-1000)/34)))
        return min(read_settings()['gpu_blocks'],capacity)+1 if capacity else 0
    # Leave display/other apps headroom on the 3 GiB card. No competing app is stopped.
    return -1 if free>=1900 else 14 if free>=1200 else 0
