"""Resumable Wikipedia lead collection. Everything remains pending human review.

One distinct article is one candidate, never split/repeated to inflate counts.
No model training, automatic approval, or public deployment is performed here.
"""
import argparse,datetime,email.utils,json,os,sqlite3,time,urllib.error,urllib.parse,urllib.request
from pathlib import Path
import psutil
import domain_knowledge as knowledge

ROOT=Path(__file__).resolve().parent
STORE=ROOT/'data/knowledge/collection'
SEEDS={'aviation':['Aviation','Aerodynamics'], 'ai':['Artificial intelligence','Machine learning'],
       'computer':['Computer science','Computer hardware','Operating systems'],
       'coding':['Computer programming','Algorithms','Data structures'],
       'language':['Grammar','Linguistics','English grammar','Korean grammar']}
API='https://en.wikipedia.org/w/api.php'
TERMS='https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use'

class RateLimited(Exception):
    def __init__(self,delay=900):
        self.delay=max(900,delay)
        super().__init__('Public source rate limit; collection paused without changing network identity')

def retry_delay(value):
    try:return max(900,int(value))
    except (TypeError,ValueError):
        try:return max(900,int(email.utils.parsedate_to_datetime(value).timestamp()-time.time()))
        except (TypeError,ValueError,OverflowError):return 900

def write_json(path,value):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(tmp,path)

def api(**params):
    url=API+'?'+urllib.parse.urlencode(dict(action='query',format='json',formatversion=2,maxlag=5,**params))
    request=urllib.request.Request(url,headers={'User-Agent':'NovaBrainKnowledgeCollector/1.0 (local educational research; read-only)'})
    for attempt in range(4):
        time.sleep(10)
        try:
            with urllib.request.urlopen(request,timeout=25) as response:raw=response.read(4_000_001)
            if len(raw)>4_000_000:raise ValueError('API response too large')
            data=json.loads(raw)
            if 'error' in data:raise RuntimeError(str(data['error']))
            return data
        except urllib.error.HTTPError as exc:
            if exc.code==429:raise RateLimited(retry_delay(exc.headers.get('Retry-After'))) from exc
            if exc.code in (401,403):raise
            if attempt==3:raise
            time.sleep(min(2**(attempt+1),15))
        except (OSError,RuntimeError):
            if attempt==3:raise
            time.sleep(min(2**(attempt+1),15))

def candidate(page):
    title=str(page.get('title','')).strip();text=str(page.get('extract','')).strip()
    revisions=page.get('revisions') or []
    if page.get('ns')!=0 or not title or len(text)<100 or len(text)>8000 or not revisions:return None
    revision=revisions[0].get('revid')
    if not isinstance(revision,int) or revision<=0:return None
    # Immutable revision attribution plus edit-history URL, not a fabricated citation.
    url='https://en.wikipedia.org/w/index.php?oldid='+str(revision)
    return {'question':title+' — overview','answer':text,'source_url':url,'license':'CC-BY-SA-4.0',
            'evidence':('Wikipedia contributors; '+url+'; history: https://en.wikipedia.org/w/index.php?title='+
                        urllib.parse.quote(title)+'&action=history; terms: '+TERMS+'\n'+text)[:4000]}

