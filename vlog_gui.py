#!/usr/bin/env python3
"""AI Vlog Maker 4.4.1 — explicit two-stage scanning/review/render GUI.
No third-party UI dependencies; input media is always read-only.
"""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from urllib.parse import quote
from urllib.request import urlopen

ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
CONFIG = Path(os.environ.get('LOCALAPPDATA',str(Path.home()))) / 'AI_Vlog_Maker_V3' / 'gui_settings.json'
DEFAULT_IN = r'C:\Users\SCE\Desktop\Travel1'
DEFAULT_OUT = r'C:\Users\SCE\Desktop\Vlogwork'
PAGE_SIZE = 120
SELECTION_FILE = 'ui_selected_v441.json'
FILE_TYPES = [('影片與照片','*.mp4 *.mov *.m4v *.avi *.mkv *.webm *.mts *.m2ts *.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff'),('全部','*.*')]


def workspace(inputs, output):
    """Keep the exact V4.4 workspace hash for compatibility with existing caches."""
    digest=hashlib.sha256('\n'.join(sorted(os.path.normcase(p) for p in inputs)).encode('utf-8')).hexdigest()[:12]
    return Path(output)/('AI_Vlog_'+digest)


def readonly_db(path):
    return sqlite3.connect('file:'+quote(path.resolve().as_posix(),safe='/:')+'?mode=ro',uri=True,timeout=4)


def candidates_page(file, page=0, text='', mode='全部'):
    # Return all indexed candidates, including failures and prefilter skips.

    # Earlier GUI hid everything except v2=1, even if candidate exists.
    empty = (0, 0, 0, [], {'media': 0, 'failed': 0, 'skipped': 0, 'pending': 0})
    if not file.is_file():
        return empty
    with closing(readonly_db(file)) as db:
        db.row_factory = sqlite3.Row
        media_count = db.execute('SELECT COUNT(*) AS n FROM media WHERE error IS NULL').fetchone()['n']
        summary = db.execute('''SELECT COUNT(*) AS total,
            COALESCE(SUM(CASE WHEN v2=1 THEN 1 ELSE 0 END),0) AS ready,
            COALESCE(SUM(CASE WHEN v2!=1 AND error IS NOT NULL AND error!='' THEN 1 ELSE 0 END),0) AS failed,
            COALESCE(SUM(CASE WHEN v2!=1 AND (error IS NULL OR error='') AND prefilter_skip IS NOT NULL THEN 1 ELSE 0 END),0) AS skipped
            FROM candidates''').fetchone()
        total,ready,failed,skipped=(int(summary[k]) for k in ('total','ready','failed','skipped'))
        stats={'media':media_count, 'failed':failed, 'skipped':skipped,
               'pending':max(0,total-ready-failed-skipped)}
        conditions=['m.error IS NULL'];args=[]
        if text:
            conditions.append('(c.path LIKE ? OR COALESCE(c.description,\'\') LIKE ? OR COALESCE(c.error,\'\') LIKE ?)')
            args.extend(['%'+text+'%']*3)
        if mode=='已完成 AI':conditions.append('c.v2=1')
        elif mode=='分析失敗':conditions.append("c.v2!=1 AND c.error IS NOT NULL AND c.error!=''")
        elif mode=='預篩跳過':conditions.append("c.v2!=1 AND (c.error IS NULL OR c.error='') AND c.prefilter_skip IS NOT NULL")
        elif mode=='尚未分析':conditions.append("c.v2!=1 AND (c.error IS NULL OR c.error='') AND c.prefilter_skip IS NULL")
        elif mode=='高分（70 以上）':conditions.append('c.v2=1 AND c.score>=70')
        clause=' AND '.join(conditions)
        from_clause=' FROM candidates c JOIN media m ON m.path=c.path WHERE '+clause
        count=db.execute('SELECT COUNT(*)'+from_clause,args).fetchone()[0]
        query=('''SELECT c.id,c.path,c.position,c.score,c.event,c.category,c.description,
            c.v2,c.error,c.prefilter_skip,c.quick_done,
            m.kind,m.duration FROM candidates c JOIN media m ON m.path=c.path WHERE '''+clause+
            ' ORDER BY CASE WHEN c.v2=1 THEN 0 WHEN c.error IS NOT NULL THEN 2 ELSE 1 END, '
            'c.score DESC,c.path,c.position LIMIT ? OFFSET ?')
        rows=[dict(x) for x in db.execute(query,args+[PAGE_SIZE,page*PAGE_SIZE])]
        for r in rows:
            if r['v2']==1:r['display_status']='已分析'
            elif r['error']:r['display_status']='分析失敗'
            elif r['prefilter_skip']:r['display_status']='預篩跳過'
            else:r['display_status']='未分析'
        return total,ready,count,rows,stats


def save_json_atomic(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)


