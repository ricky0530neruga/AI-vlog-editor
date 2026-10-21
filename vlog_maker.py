#!/usr/bin/env python3
"""AI Travel Vlog V4.3: local, resumable, source files always read-only. Python >=3.10."""
import argparse
import base64
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

# Bundled FFmpeg binaries take priority; fallback to Windows PATH.
BIN_DIR = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
FFMPEG_DIR = BIN_DIR / 'tools'
def exe(name):
    local = FFMPEG_DIR / (name + '.exe' if os.name == 'nt' else name)
    return str(local) if local.is_file() else (shutil.which(name) or name)

VIDEOS={'.mp4','.mov','.m4v','.avi','.mkv','.webm','.mts','.m2ts'}
PHOTOS={'.jpg','.jpeg','.png','.webp','.bmp','.tif','.tiff'}
DEFAULT_IN=r'C:\Users\SCE\Desktop\Travel1'
DEFAULT_OUT=r'C:\Users\SCE\Desktop\Vlogwork'
VERSION='4.3'

def command(cmd, capture=False, binary=False):
    p=subprocess.run([exe(str(x)) if str(x) in ('ffmpeg','ffprobe') else str(x) for x in cmd], stdin=subprocess.DEVNULL,
                     stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                     stderr=subprocess.PIPE)
    if p.returncode:
        raise RuntimeError(p.stderr.decode('utf-8','replace')[-1800:])
    if capture: return p.stdout if binary else p.stdout.decode('utf-8','replace')

def probe(path):
    o=json.loads(command(['ffprobe','-v','error','-show_format','-show_streams','-of','json',path],True))
    v=next((x for x in o.get('streams',[]) if x.get('codec_type')=='video'),{})
    f=o.get('format',{})
    dur=float(f.get('duration') or v.get('duration') or 0)
    date=None
    for source in (v.get('tags',{}),f.get('tags',{})):
        for key in ('creation_time','com.apple.quicktime.creationdate','date'):
            val=source.get(key)
            if val:
                try:
                    parsed=dt.datetime.fromisoformat(val.replace('Z','+00:00'))
                    date=parsed.timestamp() if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc).timestamp()
                    break
                except (ValueError,OverflowError): pass
        if date is not None: break
    return dur,int(v.get('width') or 0),int(v.get('height') or 0),date

def connect(out):
    out.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(out/'index.sqlite')
    db.execute('PRAGMA busy_timeout=10000')
    db.execute('''CREATE TABLE IF NOT EXISTS media(path TEXT PRIMARY KEY, kind TEXT, size INTEGER,
        mtime REAL, duration REAL, width INTEGER, height INTEGER, error TEXT)''')
    db.execute('''CREATE TABLE IF NOT EXISTS candidates(id TEXT PRIMARY KEY, path TEXT,
        position REAL, score REAL, description TEXT, analyzed INTEGER DEFAULT 0, error TEXT)''')
    # Upgrade existing V1 database in place; retain previously indexed sources.
    for table,col,typ in [('media','taken','REAL'),('candidates','phash','TEXT'),
                          ('candidates','category','TEXT'),('candidates','role','TEXT'),
                          ('candidates','event','REAL'),('candidates','people','INTEGER'),
                          ('candidates','v2','INTEGER DEFAULT 0'),('candidates','model_id','TEXT'),('candidates','analysis_mode','TEXT')]:
        fields={x[1] for x in db.execute(f'PRAGMA table_info({table})')}
        if col not in fields: db.execute(f'ALTER TABLE {table} ADD COLUMN {col} {typ}')
    # Separate first-pass cache from 12B review: resumable and model-specific.
    for col,typ in [('quick_score','REAL'),('quick_event','REAL'),('quick_model','TEXT'),('quick_done','INTEGER DEFAULT 0'),('prefilter_skip','TEXT')]:
        fields={x[1] for x in db.execute('PRAGMA table_info(candidates)')}
        if col not in fields: db.execute(f'ALTER TABLE candidates ADD COLUMN {col} {typ}')
    db.execute('CREATE INDEX IF NOT EXISTS candidate_media_idx ON candidates(path,position)')
    db.commit()
    return db

