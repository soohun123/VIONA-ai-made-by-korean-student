"""Local configurable text screening; image scores are heuristic, not calibrated probabilities."""
import json,re,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
CONFIG=ROOT/'data/moderation-settings.json'
DEFAULT={'privacy':True,'sexual':True,'violence':True,'image_threshold':0.65}
LOCK=threading.RLock()
def settings():
    try:
        d=json.loads(CONFIG.read_text(encoding='utf-8'));return {**DEFAULT,**{k:v for k,v in d.items() if k in DEFAULT}}
    except (OSError,ValueError):return dict(DEFAULT)
def save_settings(data):
    with LOCK:
        CONFIG.parent.mkdir(parents=True,exist_ok=True);temp=CONFIG.with_suffix('.tmp');temp.write_text(json.dumps(data),encoding='utf-8')
        for attempt in range(10):
            try:temp.replace(CONFIG);return
            except PermissionError:
                if attempt==9:raise
                time.sleep(.05)
SECRETS=[re.compile(r'\b(?:sk-[A-Za-z0-9_-]{12,256}|AIza[A-Za-z0-9_-]{20,200}|AKIA[A-Z0-9]{16})\b'),re.compile(r'(?i)(\b(?:api[_ -]?key|access[_ -]?token|password|비밀번호|비밀키)\s*[=:]\s*[\"\']?)[^\s\"\'`;,]{4,256}'),re.compile(r'(?i)(\bBearer\s+)[A-Za-z0-9_.-]{12,256}'),re.compile(r'(?<!\d)\d{6}-[1-4]\d{6}(?!\d)'),re.compile(r'(?<!\d)01[016789][- ]?\d{3,4}[- ]?\d{4}(?!\d)'),re.compile(r'\b[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,20}\b')]
def redact(text):
    for pattern in SECRETS:text=pattern.sub(lambda m:(m.group(1) if m.lastindex else '')+'[개인정보 가림]',text)
    return text
def reason(text,config=None):
    c=config or settings()
    if c['sexual'] and re.search(r'야동|포르노|성기\s*노출|노골적.{0,8}성행위|\b(?:pornography|explicit sexual activity|naked genitals)\b',text,re.I):return '성인 콘텐츠'
    if c['violence'] and re.search(r'내장\s*노출|훼손된\s*시체|토막\s*살인|\b(?:graphic gore|dismembered corpse)\b',text,re.I):return '노골적인 폭력 콘텐츠'
    return None
def sanitize(text,config=None):
    c=config or settings()
    return redact(text) if c['privacy'] else text
def filtered(text,config=None):
    c=config or settings();blocked=reason(text,c)
    return '[검열: '+blocked+' 차단]\n' if blocked else sanitize(text,c)
def image_reason(scores,config=None):
    c=config or settings()
    for key,label in [('sexual','성인 이미지'),('violence','폭력 이미지')]:
        if c[key] and scores.get(key,0)>=c['image_threshold']:return label
    return None
class TextStreamFilter:
    """Buffer complete lines so secrets split across token chunks never leak partially."""
    def __init__(self,config=None):self.config=config or settings();self.pending=''
    def feed(self,text,final=False):
        if not any(self.config[k] for k in ('privacy','sexual','violence')):return text
        self.pending+=text
        if not final and '\n' not in self.pending:return ''
        if final:ready=self.pending;self.pending=''
        else:index=self.pending.rfind('\n')+1;ready=self.pending[:index];self.pending=self.pending[index:]
        return filtered(ready,self.config)
