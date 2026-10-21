#!/usr/bin/env python3
"""AI Vlog Maker V4.4: Windows desktop review UI, using Tkinter only.

AI scoring and video rendering remain in vlog_maker.py / cinematic_editor.py.
All work is written beneath the selected output directory; originals are read-only.
"""
import hashlib
from contextlib import closing
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
import urllib.request

ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
CONFIG = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'AI_Vlog_Maker_V3' / 'gui_settings.json'
DEFAULT_INPUT = r'C:\Users\SCE\Desktop\Travel1'
DEFAULT_OUTPUT = r'C:\Users\SCE\Desktop\Vlogwork'
MEDIA_TYPES = [('影片與照片', '*.mp4 *.mov *.m4v *.avi *.mkv *.webm *.mts *.m2ts *.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff'),
               ('所有檔案', '*.*')]
PAGE_SIZE = 120


def workspace(inputs, output):
    """Exactly the same stable per-source digest as the V4.3 GUI."""
    digest = hashlib.sha256('\n'.join(sorted(os.path.normcase(p) for p in inputs)).encode('utf-8')).hexdigest()[:12]
    return Path(output) / ('AI_Vlog_' + digest)


def read_review(path):
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return {'excluded_ids': set(str(x) for x in data.get('excluded_ids', [])),
                'excluded_paths': set(str(x) for x in data.get('excluded_paths', []))}
    except (OSError, ValueError, AttributeError, TypeError):
        return {'excluded_ids': set(), 'excluded_paths': set()}


def write_review(path, review):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {'version': 1, 'excluded_ids': sorted(review['excluded_ids']),
            'excluded_paths': sorted(review['excluded_paths'])}
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def read_candidates(dbfile, page, search='', filter_mode='全部', min_score=40):
    """Read-only paged query; never loads a large media library in the UI."""
    if not dbfile.is_file():
        return 0, []
    uri = 'file:' + quote(dbfile.resolve().as_posix(), safe='/:') + '?mode=ro'
    with closing(sqlite3.connect(uri, uri=True, timeout=3)) as db:
        db.row_factory = sqlite3.Row
        clause = ['1=1']; params = []
        if search:
            clause.append('(c.path LIKE ? OR c.description LIKE ?)')
            params += ['%'+search+'%', '%'+search+'%']
        if filter_mode == '已評分':
            clause.append('c.v2=1')
        elif filter_mode == '高分':
            clause.append('c.v2=1 AND c.score>=?'); params.append(min_score)
        elif filter_mode == '分析失敗':
            clause.append('c.error IS NOT NULL')
        where = ' AND '.join(clause)
        from_query = ' FROM candidates c JOIN media m ON m.path=c.path WHERE ' + where
        count = db.execute('SELECT COUNT(*)' + from_query, params).fetchone()[0]
        query = ('''SELECT c.id,c.path,c.position,c.score,c.event,c.category,c.role,c.description,
                   c.error,c.v2,c.prefilter_skip,m.kind ''' + from_query +
                 ' ORDER BY CASE WHEN c.score IS NULL THEN 1 ELSE 0 END, c.score DESC, c.path, c.position LIMIT ? OFFSET ?')
        rows = [dict(r) for r in db.execute(query, (*params, PAGE_SIZE, page*PAGE_SIZE))]
    return count, rows


def valid_int(value, low, high, label):
    try:
        n=int(value)
        if low <= n <= high: return n
    except (ValueError,TypeError): pass
    raise ValueError(f'{label} 請輸入 {low}～{high} 的整數。')


