"""Local application accounts, not Google/Naver identity-provider authentication."""
import base64,contextlib,hashlib,hmac,json,re,secrets,sqlite3,threading,time,uuid
from pathlib import Path


def password_hash(password):
    salt=secrets.token_bytes(16)
    value=hashlib.scrypt(password.encode('utf-8'),salt=salt,n=16384,r=8,p=1,dklen=32)
    return {'algorithm':'scrypt','n':16384,'r':8,'p':1,'salt':base64.b64encode(salt).decode(),'hash':base64.b64encode(value).decode()}


def verify(password,record):
    value=hashlib.scrypt(password.encode('utf-8'),salt=base64.b64decode(record['salt']),
                         n=16384,r=8,p=1,dklen=32)
    return hmac.compare_digest(value,base64.b64decode(record['hash']))


class Accounts:
    def __init__(self,data,seed):
        self.directory=Path(data)/'accounts';self.directory.mkdir(parents=True,exist_ok=True)
        self.database=self.directory/'accounts.sqlite';self.lock=threading.RLock()
        self.developer=json.loads(Path(seed).read_text(encoding='utf-8'))
        with self.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,login TEXT UNIQUE,password TEXT,role TEXT,created REAL)')
            c.execute('CREATE TABLE IF NOT EXISTS attempts(login TEXT PRIMARY KEY,count INTEGER,until REAL)')
            c.execute('CREATE TABLE IF NOT EXISTS identities(provider TEXT,subject TEXT,user_id TEXT,display TEXT,email TEXT,PRIMARY KEY(provider,subject))')
            c.execute('INSERT OR IGNORE INTO users VALUES(?,?,?,?,?)',
                      ('developer',self.developer['login'],json.dumps(self.developer['password_hash']),'developer',time.time()))

    @contextlib.contextmanager
    def connect(self):
        c=sqlite3.connect(self.database,timeout=10);c.row_factory=sqlite3.Row
        try:
            with c:yield c
        finally:c.close()

    def register(self,login,password,confirmation):
        if not all(isinstance(v,str) for v in (login,password,confirmation)):
            return {'error':'입력 내용을 확인해 주세요.'}
        login=login.strip().lower()
        if not re.fullmatch(r'[a-z0-9][a-z0-9_]{2,31}',login):
            return {'error':'아이디는 영문 소문자·숫자·밑줄로 3~32자 입력하세요.'}
        if login in ('developer','admin','administrator','root',str(self.developer['login']).lower()):
            return {'error':'사용할 수 없는 아이디입니다.'}
        if len(password)<10 or len(password)>128:
            return {'error':'비밀번호는 10~128자로 입력하세요.'}
        if password!=confirmation:return {'error':'비밀번호 확인이 일치하지 않습니다.'}
        identifier=uuid.uuid4().hex
        hashed=json.dumps(password_hash(password))
        with self.lock,self.connect() as c:
            try:c.execute('INSERT INTO users VALUES(?,?,?,?,?)',(identifier,login,hashed,'user',time.time()))
            except sqlite3.IntegrityError:return {'error':'이미 사용 중인 아이디입니다.'}
        return {'ok':True}

    def login(self,login,password):
        login=str(login).strip().lower();password=str(password)
        if not login or len(login)>254 or len(password)>128:return {'error':'계정 또는 비밀번호를 확인해 주세요.'}
        with self.lock,self.connect() as c:
            attempt=c.execute('SELECT * FROM attempts WHERE login=?',(login,)).fetchone()
            if attempt and attempt['until']>time.time():return {'error':'로그인 시도가 많습니다. 잠시 후 다시 시도해 주세요.'}
            row=c.execute('SELECT * FROM users WHERE login=?',(login,)).fetchone()
            record=json.loads(row['password']) if row else None
            valid=verify(password,record or self.developer['password_hash']) and bool(record)
            if not row or not valid:
                count=(attempt['count'] if attempt and not attempt['until'] else 0)+1
                c.execute('INSERT OR REPLACE INTO attempts VALUES(?,?,?)',(login,count,time.time()+60 if count>=5 else 0))
                return {'error':'계정 또는 비밀번호를 확인해 주세요.'}
            c.execute('DELETE FROM attempts WHERE login=?',(login,))
            return {'ok':True,'user':{'id':row['id'],'login':row['login'],'role':row['role'],'email_verified':False}}

    def social(self,provider,profile):
        if provider not in ('google','naver'):raise ValueError('Unsupported provider')
        subject=profile.get('sub') if provider=='google' else profile.get('id')
        if not isinstance(subject,str) or not subject or len(subject)>255:raise ValueError('계정 식별 정보가 없습니다.')
        email=str(profile.get('email') or '')[:254];display=str(profile.get('name') or profile.get('nickname') or email or provider)[:120]
        with self.lock,self.connect() as c:
            row=c.execute('SELECT user_id FROM identities WHERE provider=? AND subject=?',(provider,subject)).fetchone()
            identifier=row['user_id'] if row else uuid.uuid4().hex
            if not row:
                c.execute('INSERT INTO users VALUES(?,?,?,?,?)',(identifier,provider+':'+subject,'null','user',time.time()))
                c.execute('INSERT INTO identities VALUES(?,?,?,?,?)',(provider,subject,identifier,display,email))
        # Never infer developer privileges from a provider's email or display name.
        return {'id':identifier,'login':display,'email':email,'provider':provider,'role':'user','email_verified':profile.get('email_verified') is True if provider=='google' else False}

    def history_path(self,user):
        # Only a DB-produced identifier selects a path; caller-supplied filenames do not.
        identifier=user['id']
        if identifier!='developer' and not re.fullmatch('[a-f0-9]{32}',identifier):raise ValueError('Invalid account identifier')
        return self.directory/(identifier+'-conversations.json')
