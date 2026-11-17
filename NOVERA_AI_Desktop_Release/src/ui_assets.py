"""Version local UI URLs so WebView2 never reuses an older installation's page."""
import hashlib
from pathlib import Path

def prepare_ui(assets,data):
    assets=Path(assets);contents={name:(assets/name).read_bytes() for name in ['index.html','desktop.css','desktop.js','logo.svg']}
    version=hashlib.sha256(b''.join(name.encode()+body for name,body in sorted(contents.items()))).hexdigest()[:20]
    folder=Path(data)/version;folder.mkdir(parents=True,exist_ok=True)
    html=contents.pop('index.html').decode('utf-8')
    for name in contents:html=html.replace('"'+name+'"','"'+name+'?v='+version+'"')
    for name,body in contents.items():(folder/name).write_bytes(body)
    page=folder/('index-'+version+'.html');page.write_text(html,encoding='utf-8')
    return page