class Application:
    def __init__(self, master):
        self.master = master
        master.title('AI Vlog Maker V4.4 — 剪輯工作台')
        master.geometry('1090x790')
        master.minsize(870,650)
        self.events = queue.Queue()
        self.process = None
        self.running = False
        self.cancel_requested = False
        self.inputs = []
        self.out = tk.StringVar(value=DEFAULT_OUTPUT)
        self.music = tk.StringVar()
        self.model = tk.StringVar(value='gemma3:12b')
        self.seconds = tk.StringVar(value='180')
        self.min_score = tk.StringVar(value='40')
        self.test = tk.BooleanVar(value=False)
        self.temporal = tk.BooleanVar(value=True)
        self.analysis_mode = tk.StringVar(value='balanced')
        self.hardware_profile = tk.StringVar(value='cpu')
        self.dissolve = tk.BooleanVar(value=True)
        self.ambient = tk.BooleanVar(value=True)
        self.beat_sync = tk.BooleanVar(value=True)
        self.query = tk.StringVar()
        self.filter_mode = tk.StringVar(value='全部')
        self.page=0
        self.page_rows={}
        self.timeline_rows={}
        self.review={'excluded_ids':set(), 'excluded_paths':set()}
        self.result_dir=None
        self.preview_image=None
        self.thumb_serial=0
        self.stage='就緒'
        self.make_ui()
        self.load()
        self.refresh_workspace()
        master.after(100,self.drain)
        master.protocol('WM_DELETE_WINDOW',self.close)

    def make_ui(self):
        style=ttk.Style(self.master)
        if 'vista' in style.theme_names() and os.name=='nt':style.theme_use('vista')
        shell=ttk.Frame(self.master,padding=12);shell.pack(fill='both',expand=True)
        header=ttk.Frame(shell);header.pack(fill='x')
        ttk.Label(header,text='AI Vlog Maker',font=('Segoe UI',18,'bold')).pack(side='left')
        ttk.Label(header,text='V4.4  ·  自動選片 / 人工審核 / 電影感輸出',foreground='#5c6670').pack(side='left',padx=12)
        self.workspace_label=ttk.Label(header,text='')
        self.workspace_label.pack(side='right')
        self.tabs=ttk.Notebook(shell);self.tabs.pack(fill='both',expand=True,pady=(10,8))
        self.tab_setup=ttk.Frame(self.tabs,padding=10)
        self.tab_media=ttk.Frame(self.tabs,padding=10)
        self.tab_plan=ttk.Frame(self.tabs,padding=10)
        self.tab_logs=ttk.Frame(self.tabs,padding=10)
        for tab,name in ((self.tab_setup,'① 專案設定'),(self.tab_media,'② AI 素材審核'),
                         (self.tab_plan,'③ 剪輯順序預覽'),(self.tab_logs,'④ 執行紀錄')):
            self.tabs.add(tab,text=name)
        self.make_setup();self.make_media();self.make_plan();self.make_logs()
        footer=ttk.Frame(shell);footer.pack(fill='x')
        self.progress=ttk.Progressbar(footer,maximum=100,mode='determinate',length=310)
        self.progress.pack(side='left',fill='x',expand=True)
        self.progress_text=ttk.Label(footer,text='尚未執行',width=41,anchor='w')
        self.progress_text.pack(side='left',padx=12)
        self.status=ttk.Label(footer,text='就緒',anchor='e')
        self.status.pack(side='right')

    def make_setup(self):
        top=ttk.LabelFrame(self.tab_setup,text='旅遊素材來源（可以混合多個資料夾與檔案）',padding=10)
        top.pack(fill='both',expand=True)
        line=ttk.Frame(top);line.pack(fill='x')
        ttk.Button(line,text='加入多個檔案',command=self.add_files).pack(side='left',padx=(0,7))
        ttk.Button(line,text='加入資料夾',command=self.add_folder).pack(side='left',padx=(0,7))
        ttk.Button(line,text='移除選取',command=self.remove).pack(side='left',padx=(0,7))
        ttk.Button(line,text='清空',command=self.clear).pack(side='left')
        wrap=ttk.Frame(top);wrap.pack(fill='both',expand=True,pady=(8,0))
        self.lb=tk.Listbox(wrap,height=7,selectmode='extended',exportselection=False)
        self.lb.pack(side='left',fill='both',expand=True)
        ttk.Scrollbar(wrap,orient='vertical',command=self.lb.yview).pack(side='right',fill='y')

        options=ttk.LabelFrame(self.tab_setup,text='剪輯與 AI 設定',padding=10);options.pack(fill='x',pady=(10,0))
        options.columnconfigure(1,weight=1)
        ttk.Label(options,text='輸出根目錄').grid(row=0,column=0,sticky='w',pady=3)
        ent=ttk.Entry(options,textvariable=self.out);ent.grid(row=0,column=1,sticky='ew',padx=8)
        ent.bind('<FocusOut>',lambda e:self.refresh_workspace())
        ttk.Button(options,text='瀏覽',command=self.select_out).grid(row=0,column=2)
        ttk.Label(options,text='背景音樂').grid(row=1,column=0,sticky='w',pady=3)
        ttk.Entry(options,textvariable=self.music).grid(row=1,column=1,sticky='ew',padx=8)
        ttk.Button(options,text='選擇音樂',command=self.select_music).grid(row=1,column=2)
        ttk.Label(options,text='複審模型').grid(row=2,column=0,sticky='w',pady=3)
        ttk.Entry(options,textvariable=self.model,width=22).grid(row=2,column=1,sticky='w',padx=8)
        row=ttk.Frame(options);row.grid(row=3,column=0,columnspan=3,sticky='w',pady=4)
        ttk.Label(row,text='影片秒數').pack(side='left')
        ttk.Combobox(row,textvariable=self.seconds,values=['30','60','180','300','600'],width=7).pack(side='left',padx=(7,18))
        ttk.Label(row,text='選片最低分').pack(side='left')
        ttk.Combobox(row,textvariable=self.min_score,values=['20','30','40','50','60','70','80'],width=5).pack(side='left',padx=7)
        ttk.Checkbutton(row,text='測試模式：最多 30 秒',variable=self.test).pack(side='left',padx=14)
        row2=ttk.Frame(options);row2.grid(row=4,column=0,columnspan=3,sticky='w',pady=4)
        ttk.Label(row2,text='AI').pack(side='left')
        ttk.Radiobutton(row2,text='平衡（4B 初選＋12B 複審）',variable=self.analysis_mode,value='balanced').pack(side='left',padx=(8,6))
        ttk.Radiobutton(row2,text='完整 12B',variable=self.analysis_mode,value='quality').pack(side='left',padx=(0,17))
        ttk.Label(row2,text='效能').pack(side='left')
        ttk.Radiobutton(row2,text='CPU 省時',variable=self.hardware_profile,value='cpu').pack(side='left',padx=(7,2))
        ttk.Radiobutton(row2,text='標準',variable=self.hardware_profile,value='standard').pack(side='left',padx=(0,5))
        ttk.Checkbutton(row2,text='三影格',variable=self.temporal).pack(side='left',padx=(5,0))
        row3=ttk.Frame(options);row3.grid(row=5,column=0,columnspan=3,sticky='w',pady=(5,4))
        for label,var in (('鏡頭交叉淡化',self.dissolve),('保留現場音訊',self.ambient),('音樂節奏近似對齊',self.beat_sync)):
            ttk.Checkbutton(row3,text=label,variable=var).pack(side='left',padx=(0,20))
        ttk.Label(options,text='輸出：1920×1080 · 16:9 · 無字幕。素材僅供讀取；輸出與快取放在獨立工作區。',foreground='#62676f').grid(row=6,column=0,columnspan=3,sticky='w',pady=(4,0))
        command=ttk.Frame(self.tab_setup);command.pack(fill='x',pady=(10,0))
        self.start_btn=ttk.Button(command,text='▶ 一鍵掃描 + AI 分析 + 輸出',command=self.start)
        self.start_btn.pack(side='left')
        self.render_btn=ttk.Button(command,text='只重新剪輯（不重跑 AI）',command=self.render_only)
        self.render_btn.pack(side='left',padx=8)
        self.stop_btn=ttk.Button(command,text='■ 停止',command=self.stop,state='disabled')
        self.stop_btn.pack(side='left',padx=3)
        ttk.Button(command,text='環境檢查',command=self.check_env).pack(side='right')
        ttk.Button(command,text='開啟輸出資料夾',command=self.open_folder).pack(side='right',padx=8)

    def make_media(self):
        row=ttk.Frame(self.tab_media);row.pack(fill='x')
        ttk.Label(row,text='搜尋檔名／AI 描述').pack(side='left')
        find=ttk.Entry(row,textvariable=self.query,width=25);find.pack(side='left',padx=7)
        find.bind('<Return>',lambda e:self.reload_candidates(reset=True))
        ttk.Label(row,text='檢視').pack(side='left',padx=(12,4))
        ttk.Combobox(row,textvariable=self.filter_mode,values=['全部','已評分','高分','分析失敗'],state='readonly',width=10).pack(side='left')
        ttk.Button(row,text='查詢／重新整理',command=lambda:self.reload_candidates(reset=True)).pack(side='left',padx=8)
        columns=('state','score','event','category','time','source','description')
        self.candidates=ttk.Treeview(self.tab_media,columns=columns,show='headings',height=11,selectmode='extended')
        for col,label,w in [('state','審核',90),('score','分數',65),('event','事件',65),('category','類型',100),('time','位置',65),('source','來源檔案',200),('description','AI 評語（原文）',360)]:
            self.candidates.heading(col,text=label)
            self.candidates.column(col,width=w,minwidth=45,stretch=(col in ('source','description')))
        self.candidates.tag_configure('excluded',foreground='#999999')
        wrapper=ttk.Frame(self.tab_media);wrapper.pack(fill='both',expand=True,pady=(8,5))
        self.candidates.pack(in_=wrapper,side='left',fill='both',expand=True)
        sy=ttk.Scrollbar(wrapper,orient='vertical',command=self.candidates.yview);sy.pack(side='right',fill='y')
        self.candidates.config(yscrollcommand=sy.set)
        self.candidates.bind('<<TreeviewSelect>>',self.on_candidate_select)
        pagination=ttk.Frame(self.tab_media);pagination.pack(fill='x')
        ttk.Button(pagination,text='上一頁',command=lambda:self.change_page(-1)).pack(side='left')
        ttk.Button(pagination,text='下一頁',command=lambda:self.change_page(1)).pack(side='left',padx=7)
        self.page_label=ttk.Label(pagination,text='尚無資料');self.page_label.pack(side='left',padx=12)
        ttk.Button(pagination,text='排除選取鏡頭／取消排除',command=self.toggle_candidates).pack(side='right')
        ttk.Button(pagination,text='排除整個來源檔案／取消',command=self.toggle_sources).pack(side='right',padx=8)
        view=ttk.LabelFrame(self.tab_media,text='選定候選鏡頭',padding=8);view.pack(fill='both',expand=False,pady=(8,0))
        row=ttk.Frame(view);row.pack(fill='x')
        self.thumb=ttk.Label(row,text='選取鏡頭後顯示畫面縮圖',width=38,anchor='center')
        self.thumb.pack(side='left',padx=(0,12))
        detail=ttk.Frame(row);detail.pack(side='left',fill='both',expand=True)
        self.media_details=tk.Text(detail,height=5,wrap='word',state='disabled',font=('Segoe UI',10))
        self.media_details.pack(fill='both',expand=True)
        buttons=ttk.Frame(detail);buttons.pack(anchor='w',pady=(5,0))
        ttk.Button(buttons,text='以系統播放器開啟原始檔',command=self.open_selected_source).pack(side='left')
        ttk.Button(buttons,text='更新畫面',command=lambda:self.on_candidate_select(None)).pack(side='left',padx=7)
        ttk.Label(view,text='縮圖按需從原始素材擷取，影片播放使用 Windows 預設播放器；排除只影響最終選片，不刪除素材。',foreground='#646b73').pack(anchor='w',pady=(6,0))

    def make_plan(self):
        row=ttk.Frame(self.tab_plan);row.pack(fill='x')
        self.plan_btn=ttk.Button(row,text='產生／更新剪輯預覽（不重跑 AI）',command=self.generate_plan)
        self.plan_btn.pack(side='left')
        ttk.Button(row,text='讀取已儲存剪輯清單',command=self.reload_plan).pack(side='left',padx=7)
        ttk.Button(row,text='排除選取鏡頭',command=self.exclude_plan_selection).pack(side='left')
        ttk.Button(row,text='只重新剪輯輸出',command=self.render_only).pack(side='right')
        self.plan_hint=ttk.Label(self.tab_plan,text='尚未建立預覽；請先完成 AI 分析，按「產生／更新剪輯預覽」。',foreground='#56616b')
        self.plan_hint.pack(anchor='w',pady=(8,7))
        columns=('n','role','score','seconds','time','source','description')
        self.timeline=ttk.Treeview(self.tab_plan,columns=columns,show='headings',height=15)
        for col,name,w in [('n','#',40),('role','敘事段落',95),('score','AI 分數',70),('seconds','片段長度',85),('time','原片起點',85),('source','素材',205),('description','鏡頭描述',355)]:
            self.timeline.heading(col,text=name)
            self.timeline.column(col,width=w,minwidth=35,stretch=col in ('source','description'))
        wrap=ttk.Frame(self.tab_plan);wrap.pack(fill='both',expand=True)
        self.timeline.pack(in_=wrap,side='left',fill='both',expand=True)
        sy=ttk.Scrollbar(wrap,orient='vertical',command=self.timeline.yview)
        sy.pack(side='right',fill='y');self.timeline.configure(yscrollcommand=sy.set)
        ttk.Label(self.tab_plan,text='此清單是輸出前估算；實際交叉淡化與音樂微調會影響最終片長。排除後需重新產生預覽。',foreground='#666').pack(anchor='w',pady=(8,0))

    def make_logs(self):
        top=ttk.Frame(self.tab_logs);top.pack(fill='x')
        ttk.Button(top,text='複製全部紀錄',command=self.copy_log).pack(side='left')
        ttk.Button(top,text='清除畫面',command=self.clear_log).pack(side='left',padx=8)
        ttk.Label(top,text='程式出錯時可複製這裡的訊息；最多保留最近約 1500 行',foreground='#666').pack(side='left',padx=12)
        panel=ttk.Frame(self.tab_logs);panel.pack(fill='both',expand=True,pady=(8,0))
        self.log_widget=tk.Text(panel,state='disabled',wrap='word',font=('Consolas',10))
        self.log_widget.pack(side='left',fill='both',expand=True)
        ttk.Scrollbar(panel,orient='vertical',command=self.log_widget.yview).pack(side='right',fill='y')

    def append_log(self,line):
        self.log_widget.config(state='normal')
        self.log_widget.insert('end',line.rstrip()+'\n')
        if int(self.log_widget.index('end-1c').split('.')[0]) > 1550:
            self.log_widget.delete('1.0','250.0')
        self.log_widget.see('end')
        self.log_widget.config(state='disabled')
        self.update_progress(line)

    def update_progress(self,line):
        phase=re.search(r'\[(FAST|REVIEW|V4\.3 CLIP|V4\.3 GROUP)\s+(\d+)/(\d+)\]',line)
        if phase:
            label,n,total=phase.group(1),int(phase.group(2)),max(1,int(phase.group(3)))
            if label=='FAST': value=70*n/total
            elif label=='REVIEW': value=(70 if self.analysis_mode.get()=='balanced' else 0)+(30 if self.analysis_mode.get()=='balanced' else 100)*n/total
            elif label=='V4.3 CLIP': value=85*n/total
            else:value=85+15*n/total
            self.progress['value']=min(100,value)
            self.progress_text.config(text=f'{label}：{n}/{total}')
        remaining=re.search(r'預估剩餘\s+([\d.]+)\s+分',line)
        if remaining:
            self.progress_text.config(text=self.progress_text.cget('text')+f' · 剩餘約 {remaining.group(1)} 分')

    def add(self,items):
        if self.running:return
        existing={os.path.normcase(os.path.abspath(x)) for x in self.inputs}
        for item in items:
            p=os.path.abspath(item);key=os.path.normcase(p)
            if key not in existing:
                self.inputs.append(p);self.lb.insert('end',p);existing.add(key)
        self.save();self.refresh_workspace()

    def add_files(self):
        self.add(filedialog.askopenfilenames(title='選取多個影片或照片',filetypes=MEDIA_TYPES))

    def add_folder(self):
        p=filedialog.askdirectory(title='選擇素材資料夾')
        if p:self.add([p])

    def remove(self):
        if self.running:return
        for i in reversed(self.lb.curselection()):
            self.lb.delete(i);del self.inputs[i]
        self.save();self.refresh_workspace()

    def clear(self):
        if self.running:return
        self.lb.delete(0,'end');self.inputs.clear()
        self.save();self.refresh_workspace()

    def select_out(self):
        if self.running:return
        p=filedialog.askdirectory(title='選擇輸出根目錄')
        if p:self.out.set(p);self.save();self.refresh_workspace()

    def select_music(self):
        p=filedialog.askopenfilename(title='選擇配樂',filetypes=[('音訊','*.mp3 *.wav *.m4a *.flac *.aac'),('全部','*.*')])
        if p:self.music.set(p);self.save()

    def save(self):
        data={'inputs':self.inputs,'output':self.out.get(),'music':self.music.get(),'model':self.model.get(),
              'seconds':self.seconds.get(),'min_score':self.min_score.get(),'temporal':self.temporal.get(),
              'analysis_mode':self.analysis_mode.get(),'hardware_profile':self.hardware_profile.get(),
              'dissolve':self.dissolve.get(),'ambient':self.ambient.get(),'beat_sync':self.beat_sync.get()}
        try:
            CONFIG.parent.mkdir(parents=True,exist_ok=True)
            CONFIG.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        except OSError:pass

    def load(self):
        try: data=json.loads(CONFIG.read_text(encoding='utf-8'))
        except (OSError,ValueError):data={'inputs':[DEFAULT_INPUT] if Path(DEFAULT_INPUT).exists() else []}
        # Do not invoke add() here: avoid unnecessary workspace queries while restoring state.
        for p in data.get('inputs',[]):
            if p not in self.inputs:self.inputs.append(p);self.lb.insert('end',p)
        for name,var in [('output',self.out),('music',self.music),('model',self.model),('seconds',self.seconds),
                         ('min_score',self.min_score),('temporal',self.temporal),('analysis_mode',self.analysis_mode),
                         ('hardware_profile',self.hardware_profile),('dissolve',self.dissolve),('ambient',self.ambient),('beat_sync',self.beat_sync)]:
            if data.get(name) is not None:
                value=data[name]
                if name=='model' and value=='gemma3:4b':value='gemma3:12b'
                if isinstance(var,tk.BooleanVar):var.set(bool(value))
                else:var.set(str(value))

    def refresh_workspace(self):
        if self.running:return
        directory=self.out.get().strip()
        if not directory or not self.inputs:
            self.result_dir=None;self.review={'excluded_ids':set(),'excluded_paths':set()}
            self.workspace_label.config(text='尚未選取素材')
        else:
            self.result_dir=workspace(self.inputs,directory)
            self.review=read_review(self.result_dir/'ui_review_v44.json')
            self.workspace_label.config(text='工作區：'+self.result_dir.name)
        self.reload_candidates(reset=True)
        self.reload_plan()

    def reload_candidates(self,reset=False):
        if reset:self.page=0
        for item in self.candidates.get_children():self.candidates.delete(item)
        self.page_rows={}
        if not self.result_dir:
            self.page_label.config(text='未指定工作區');return
        try:
            count,rows=read_candidates(self.result_dir/'index.sqlite',self.page,self.query.get().strip(),self.filter_mode.get(),
                                        valid_int(self.min_score.get(),0,100,'最低分'))
        except (sqlite3.Error,ValueError) as exc:
            self.page_label.config(text='讀取失敗：'+str(exc));return
        pages=max(1,(count+PAGE_SIZE-1)//PAGE_SIZE)
        if self.page>=pages:
            self.page=pages-1;return self.reload_candidates()
        for row in rows:
            key=row['id'];self.page_rows[key]=row
            excluded=key in self.review['excluded_ids'] or row['path'] in self.review['excluded_paths']
            status='已排除' if excluded else ('已分析' if row['v2'] else ('未分析' if not row['error'] else '錯誤'))
            self.candidates.insert('', 'end',iid=key,values=(status,
                f"{row['score']:.0f}" if row['score'] is not None else '—',
                f"{row['event']:.0f}" if row['event'] is not None else '—',
                row['category'] or '—',f"{row['position']:.1f}s",Path(row['path']).name,row['description'] or row['prefilter_skip'] or row['error'] or '—'),
                tags=('excluded',) if excluded else ())
        self.page_label.config(text=f'第 {self.page+1}/{pages} 頁 · 共 {count} 個候選 · 排除 {len(self.review["excluded_ids"])} 鏡頭 / {len(self.review["excluded_paths"])} 來源')

    def change_page(self,delta):
        self.page=max(0,self.page+delta)
        self.reload_candidates()

    def selected_rows(self):
        return [self.page_rows[k] for k in self.candidates.selection() if k in self.page_rows]

    def ensure_editable(self):
        if self.running:
            messagebox.showwarning('任務執行中','請先停止工作後再修改排除設定。')
            return False
        if not self.result_dir:return False
        return True

    def persist_review(self):
        try:write_review(self.result_dir/'ui_review_v44.json',self.review)
        except OSError as exc:
            messagebox.showerror('寫入排除設定失敗',str(exc));return
        self.append_log('[V4.4] 已儲存手動排除設定；請重新產生剪輯預覽。')
        self.reload_candidates()
        self.plan_hint.config(text='排除設定已變動。現有預覽可能過期，請重新產生。')

    def toggle_candidates(self):
        if not self.ensure_editable():return
        rows=self.selected_rows()
        if not rows:return
        for row in rows:
            key=row['id'];excluded=self.review['excluded_ids']
            if key in excluded:excluded.remove(key)
            else:excluded.add(key)
        self.persist_review()

    def toggle_sources(self):
        if not self.ensure_editable():return
        paths={r['path'] for r in self.selected_rows()}
        for path in paths:
            excluded=self.review['excluded_paths']
            if path in excluded:excluded.remove(path)
            else:excluded.add(path)
        if paths:self.persist_review()

    def on_candidate_select(self,_event):
        rows=self.selected_rows()
        if not rows:return
        row=rows[0]
        detail=(f"來源：{row['path']}\n時間：{row['position']:.2f} 秒　分數：{row['score']}　事件：{row['event']}\n"
                f"類型：{row['category'] or '未知'}　角色：{row['role'] or '未知'}\n"
                f"AI 描述：{row['description'] or '（尚未分析）'}\n"
                f"錯誤：{row['error'] or '無'}")
        self.media_details.config(state='normal');self.media_details.delete('1.0','end')
        self.media_details.insert('end',detail);self.media_details.config(state='disabled')
        self.load_thumbnail(row)

    def load_thumbnail(self,row):
        if not self.result_dir:return
        self.thumb_serial+=1;serial=self.thumb_serial
        self.preview_image=None
        self.thumb.config(image='',text='擷取縮圖中…')
        dest=self.result_dir/'ui_thumbnails_v44'/f"{row['id']}.png"
        # Existing thumbnail JPEG is a fast, safe source if available.
        jpg=self.result_dir/'thumbnails_v2'/f"{row['id']}.jpg"
        source=str(jpg if jpg.is_file() else row['path'])
        def job():
            try:
                dest.parent.mkdir(parents=True,exist_ok=True)
                if not dest.is_file():
                    local=ROOT/'tools'/'ffmpeg.exe'
                    ffmpeg=str(local) if local.is_file() else shutil.which('ffmpeg')
                    if not ffmpeg:raise RuntimeError('找不到 ffmpeg')
                    cmd=[ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-y']
                    if source==row['path'] and row['kind']=='video':cmd+=['-ss',str(row['position'])]
                    cmd+=['-i',source,'-frames:v','1','-vf','scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2',str(dest)]
                    flags=getattr(subprocess,'CREATE_NO_WINDOW',0) if os.name=='nt' else 0
                    subprocess.run(cmd,check=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                                   stderr=subprocess.PIPE,timeout=35,creationflags=flags)
                self.events.put(('thumbnail',(serial,str(dest),'')))
            except (OSError,subprocess.SubprocessError,RuntimeError) as exc:
                self.events.put(('thumbnail',(serial,'',str(exc)[:100])))
        threading.Thread(target=job,daemon=True).start()

    def open_selected_source(self):
        rows=self.selected_rows()
        if not rows:return
        path=Path(rows[0]['path'])
        if not path.exists():return messagebox.showerror('找不到原檔',str(path))
        if os.name=='nt':os.startfile(str(path))
        else:messagebox.showinfo('來源路徑',str(path))

    def reload_plan(self):
        self.timeline_rows={}
        for iid in self.timeline.get_children():self.timeline.delete(iid)
        if not self.result_dir:return
        plan_file=self.result_dir/'edit_plan_preview_v44.json'
        if not plan_file.is_file():return
        try:
            data=json.loads(plan_file.read_text(encoding='utf-8'))
            plan=data.get('plan',[])
            total=0
            for i,clip in enumerate(plan,1):
                total+=float(clip.get('seconds',0))
                self.timeline_rows[str(i)]=clip
                self.timeline.insert('','end',iid=str(i),values=(i,
                  {'opening':'開場','journey':'旅程','highlight':'高潮','ending':'結尾'}.get(clip.get('role'),clip.get('role','旅程')),
                  f"{clip.get('score',0):.0f}",f"{clip.get('seconds',0):.1f}s",f"{clip.get('start',0):.1f}s",
                  Path(clip['path']).name,clip.get('description','')))
            self.plan_hint.config(text=f'預估 {len(plan)} 個鏡頭，約 {total:.1f} 秒（尚未計入 V4.3 轉場與音樂微調）。')
        except (OSError,ValueError,TypeError,KeyError) as exc:
            self.plan_hint.config(text='讀取預覽失敗：'+str(exc))

    def exclude_plan_selection(self):
        if not self.ensure_editable():return
        n=0
        for iid in self.timeline.selection():
            p=self.timeline_rows.get(iid,{})
            if p.get('candidate_id'):
                self.review['excluded_ids'].add(p['candidate_id']);n+=1
            elif p.get('path'):
                self.review['excluded_paths'].add(p['path']);n+=1
        if n:self.persist_review()

    def validate(self,need_inputs=False):
        try:
            length=valid_int(self.seconds.get(),1,3600,'片長')
            minimum=valid_int(self.min_score.get(),0,100,'最低分')
        except ValueError as e:
            messagebox.showerror('設定錯誤',str(e));return None
        if need_inputs and not self.inputs:
            messagebox.showerror('沒有素材','請先加入照片、影片或資料夾。');return None
        if need_inputs:
            missing=[x for x in self.inputs if not Path(x).exists()]
            if missing:messagebox.showerror('找不到素材','\n'.join(missing[:5]));return None
        if not self.model.get().strip():messagebox.showerror('缺少模型','請填寫 Ollama 模型。');return None
        if self.music.get().strip() and not Path(self.music.get().strip()).is_file():
            messagebox.showerror('音樂檔案不存在',self.music.get());return None
        if not self.result_dir:
            self.refresh_workspace()
            if not self.result_dir:
                messagebox.showerror('工作區未設定','請設定素材來源及輸出資料夾。');return None
        try:self.result_dir.mkdir(parents=True,exist_ok=True)
        except OSError as exc:
            messagebox.showerror('輸出資料夾錯誤',str(exc));return None
        self.save()
        return length,minimum

    def common_render_args(self,length,minimum):
        args=['--seconds',str(min(length,30) if self.test.get() else length),'--min-score',str(minimum)]
        args+=['--review-file',str(self.result_dir/'ui_review_v44.json')] if (self.result_dir/'ui_review_v44.json').is_file() else []
        if self.music.get().strip():args+=['--music',self.music.get().strip()]
        if not self.dissolve.get():args.append('--no-dissolve')
        if not self.ambient.get():args.append('--no-ambient')
        if not self.beat_sync.get():args.append('--no-beat-sync')
        return args

    def start(self):
        if self.running:return
        valid=self.validate(need_inputs=True)
        if valid is None:return
        length,minimum=valid
        inputs=list(self.inputs)
        tasks=[['scan']+sum((['--input',p] for p in inputs),[])+(['--scan-limit','20'] if self.test.get() else []),
               ['analyze','--model',self.model.get().strip(),'--analysis-mode',self.analysis_mode.get(),
                '--hardware-profile',self.hardware_profile.get(),'--fast-model','gemma3:4b','--ai-timeout','120']+
                ([] if self.temporal.get() else ['--single-frame'])+(['--analyze-limit','50'] if self.test.get() else []),
               ['plan']+self.common_render_args(length,minimum),
               ['render']+self.common_render_args(length,minimum)]
        self.launch(tasks,'完整剪輯')

    def generate_plan(self):
        if self.running:return
        valid=self.validate()
        if valid is None:return
        if not (self.result_dir/'index.sqlite').is_file():
            messagebox.showwarning('缺少分析資料','請先在①完成掃描與 AI 分析。');return
        self.launch([['plan']+self.common_render_args(*valid)],'預覽')

    def render_only(self):
        if self.running:return
        valid=self.validate()
        if valid is None:return
        if not (self.result_dir/'index.sqlite').is_file():
            messagebox.showwarning('沒有資料庫','請先執行完整分析。');return
        self.launch([['plan']+self.common_render_args(*valid),['render']+self.common_render_args(*valid)],'直接重新剪輯')

    def launch(self,tasks,action):
        self.cancel_requested=False;self.running=True
        self.progress['value']=0
        self.progress_text.config(text='準備執行…')
        self.status.config(text=action+'執行中')
        for btn in (self.start_btn,self.render_btn,self.plan_btn):btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        output=str(self.result_dir)
        self.append_log(f'=== {action}：{output} ===')
        self.tabs.select(self.tab_logs)
        threading.Thread(target=self.worker,args=(tasks,output,action),daemon=True).start()

    def worker(self,tasks,output,action):
        try:
            for args in tasks:
                if self.cancel_requested:break
                cmd=([sys.executable,'--cli'] if getattr(sys,'frozen',False)
                     else [sys.executable,'-u',str(ROOT/'vlog_maker.py')]) + [args[0],'--out',output]+args[1:]
                self.events.put(('stage',args[0]))
                flags=getattr(subprocess,'CREATE_NO_WINDOW',0) if os.name=='nt' else 0
                self.process=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                   stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1,creationflags=flags)
                for line in self.process.stdout:self.events.put(('log',line.rstrip()))
                result=self.process.wait()
                self.process=None
                if self.cancel_requested:break
                if result:raise RuntimeError(f'{args[0]} 執行失敗，exit code {result}；請查看執行紀錄。')
            self.events.put(('done',('已停止' if self.cancel_requested else action+'完成',action)))
        except Exception as exc:
            self.events.put(('error',str(exc)))
        finally:self.process=None

    def stop(self):
        self.cancel_requested=True
        process=self.process
        if process and process.poll() is None:
            try:
                if os.name=='nt':
                    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
                    subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],
                                   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=8,creationflags=flags)
                else:process.terminate()
            except (OSError,subprocess.SubprocessError):pass
        self.status.config(text='正在停止…')

    def check_env(self):
        selected_model=self.model.get().strip().lower()
        selected_mode=self.analysis_mode.get()
        def job():
            checks=[]
            for name in ('ffmpeg','ffprobe'):
                local=ROOT/'tools'/(name+'.exe')
                checks.append(name+': '+('正常（內附）' if local.is_file() else '正常（PATH）' if shutil.which(name) else '未找到'))
            try:
                with urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=3) as r:
                    models=json.load(r).get('models',[])
                names={m.get('name','').lower() for m in models}
                target=selected_model
                checks.append('Ollama：服務正常')
                checks.append('複審模型：'+('已安裝' if target in names else '未找到，請使用 ollama pull '+target))
                if selected_mode=='balanced':
                    checks.append('初選模型 gemma3:4b：'+('已安裝' if 'gemma3:4b' in names else '未找到'))
            except Exception:checks.append('Ollama：無法連線，請檢查服務是否啟動')
            self.events.put(('environment','\n'.join(checks)))
        threading.Thread(target=job,daemon=True).start()

    def drain(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='log':self.append_log(value)
                elif kind=='stage':
                    self.stage=value;self.progress['value']=0
                    self.progress_text.config(text={'scan':'正在掃描','analyze':'正在分析 AI','plan':'正在產生剪輯預覽','render':'正在輸出 MP4'}.get(value,value))
                    self.append_log('>>> '+value)
                elif kind=='thumbnail':
                    serial,name,error=value
                    if serial==self.thumb_serial:
                        if name:
                            try:
                                self.preview_image=tk.PhotoImage(file=name)
                                self.thumb.config(image=self.preview_image,text='')
                            except tk.TclError as exc:self.thumb.config(image='',text='縮圖無法顯示：'+str(exc)[:55])
                        else:self.thumb.config(image='',text='無法擷取縮圖：'+error[:55])
                elif kind=='environment':
                    self.append_log('=== 環境檢查 ===\n'+value)
                    messagebox.showinfo('環境檢查',value)
                elif kind in ('done','error'):
                    self.running=False
                    for btn in (self.start_btn,self.render_btn,self.plan_btn):btn.config(state='normal')
                    self.stop_btn.config(state='disabled')
                    if kind=='error':
                        self.status.config(text='執行失敗');self.append_log('ERROR: '+value)
                        messagebox.showerror('執行失敗',value)
                    else:
                        msg,action=value
                        self.status.config(text=msg);self.append_log(msg)
                        if not self.cancel_requested:
                            self.progress['value']=100
                            self.reload_candidates(reset=True)
                            self.reload_plan()
                            if action=='預覽':self.tabs.select(self.tab_plan)
                            else:
                                messagebox.showinfo('處理完成','輸出位置：\n'+str(self.result_dir/'Travel_Vlog_Final_V43.mp4'))
        except queue.Empty:pass
        self.master.after(100,self.drain)

    def copy_log(self):
        self.master.clipboard_clear();self.master.clipboard_append(self.log_widget.get('1.0','end-1c'))

    def clear_log(self):
        self.log_widget.config(state='normal');self.log_widget.delete('1.0','end');self.log_widget.config(state='disabled')

    def open_folder(self):
        path=self.result_dir or Path(self.out.get())
        if path.is_dir():
            if os.name=='nt':os.startfile(str(path))
            else:messagebox.showinfo('工作區',str(path))
        else:messagebox.showwarning('尚無工作區','請先執行掃描或剪輯。')

    def close(self):
        if self.running:
            if not messagebox.askyesno('正在執行','確定停止目前任務並關閉？'):return
            self.stop()
        self.save()
        self.master.destroy()


if __name__=='__main__':
    main=tk.Tk()
    Application(main)
    main.mainloop()