def run(minutes,target):
    STORE.mkdir(parents=True,exist_ok=True)
    # OS-held lock prevents two collectors sharing cursors or inflating counts.
    import msvcrt
    lock=(STORE/'collector.lock').open('a+b');lock.seek(0,2)
    if not lock.tell():lock.write(b'0');lock.flush()
    lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    state_path=STORE/'status.json'
    if state_path.exists():state=json.loads(state_path.read_text(encoding='utf-8'))
    else:
        state={'requested_additional_per_domain':target,'baseline':{r['domain']:r['imported'] for r in knowledge.summary()},
               'source':'Wikipedia English article leads','license':'CC-BY-SA-4.0','review':'pending_human_review',
               'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    if state['requested_additional_per_domain']!=target:raise ValueError('Existing request target differs; preserve original state')
    if state.get('resume_after_unix',0)>time.time():
        print('Source cooldown active. Existing data and cursors preserved.');return
    c=sqlite3.connect(STORE/'cursor.sqlite')
    c.execute('CREATE TABLE IF NOT EXISTS categories(domain TEXT,title TEXT,depth INTEGER,cursor TEXT DEFAULT "",done INTEGER DEFAULT 0,PRIMARY KEY(domain,title))')
    c.execute('CREATE TABLE IF NOT EXISTS pages(domain TEXT,id INTEGER,done INTEGER DEFAULT 0,PRIMARY KEY(domain,id))')
    for domain,seeds in SEEDS.items():
        c.executemany('INSERT OR IGNORE INTO categories(domain,title,depth) VALUES(?,?,0)',[(domain,'Category:'+s) for s in seeds])
    c.commit();started=time.monotonic();state.update(state='running',pid=os.getpid(),error=None)
    try:
        while time.monotonic()-started<minutes*60:
            counts={r['domain']:r['imported'] for r in knowledge.summary()}
            state['added']={d:max(0,counts[d]-state['baseline'][d]) for d in SEEDS}
            state['updated_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();write_json(state_path,state)
            if (STORE/'stop').exists():state['state']='stopped';break
            if psutil.virtual_memory().available<2*2**30:state['state']='paused_low_ram';break
            progressed=False
            for domain in SEEDS:
                if state['added'][domain]>=target:continue
                remaining=target-state['added'][domain]
                ids=[r[0] for r in c.execute('SELECT id FROM pages WHERE domain=? AND done=0 LIMIT ?',(domain,min(20,remaining)))]
                if ids:
                    data=api(prop='extracts|info|revisions',pageids='|'.join(map(str,ids)),exintro=1,explaintext=1,exlimit=20,inprop='url',rvprop='ids|timestamp')
                    records=[]
                    for page in data.get('query',{}).get('pages',[]):
                        record=candidate(page)
                        if record:
                            archive=STORE/'sources'/str(page['pageid']);archive.mkdir(parents=True,exist_ok=True)
                            path=archive/(str(page['revisions'][0]['revid'])+'.json')
                            if not path.exists():write_json(path,page)
                            records.append(record)
                    knowledge.ingest(domain,records)
                    c.executemany('UPDATE pages SET done=1 WHERE domain=? AND id=?',[(domain,i) for i in ids]);c.commit();progressed=True
                else:
                    row=c.execute('SELECT title,depth,cursor FROM categories WHERE domain=? AND done=0 ORDER BY depth,rowid LIMIT 1',(domain,)).fetchone()
                    if not row:continue
                    title,depth,cursor=row
                    params=dict(list='categorymembers',cmtitle=title,cmtype='page|subcat',cmlimit=100)
                    if cursor:params['cmcontinue']=cursor
                    data=api(**params)
                    for member in data.get('query',{}).get('categorymembers',[]):
                        if member['ns']==0:c.execute('INSERT OR IGNORE INTO pages(domain,id) VALUES(?,?)',(domain,member['pageid']))
                        elif member['ns']==14 and depth<3:c.execute('INSERT OR IGNORE INTO categories(domain,title,depth) VALUES(?,?,?)',(domain,member['title'],depth+1))
                    continuation=data.get('continue',{}).get('cmcontinue','')
                    c.execute('UPDATE categories SET cursor=?,done=? WHERE domain=? AND title=?',(continuation,int(not continuation),domain,title));c.commit();progressed=True
            if not progressed:
                state['state']='target_reached' if all(n>=target for n in state['added'].values()) else 'sources_exhausted_partial'
                break
        else:state['state']='paused_time_budget'
    except RateLimited as exc:
        state.update(state='paused_rate_limit',error=str(exc),resume_after_unix=time.time()+exc.delay)
    except Exception as exc:state.update(state='error',error=str(exc));raise
    finally:
        counts={r['domain']:r['imported'] for r in knowledge.summary()}
        state['added']={d:max(0,counts[d]-state['baseline'][d]) for d in SEEDS}
        state['updated_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();write_json(state_path,state);c.close();lock.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--minutes',type=int,default=60);p.add_argument('--per-domain',type=int,default=50000)
    p.add_argument('--follow',action='store_true',help='Resume after source cooldown within the same time budget; never approve records')
    a=p.parse_args()
    if not 1<=a.minutes<=1440 or not 1<=a.per_domain<=50000:p.error('minutes 1..1440; per-domain 1..50000')
    if not a.follow:run(a.minutes,a.per_domain)
    else:
        import msvcrt
        STORE.mkdir(parents=True,exist_ok=True)
        follow_lock=(STORE/'follow.lock').open('a+b');follow_lock.seek(0,2)
        if not follow_lock.tell():follow_lock.write(b'0');follow_lock.flush()
        follow_lock.seek(0);msvcrt.locking(follow_lock.fileno(),msvcrt.LK_NBLCK,1)
        deadline=time.monotonic()+a.minutes*60
        while time.monotonic()<deadline and not (STORE/'stop').exists():
            state=json.loads((STORE/'status.json').read_text(encoding='utf-8')) if (STORE/'status.json').exists() else {}
            if state.get('state') in ('target_reached','sources_exhausted_partial','stopped','error'):break
            if state.get('resume_after_unix',0)>time.time() or psutil.virtual_memory().available<2*2**30:
                time.sleep(min(30,max(.1,deadline-time.monotonic())));continue
            run(max(1,int((deadline-time.monotonic())/60)),a.per_domain)
        follow_lock.close()
