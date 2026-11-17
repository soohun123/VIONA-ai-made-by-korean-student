"""Persistent local API credential; never returned by a web endpoint."""
import os,re,secrets
from pathlib import Path

KEY_FILE=Path(__file__).resolve().parent/'.secrets'/'api-key.txt'

def load_api_key():
    KEY_FILE.parent.mkdir(exist_ok=True)
    try:
        fd=os.open(KEY_FILE,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(fd,'w',encoding='ascii') as f:
            f.write('nb_live_'+secrets.token_urlsafe(32)+'\n')
    if KEY_FILE.stat().st_size>256:
        raise RuntimeError('Invalid local API key file; restore the original credential.')
    key=KEY_FILE.read_text(encoding='ascii').strip()
    if not re.fullmatch(r'nb_live_[A-Za-z0-9_-]{43}',key):
        raise RuntimeError('Invalid local API key file; restore the original credential.')
    return key

if __name__=='__main__':
    load_api_key()
    print('API key file:',KEY_FILE)
