"""Versioned, strict Ollama assessments; separate resumable SQLite sidecar."""
from __future__ import annotations
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import urllib.request

import vlog_maker as core

SCHEMA_VERSION = 1
PROMPT_VERSION = 'travel-observations-1'
CATEGORIES = {'landscape','city','transport','food','people','activity','architecture','other'}
PROMPT = '''Evaluate only the supplied chronological representative images from one video scene.
Return exactly one JSON object with these fields:
technical_quality (number 0..100), visual_interest (number 0..100),
event_importance (number 0..100), category (landscape|city|transport|food|people|activity|architecture|other),
description (nonempty factual string <=500 characters), analysis_confidence (number 0..1 or null).
Do not infer unseen action. Use null confidence if it cannot be calibrated.
Do not assess story relevance or redundancy: these require the editing context and other candidates.
Technical quality should account for uncertainty across all representative images.'''


def validate(value):
    keys = {'technical_quality','visual_interest','event_importance','category','description','analysis_confidence'}
    if not isinstance(value, dict) or set(value) != keys: raise ValueError('Assessment fields mismatch')
    def number(key, maximum):
        n = value[key]
        if isinstance(n,bool) or not isinstance(n,(int,float)) or not math.isfinite(n) or not 0 <= n <= maximum:
            raise ValueError(f'Invalid {key}')
    for key in ('technical_quality','visual_interest','event_importance'): number(key,100)
    if value['analysis_confidence'] is not None: number('analysis_confidence',1)
    if not isinstance(value['category'],str) or value['category'] not in CATEGORIES: raise ValueError('Invalid category')
    description = value['description']
    if not isinstance(description,str) or not description.strip() or len(description)>500: raise ValueError('Invalid description')
    return dict(value)


def decode(raw):
    def unique(pairs):
        result = {}
        for key,value in pairs:
            if key in result: raise ValueError('Duplicate JSON field')
            result[key] = value
        return result
    return validate(json.loads(raw, object_pairs_hook=unique))


def model_identity(model):
    url = os.environ.get('AI_VLOG_OLLAMA_URL','http://127.0.0.1:11434').rstrip('/')
    with urllib.request.urlopen(url+'/api/tags',timeout=15) as response: tags=json.load(response)
    wanted = model if ':' in model else model+':latest'
    matches = [m for m in tags['models'] if m.get('name','').casefold()==wanted.casefold()]
    if not matches or not matches[0].get('digest'): raise ValueError('Cannot resolve installed model digest')
    return matches[0]['name'], matches[0]['digest']


def infer(candidate, model, timeout=120):
    images=[]
    for position in candidate['positions']:
        args=['ffmpeg','-nostdin','-v','error']
        if candidate['kind']=='video': args+=['-ss',str(position)]
        args+=['-i',candidate['path'],'-frames:v','1','-vf','scale=640:360:force_original_aspect_ratio=decrease',
               '-f','image2pipe','-c:v','mjpeg','-']
        images.append(base64.b64encode(core.command(args,True,True)).decode('ascii'))
    body=dict(model=model,stream=False,format='json',
              options=dict(temperature=0,seed=0,num_gpu=0,num_predict=768),
              messages=[dict(role='user',content=PROMPT,images=images)])
    url=os.environ.get('AI_VLOG_OLLAMA_URL','http://127.0.0.1:11434').rstrip('/')+'/api/chat'
    request=urllib.request.Request(url,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=timeout) as response: payload=json.load(response)
    return payload['message']['content']


class AssessmentCache:
    def __init__(self, path):
        path=Path(path)
        # Deliberately refuse legacy workspace databases, including a caller typo.
        if path.name.lower()=='index.sqlite': raise ValueError('Use a separate v16 assessment cache')
        path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path)
        try:
            existing={r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if existing-{'assessments'}: raise ValueError('Not a v16 assessment sidecar')
            self.db.execute('''CREATE TABLE IF NOT EXISTS assessments(
                key TEXT PRIMARY KEY, candidate_id TEXT, model TEXT, model_digest TEXT,
                prompt_version TEXT, schema_version INTEGER, status TEXT,
                assessment TEXT, raw TEXT, error TEXT, attempts INTEGER NOT NULL)''')
            self.db.commit()
        except Exception:
            self.db.close();raise

    def close(self): self.db.close()

    def assess(self, candidate, model, digest, transport=infer):
        canonical=json.dumps(dict(candidate=candidate,model=model,digest=digest,prompt=PROMPT,
                                  prompt_version=PROMPT_VERSION,schema_version=SCHEMA_VERSION),sort_keys=True,allow_nan=False)
        key=hashlib.sha256(canonical.encode()).hexdigest()
        row=self.db.execute('SELECT status,assessment,attempts FROM assessments WHERE key=?',(key,)).fetchone()
        if row and row[0]=='ok':
            try: return dict(status='ok',assessment=decode(row[1]),cached=True,key=key)
            except (ValueError,TypeError): pass
        raw=None;assessment=None;error=None
        try:
            raw=transport(candidate,model)
            assessment=decode(raw)
        except Exception as exc: error=f'{type(exc).__name__}: {exc}'
        status='failed' if error else 'ok'
        if raw is not None and not isinstance(raw,str): raw=repr(raw)
        self.db.execute('INSERT OR REPLACE INTO assessments VALUES(?,?,?,?,?,?,?,?,?,?,?)',
            (key,candidate['id'],model,digest,PROMPT_VERSION,SCHEMA_VERSION,status,
             json.dumps(assessment,ensure_ascii=False) if assessment else None,raw,error,(row[2] if row else 0)+1))
        self.db.commit()
        return dict(status=status,assessment=assessment,error=error,cached=False,key=key)
