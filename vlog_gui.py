#!/usr/bin/env python3
"""Tkinter frontend for AI Vlog Maker V2. Python standard library only."""
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
CONFIG = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'AI_Vlog_Maker_V3' / 'gui_settings.json'
CONFIG.parent.mkdir(parents=True, exist_ok=True)
DEFAULT_INPUT = r'C:\Users\SCE\Desktop\Travel1'
DEFAULT_OUTPUT = r'C:\Users\SCE\Desktop\Vlogwork'
EXTENSIONS = '.mp4 .mov .m4v .avi .mkv .webm .mts .m2ts .jpg .jpeg .png .webp .bmp .tif .tiff'

class Application:
    def __init__(self, master):
        self.master = master
        master.title('AI Travel Vlog V4.1 — 自動剪輯控制台')
        master.geometry('850x690')
        master.minsize(710, 570)
        self.events = queue.Queue()
        self.process = None
        self.cancel_requested = False
        self.running = False
        self.inputs = []
        self.out = tk.StringVar(value=DEFAULT_OUTPUT)
        self.music = tk.StringVar()
        self.model = tk.StringVar(value='gemma3:12b')
        self.seconds = tk.StringVar(value='180')
        self.test = tk.BooleanVar(value=False)
        self.temporal = tk.BooleanVar(value=True)
        self.analysis_mode = tk.StringVar(value='balanced')
        self.hardware_profile = tk.StringVar(value='cpu')
        self.result_dir = None
        self.build()
        self.load()
        master.after(100, self.drain)
        master.protocol('WM_DELETE_WINDOW', self.close)

    def build(self):
        pad = ttk.Frame(self.master, padding=14)
        pad.pack(fill='both', expand=True)
        ttk.Label(pad, text='AI Travel Vlog V4.1', font=('Segoe UI', 18, 'bold')).pack(anchor='w')
        ttk.Label(pad, text='選擇多個資料夾或個別照片／影片；原始檔案只讀取，不會覆寫。').pack(anchor='w', pady=(1, 12))
        frm = ttk.LabelFrame(pad, text='1. 旅遊素材（可混合多個檔案與資料夾）', padding=8)
        frm.pack(fill='both', expand=False)
        top = ttk.Frame(frm)
        top.pack(fill='x')
        ttk.Button(top, text='加入檔案（可複選）', command=self.add_files).pack(side='left', padx=(0, 6))
        ttk.Button(top, text='加入資料夾', command=self.add_folder).pack(side='left', padx=(0, 6))
        ttk.Button(top, text='移除選取', command=self.remove).pack(side='left', padx=(0, 6))
        ttk.Button(top, text='全部清除', command=self.clear).pack(side='left')
        lf = ttk.Frame(frm)
        lf.pack(fill='both', pady=(8, 0))
        self.lb = tk.Listbox(lf, height=7, selectmode='extended', exportselection=False)
        sb = ttk.Scrollbar(lf, orient='vertical', command=self.lb.yview)
        self.lb.config(yscrollcommand=sb.set)
        self.lb.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')

        f2 = ttk.LabelFrame(pad, text='2. 輸出位置與設定', padding=8)
        f2.pack(fill='x', pady=(10, 0))
        f2.columnconfigure(1, weight=1)
        ttk.Label(f2, text='輸出根目錄').grid(row=0, column=0, sticky='w')
        ttk.Entry(f2, textvariable=self.out).grid(row=0, column=1, sticky='ew', padx=8, pady=3)
        ttk.Button(f2, text='瀏覽', command=self.select_out).grid(row=0, column=2)
        ttk.Label(f2, text='背景音樂（可不選）').grid(row=1, column=0, sticky='w')
        ttk.Entry(f2, textvariable=self.music).grid(row=1, column=1, sticky='ew', padx=8, pady=3)
        ttk.Button(f2, text='選擇音樂', command=self.select_music).grid(row=1, column=2)
        ttk.Label(f2, text='Ollama 模型').grid(row=2, column=0, sticky='w')
        ttk.Entry(f2, textvariable=self.model, width=18).grid(row=2, column=1, sticky='w', padx=8, pady=3)
        opt = ttk.Frame(f2)
        opt.grid(row=3, column=0, columnspan=3, sticky='w', pady=(7, 0))
        ttk.Label(opt, text='目標片長（秒）').pack(side='left')
        ttk.Combobox(opt, textvariable=self.seconds, values=['30', '60', '180', '300', '600'], width=7).pack(side='left', padx=8)
        ttk.Checkbutton(opt, text='測試模式（只掃描 20 個素材、分析 50 個影格，輸出最多 30 秒）', variable=self.test).pack(side='left', padx=7)
        ttk.Checkbutton(f2, text='12B 複審採三影格（慢但有利事件辨識）', variable=self.temporal).grid(row=5, column=0, columnspan=3, sticky='w')
        ttk.Label(f2, text='AI 分析策略').grid(row=6,column=0,sticky='w')
        ttk.Combobox(f2,textvariable=self.analysis_mode,values=['balanced','quality'],state='readonly',width=14).grid(row=6,column=1,sticky='w',padx=8)
        ttk.Label(f2,text='硬體效能設定').grid(row=7,column=0,sticky='w')
        ttk.Combobox(f2,textvariable=self.hardware_profile,values=['cpu','standard'],state='readonly',width=14).grid(row=7,column=1,sticky='w',padx=8)
        ttk.Label(f2, text='balanced：CPU 約 8% 複審／standard 約 20%；quality：12B 全部分析',foreground='#666').grid(row=8,column=0,columnspan=3,sticky='w')
        ttk.Label(f2, text='固定輸出：1920×1080、16:9、無字幕。每組素材使用獨立快取資料夾。', foreground='#666').grid(row=4, column=0, columnspan=3, sticky='w', pady=(8, 0))

        btn = ttk.Frame(pad)
        btn.pack(fill='x', pady=(11, 7))
        self.start_btn = ttk.Button(btn, text='▶ 開始：掃描 → AI 分析 → 輸出', command=self.start)
        self.start_btn.pack(side='left')
        self.stop_btn = ttk.Button(btn, text='■ 停止', command=self.stop, state='disabled')
        self.stop_btn.pack(side='left', padx=9)
        ttk.Button(btn, text='打開輸出資料夾', command=self.open_folder).pack(side='left', padx=4)
        ttk.Button(btn, text='環境檢查', command=self.check_env).pack(side='left', padx=4)
        self.status = ttk.Label(btn, text='就緒')
        self.status.pack(side='right')

        logbox = ttk.LabelFrame(pad, text='執行紀錄', padding=6)
        logbox.pack(fill='both', expand=True)
        self.log_widget = tk.Text(logbox, height=10, state='disabled', wrap='word', font=('Consolas', 9))
        self.log_widget.pack(fill='both', expand=True)
        ttk.Label(pad, text='注意：Windows 安全設定可能要求首次允許 Python / Ollama；請先確認 ffmpeg、ffprobe、ollama 可執行。', foreground='#666').pack(anchor='w', pady=(7, 0))

    def append_log(self, text):
        self.log_widget.config(state='normal')
        self.log_widget.insert('end', text.rstrip()+'\n')
        self.log_widget.see('end')
        self.log_widget.config(state='disabled')

    def add(self, items):
        existing={os.path.normcase(os.path.abspath(x)) for x in self.inputs}
        for item in items:
            p=os.path.abspath(item)
            k=os.path.normcase(p)
            if k not in existing:
                self.inputs.append(p)
                self.lb.insert('end', p)
                existing.add(k)
        self.save()

    def add_files(self):
        p=filedialog.askopenfilenames(title='選擇多個影片／照片', filetypes=[('影片與照片', '*' + ' *'.join(EXTENSIONS.split())), ('所有檔案', '*.*')])
        self.add(p)

    def add_folder(self):
        p=filedialog.askdirectory(title='選擇素材資料夾')
        if p:self.add([p])

    def remove(self):
        for i in reversed(self.lb.curselection()):
            self.lb.delete(i)
            del self.inputs[i]
        self.save()

    def clear(self):
        self.lb.delete(0, 'end')
        self.inputs.clear()
        self.save()

    def select_out(self):
        p=filedialog.askdirectory(title='選擇輸出根目錄')
        if p:self.out.set(p);self.save()

    def select_music(self):
        p=filedialog.askopenfilename(title='選擇配樂', filetypes=[('音訊', '*.mp3 *.wav *.m4a *.flac *.aac'), ('所有檔案', '*.*')])
        if p:self.music.set(p);self.save()

    def save(self):
        try:
            CONFIG.write_text(json.dumps({'inputs':self.inputs,'output':self.out.get(),'music':self.music.get(),'model':self.model.get(),'seconds':self.seconds.get(),'temporal':self.temporal.get(),'analysis_mode':self.analysis_mode.get(),'hardware_profile':self.hardware_profile.get()}, ensure_ascii=False,indent=2), encoding='utf-8')
        except OSError:pass

    def load(self):
        try:data=json.loads(CONFIG.read_text(encoding='utf-8'))
        except (OSError, ValueError):data={'inputs':[DEFAULT_INPUT]}
        self.add(data.get('inputs',[]))
        for key,var in [('output',self.out),('music',self.music),('model',self.model),('seconds',self.seconds),('temporal',self.temporal),('analysis_mode',self.analysis_mode),('hardware_profile',self.hardware_profile)]:
            if data.get(key) is not None:
                value=data[key]
                if key=='model' and value=='gemma3:4b':value='gemma3:12b'
                if key=='temporal':var.set(bool(value))
                else:var.set(str(value))

    def check_env(self):
        import shutil
        checks=[]
        folder=ROOT/'tools'
        for tool in ('ffmpeg','ffprobe'):
            local=folder/(tool+'.exe')
            checks.append(f'{tool}: '+('正常（內附）' if local.is_file() else ('正常（PATH）' if shutil.which(tool) else '缺少')))
        ollama=shutil.which('ollama')
        try:
            import urllib.request
            with urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=3) as r:
                models=json.load(r).get('models',[])
            names=[m.get('name','') for m in models]
            target=self.model.get().strip()
            checks.append('Ollama 服務: 正常')
            checks.append('模型 '+target+': '+('已安裝' if target in names else '未找到，請執行 ollama pull '+target))
        except Exception:
            checks.append('Ollama 服務: 未連線，請安裝並啟動 Ollama')
        msg='\n'.join(checks)
        self.append_log('=== 環境檢查 ===\n'+msg)
        messagebox.showinfo('環境檢查',msg)

    def start(self):
        if self.running:return
        self.check_env()
        if not self.inputs:
            messagebox.showerror('沒有素材', '請先加入至少一個檔案或資料夾。');return
        invalid=[p for p in self.inputs if not Path(p).exists()]
        if invalid:
            messagebox.showerror('找不到素材', '\n'.join(invalid[:5]));return
        try:
            length=int(self.seconds.get())
            if length < 1 or length > 3600:raise ValueError
        except ValueError:
            messagebox.showerror('片長錯誤','請輸入 1 到 3600 秒。');return
        if not self.model.get().strip():messagebox.showerror('模型錯誤','請填入 Ollama 模型名稱。');return
        if self.music.get().strip() and not Path(self.music.get()).is_file():
            messagebox.showerror('音樂檔案錯誤','找不到指定的音樂檔案。');return
        if not Path(self.out.get()).is_dir():
            try:Path(self.out.get()).mkdir(parents=True,exist_ok=True)
            except OSError as e:messagebox.showerror('輸出錯誤',str(e));return
        self.save()
        # One index per selected source set prevents stale sources from contaminating jobs.
        digest=hashlib.sha256('\n'.join(sorted(os.path.normcase(p) for p in self.inputs)).encode('utf-8')).hexdigest()[:12]
        self.result_dir=Path(self.out.get()) / ('AI_Vlog_' + digest)
        self.result_dir.mkdir(parents=True,exist_ok=True)
        self.cancel_requested=False
        self.running=True
        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.status.config(text='執行中…')
        inputs=list(self.inputs); output=str(self.result_dir); model=self.model.get().strip()
        test=self.test.get(); music=self.music.get().strip(); temporal=self.temporal.get(); analysis_mode=self.analysis_mode.get(); hardware_profile=self.hardware_profile.get()
        self.append_log('=== 開始工作：'+output+' ===')
        self.append_log('素材來源：'+str(len(inputs))+' 項')
        threading.Thread(target=self.worker,args=(inputs,output,model,length,test,music,temporal,analysis_mode,hardware_profile),daemon=True).start()

    def worker(self,inputs,output,model,length,test,music,temporal,analysis_mode,hardware_profile):
        stages=[['scan']+sum((['--input',p] for p in inputs), [])+(['--scan-limit','20'] if test else []),
                ['analyze','--model',model,'--analysis-mode',analysis_mode,'--hardware-profile',hardware_profile,'--fast-model','gemma3:4b','--ai-timeout','120']+([] if temporal else ['--single-frame'])+(['--analyze-limit','50'] if test else []),
                ['render','--seconds',str(min(length,30) if test else length),'--min-score','40']+(['--music',music] if music else [])]
        try:
            for args in stages:
                if self.cancel_requested:break
                cmd=([sys.executable, '--cli'] if getattr(sys,'frozen',False) else [sys.executable,'-u',str(ROOT/'vlog_maker.py')]) + [args[0],'--out',output]+args[1:]
                self.events.put(('log','>>> '+args[0]))
                flags=getattr(subprocess,'CREATE_NO_WINDOW',0) if os.name=='nt' else 0
                self.process=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1,creationflags=flags)
                for line in self.process.stdout:
                    self.events.put(('log',line.rstrip()))
                code=self.process.wait()
                self.process=None
                if self.cancel_requested:break
                if code!=0:raise RuntimeError(f'{args[0]} 執行失敗（exit code {code}）。請查看上方紀錄。')
            self.events.put(('done','已停止' if self.cancel_requested else '剪輯完成！'))
        except Exception as exc:self.events.put(('error',str(exc)))
        finally:self.process=None

    def drain(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='log':self.append_log(value)
                elif kind in ('done','error'):
                    self.running=False
                    self.start_btn.config(state='normal')
                    self.stop_btn.config(state='disabled')
                    self.status.config(text=value if kind=='done' else '執行失敗')
                    self.append_log(value)
                    if kind=='done' and not self.cancel_requested:
                        messagebox.showinfo('完成','影片位置：\n'+str(self.result_dir/'Travel_Vlog_Final_V2.mp4'))
                    elif kind=='error':messagebox.showerror('執行失敗',value)
        except queue.Empty:pass
        self.master.after(100,self.drain)

    def stop(self):
        self.cancel_requested=True
        proc=self.process
        if proc and proc.poll() is None:
            try:proc.terminate()
            except OSError:pass
        self.status.config(text='停止中…')

    def open_folder(self):
        path=self.result_dir or Path(self.out.get())
        if not path.is_dir():messagebox.showinfo('找不到資料夾',str(path));return
        if os.name=='nt':os.startfile(str(path))
        else:messagebox.showinfo('輸出路徑',str(path))

    def close(self):
        if self.running:
            if not messagebox.askyesno('正在執行','要停止任務並關閉嗎？'):return
            self.stop()
        self.save()
        self.master.destroy()

if __name__=='__main__':
    window=tk.Tk()
    Application(window)
    window.mainloop()