def scan(db,roots,out,limit):
    count=0
    for root in roots:
        root=root.expanduser().resolve()
        if not root.exists(): raise ValueError(f'Input does not exist: {root}')
        if root.is_file():
            walk_items=[(str(root.parent), [], [root.name])]
        else:
            walk_items=os.walk(root)
        for folder,dirs,files in walk_items:
            dirs[:]=sorted(d for d in dirs if not (Path(folder)/d).resolve().is_relative_to(out))
            for name in sorted(files):
                path=Path(folder)/name
                ext=path.suffix.lower()
                if ext not in VIDEOS|PHOTOS or path.resolve().is_relative_to(out):continue
                try:
                    st=path.stat(); old=db.execute('SELECT size,mtime,error FROM media WHERE path=?',(str(path),)).fetchone()
                    if old and old[0]==st.st_size and old[1]==st.st_mtime and not old[2]:continue
                    kind='photo' if ext in PHOTOS else 'video'
                    dur,w,h,taken=(0.,0,0,None) if kind=='photo' else probe(path)
                    if kind=='video' and dur<0.4: raise ValueError('Missing/short duration')
                    db.execute('''INSERT INTO media(path,kind,size,mtime,duration,width,height,error,taken)
                        VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET
                        kind=excluded.kind,size=excluded.size,mtime=excluded.mtime,duration=excluded.duration,
                        width=excluded.width,height=excluded.height,error=excluded.error,taken=excluded.taken''',
                        (str(path),kind,st.st_size,st.st_mtime,dur,w,h,None,taken))
                    db.execute('DELETE FROM candidates WHERE path=?',(str(path),))
                except Exception as e:
                    print('[SKIP]',path,str(e)[:150])
                count+=1
                if count%25==0: db.commit();print('Scanned',count)
                if limit and count>=limit:db.commit();return
    db.commit()

def candidates(db,step,max_per_video):
    for path,kind,dur in db.execute('SELECT path,kind,duration FROM media WHERE error IS NULL ORDER BY COALESCE(taken,mtime),path'):
        if kind=='photo':positions=[0.]
        else:
            n=min(max_per_video,max(1,math.ceil(dur/step)))
            positions=[round(min(dur-0.1,(i+0.5)*dur/n),3) for i in range(n)]
        for pos in positions:
            key=hashlib.sha256(f'{path}|{pos}'.encode('utf-8')).hexdigest()[:24]
            db.execute('INSERT OR IGNORE INTO candidates(id,path,position) VALUES(?,?,?)',(key,path,pos))
    db.commit()

def thumbnail(path,kind,pos,dest):
    dest.parent.mkdir(parents=True,exist_ok=True)
    cmd=['ffmpeg','-hide_banner','-loglevel','error','-y']
    if kind=='video':cmd+=['-ss',str(max(0,pos))]
    cmd+=['-i',path,'-frames:v','1','-vf','scale=640:360:force_original_aspect_ratio=decrease',str(dest)]
    command(cmd)

def perceptual_hash(image):
    """Difference hash, aspect-ratio normalized, 64 bits; no pip dependencies."""
    raw=command(['ffmpeg','-hide_banner','-loglevel','error','-i',image,'-frames:v','1',
                 '-vf','scale=9:8,format=gray','-f','rawvideo','-'],True,True)
    if len(raw)!=72: raise ValueError('Cannot compute image hash')
    bits=0
    for y in range(8):
        for x in range(8):bits=(bits<<1)|int(raw[y*9+x]>raw[y*9+x+1])
    return f'{bits:016x}'

