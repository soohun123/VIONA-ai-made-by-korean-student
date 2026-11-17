"""Source-tracked human review and retrieval. Indexing is not neural weight training."""
import datetime,hashlib,json,re,sqlite3,contextlib
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parent
DATABASE=ROOT/'data/knowledge/review.sqlite'
DOMAINS=('aviation','ai','computer','coding','language')
LICENSES={'CC0','CC-BY-4.0','CC-BY-SA-4.0','MIT','Apache-2.0','public-domain','permission'}
@contextlib.contextmanager
def connect(path=None):
    path=Path(path or DATABASE);path.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(path,timeout=20,check_same_thread=False);c.row_factory=sqlite3.Row
    try:
        c.execute('CREATE TABLE IF NOT EXISTS facts(id TEXT PRIMARY KEY,domain TEXT,question TEXT,answer TEXT,url TEXT,license TEXT,evidence TEXT,reviewed INTEGER DEFAULT 0,reviewer TEXT,reviewed_at TEXT,content_hash TEXT)')
        try:c.execute('CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(id UNINDEXED,question,answer)')
        except sqlite3.OperationalError:pass
        with c:yield c
    finally:c.close()
def summary(path=None):
    collection={}
    if path is None:
        try:collection=json.loads((ROOT/'data/knowledge/collection/status.json').read_text(encoding='utf-8'))
        except (OSError,ValueError):pass
    with connect(path) as c:
        return [{'domain':d,'target':100000,'imported':c.execute('SELECT count(*) FROM facts WHERE domain=?',(d,)).fetchone()[0],'approved':c.execute('SELECT count(*) FROM facts WHERE domain=? AND reviewed=1',(d,)).fetchone()[0],'weight_training':'not_started',
                 **({'collection':{'state':collection.get('state'),'requested_additional':collection.get('requested_additional_per_domain',0),'added':collection.get('added',{}).get(d,0),'updated_at':collection.get('updated_at')}} if collection else {})} for d in DOMAINS]
def ingest(domain,records):
    if domain not in DOMAINS:raise ValueError('지원하지 않는 분야입니다.')
    rows=[]
    for r in records:
        q=str(r.get('question','')).strip();a=str(r.get('answer','')).strip();url=str(r.get('source_url','')).strip()
        if not q or not a or len(q)>2000 or len(a)>8000:raise ValueError('질문·답변 길이를 확인해 주세요.')
        parsed=urlsplit(url)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username:raise ValueError('HTTPS 출처 주소를 입력해 주세요.')
        license=str(r.get('license','unknown'));evidence=str(r.get('evidence',''))[:4000]
        digest=hashlib.sha256((q+'\0'+a).encode()).hexdigest();identifier=hashlib.sha256((domain+digest).encode()).hexdigest()
        rows.append((identifier,domain,q,a,url,license,evidence,digest))
    added=0
    with connect() as c:
        fts=c.execute("SELECT 1 FROM sqlite_master WHERE name='search'").fetchone()
        for r in rows:
            if c.execute('INSERT OR IGNORE INTO facts(id,domain,question,answer,url,license,evidence,content_hash) VALUES(?,?,?,?,?,?,?,?)',r).rowcount:
                added+=1
                if fts:c.execute('INSERT INTO search VALUES(?,?,?)',(r[0],r[2],r[3]))
            else:c.execute('UPDATE facts SET url=?,license=?,evidence=? WHERE id=? AND reviewed=0',(r[4],r[5],r[6],r[0]))
    return {'added':added,'duplicates':len(rows)-added,'status':'pending_human_review'}
def pending(domain,limit=20):
    with connect() as c:return [dict(r) for r in c.execute('SELECT * FROM facts WHERE domain=? AND reviewed=0 LIMIT ?',(domain,limit))]
def approve(identifier,reviewer,approved=True):
    reviewer=reviewer.strip()
    if not reviewer:raise ValueError('검수자 이름을 입력해 주세요.')
    with connect() as c:
        row=c.execute('SELECT * FROM facts WHERE id=?',(identifier,)).fetchone()
        if not row:raise ValueError('자료를 찾을 수 없습니다.')
        if approved and (row['license'] not in LICENSES or not row['evidence'].strip()):raise ValueError('이용 허락과 근거 본문을 확인해야 승인할 수 있습니다.')
        c.execute('UPDATE facts SET reviewed=?,reviewer=?,reviewed_at=? WHERE id=?',(int(approved),reviewer,datetime.datetime.now(datetime.timezone.utc).isoformat(),identifier))
    return {'id':identifier,'approved':approved}
def retrieve(domain,text,path=None):
    tokens=list(dict.fromkeys(re.findall(r'[A-Za-z0-9가-힣]{2,}',text)))[:8]
    if not tokens or domain not in DOMAINS:return []
    with connect(path) as c:
        try:
            query=' OR '.join('"'+t+'"*' for t in tokens)
            rows=c.execute('SELECT f.* FROM search JOIN facts f ON f.id=search.id WHERE search MATCH ? AND f.domain=? AND f.reviewed=1 ORDER BY rank LIMIT 3',(query,domain)).fetchall()
        except sqlite3.OperationalError:
            rows=c.execute('SELECT * FROM facts WHERE domain=? AND reviewed=1 AND (question LIKE ? OR answer LIKE ?) LIMIT 3',(domain,'%'+tokens[0]+'%','%'+tokens[0]+'%')).fetchall()
    return [{'id':r['id'],'title':r['question'],'answer':r['answer'][:1000],'url':r['url'],'license':r['license'],'reviewed':True} for r in rows]
def snapshot(path):
    with connect() as source,contextlib.closing(sqlite3.connect(path)) as destination:source.backup(destination)
def export(domain):
    if domain not in DOMAINS:raise ValueError('지원하지 않는 분야입니다.')
    directory=ROOT/'data/knowledge/exports';directory.mkdir(parents=True,exist_ok=True);path=directory/(domain+'.jsonl')
    with connect() as c,path.open('w',encoding='utf-8') as f:
        for row in c.execute('SELECT * FROM facts WHERE domain=? AND reviewed=1',(domain,)):
            f.write(json.dumps({'messages':[{'role':'user','content':row['question']},{'role':'assistant','content':row['answer']}],'source_url':row['url'],'license':row['license'],'reviewed_by':row['reviewer'],'content_hash':row['content_hash']},ensure_ascii=False)+'\n')
    return path