class Application:
    def __init__(self,root):
        self.root=root
        self.root.title('AI Vlog Maker 4.4.2 — 修復候選片段顯示')
        self.root.geometry('1150x800')
        self.root.minsize(920,670)
        self.events=queue.Queue()
        self.process=None;self.running=False;self.cancel_requested=False
        self.inputs=[]
        self.output=tk.StringVar(value=DEFAULT_OUT)
        self.music=tk.StringVar()
        self.model=tk.StringVar(value='gemma3:12b')
        self.seconds=tk.StringVar(value='180')
        self.min_score=tk.StringVar(value='40')
        self.test=tk.BooleanVar(value=False)
        self.temporal=tk.BooleanVar(value=True)
        self.mode=tk.StringVar(value='balanced')
        self.hardware=tk.StringVar(value='cpu')
        self.dissolve=tk.BooleanVar(value=True)
        self.ambient=tk.BooleanVar(value=True)
        self.beat=tk.BooleanVar(value=True)
        self.search=tk.StringVar()
        self.candidate_filter=tk.StringVar(value='全部')
        self.workspace_dir=None
        self.override_workspace=None
        self.page=0;self.page_rows={};self.selected_ids=[];self.plan_rows={}
        self.photo=None;self.thumb_request=0
        self.make_ui();self.load_settings();self.update_workspace()
        root.after(100,self.drain)
        root.protocol('WM_DELETE_WINDOW',self.close)

    def make_ui(self):
        style=ttk.Style(self.root)
        if os.name=='nt' and 'vista' in style.theme_names():style.theme_use('vista')
        outer=ttk.Frame(self.root,padding=12);outer.pack(fill='both',expand=True)
        hdr=ttk.Frame(outer);hdr.pack(fill='x')
        ttk.Label(hdr,text='AI Vlog Maker',font=('Segoe UI',17,'bold')).pack(side='left')
        ttk.Label(hdr,text='V4.4.2 · 分階段剪輯',foreground='#586a78').pack(side='left',padx=12)
        self.workspace_text=ttk.Label(hdr,text='');self.workspace_text.pack(side='right')
        self.tabs=ttk.Notebook(outer);self.tabs.pack(fill='both',expand=True,pady=(10,6))
        self.tab_scan=ttk.Frame(self.tabs,padding=10)
        self.tab_edit=ttk.Frame(self.tabs,padding=10)
        self.tab_logs=ttk.Frame(self.tabs,padding=10)
        self.tabs.add(self.tab_scan,text='① 掃描與 AI 分析')
        self.tabs.add(self.tab_edit,text='② 挑選片段 → 剪輯輸出')
        self.tabs.add(self.tab_logs,text='③ 執行紀錄')
        self.make_scan();self.make_edit();self.make_log()
        footer=ttk.Frame(outer);footer.pack(fill='x',pady=(5,0))
        self.progress=ttk.Progressbar(footer,mode='determinate',maximum=100,length=240)
        self.progress.pack(side='left',fill='x',expand=True)
        self.progress_label=ttk.Label(footer,text='就緒',width=48,anchor='w')
        self.progress_label.pack(side='left',padx=10)
        self.status=ttk.Label(footer,text='就緒');self.status.pack(side='right')

    def make_scan(self):
        frame=ttk.LabelFrame(self.tab_scan,text='旅遊照片／影片來源',padding=10)
        frame.pack(fill='both',expand=True)
        buttons=ttk.Frame(frame);buttons.pack(fill='x')
        ttk.Button(buttons,text='加入多個檔案',command=self.add_files).pack(side='left',padx=(0,7))
        ttk.Button(buttons,text='加入資料夾',command=self.add_folder).pack(side='left',padx=7)
        ttk.Button(buttons,text='移除選取',command=self.remove_input).pack(side='left',padx=7)
        ttk.Button(buttons,text='清空',command=self.clear_inputs).pack(side='left',padx=7)
        frame_list=ttk.Frame(frame);frame_list.pack(fill='both',expand=True,pady=(8,0))
        self.input_list=tk.Listbox(frame_list,height=6,selectmode='extended',exportselection=False)
        self.input_list.pack(side='left',fill='both',expand=True)
        ttk.Scrollbar(frame_list,orient='vertical',command=self.input_list.yview).pack(side='right',fill='y')
        config=ttk.LabelFrame(self.tab_scan,text='AI 分析設定',padding=10)
        config.pack(fill='x',pady=(8,0));config.columnconfigure(1,weight=1)
        ttk.Label(config,text='工作與輸出目錄').grid(row=0,column=0,sticky='w',pady=3)
        entry=ttk.Entry(config,textvariable=self.output)
        entry.grid(row=0,column=1,sticky='ew',padx=8)
        entry.bind('<FocusOut>',lambda e:self.update_workspace())
        ttk.Button(config,text='選擇資料夾',command=self.browse_output).grid(row=0,column=2)
        ttk.Label(config,text='12B 複審模型').grid(row=1,column=0,sticky='w',pady=3)
        ttk.Entry(config,textvariable=self.model,width=19).grid(row=1,column=1,sticky='w',padx=8)
        a=ttk.Frame(config);a.grid(row=2,column=0,columnspan=3,sticky='w',pady=5)
        ttk.Label(a,text='AI 策略').pack(side='left')
        for name,val in [('平衡：4B 初選＋12B 複審','balanced'),('完整 12B','quality')]:
            ttk.Radiobutton(a,text=name,variable=self.mode,value=val).pack(side='left',padx=7)
        ttk.Label(a,text='效能').pack(side='left',padx=(10,0))
        for name,val in [('CPU 省時','cpu'),('標準','standard')]:
            ttk.Radiobutton(a,text=name,variable=self.hardware,value=val).pack(side='left',padx=5)
        b=ttk.Frame(config);b.grid(row=3,column=0,columnspan=3,sticky='w',pady=3)
        ttk.Checkbutton(b,text='三影格複審',variable=self.temporal).pack(side='left')
        ttk.Checkbutton(b,text='少量素材測試（最多掃描 20 筆、分析 50 個候選）',variable=self.test).pack(side='left',padx=24)
        ttk.Label(config,text='本步驟僅掃描及 AI 評分，不會開始剪輯或輸出影片。',foreground='#536575').grid(row=4,column=0,columnspan=3,sticky='w',pady=6)
        cmd=ttk.Frame(self.tab_scan);cmd.pack(fill='x',pady=(10,0))
        self.scan_btn=ttk.Button(cmd,text='① 開始掃描並分析',command=self.start_scan)
        self.scan_btn.pack(side='left')
        self.stop_btn=ttk.Button(cmd,text='停止',command=self.stop,state='disabled')
        self.stop_btn.pack(side='left',padx=10)
        ttk.Button(cmd,text='檢查環境',command=self.check_env).pack(side='right')
        ttk.Button(cmd,text='沿用上次 AI 分析結果',command=self.reuse_results).pack(side='right',padx=8)

    def make_edit(self):
        head=ttk.Frame(self.tab_edit);head.pack(fill='x')
        self.scan_summary=ttk.Label(head,text='尚未載入分析結果。請先按①掃描並分析。',foreground='#536575')
        self.scan_summary.pack(side='left')
        ttk.Button(head,text='選擇既有分析工作區',command=self.open_existing_workspace).pack(side='right',padx=6)
        ttk.Button(head,text='重新整理分析結果',command=lambda:self.load_candidates(reset=True)).pack(side='right')
        panels=ttk.Panedwindow(self.tab_edit,orient='horizontal');panels.pack(fill='both',expand=True,pady=(8,4))
        avail=ttk.LabelFrame(panels,text='AI 已分析片段（左側可挑選）',padding=6)
        curated=ttk.LabelFrame(panels,text='本次要輸出的鏡頭（右側可排序）',padding=6)
        panels.add(avail,weight=3);panels.add(curated,weight=2)
        filterline=ttk.Frame(avail);filterline.pack(fill='x')
        ttk.Entry(filterline,textvariable=self.search,width=23).pack(side='left',fill='x',expand=True)
        self.search.trace_add('write',lambda *_:None)  # Return triggers search to avoid DB query per keystroke
        self.filter_box=ttk.Combobox(filterline,textvariable=self.candidate_filter,values=['全部','已完成 AI','尚未分析','預篩跳過','分析失敗','高分（70 以上）'],state='readonly',width=15)
        self.filter_box.pack(side='left',padx=4)
        ttk.Button(filterline,text='搜尋',command=lambda:self.load_candidates(reset=True)).pack(side='left')
        self.available=ttk.Treeview(avail,columns=('flag','status','score','kind','time','name'),show='headings',height=12,selectmode='extended')
        for col,title,width in [('flag','片單',45),('status','分析狀態',79),('score','AI 分數',65),('kind','類型',48),('time','位置',60),('name','來源檔案',200)]:
            self.available.heading(col,text=title)
            self.available.column(col,width=width,anchor='w',stretch=col=='name')
        bar=ttk.Frame(avail);bar.pack(fill='both',expand=True,pady=(5,0))
        self.available.pack(in_=bar,side='left',fill='both',expand=True)
        sc=ttk.Scrollbar(bar,orient='vertical',command=self.available.yview);sc.pack(side='right',fill='y')
        self.available.configure(yscrollcommand=sc.set)
        self.available.bind('<<TreeviewSelect>>',self.on_available_select)
        ops=ttk.Frame(avail);ops.pack(fill='x',pady=5)
        ttk.Button(ops,text='加入選取片段 →',command=self.add_selection).pack(side='left')
        ttk.Button(ops,text='◀ 上一頁',command=lambda:self.page_by(-1)).pack(side='right')
        ttk.Button(ops,text='下一頁 ▶',command=lambda:self.page_by(1)).pack(side='right',padx=5)
        self.page_label=ttk.Label(avail,text='');self.page_label.pack(anchor='w')
        self.plan_tree=ttk.Treeview(curated,columns=('n','score','time','name'),show='headings',height=12,selectmode='extended')
        for col,title,width in [('n','#',28),('score','分數',44),('time','長度',59),('name','選定鏡頭',200)]:
            self.plan_tree.heading(col,text=title)
            self.plan_tree.column(col,width=width,stretch=col=='name')
        wrap=ttk.Frame(curated);wrap.pack(fill='both',expand=True)
        self.plan_tree.pack(in_=wrap,side='left',fill='both',expand=True)
        sc2=ttk.Scrollbar(wrap,orient='vertical',command=self.plan_tree.yview)
        sc2.pack(side='right',fill='y');self.plan_tree.config(yscrollcommand=sc2.set)
        self.plan_tree.bind('<<TreeviewSelect>>',self.on_plan_select)
        row=ttk.Frame(curated);row.pack(fill='x',pady=5)
        ttk.Button(row,text='移除',command=self.remove_plan).pack(side='left')
        ttk.Button(row,text='上移 ↑',command=lambda:self.move_plan(-1)).pack(side='left',padx=4)
        ttk.Button(row,text='下移 ↓',command=lambda:self.move_plan(1)).pack(side='left')
        ttk.Button(row,text='重選 AI 推薦',command=self.auto_plan).pack(side='right')
        self.plan_status=ttk.Label(curated,text='尚無片單');self.plan_status.pack(anchor='w')

        sample=ttk.LabelFrame(self.tab_edit,text='鏡頭內容預覽（非 JSON）',padding=7)
        sample.pack(fill='x',pady=(5,0))
        r=ttk.Frame(sample);r.pack(fill='x')
        self.thumb=ttk.Label(r,text='點選左側或右側鏡頭以顯示縮圖',width=41,anchor='center')
        self.thumb.pack(side='left',padx=(0,12))
        self.detail=ttk.Label(r,text='可查看 AI 評語、來源檔名和影片位置。',wraplength=730,justify='left')
        self.detail.pack(side='left',fill='both',expand=True)
        settings=ttk.LabelFrame(self.tab_edit,text='最後輸出設定',padding=7)
        settings.pack(fill='x',pady=(7,0))
        sett=ttk.Frame(settings);sett.pack(fill='x')
        ttk.Label(sett,text='目標秒數').pack(side='left')
        ttk.Combobox(sett,textvariable=self.seconds,values=['30','60','180','300','600'],width=6).pack(side='left',padx=5)
        ttk.Label(sett,text='AI 推薦最低分').pack(side='left',padx=(15,2))
        ttk.Combobox(sett,textvariable=self.min_score,values=['20','30','40','50','60','70'],width=5).pack(side='left',padx=5)
        ttk.Label(sett,text='配樂').pack(side='left',padx=(15,2))
        ttk.Entry(sett,textvariable=self.music,width=31).pack(side='left',fill='x',expand=True,padx=3)
        ttk.Button(sett,text='選擇',command=self.browse_music).pack(side='left')
        options=ttk.Frame(settings);options.pack(fill='x',pady=5)
        for label,var in [('交叉淡化',self.dissolve),('保留現場聲',self.ambient),('配樂節奏對齊',self.beat)]:
            ttk.Checkbutton(options,text=label,variable=var).pack(side='left',padx=(0,16))
        ttk.Label(options,text='固定輸出：1080p · 16:9 · 無字幕',foreground='#5e6a76').pack(side='right')
        action=ttk.Frame(self.tab_edit);action.pack(fill='x',pady=(9,0))
        self.render_btn=ttk.Button(action,text='② 按選定片單開始剪輯輸出 MP4',command=self.start_render)
        self.render_btn.pack(side='left')
        ttk.Button(action,text='開啟輸出資料夾',command=self.open_output).pack(side='right')

    def make_log(self):
        tools=ttk.Frame(self.tab_logs);tools.pack(fill='x')
        ttk.Button(tools,text='複製紀錄',command=self.copy_log).pack(side='left')
        self.log=tk.Text(self.tab_logs,font=('Consolas',10),wrap='word',state='disabled')
        self.log.pack(fill='both',expand=True,pady=(7,0))

    def log_line(self,line):
        self.log.config(state='normal');self.log.insert('end',line.rstrip()+'\n')
        if int(self.log.index('end-1c').split('.')[0])>1500:self.log.delete('1.0','250.0')
        self.log.see('end');self.log.config(state='disabled')
        m=re.search(r'\[(FAST|REVIEW|V4\.3 CLIP|V4\.3 GROUP)\s+(\d+)/(\d+)\]',line)
        if m:
            n,total=int(m.group(2)),max(1,int(m.group(3)))
            self.progress['value']=min(100,100*n/total)
            self.progress_label.config(text=f'{m.group(1)} {n}/{total}')
        eta=re.search(r'預估剩餘\s+([\d.]+)\s+分',line)
        if eta:self.progress_label.config(text=self.progress_label.cget('text')+' · 剩餘約 '+eta.group(1)+' 分')

    def add_inputs(self,items):
        if self.running:return
        keys={os.path.normcase(os.path.abspath(p)) for p in self.inputs}
        for p in items:
            p=os.path.abspath(p)
            if os.path.normcase(p) not in keys:
                self.inputs.append(p);self.input_list.insert('end',p);keys.add(os.path.normcase(p))
        self.override_workspace=None
        self.update_workspace();self.save_settings()

    def add_files(self):self.add_inputs(filedialog.askopenfilenames(title='選多個素材',filetypes=FILE_TYPES))
    def add_folder(self):
        path=filedialog.askdirectory(title='選擇素材資料夾')
        if path:self.add_inputs([path])

    def remove_input(self):
        if self.running:return
        for i in reversed(self.input_list.curselection()):
            self.input_list.delete(i);self.inputs.pop(i)
        self.override_workspace=None;self.update_workspace();self.save_settings()

    def clear_inputs(self):
        if self.running:return
        self.inputs.clear();self.input_list.delete(0,'end')
        self.override_workspace=None;self.update_workspace();self.save_settings()

    def browse_output(self):
        if self.running:return
        p=filedialog.askdirectory(title='選擇輸出目錄')
        if p:self.output.set(p);self.override_workspace=None;self.update_workspace();self.save_settings()

    def browse_music(self):
        p=filedialog.askopenfilename(title='選擇授權配樂',filetypes=[('音訊','*.mp3 *.wav *.m4a *.flac *.aac'),('全部','*.*')])
        if p:self.music.set(p);self.save_settings()

    def save_settings(self):
        data={'inputs':self.inputs,'output':self.output.get(),'music':self.music.get(),'model':self.model.get(),
              'seconds':self.seconds.get(),'min_score':self.min_score.get(),'test':self.test.get(),
              'temporal':self.temporal.get(),'analysis_mode':self.mode.get(),
              'hardware_profile':self.hardware.get(),'dissolve':self.dissolve.get(),
              'ambient':self.ambient.get(),'beat_sync':self.beat.get()}
        try:save_json_atomic(CONFIG,data)
        except OSError:pass

    def load_settings(self):
        try:data=json.loads(CONFIG.read_text(encoding='utf-8'))
        except (OSError,ValueError):data={'inputs':[DEFAULT_IN] if Path(DEFAULT_IN).exists() else []}
        for p in data.get('inputs',[]):
            if p not in self.inputs:self.inputs.append(p);self.input_list.insert('end',p)
        for key,var in [('output',self.output),('music',self.music),('model',self.model),
             ('seconds',self.seconds),('min_score',self.min_score),('temporal',self.temporal),
             ('analysis_mode',self.mode),('hardware_profile',self.hardware),
             ('dissolve',self.dissolve),('ambient',self.ambient),('beat_sync',self.beat)]:
            if key in data:
                var.set(data[key])
        # Test mode intentionally resets to off on every launch.

    def update_workspace(self):
        if self.running:return
        previous=self.workspace_dir
        out=self.output.get().strip()
        self.workspace_dir=(self.override_workspace if self.override_workspace else
                            (workspace(self.inputs,out) if self.inputs and out else None))
        self.workspace_text.config(text=self.workspace_dir.name if self.workspace_dir else '尚未指定素材')
        if previous!=self.workspace_dir:
            self.page=0;self.selected_ids=[]
            self.load_candidates(reset=True)
            self.load_selection_or_recommend()

    def get_count(self):
        if not self.workspace_dir:return 0,0
        file=self.workspace_dir/'index.sqlite'
        if not file.is_file():return 0,0
        try:
            with closing(readonly_db(file)) as db:
                return (db.execute('SELECT COUNT(*) FROM candidates').fetchone()[0],
                        db.execute('SELECT COUNT(*) FROM candidates WHERE v2=1').fetchone()[0])
        except sqlite3.Error:return 0,0

    def load_candidates(self,reset=False):
        if reset:self.page=0
        self.page_rows={}
        for row in self.available.get_children():self.available.delete(row)
        if not self.workspace_dir:
            self.scan_summary.config(text='尚未指定素材／工作區；可按「選擇既有分析工作區」。')
            self.page_label.config(text='');return
        try:
            total,ready,count,rows,stats=candidates_page(
                self.workspace_dir/'index.sqlite',self.page,
                self.search.get().strip(),self.candidate_filter.get())
        except sqlite3.Error as exc:
            self.scan_summary.config(text='分析資料庫讀取失敗：'+str(exc));return
        if count and self.page*PAGE_SIZE>=count:
            self.page=max(0,(count-1)//PAGE_SIZE)
            return self.load_candidates()
        parts=[f'已索引 {stats["media"]} 個素材、候選 {total} 段',
               f'AI 完成 {ready}',f'跳過 {stats["skipped"]}',f'失敗 {stats["failed"]}']
        if total==0 and stats['media']>0:
            parts.append('尚未產生候選，請執行 AI 分析')
        elif total==0:
            parts.append('本工作區沒有索引資料；請確認來源或選擇既有工作區')
        elif ready==0 and stats['failed']:
            parts.append('AI 未成功；請到③執行紀錄檢查 [FAST ERROR] / [REVIEW ERROR]')
        elif ready==0:
            parts.append('尚無 AI 評分，但可以手動選擇候選鏡頭')
        self.scan_summary.config(text=' | '.join(parts))
        self.page_label.config(text=f'第 {self.page+1}/{max(1,(count+PAGE_SIZE-1)//PAGE_SIZE)} 頁 · 篩選後 {count} 筆')
        for r in rows:
            key=r['id'];self.page_rows[key]=r
            selected='✓' if key in self.selected_ids else ''
            self.available.insert('','end',iid=key,values=(selected,r['display_status'],
                '—' if r['score'] is None else f"{r['score']:.0f}",
                '影片' if r['kind']=='video' else '照片',
                f"{r['position']:.1f}s" if r['kind']=='video' else '照片',Path(r['path']).name))

    def open_existing_workspace(self):
        """Recover prior analysis when the current input-set hash differs."""
        if self.running:return
        folder=filedialog.askdirectory(title='選擇含 index.sqlite 的 AI_Vlog_... 工作資料夾')
        if not folder:return
        chosen=Path(folder)
        if not (chosen/'index.sqlite').is_file():
            messagebox.showerror('找不到分析資料',str(chosen)+'\n此資料夾沒有 index.sqlite。')
            return
        self.override_workspace=chosen
        self.update_workspace()
        self.load_candidates(reset=True)
        self.load_selection_or_recommend()
        self.tabs.select(self.tab_edit)

    def page_by(self,delta):
        self.page=max(0,self.page+delta);self.load_candidates()

    def selection_path(self):return self.workspace_dir/SELECTION_FILE

    def load_selection_or_recommend(self):
        if not self.workspace_dir:return
        selection_file=self.selection_path()
        if selection_file.is_file():
            try:
                payload=json.loads(selection_file.read_text(encoding='utf-8'))
                ids=payload.get('candidate_ids',[])
                if not isinstance(ids,list) or not all(isinstance(x,str) for x in ids):raise ValueError('格式錯誤')
                self.selected_ids=list(dict.fromkeys(ids))
                self.refresh_plan();return
            except (OSError,ValueError,TypeError) as exc:
                self.log_line('選片記錄無法讀取：'+str(exc))
        self.recommend(quiet=True)

    def recommend(self,quiet=False):
        if not self.workspace_dir or not (self.workspace_dir/'index.sqlite').is_file():return False
        try:
            import vlog_maker as core
            with closing(readonly_db(self.workspace_dir/'index.sqlite')) as db:
                excluded_ids=set();excluded_paths=set()
                legacy=self.workspace_dir/'ui_review_v44.json'
                if legacy.is_file():
                    old=json.loads(legacy.read_text(encoding='utf-8'))
                    excluded_ids=set(old.get('excluded_ids',[]));excluded_paths=set(old.get('excluded_paths',[]))
                length=self.get_length()
                picked=core.choose(db,length,5.,int(self.min_score.get()),excluded_ids,excluded_paths)
            self.selected_ids=[p['candidate_id'] for p in picked]
            self.persist_selection();self.refresh_plan()
            return bool(picked)
        except (OSError,ValueError,sqlite3.Error) as exc:
            if not quiet:messagebox.showerror('AI 推薦失敗',str(exc))
            return False

    def auto_plan(self):
        if self.running:return
        if self.selected_ids and not messagebox.askyesno('重建片單','會以 AI 推薦取代目前手動選片與順序。確定？'):return
        if not self.recommend():messagebox.showinfo('無可用推薦','目前沒有足夠的已評分素材，請先完成①AI 分析。')

    def persist_selection(self):
        if not self.workspace_dir:return
        save_json_atomic(self.selection_path(),{'version':'4.4.1','candidate_ids':self.selected_ids})
        self.save_settings()

    def get_length(self):
        try:
            n=int(self.seconds.get());assert 1<=n<=3600
            return min(n,30) if self.test.get() else n
        except (ValueError,AssertionError):raise ValueError('片長請輸入 1～3600 秒。')

    def refresh_plan(self):
        self.plan_rows={}
        for row in self.plan_tree.get_children():self.plan_tree.delete(row)
        if not self.workspace_dir:return
        if not self.selected_ids:
            self.plan_status.config(text='尚未選片，請從左邊加入或按「重選 AI 推薦」。');return
        try:
            import vlog_maker as core
            with closing(readonly_db(self.workspace_dir/'index.sqlite')) as db:
                plan=core.choose_selected(db,self.selected_ids,self.get_length())
        except (ValueError,sqlite3.Error,OSError) as exc:
            self.plan_status.config(text='片單需要修復：'+str(exc))
            return
        for i,part in enumerate(plan):
            key=part['candidate_id'];self.plan_rows[key]=part
            self.plan_tree.insert('','end',iid=key,values=(i+1,
                f"{float(part['score'] or 0):.0f}",f"{part['seconds']:.1f}s",Path(part['path']).name))
        total=sum(p['seconds'] for p in plan)
        self.plan_status.config(text=f'已選 {len(plan)} 段 · 預估素材長度 {total:.1f}s（轉場後可能略短）')
        for key,row in self.page_rows.items():
            if self.available.exists(key):
                self.available.set(key,'flag','✓' if key in self.selected_ids else '')

    def add_selection(self):
        if self.running:return
        new=[key for key in self.available.selection() if key not in self.selected_ids]
        if new:
            self.selected_ids.extend(new)
            self.persist_selection();self.refresh_plan()

    def remove_plan(self):
        if self.running:return
        remove=set(self.plan_tree.selection())
        if remove:
            self.selected_ids=[x for x in self.selected_ids if x not in remove]
            self.persist_selection();self.refresh_plan()

    def move_plan(self,delta):
        if self.running:return
        chosen=self.plan_tree.selection()
        if len(chosen)!=1:return
        key=chosen[0];pos=self.selected_ids.index(key);destination=pos+delta
        if not 0<=destination<len(self.selected_ids):return
        self.selected_ids[pos],self.selected_ids[destination]=self.selected_ids[destination],self.selected_ids[pos]
        self.persist_selection();self.refresh_plan();self.plan_tree.selection_set(key);self.plan_tree.see(key)

    def on_available_select(self,_=None):
        keys=self.available.selection()
        if keys:self.show_preview(self.page_rows.get(keys[0]))

    def on_plan_select(self,_=None):
        keys=self.plan_tree.selection()
        if keys:self.show_preview(self.plan_rows.get(keys[0]))

    def show_preview(self,item):
        if not item:return
        self.detail.config(text=(f"{Path(item['path']).name}\n"
              f"原片位置：{float(item.get('candidate_position',item.get('position',0))):.1f} 秒\n"
              f"狀態：{item.get('display_status', '手動選定')}\n"
              f"AI 分數：{('%.0f' % float(item['score'])) if item.get('score') is not None else '尚無評分'}\n"
              f"AI 描述：{item.get('description') or '尚無描述'}\n"
              f"{('錯誤：'+str(item['error'])[:180]) if item.get('error') else ''}"
              f"{('預篩原因：'+str(item['prefilter_skip'])) if item.get('prefilter_skip') else ''}"))
        self.thumb_request+=1;token=self.thumb_request
        self.photo=None;self.thumb.config(image='',text='正在擷取縮圖…')
        folder=self.workspace_dir/'ui_thumbnails_v441'
        folder.mkdir(parents=True,exist_ok=True)
        key=item.get('candidate_id',item.get('id'))
        dest=folder/(key+'.png')
        original=self.workspace_dir/'thumbnails_v2'/(key+'.jpg')
        path=original if original.is_file() else Path(item['path'])
        def work():
            try:
                if not dest.is_file():
                    local=ROOT/'tools'/'ffmpeg.exe'
                    ffmpeg=str(local) if local.is_file() else (shutil.which('ffmpeg') or 'ffmpeg')
                    cmd=[ffmpeg,'-nostdin','-v','error','-y']
                    if path==Path(item['path']) and item['kind']=='video':
                        cmd+=['-ss',str(item.get('candidate_position',item.get('position',0)))]
                    cmd+=['-i',str(path),'-frames:v','1','-vf',
                          'scale=300:168:force_original_aspect_ratio=decrease,pad=300:168:(ow-iw)/2:(oh-ih)/2',str(dest)]
                    flags=getattr(subprocess,'CREATE_NO_WINDOW',0) if os.name=='nt' else 0
                    subprocess.run(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,
                                   stdin=subprocess.DEVNULL,check=True,timeout=35,creationflags=flags)
                self.events.put(('thumb',(token,str(dest),'')))
            except (OSError,subprocess.SubprocessError) as e:self.events.put(('thumb',(token,'',str(e)[:90])))
        threading.Thread(target=work,daemon=True).start()

    def validate_workspace(self,scan=False):
        if self.running:return False
        if not self.inputs and (scan or self.override_workspace is None):
            messagebox.showerror('缺少素材','請先加入素材，或選擇既有分析工作區。')
            return False
        missing=[p for p in self.inputs if not Path(p).exists()] if scan or self.override_workspace is None else []
        if missing:messagebox.showerror('找不到檔案','\n'.join(missing[:5]));return False
        self.update_workspace()
        if not self.workspace_dir:return False
        if scan and not self.model.get().strip():messagebox.showerror('缺少模型','請輸入 Ollama 模型名稱。');return False
        try:self.get_length();int(self.min_score.get())
        except ValueError as exc:messagebox.showerror('設定錯誤',str(exc));return False
        if self.music.get().strip() and not Path(self.music.get().strip()).is_file():
            messagebox.showerror('背景音樂不存在',self.music.get());return False
        self.workspace_dir.mkdir(parents=True,exist_ok=True)
        self.save_settings();return True

    def start_scan(self):
        self.override_workspace=None
        if not self.validate_workspace(scan=True):return
        args1=['scan']+sum((['--input',p] for p in self.inputs),[])
        if self.test.get():args1+=['--scan-limit','20']
        args2=['analyze','--model',self.model.get().strip(), '--analysis-mode',self.mode.get(),
               '--hardware-profile',self.hardware.get(),'--fast-model','gemma3:4b','--ai-timeout','120']
        if not self.temporal.get():args2.append('--single-frame')
        if self.test.get():args2+=['--analyze-limit','50']
        self.launch([args1,args2],'scan')

    def reuse_results(self):
        if self.running:return
        self.update_workspace()
        self.load_candidates(reset=True)
        self.load_selection_or_recommend()
        self.tabs.select(self.tab_edit)
        if not self.get_count()[1]:
            messagebox.showinfo('尚無 AI 評分','目前工作區沒有已完成 AI 評分的候選。\n請查看②候選清單的分析狀態；未評分片段也可以手動加入。')

    def start_render(self):
        if not self.validate_workspace():return
        if not self.selected_ids:return messagebox.showwarning('還沒選片','請先在②挑選至少一段鏡頭。')
        try:
            import vlog_maker as core
            with closing(readonly_db(self.workspace_dir/'index.sqlite')) as db:
                core.choose_selected(db,self.selected_ids,self.get_length())
        except (sqlite3.Error,ValueError,OSError) as exc:
            return messagebox.showerror('無法剪輯',str(exc))
        final=self.workspace_dir/'Travel_Vlog_Final_V43.mp4'
        if final.is_file() and not messagebox.askyesno('覆蓋既有成片','剪輯輸出將覆蓋此工作區既有的成片：\n'+str(final)+'\n原始素材不會更動。是否繼續？'):
            return
        self.persist_selection()
        args=['render','--selection-file',str(self.selection_path()),'--seconds',str(self.get_length()),
              '--min-score',str(int(self.min_score.get()))]
        if self.music.get().strip():args+=['--music',self.music.get().strip()]
        if not self.dissolve.get():args.append('--no-dissolve')
        if not self.ambient.get():args.append('--no-ambient')
        if not self.beat.get():args.append('--no-beat-sync')
        self.launch([args],'render')

    def launch(self,tasks,action):
        self.running=True;self.cancel_requested=False
        self.progress['value']=0;self.progress_label.config(text='任務準備中…')
        self.scan_btn.config(state='disabled');self.render_btn.config(state='disabled');self.stop_btn.config(state='normal')
        self.status.config(text='執行中')
        self.tabs.select(self.tab_logs)
        self.log_line('==== '+('正在掃描與分析' if action=='scan' else '正在輸出 MP4')+' ====')
        threading.Thread(target=self.worker,args=(tasks,action,str(self.workspace_dir)),daemon=True).start()

    def worker(self,tasks,action,out):
        try:
            for args in tasks:
                if self.cancel_requested:break
                cmd=([sys.executable,'--cli'] if getattr(sys,'frozen',False) else
                     [sys.executable,'-u',str(ROOT/'vlog_maker.py')])+[args[0],'--out',out]+args[1:]
                self.events.put(('stage',args[0]))
                flags=getattr(subprocess,'CREATE_NO_WINDOW',0) if os.name=='nt' else 0
                process=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1,creationflags=flags)
                self.process=process
                for line in process.stdout:self.events.put(('log',line.rstrip()))
                code=process.wait();self.process=None
                if self.cancel_requested:break
                if code:raise RuntimeError(f'{args[0]} 失敗（代碼 {code}）。請查看執行紀錄。')
            self.events.put(('done',(action,self.cancel_requested)))
        except Exception as exc:self.events.put(('error',str(exc)))
        finally:self.process=None

    def stop(self):
        self.cancel_requested=True
        proc=self.process
        if proc and proc.poll() is None:
            try:
                if os.name=='nt':
                    subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],
                        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=8,
                        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                else:proc.terminate()
            except (OSError,subprocess.SubprocessError):pass
        self.status.config(text='正在停止…')

    def drain(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='log':self.log_line(value)
                elif kind=='stage':
                    self.progress['value']=0
                    self.progress_label.config(text={'scan':'正在掃描檔案','analyze':'正在執行 AI 分析','render':'正在剪輯 MP4'}.get(value,value))
                    self.log_line('>>> '+value)
                elif kind=='env':messagebox.showinfo('環境檢查',value)
                elif kind=='thumb':
                    serial,path,error=value
                    if serial==self.thumb_request:
                        if path:
                            try:
                                self.photo=tk.PhotoImage(file=path)
                                self.thumb.config(image=self.photo,text='')
                            except tk.TclError as exc:self.thumb.config(image='',text='縮圖顯示失敗：'+str(exc)[:35])
                        else:self.thumb.config(image='',text='縮圖擷取失敗：'+error)
                elif kind in ('done','error'):
                    self.running=False
                    self.scan_btn.config(state='normal');self.render_btn.config(state='normal');self.stop_btn.config(state='disabled')
                    if kind=='error':
                        self.status.config(text='執行失敗');self.log_line('ERROR: '+value)
                        self.load_candidates(reset=True)
                        self.load_selection_or_recommend()
                        messagebox.showerror('執行失敗',value+'\n\n已保留掃描成功的候選鏡頭，可在②查看及手動挑選。')
                    else:
                        action,was_stopped=value
                        if was_stopped:
                            self.status.config(text='已停止');self.log_line('任務已停止')
                        else:
                            self.progress['value']=100;self.status.config(text='完成')
                            if action=='scan':
                                self.load_candidates(reset=True)
                                self.load_selection_or_recommend()
                                self.tabs.select(self.tab_edit)
                                total,ready=self.get_count()
                                if ready==0:
                                    messagebox.showwarning('沒有成功的 AI 評分',
                                        f'已建立 {total} 個候選鏡頭，但沒有任何片段成功取得 AI 評分。\n'
                                        '你仍可在②查看候選素材與手動挑片。\n'
                                        '請檢查③執行紀錄中的 [FAST ERROR] 或 [REVIEW ERROR]。')
                                else:
                                    messagebox.showinfo('分析完成',
                                        f'已建立 {total} 個候選鏡頭，其中 {ready} 個完成 AI 評分。\n'
                                        '請在②挑選片段，確認後再輸出。')
                            else:
                                messagebox.showinfo('剪輯完成','輸出位置：\n'+str(self.workspace_dir/'Travel_Vlog_Final_V43.mp4'))
        except queue.Empty:pass
        self.root.after(100,self.drain)

    def check_env(self):
        def work():
            checks=[]
            for name in ('ffmpeg','ffprobe'):
                local=ROOT/'tools'/(name+'.exe')
                checks.append(f'{name}：'+('正常（內附）' if local.is_file() else '正常（PATH）' if shutil.which(name) else '未安裝'))
            try:
                with urlopen('http://127.0.0.1:11434/api/tags',timeout=3) as r:models=json.load(r).get('models',[])
                names={x.get('name','').lower() for x in models}
                checks.append('Ollama 服務：正常')
                for name in ([self.model.get().strip()] + (['gemma3:4b'] if self.mode.get()=='balanced' else [])):
                    checks.append(name+'：'+('已安裝' if name.lower() in names else '缺少模型'))
            except Exception:checks.append('Ollama 服務：無法連線')
            self.events.put(('env','\n'.join(checks)))
        threading.Thread(target=work,daemon=True).start()
    def copy_log(self):
        self.root.clipboard_clear();self.root.clipboard_append(self.log.get('1.0','end-1c'))

    def open_output(self):
        if self.workspace_dir and self.workspace_dir.is_dir():
            if os.name=='nt':os.startfile(str(self.workspace_dir))
            else:messagebox.showinfo('輸出工作區',str(self.workspace_dir))
        else:messagebox.showinfo('尚未輸出','請先執行①掃描。')

    def close(self):
        if self.running:
            if not messagebox.askyesno('任務進行中','停止任務並關閉程式？'):return
            self.stop()
        self.save_settings();self.root.destroy()


if __name__=='__main__':
    root=tk.Tk();Application(root);root.mainloop()