def vision(image,model,extra_frames=None,timeout=120):
    prompt=('You are a strict travel documentary footage editor. Evaluate ONLY the supplied image(s) as a short sequence in chronological order. Do not invent unseen events. '
      'Return a single JSON object with: score (0..100 overall usefulness), event (0..100 likelihood this frame depicts '
      'a distinctive memorable action rather than generic scenery), people (true/false), description (specific factual '
      'English sentence <=25 words), category (one of landscape,city,transport,food,people,activity,architecture,other), '
      'role (one of opening,journey,highlight,ending). Favor authentic interactions, distinctive sights, active scenes '
      'and good composition. Penalize blur, darkness, occlusion and generic duplicates. Do not invent offscreen action.')
    body={'model':model,'stream':False,'format':'json','options':{'temperature':0.1},
      'messages':[{'role':'user','content':prompt,'images':[base64.b64encode(img.read_bytes()).decode('ascii') for img in (([extra_frames[0],image,extra_frames[1]] if len(extra_frames or [])==2 else [image]))]}]}
    req=urllib.request.Request('http://127.0.0.1:11434/api/chat',data=json.dumps(body).encode(),
                               headers={'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(req,timeout=timeout) as resp: answer=json.load(resp)
    content=answer['message']['content']
    try: data=json.loads(content)
    except json.JSONDecodeError:
        match=re.search(r'\{.*\}',content,re.S)
        if not match:raise ValueError('Ollama did not return JSON')
        data=json.loads(match.group())
    def number(k,default=50):
        try:return max(0.,min(100.,float(data.get(k,default))))
        except (ValueError,TypeError):return float(default)
    category=str(data.get('category','other')).lower()
    if category not in {'landscape','city','transport','food','people','activity','architecture','other'}:category='other'
    role=str(data.get('role','journey')).lower()
    if role not in {'opening','journey','highlight','ending'}:role='journey'
    people=data.get('people',False)
    return number('score'),number('event'),int(people is True or str(people).lower()=='true'),category,role,str(data.get('description',''))[:240]

def thumbnail_brightness(image):
    raw=command(['ffmpeg','-hide_banner','-loglevel','error','-i',image,'-frames:v','1',
                 '-vf','scale=16:16,format=gray','-f','rawvideo','-'],True,True)
    return sum(raw)/len(raw) if raw else 0

def report_progress(label, index, total, start):
    elapsed=time.monotonic()-start
    eta=(elapsed/max(1,index))*(total-index)
    print(f'[{label} {index}/{total}] 耗時 {elapsed/60:.1f} 分 / 預估剩餘 {eta/60:.1f} 分 (估算)',flush=True)

def analyze(db,out,model,limit,step,max_per_video,retry,temporal=True,mode='balanced',fast_model='gemma3:4b',timeout=120,profile='cpu'):

    candidates(db,step,max_per_video)
    analysis_mode='sequence3' if temporal else 'single'
    start=time.monotonic()
    print(f'[V4.2] 分析模式={mode}；硬體設定={profile}（手動設定，非 GPU 自動偵測）',flush=True)
    if mode=='balanced':
        # First pass: 4B scans every candidate using one frame. Its ratings are
        # committed immediately, so interruption does not throw away progress.
        rows=db.execute("""SELECT c.id,c.path,c.position,m.kind FROM candidates c
            JOIN media m ON c.path=m.path WHERE (c.quick_done!=1 OR c.quick_model IS NULL OR c.quick_model!=?) AND c.prefilter_skip IS NULL
            ORDER BY COALESCE(m.taken,m.mtime),c.path,c.position""",(fast_model,)).fetchall() if not retry else db.execute("SELECT c.id,c.path,c.position,m.kind FROM candidates c JOIN media m ON c.path=m.path ORDER BY COALESCE(m.taken,m.mtime),c.path,c.position").fetchall()
        if limit:rows=rows[:limit]
        print(f'[PHASE 1/2] 快速初選 {len(rows)} 個候選片段，模型 {fast_model}',flush=True)
        recent_hashes={}
        skipped=0
        for i,(key,path,pos,kind) in enumerate(rows,1):
            print(f'[FAST {i}/{len(rows)}] 開始 {Path(path).name} @ {pos:.1f}s',flush=True)
            try:
                img=out/'thumbnails_v2'/f'{key}.jpg'
                if not img.is_file():thumbnail(path,kind,pos,img)
                phash=perceptual_hash(img)
                if profile=='cpu' and not retry:
                    brightness=thumbnail_brightness(img)
                    prev=recent_hashes.get(path,[])
                    reason=('過暗畫面' if brightness<13 else
                            '相同來源的近似重複畫面' if any((int(phash,16)^int(h,16)).bit_count()<=2 and abs(pos-t)<90 for t,h in prev) else None)
                    recent_hashes.setdefault(path,[]).append((pos,phash))
                    if reason:
                        db.execute('UPDATE candidates SET prefilter_skip=?,phash=?,v2=0,quick_done=0 WHERE id=?',(reason,phash,key))
                        db.commit();skipped+=1
                        print(f'[PREFILTER SKIP {i}/{len(rows)}] {reason}',flush=True)
                        report_progress('FAST',i,len(rows),start)
                        continue
                score,event,people,category,role,description=vision(img,fast_model,timeout=timeout)
                db.execute("""UPDATE candidates SET quick_score=?,quick_event=?,quick_model=?,quick_done=1,
                   score=?,event=?,people=?,category=?,role=?,description=?,phash=?,analyzed=1,v2=1,
                   model_id=?,analysis_mode=?,error=NULL WHERE id=?""",
                   (score,event,fast_model,score,event,people,category,role,description,phash,
                    f'fast:{fast_model}','single',key))
                db.commit()
                print(f'[FAST {i}/{len(rows)}] 完成 {score:.0f} / event {event:.0f}',flush=True)
            except (Exception) as exc:
                db.execute('UPDATE candidates SET error=? WHERE id=?',(str(exc)[:300],key));db.commit()
                print(f'[FAST ERROR {i}/{len(rows)}] {str(exc)[:180]}',flush=True)
            report_progress('FAST',i,len(rows),start)
        # Best representatives per video, then highest-rated across the library.
        # Approx 20%, maximum 40 expensive reviews; a different model never reuses another model's review.
        source=db.execute("""SELECT c.id,c.path,c.position,m.kind,c.quick_score,c.quick_event,c.model_id,c.analysis_mode
                FROM candidates c JOIN media m ON m.path=c.path
                WHERE c.quick_done=1 AND c.quick_model=? ORDER BY (c.quick_score+0.45*c.quick_event) DESC""",(fast_model,)).fetchall()
        if limit:source=source[:max(limit,1)]
        fraction,maximum=(0.08,12) if profile=='cpu' else (0.20,40)
        cap=min(maximum,max(1,math.ceil(len(source)*fraction))) if source else 0
        shortlist=[];counts={}
        for item in source:
            key,path,pos,kind,score,event,oldmodel,oldmode=item
            if counts.get(path,0)>=max(2,math.ceil(cap/4)):continue
            shortlist.append(item);counts[path]=counts.get(path,0)+1
            if len(shortlist)>=cap:break
        pending=[x for x in shortlist if retry or x[6]!=model or x[7]!=analysis_mode]
        print(f'[PHASE 2/2] 12B 複審 {len(pending)}/{len(shortlist)} 個精選片段，模型 {model}',flush=True)
        rows=[(x[0],x[1],x[2],x[3]) for x in pending]
    else:
        where='(c.v2 IS NULL OR c.v2=0 OR c.model_id IS NULL OR c.model_id != ? OR c.analysis_mode IS NULL OR c.analysis_mode != ?)' if not retry else '1=1'
        rows=db.execute(f"""SELECT c.id,c.path,c.position,m.kind FROM candidates c JOIN media m ON c.path=m.path
            WHERE {where} ORDER BY COALESCE(m.taken,m.mtime),c.path,c.position""", (() if retry else (model,analysis_mode))).fetchall()
        if limit:rows=rows[:limit]
        print(f'[PHASE 1/1] 完整分析 {len(rows)} 個候選片段，模型 {model}',flush=True)
    if not rows:
        print('No new frames to analyze.',flush=True);return
    for i,(key,path,pos,kind) in enumerate(rows,1):
        print(f'[REVIEW {i}/{len(rows)}] 開始 {Path(path).name} @ {pos:.1f}s',flush=True)
        img=out/'thumbnails_v2'/f'{key}.jpg'
        try:
            if not img.is_file():thumbnail(path,kind,pos,img)
            phash=perceptual_hash(img)
            others=[]
            if temporal and kind=='video':
                for j,delta in enumerate((-1.5,1.5)):
                    frame=out/'thumbnails_v2'/f'{key}_seq{j}.jpg'
                    if not frame.is_file():thumbnail(path,kind,max(0.,pos+delta),frame)
                    others.append(frame)
            score,event,people,category,role,description=vision(img,model,others,timeout=timeout)
            db.execute("""UPDATE candidates SET score=?,event=?,people=?,category=?,role=?,description=?,
                         phash=?,analyzed=1,v2=1,model_id=?,analysis_mode=?,error=NULL WHERE id=?""",
                      (score,event,people,category,role,description,phash,model,analysis_mode,key))
            db.commit()
            print(f'[REVIEW {i}/{len(rows)}] 完成 {score:.0f}/{event:.0f} [{category}] {description[:55]}',flush=True)
        except Exception as exc:
            db.execute('UPDATE candidates SET error=? WHERE id=?',(str(exc)[:300],key));db.commit()
            print(f'[REVIEW ERROR {i}/{len(rows)}] {str(exc)[:180]}',flush=True)
        report_progress('REVIEW',i,len(rows),start)
    print('[ANALYZE DONE]',flush=True)

def distance(a,b):
    if not a or not b:return 64
    try:return (int(a,16)^int(b,16)).bit_count()
    except ValueError:return 64

def choose(db,target,shot,min_score):
    db.row_factory=sqlite3.Row
    rows=[dict(x) for x in db.execute('''SELECT c.id,c.path,c.position,c.score,c.description,c.phash,
      c.category,c.role,c.event,c.people,m.kind,m.duration,m.mtime,m.taken
      FROM candidates c JOIN media m ON m.path=c.path WHERE c.v2=1 AND c.score>=?
      ORDER BY COALESCE(m.taken,m.mtime),c.path,c.position''',(min_score,))]
    db.row_factory=None
    if not rows:return []
    # Windows modified timestamps are fallback only; do not claim they establish trip chronology.
    for r in rows:
        r['when']=r['taken'] if r['taken'] is not None else r['mtime']
        r['interest']=0.70*r['score']+0.30*(r['event'] or 0)
    rows.sort(key=lambda r:(r['when'],r['path'],r['position']))
    selected=[]; counts={}; category_count={}; limit=max(1,math.ceil(target/max(2,shot)))
    total_sources=len({r['path'] for r in rows})
    soft_source_limit=max(2,math.ceil(limit/max(1,total_sources))*2)
    time_min=min(r['when'] for r in rows);time_max=max(r['when'] for r in rows)

    def conflict(r):
        for s in selected:
            if r['id']==s['id']:return True
            if r['path']==s['path'] and abs(r['position']-s['position'])<max(10.,shot*1.5):return True
            # dHash alone has false matches on flat images. Be conservative.
            if r['category']==s['category'] and distance(r['phash'],s['phash'])<=5:return True
        return False

    def pick(stage):
        feasible=[r for r in rows if not conflict(r) and counts.get(r['path'],0)<soft_source_limit]
        if not feasible:return None
        def rank(r):
            normalized=(r['when']-time_min)/(time_max-time_min) if time_max>time_min else 0.5
            prefer={'opening':1-normalized,'journey':0.5,'highlight':normalized,'ending':normalized}[stage]
            role_bonus=12 if r['role']==stage else 0
            action_bonus=(r['event'] or 0)*(.12 if stage=='highlight' else .03)
            diversity=5*category_count.get(r['category'],0)
            per_source=9*counts.get(r['path'],0)
            return r['interest']+role_bonus+12*prefer+action_bonus-diversity-per_source
        chosen=max(feasible,key=rank)
        selected.append(chosen)
        counts[chosen['path']]=counts.get(chosen['path'],0)+1
        category_count[chosen['category']]=category_count.get(chosen['category'],0)+1
        return chosen

    # Reserve meaningful open / highlight / close, then fill the trip without repeatedly picking a single file.
    opening=pick('opening') if limit>=3 else None
    climax=pick('highlight') if limit>=4 else None
    ending=pick('ending') if limit>=5 else None
    while len(selected)<limit:
        if pick('journey') is None:break
    others=sorted([r for r in selected if r not in (opening,climax,ending)],
                  key=lambda r:(r['when'],r['path'],r['position']))
    ordered=([opening] if opening else [])+others+([climax] if climax else [])+([ending] if ending else [])
    if not ordered:return []
    # Vary shot length by role and activity, then adjust all to requested duration.
    lengths=[]
    for r in ordered:
        if r is opening:length=6.0
        elif r is climax:length=6.2
        elif r is ending:length=8.0
        elif r['category']=='landscape':length=shot*1.18
        elif r['category'] in ('city','transport'):length=shot*0.80
        elif (r['event'] or 0)>75 or r['category'] in ('people','activity'):length=shot*1.12
        else:length=shot
        lengths.append(min(float(length),max(0.5,float(r['duration'])) if r['kind']=='video' else 30))
    # Allocate remaining time within per-clip duration caps; never repeat or slow down a source to pad.
    for _ in range(10):
        missing=target-sum(lengths)
        if abs(missing)<0.05:break
        adjustable=[i for i,r in enumerate(ordered) if (lengths[i]<min(11.,r['duration'] if r['kind']=='video' else 11.)-0.02 if missing>0 else lengths[i]>1.5)]
        if not adjustable:break
        delta=missing/len(adjustable)
        for i in adjustable:
            cap=min(11.,ordered[i]['duration'] if ordered[i]['kind']=='video' else 11.)
            lengths[i]=min(cap,max(1.5,lengths[i]+delta))
    plan=[]
    for r,seconds in zip(ordered,lengths):
        seconds=round(seconds,3)
        if seconds<0.4:continue
        start=round(max(0.,min(float(r['duration'])-seconds,r['position']-seconds/2)),3) if r['kind']=='video' else 0.
        plan.append({'path':r['path'],'kind':r['kind'],'start':start,'seconds':seconds,
                     'score':r['score'],'event':r['event'],'category':r['category'],
                     'description':r['description'],'people':r.get('people'),
                     'source_duration':r['duration'],'candidate_position':r['position'],
                     'role':('opening' if r is opening else 'highlight' if r is climax else 'ending' if r is ending else 'journey')})
    return plan

def render(db,out,target,shot,minimum,music,crf,force,cinematic=True,transition=True,preserve_audio=True,beat_sync=True):
    plan=choose(db,target,shot,minimum)
    if cinematic:
        from cinematic_editor import render_v43
        return render_v43(plan,out,target,music,crf,force,transition,preserve_audio,beat_sync)
    if not plan:raise ValueError('No V2 analyzed clips. Run analyze, or lower --min-score.')
    plan_file=out/'edit_plan_v2.json'
    plan_file.write_text(json.dumps({'version':'4.2-classic','target':target,'plan':plan},ensure_ascii=False,indent=2),encoding='utf-8')
    total=sum(x['seconds'] for x in plan)
    print(f'Edit plan: {len(plan)} clips / {total:.1f} s (target {target}); {plan_file}')
    if total<target-2:print('NOTICE: Insufficient distinct material; output intentionally shorter instead of repeating footage.')
    clips=out/'clips_v2';clips.mkdir(exist_ok=True)
    vf='scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps=30,format=yuv420p'
    outputs=[]
    for i,part in enumerate(plan,1):
        stat=Path(part['path']).stat()
        fingerprint=hashlib.sha256(json.dumps([part['path'],stat.st_mtime,stat.st_size,part['start'],part['seconds'],crf,vf]).encode()).hexdigest()[:16]
        name=f'{fingerprint}.mp4';output=clips/name;outputs.append(output)
        if not force and output.exists() and output.stat().st_size>1000:
            print(f'Cached {i}/{len(plan)}');continue
        tmp=clips/f'{fingerprint}.partial.mp4'
        cmd=['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y']
        if part['kind']=='photo': cmd+=['-loop','1','-framerate','30','-i',part['path'],'-t',str(part['seconds'])]
        else:cmd+=['-ss',str(part['start']),'-i',part['path'],'-t',str(part['seconds'])]
        cmd+=['-vf',vf,'-an','-c:v','libx264','-preset','veryfast','-crf',str(crf),'-r','30',
              '-pix_fmt','yuv420p','-movflags','+faststart',str(tmp)]
        command(cmd);tmp.replace(output)
        print(f'Encoded {i}/{len(plan)}')
    concat=out/'concat_v2.txt'
    # Relative forward-slash paths avoid Windows absolute-path escaping issues.
    concat.write_text('ffconcat version 1.0\n'+''.join(f"file 'clips_v2/{p.name}'\n" for p in outputs),encoding='utf-8')
    silent=out/'silent_v2.mp4';final=out/'Travel_Vlog_Final_V2.mp4'
    command(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0',
             '-i',concat,'-c','copy',silent])
    if music:
        command(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-i',silent,
          '-stream_loop','-1','-i',music,'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac',
          '-b:a','192k','-af','volume=0.40,afade=t=in:st=0:d=2','-t',str(total),
          '-shortest','-movflags','+faststart',final])
    else: shutil.copy2(silent,final)
    print('DONE:',final)

