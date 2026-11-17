"""Private durable managed-run records; never included in standalone exports."""
from contextlib import contextmanager
import hashlib
import json
import mimetypes
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import sqlite3
import time
import uuid

TERMINAL = frozenset(('completed','failed','cancelled'))
STOPPED = TERMINAL | {'needs_reconciliation'}
MAX_ARTIFACT_BYTES=25*1024**2
MAX_RUN_ARTIFACT_BYTES=100*1024**2
ARTIFACT_EXTENSIONS={'.txt','.md','.json','.csv','.tsv','.pdf','.docx','.xlsx','.pptx','.png','.jpg','.jpeg','.webp'}


def fingerprint(app):return hashlib.sha256(json.dumps(app,sort_keys=True).encode()).hexdigest()
def encode(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'))


class RunStore:
    def __init__(self,data_dir):
        self.root=Path(data_dir);self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.files=self.root/'managed-artifacts';self.files.mkdir(exist_ok=True,mode=0o700)
        self.db_path=self.root/'managed.sqlite3'
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY,app_id TEXT NOT NULL,fingerprint TEXT NOT NULL,
              messages TEXT NOT NULL,provider_session_id TEXT,environment_id TEXT,knowledge_revision TEXT,archived INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,app_id TEXT NOT NULL,session_id TEXT NOT NULL,
              submission_id TEXT NOT NULL,request_hash TEXT NOT NULL,state TEXT NOT NULL,created REAL NOT NULL,
              updated REAL NOT NULL,record TEXT NOT NULL,payload TEXT,UNIQUE(app_id,submission_id));
            CREATE TABLE IF NOT EXISTS events(sequence INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT NOT NULL,event TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS run_events ON events(run_id,sequence);
            CREATE TABLE IF NOT EXISTS tool_calls(run_id TEXT,turn_id TEXT,call_id TEXT,name TEXT,args TEXT,result TEXT,
              PRIMARY KEY(run_id,turn_id,call_id));
            CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY,app_id TEXT,session_id TEXT,run_id TEXT,
              provider_id TEXT,record TEXT,filename TEXT,UNIQUE(run_id,provider_id));
            CREATE TABLE IF NOT EXISTS resources(session_id TEXT,kind TEXT,provider_id TEXT,status TEXT NOT NULL DEFAULT 'pending',
              PRIMARY KEY(session_id,kind,provider_id));
            ''')
        self.db_path.chmod(0o600)

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.db_path,timeout=15)
        db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()

    def create(self,app,session_id,submission_id,message,attachments):
        if not isinstance(submission_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,128}',submission_id):
            raise ValueError('A stable submission ID of 8–128 safe characters is required')
        request_hash=hashlib.sha256(encode([fingerprint(app),session_id,message,attachments]).encode()).hexdigest()
        # A retried new-conversation request keeps session_id=None and resolves its existing run.
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            prior=db.execute('SELECT * FROM runs WHERE app_id=? AND submission_id=?',(app['id'],submission_id)).fetchone()
            if prior:
                if prior['request_hash']!=request_hash:raise ValueError('Conflicting submission ID; use a new submission for different input')
                return self._internal(prior)
            if session_id is None:
                session_id='managed-'+uuid.uuid4().hex
                db.execute('INSERT INTO conversations(id,app_id,fingerprint,messages) VALUES(?,?,?,?)',
                           (session_id,app['id'],fingerprint(app),'[]'))
            conv=db.execute('SELECT * FROM conversations WHERE id=? AND app_id=?',(session_id,app['id'])).fetchone()
            if not conv:raise ValueError('Conversation not found')
            if conv['archived']:raise ValueError('Conversation workspace is archived; start a new conversation')
            if conv['fingerprint']!=fingerprint(app):raise ValueError('Application configuration changed; start a new conversation')
            if db.execute("SELECT 1 FROM runs WHERE session_id=? AND state NOT IN ('completed','failed','cancelled')",(session_id,)).fetchone():
                raise ValueError('This conversation already has an active or unresolved task')
            messages=json.loads(conv['messages'])
            if len(messages)>=80:raise ValueError('Conversation limit reached; start a new conversation')
            prior_bytes=db.execute('SELECT payload FROM runs WHERE session_id=? AND payload IS NOT NULL',(session_id,)).fetchall()
            if sum(sum(f['size'] for f in json.loads(row[0]).get('attachments',[])) for row in prior_bytes)+sum(f['size'] for f in attachments)>20*1024**2:
                raise ValueError('Conversation attachment limit reached (20 MiB); start a new conversation')
            if sum(len(m.get('content','')) for m in messages)+len(message)>160000:
                raise ValueError('Conversation input limit reached; start a new conversation')
            run_id=uuid.uuid4().hex;now=time.time()
            record={'id':run_id,'app_id':app['id'],'session_id':session_id,'state':'queued','created':now,'updated':now,
                    'provider_session_id':conv['provider_session_id'],'turn_id':None,'error':None,'text':'',
                    'model':app['runtime']['model'],'runtime':'agents','artifacts':[],'usage':None,
                    'cancel_requested':False,'result':None,'knowledge_revision':conv['knowledge_revision']}
            payload={'app':app,'message':message,'attachments':attachments}
            db.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,?,?,?,?)',
                       (run_id,app['id'],session_id,submission_id,request_hash,'queued',now,now,encode(record),encode(payload)))
            public_files=[{k:f[k] for k in ('name','mime_type','size')} for f in attachments]
            messages.append({'role':'user','content':message,'attachments':public_files,'run_id':run_id})
            db.execute('UPDATE conversations SET messages=? WHERE id=?',(encode(messages),session_id))
            return {**record,'submission_id':submission_id,'payload':payload}

    def _internal(self,row):
        return {**json.loads(row['record']),'submission_id':row['submission_id'],
                'payload':json.loads(row['payload']) if row['payload'] else None}

    def find_submission(self,app_id,submission_id):
        with self.db() as db:
            row=db.execute('SELECT record FROM runs WHERE app_id=? AND submission_id=?',(app_id,submission_id)).fetchone()
        if not row:raise ValueError('Run not found')
        return json.loads(row[0])

    def internal(self,run_id):
        with self.db() as db:row=db.execute('SELECT * FROM runs WHERE id=?',(run_id,)).fetchone()
        if not row:raise ValueError('Run not found')
        return self._internal(row)

    def get(self,app_id,run_id):
        with self.db() as db:row=db.execute('SELECT record FROM runs WHERE id=? AND app_id=?',(run_id,app_id)).fetchone()
        if not row:raise ValueError('Run not found')
        return json.loads(row[0])

    def update(self,run_id,**values):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT record FROM runs WHERE id=?',(run_id,)).fetchone()
            if not row:raise ValueError('Run not found')
            record=json.loads(row[0])
            if record['state'] in TERMINAL and values.get('state',record['state'])!=record['state']:return record
            record.update(values);record['updated']=time.time()
            db.execute('UPDATE runs SET state=?,updated=?,record=? WHERE id=?',
                       (record['state'],record['updated'],encode(record),run_id))
        return record

    def bind(self,run_id,provider_session_id,environment_id=None,knowledge_revision=None):
        run=self.update(run_id,provider_session_id=provider_session_id)
        with self.db() as db:
            db.execute('UPDATE conversations SET provider_session_id=?,environment_id=COALESCE(?,environment_id),knowledge_revision=COALESCE(?,knowledge_revision) WHERE id=?',
                       (provider_session_id,environment_id,knowledge_revision,run['session_id']))
        self.resource(run['session_id'],'session',provider_session_id)

    def conversation(self,app_id,session_id):
        with self.db() as db:row=db.execute('SELECT * FROM conversations WHERE id=? AND app_id=?',(session_id,app_id)).fetchone()
        if not row:raise ValueError('Conversation not found')
        return dict(row)

    def event(self,run_id,event):
        with self.db() as db:
            cur=db.execute('INSERT INTO events(run_id,event) VALUES(?,?)',(run_id,encode(event)))
            return {**event,'sequence':cur.lastrowid,'run_id':run_id}

    def events(self,app_id,run_id,after=0):
        self.get(app_id,run_id)
        with self.db() as db:rows=db.execute('SELECT sequence,event FROM events WHERE run_id=? AND sequence>? ORDER BY sequence LIMIT 500',(run_id,after)).fetchall()
        return [{**json.loads(r['event']),'sequence':r['sequence'],'run_id':run_id} for r in rows]

    def active(self):
        with self.db() as db:rows=db.execute("SELECT * FROM runs WHERE state NOT IN ('completed','failed','cancelled')").fetchall()
        return [self._internal(row) for row in rows]

    def finish(self,run_id,message):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM runs WHERE id=?',(run_id,)).fetchone();record=json.loads(row['record'])
            if record['state']=='completed':return record
            if record['state'] in ('failed','cancelled'):raise ValueError('Cannot complete a terminal run')
            messages=json.loads(db.execute('SELECT messages FROM conversations WHERE id=?',(row['session_id'],)).fetchone()[0])
            message={**message,'run_id':run_id};messages.append(message)
            result={'session_id':row['session_id'],'message':message}
            record.update(state='completed',result=result,updated=time.time())
            db.execute('UPDATE conversations SET messages=? WHERE id=?',(encode(messages),row['session_id']))
            db.execute('UPDATE runs SET state=?,updated=?,record=? WHERE id=?',('completed',record['updated'],encode(record),run_id))
        return record

    def list_sessions(self,app_id):
        with self.db() as db:rows=db.execute('SELECT id,messages FROM conversations WHERE app_id=? ORDER BY rowid DESC',(app_id,)).fetchall()
        return [{'id':r['id'],'title':(json.loads(r['messages'])[0]['content'] or 'Attached documents')[:70]} for r in rows]

    def get_session(self,app_id,session_id):
        conv=self.conversation(app_id,session_id)
        with self.db() as db:row=db.execute('SELECT record FROM runs WHERE session_id=? ORDER BY rowid DESC LIMIT 1',(session_id,)).fetchone()
        return {'id':session_id,'messages':json.loads(conv['messages']),'run':json.loads(row[0]) if row else None,'archived':bool(conv['archived'])}

    def tool_begin(self,run_id,turn_id,call_id,name,args):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM tool_calls WHERE run_id=? AND turn_id=? AND call_id=?',(run_id,turn_id,call_id)).fetchone()
            if row:
                if row['name']!=name or json.loads(row['args'])!=args:raise ValueError('Conflicting pending tool call')
                return {'replayed':True,'result':json.loads(row['result']) if row['result'] else None}
            db.execute('INSERT INTO tool_calls VALUES(?,?,?,?,?,NULL)',(run_id,turn_id,call_id,name,encode(args)))
        return {'replayed':False,'result':None}

    def tool_finish(self,run_id,turn_id,call_id,result):
        if len(encode(result).encode())>1024**2:raise ValueError('Application tool output exceeds 1 MiB')
        with self.db() as db:db.execute('UPDATE tool_calls SET result=? WHERE run_id=? AND turn_id=? AND call_id=?',(encode(result),run_id,turn_id,call_id))

    def tool_count(self,run_id):
        with self.db() as db:return db.execute('SELECT count(*) FROM tool_calls WHERE run_id=?',(run_id,)).fetchone()[0]

    def artifact(self,run_id,metadata,chunks):
        run=self.internal(run_id);path=metadata.get('path','');size=metadata.get('size_bytes')
        if (metadata.get('session_id')!=run['provider_session_id'] or metadata.get('turn_id')!=run['turn_id']
            or not isinstance(path,str) or not path.startswith('/workspace/outputs/') or posixpath.normpath(path)!=path
            or re.search(r'[\x00-\x1f\x7f\\]',path) or len(PurePosixPath(path).name)>200
            or PurePosixPath(path).suffix.lower() not in ARTIFACT_EXTENSIONS
            or type(size) is not int or not 0<=size<=MAX_ARTIFACT_BYTES):
            raise ValueError('Invalid, unsupported, oversized or cross-turn artifact')
        with self.db() as db:
            prior=db.execute('SELECT record FROM artifacts WHERE run_id=? AND provider_id=?',(run_id,metadata['id'])).fetchone()
            rows=db.execute('SELECT record FROM artifacts WHERE run_id=?',(run_id,)).fetchall()
        if prior:return json.loads(prior[0])
        if sum(json.loads(r[0])['size'] for r in rows)+size>MAX_RUN_ARTIFACT_BYTES:raise ValueError('Run artifacts exceed 100 MiB')
        aid=uuid.uuid4().hex;target=self.files/aid;total=0
        try:
            with target.open('xb') as file:
                target.chmod(0o600)
                for chunk in chunks:
                    if not isinstance(chunk,bytes):raise ValueError('Invalid artifact content')
                    total+=len(chunk)
                    if total>size or total>MAX_ARTIFACT_BYTES:raise ValueError('Artifact content exceeds declared size')
                    file.write(chunk)
            if total!=size:raise ValueError('Artifact content does not match declared size')
            record={'id':aid,'name':PurePosixPath(path).name,'size':size,'run_id':run_id,'session_id':run['session_id'],
                    'type':mimetypes.guess_type(path)[0] or 'application/octet-stream'}
            with self.db() as db:db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)',
                (aid,run['app_id'],run['session_id'],run_id,metadata['id'],encode(record),aid))
            return record
        except Exception:
            target.unlink(missing_ok=True);raise

    def artifact_content(self,app_id,artifact_id):
        with self.db() as db:row=db.execute('SELECT * FROM artifacts WHERE app_id=? AND id=?',(app_id,artifact_id)).fetchone()
        if not row:raise ValueError('Artifact not found')
        target=self.files/row['filename']
        if not target.is_file():raise ValueError('Artifact expired or unavailable')
        return {**json.loads(row['record']),'path':target}

    def resource(self,session_id,kind,provider_id):
        with self.db() as db:db.execute('INSERT OR IGNORE INTO resources(session_id,kind,provider_id) VALUES(?,?,?)',(session_id,kind,provider_id))

    def resources(self,session_id):
        with self.db() as db:return [dict(r) for r in db.execute('SELECT * FROM resources WHERE session_id=?',(session_id,)).fetchall()]

    def resource_done(self,session_id,kind,provider_id):
        with self.db() as db:db.execute("UPDATE resources SET status='deletion_confirmed' WHERE session_id=? AND kind=? AND provider_id=?",(session_id,kind,provider_id))

    def archive(self,app_id,session_id):
        self.conversation(app_id,session_id)
        with self.db() as db:
            if db.execute("SELECT 1 FROM runs WHERE session_id=? AND state NOT IN ('completed','failed','cancelled')",(session_id,)).fetchone():
                raise ValueError('Cancel or reconcile active work before deleting its resources')
            rows=db.execute('SELECT id,filename FROM artifacts WHERE session_id=?',(session_id,)).fetchall()
            for row in rows:(self.files/row['filename']).unlink(missing_ok=True)
            db.execute('DELETE FROM artifacts WHERE session_id=?',(session_id,))
            db.execute('DELETE FROM events WHERE run_id IN (SELECT id FROM runs WHERE session_id=?)',(session_id,))
            db.execute('DELETE FROM tool_calls WHERE run_id IN (SELECT id FROM runs WHERE session_id=?)',(session_id,))
            db.execute('UPDATE runs SET payload=NULL WHERE session_id=?',(session_id,))
            for row in db.execute('SELECT id,record FROM runs WHERE session_id=?',(session_id,)).fetchall():
                record=json.loads(row['record']);record.pop('sources',None);record['artifacts_expired']=True
                if record.get('result'):
                    for item in record['result']['message'].get('artifacts',[])+record['result']['message'].get('citations',[]):item['expired']=True
                for item in record.get('artifacts',[]):item['expired']=True
                db.execute('UPDATE runs SET record=? WHERE id=?',(encode(record),row['id']))
            messages=json.loads(db.execute('SELECT messages FROM conversations WHERE id=?',(session_id,)).fetchone()[0])
            for message in messages:
                for item in message.get('artifacts',[])+message.get('citations',[]):item['expired']=True
            db.execute('UPDATE conversations SET archived=1,messages=? WHERE id=?',(encode(messages),session_id))

    def pending_cleanup(self):
        with self.db() as db:
            rows=db.execute("SELECT DISTINCT c.app_id,c.id FROM conversations c JOIN resources r ON c.id=r.session_id WHERE c.archived=1 AND r.status!='deletion_confirmed'").fetchall()
        return [(r['app_id'],r['id']) for r in rows]

    def expired(self,now=None):
        now=time.time() if now is None else now;found=[]
        with self.db() as db:rows=db.execute('SELECT c.id,c.app_id,r.payload,max(r.updated) AS updated FROM conversations c JOIN runs r ON c.id=r.session_id WHERE c.archived=0 GROUP BY c.id').fetchall()
        for row in rows:
            payload=json.loads(row['payload']) if row['payload'] else {}
            days=payload.get('app',{}).get('runtime',{}).get('agents',{}).get('artifact_retention_days',7)
            if row['updated']<now-days*86400:found.append((row['app_id'],row['id']))
        return found