def main():
    p=argparse.ArgumentParser(description='AI Vlog V4.3, Windows 1080p 16:9, no subtitles; original files preserved.')
    p.add_argument('stage',choices=['scan','analyze','render','all'])
    p.add_argument('--input',action='append',default=[])
    p.add_argument('--out',type=Path,default=Path(DEFAULT_OUT))
    p.add_argument('--model',default='gemma3:12b')
    p.add_argument('--analysis-mode',choices=['balanced','quality'],default='balanced')
    p.add_argument('--hardware-profile',choices=['cpu','standard'],default='cpu',help='cpu=8 percent 12B review and prefilter; standard=20 percent')
    p.add_argument('--fast-model',default='gemma3:4b')
    p.add_argument('--ai-timeout',type=int,default=120)
    p.add_argument('--single-frame',action='store_true',help='disable 3-frame temporal analysis')
    p.add_argument('--scan-limit',type=int,default=0)
    p.add_argument('--analyze-limit',type=int,default=0)
    p.add_argument('--step',type=float,default=8,help='seconds between candidate frames')
    p.add_argument('--max-per-video',type=int,default=36)
    p.add_argument('--seconds',type=int,default=180)
    p.add_argument('--shot',type=float,default=5.0)
    p.add_argument('--min-score',type=int,default=45)
    p.add_argument('--music',type=Path)
    p.add_argument('--crf',type=int,default=21)
    p.add_argument('--classic-render',action='store_true',help='Use the original V4.2 renderer instead of V4.3 cinematic output')
    p.add_argument('--no-dissolve',action='store_true',help='Use hard cuts instead of grouped 0.4s dissolves')
    p.add_argument('--no-ambient',action='store_true',help='Do not preserve original ambient audio')
    p.add_argument('--no-beat-sync',action='store_true',help='Disable approximate music onset alignment')
    p.add_argument('--retry',action='store_true',help='re-analyze previously analyzed frames')
    p.add_argument('--force',action='store_true',help='force re-encode cached clips')
    a=p.parse_args()
    if not all(shutil.which(name) or (FFMPEG_DIR/(name+'.exe')).is_file() for name in ('ffmpeg','ffprobe')):p.error('請在 tools 資料夾放入 ffmpeg.exe / ffprobe.exe，或將 FFmpeg 加入 PATH')
    if a.seconds<1 or a.shot<1 or a.step<=0 or a.max_per_video<1:p.error('Invalid duration/step')
    out=a.out.expanduser().resolve()
    db=connect(out)
    try:
        if a.stage in ('scan','all'):
            scan(db,[Path(x) for x in (a.input or [DEFAULT_IN])],out,a.scan_limit)
            print('Indexed:',db.execute('SELECT count(*) FROM media WHERE error IS NULL').fetchone()[0])
        if a.stage in ('analyze','all'):analyze(db,out,a.model,a.analyze_limit,a.step,a.max_per_video,a.retry,not a.single_frame,a.analysis_mode,a.fast_model,a.ai_timeout,a.hardware_profile)
        if a.stage in ('render','all'):
            if a.music and not a.music.is_file():p.error('Music file not found')
            render(db,out,a.seconds,a.shot,a.min_score,a.music,a.crf,a.force,
                   not a.classic_render,not a.no_dissolve,not a.no_ambient,not a.no_beat_sync)
    finally:db.close()
if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError,urllib.error.URLError,sqlite3.Error,OSError) as e:
        print('ERROR:',e,file=sys.stderr);sys.exit(1)
