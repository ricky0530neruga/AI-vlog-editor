#!/usr/bin/env python3
"""AI Vlog Maker v1.4: native-window VLC preview + exact In/Out editor.

Optional GUI dependency: python-vlc AND the 64-bit VLC application on Windows.
No source media is modified. If VLC is unavailable, time editing still works
and the dialog explains what has to be installed.
"""
from __future__ import annotations

import ctypes
import math
import os
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk, messagebox

_VLC_DLL_HANDLE = None


def _import_vlc():
    """Prefer a system VLC installation; python-vlc itself does not ship libvlc."""
    global _VLC_DLL_HANDLE
    if sys.platform == 'win32':
        candidates=[]
        for name in ('VLC_DIR','VLC_HOME'):
            if os.environ.get(name):candidates.append(Path(os.environ[name]))
        for name in ('PROGRAMFILES','PROGRAMFILES(X86)'):
            if os.environ.get(name):candidates.append(Path(os.environ[name])/'VideoLAN'/'VLC')
        for folder in candidates:
            if (folder/'libvlc.dll').is_file():
                os.environ.setdefault('VLC_PLUGIN_PATH',str(folder/'plugins'))
                if hasattr(os,'add_dll_directory'):
                    _VLC_DLL_HANDLE=os.add_dll_directory(str(folder))
                else:
                    os.environ['PATH']=str(folder)+os.pathsep+os.environ.get('PATH','')
                break
    import vlc  # python-vlc binding, needs a matching LibVLC installation
    return vlc


def parse_time(value):
    """Return seconds from e.g. 12.5, 00:12.5 or 00:01:12.5."""
    parts=str(value).strip().split(':')
    if not 1<=len(parts)<=3:raise ValueError('請輸入秒數、分:秒或時:分:秒。')
    try:
        nums=[float(x) for x in parts]
    except ValueError as exc:raise ValueError('時間格式不正確，請輸入 12.5 或 00:12.5。') from exc
    if any(not math.isfinite(n) or n<0 for n in nums):raise ValueError('時間不能為負數、無限大或非數值。')
    if len(parts)>1 and any(x>=60 for x in nums[1:]):
        raise ValueError('分、秒的欄位必須小於 60。')
    sec=0.
    for n in nums:sec=sec*60+n
    return round(sec,3)


def validate_times(start, end, duration):
    start,end,duration=float(start),float(end),float(duration)
    if not all(map(math.isfinite,(start,end,duration))):raise ValueError('時間必須是有限數值。')
    if not 0<=start<end:raise ValueError('結束時間必須晚於開始時間。')
    if end>duration+0.005:raise ValueError(f'結束時間不可超過來源影片長度 {duration:.3f} 秒。')
    if end-start<0.5:raise ValueError('保留片段不可短於 0.5 秒。')
    return round(start,3),round(min(end,duration),3)


def display_time(seconds):
    seconds=max(0.,float(seconds))
    hours=int(seconds//3600);minutes=int(seconds//60)%60
    if hours:return f'{hours:02d}:{minutes:02d}:{seconds%60:06.3f}'
    return f'{minutes:02d}:{seconds%60:06.3f}'


class VideoTrimDialog:
    def __init__(self, parent, source, duration, start, end, on_save, on_close=None):
        self.parent=parent;self.source=Path(source);self.duration=float(duration)
        self.on_save=on_save;self.on_close=on_close
        self._closed=False;self._initial_seek_attempts=0
        self.window=tk.Toplevel(parent)
        self.window.title('v1.4 · 播放與裁切 — '+self.source.name)
        self.window.geometry('880x710');self.window.minsize(650,550)
        self.window.transient(parent)
        self.window.protocol('WM_DELETE_WINDOW',self.close)
        self._after_id=None;self.player=None;self.instance=None;self.vlc=None
        self._is_scrubbing=False;self._updating_seek=False;self._range_play=False;self._range_seek_pending=False
        self.start_str=tk.StringVar(value=display_time(start))
        self.end_str=tk.StringVar(value=display_time(end))
        self.clock=tk.StringVar(value=display_time(start)+' / '+display_time(self.duration))
        self.message=tk.StringVar(value='播放器初始化中…')
        self.position=tk.DoubleVar(value=float(start))
        self.volume=tk.IntVar(value=70)
        self._make_ui()
        self.window.after(80,self._init_player)

    def _make_ui(self):
        box=ttk.Frame(self.window,padding=12);box.pack(fill='both',expand=True)
        ttk.Label(box,text=self.source.name,font=('Segoe UI',12,'bold')).pack(anchor='w')
        ttk.Label(box,textvariable=self.message,foreground='#52616f').pack(anchor='w',pady=(2,8))
        self.canvas=tk.Frame(box,background='#121821',height=320)
        self.canvas.pack(fill='both',expand=True)
        controls=ttk.Frame(box);controls.pack(fill='x',pady=(9,0))
        self.play_button=ttk.Button(controls,text='▶ 播放',command=self.toggle_play)
        self.play_button.pack(side='left')
        ttk.Button(controls,text='■ 停止',command=self.stop).pack(side='left',padx=5)
        ttk.Button(controls,text='▶ 只播放裁切範圍',command=self.play_range).pack(side='left',padx=(0,7))
        ttk.Label(controls,textvariable=self.clock).pack(side='left',padx=6)
        ttk.Label(controls,text='音量').pack(side='right')
        ttk.Scale(controls,from_=0,to=100,variable=self.volume,command=self._set_volume,length=100).pack(side='right',padx=6)
        seek=ttk.Frame(box);seek.pack(fill='x',pady=(12,0))
        self.seek=ttk.Scale(seek,from_=0,to=self.duration,variable=self.position,command=self._on_seek_drag)
        self.seek.pack(fill='x')
        self.seek.bind('<ButtonRelease-1>',self._on_seek_release)
        ttk.Label(box,text='拖曳上方進度條定位；「設為 In／Out」會使用目前播放位置。',foreground='#52616f').pack(anchor='w',pady=4)
        edits=ttk.LabelFrame(box,text='裁切範圍（可直接輸入 MM:SS.mmm）',padding=10)
        edits.pack(fill='x',pady=(8,5))
        for label,variable,mark in [('開始 In',self.start_str,self.mark_in),('結束 Out',self.end_str,self.mark_out)]:
            group=ttk.Frame(edits);group.pack(side='left',padx=(0,16))
            ttk.Label(group,text=label).pack(anchor='w')
            ttk.Entry(group,textvariable=variable,width=14).pack(side='left')
            ttk.Button(group,text='設為目前時間',command=mark).pack(side='left',padx=3)
        buttons=ttk.Frame(box);buttons.pack(fill='x',pady=(13,0))
        ttk.Button(buttons,text='取消',command=self.close).pack(side='right')
        ttk.Button(buttons,text='套用裁切並加入片單',command=self.save).pack(side='right',padx=8)

    def _init_player(self):
        if not self.window.winfo_exists():return
        try:
            self.vlc=_import_vlc()
            self.instance=self.vlc.Instance('--quiet','--no-video-title-show')
            if self.instance is None:raise RuntimeError('LibVLC 初始化失敗')
            self.player=self.instance.media_player_new()
            self.canvas.update_idletasks()
            hwnd=self.canvas.winfo_id()
            if sys.platform=='win32':self.player.set_hwnd(hwnd)
            elif sys.platform.startswith('linux'):self.player.set_xwindow(hwnd)
            else:raise RuntimeError('目前僅驗證 Windows / Linux 的播放器嵌入')
            media=self.instance.media_new(str(self.source))
            self.player.set_media(media)
            self.player.audio_set_volume(0)  # avoid audio burst before initial pause
            if self.player.play()==-1:raise RuntimeError('VLC 無法開始播放來源檔案')
            self.message.set('已載入影片。可播放、暫停、拖曳或輸入精確 In／Out。')
            self.window.after(120,self._seek_initial)
        except Exception as exc:
            self.message.set('無法啟動內建播放器：'+str(exc)[:140]+
                             '。請安裝 64 位元 VLC 和 python-vlc；仍可手動輸入裁切時間。')
            self.play_button.configure(state='disabled')
        self._tick()

    def _seek_initial(self):
        if self._closed or not self.player:return
        try:
            if self.player.is_seekable():
                self.player.set_time(int(self.position.get()*1000))
                self.player.set_pause(1)
                self.player.audio_set_volume(int(self.volume.get()))
                return
        except Exception:pass
        self._initial_seek_attempts+=1
        if self._initial_seek_attempts<45:
            self.window.after(100,self._seek_initial)
        else:
            try:
                self.player.set_pause(1)
                self.player.audio_set_volume(int(self.volume.get()))
            except Exception:pass
            self.message.set('播放器尚未完成定位，請稍後使用進度條。')

    def _tick(self):
        if not self.window.winfo_exists():return
        if self.player:
            try:
                time_ms=self.player.get_time()
                if time_ms>=0:
                    current=min(self.duration,time_ms/1000)
                    if not self._is_scrubbing:
                        self._updating_seek=True
                        try:self.position.set(current)
                        finally:self._updating_seek=False
                    self.clock.set(display_time(current)+' / '+display_time(self.duration))
                    if self._range_play and not self._range_seek_pending and current>=parse_time(self.end_str.get()):
                        self.player.set_pause(1);self._range_play=False
                        self.play_button.configure(text='▶ 播放')
                if not self.player.is_playing():self.play_button.configure(text='▶ 播放')
            except Exception:pass
        self._after_id=self.window.after(80,self._tick)

    def _set_volume(self,_value=None):
        if self.player:
            try:self.player.audio_set_volume(int(self.volume.get()))
            except Exception:pass

    def toggle_play(self):
        if not self.player:return
        if self.player.is_playing():self.player.set_pause(1);self.play_button.configure(text='▶ 播放')
        else:
            state=self.player.get_state()
            if state in (self.vlc.State.Ended,self.vlc.State.Stopped,
                         self.vlc.State.NothingSpecial,self.vlc.State.Error):
                if self.player.play()==-1:
                    self.message.set('影片重新播放失敗');return
            else:self.player.set_pause(0)
            self._range_play=False
            self.play_button.configure(text='⏸ 暫停')

    def stop(self):
        if self.player:
            self.player.stop();self._range_play=False;self._range_seek_pending=False
        self.play_button.configure(text='▶ 播放')

    def play_range(self):
        try:start,end=validate_times(parse_time(self.start_str.get()),parse_time(self.end_str.get()),self.duration)
        except ValueError as exc:return messagebox.showerror('裁切時間無效',str(exc),parent=self.window)
        if self.player:
            if self.player.play()==-1:
                return messagebox.showerror('無法播放','播放器無法播放選定區間。',parent=self.window)
            self._range_play=True;self._range_seek_pending=True
            self.player.audio_set_volume(0)
            self._range_seek(start,0)
            self.play_button.configure(text='⏸ 暫停')
        else:messagebox.showinfo('未安裝 VLC','需要安裝 VLC 才能播放；你仍可儲存裁切時間。',parent=self.window)

    def _range_seek(self,start,attempt):
        if self._closed or not self.player or not self._range_play:return
        try:
            if self.player.is_seekable():
                self.player.set_time(int(start*1000))
                self.player.audio_set_volume(int(self.volume.get()))
                self._range_seek_pending=False
                return
        except Exception:pass
        if attempt<40:self.window.after(100,lambda:self._range_seek(start,attempt+1))
        else:
            self._range_play=False;self._range_seek_pending=False
            self.player.set_pause(1)
            self.player.audio_set_volume(int(self.volume.get()))
            self.play_button.configure(text='▶ 播放')
            self.message.set('尚無法精確定位，請稍後重試區間播放。')

    def _on_seek_drag(self,_value):
        if self._updating_seek:return
        self._is_scrubbing=True
        self.clock.set(display_time(self.position.get())+' / '+display_time(self.duration))

    def _on_seek_release(self,_event):
        self._is_scrubbing=False
        if self.player:
            try:self.player.set_time(int(self.position.get()*1000))
            except Exception:pass

    def _current_time(self):
        if self._is_scrubbing:return self.position.get()
        if self.player:
            try:
                milliseconds=self.player.get_time()
                if milliseconds>=0:return min(self.duration,milliseconds/1000)
            except Exception:pass
        return self.position.get()

    def mark_in(self):self.start_str.set(display_time(self._current_time()))
    def mark_out(self):self.end_str.set(display_time(self._current_time()))

    def save(self):
        try:
            start,end=validate_times(parse_time(self.start_str.get()),parse_time(self.end_str.get()),self.duration)
            if self.on_save(start,end) is False:return
        except (ValueError,OSError) as exc:return messagebox.showerror('無法儲存裁切',str(exc),parent=self.window)
        self.close()

    def close(self):
        if self._closed:return
        self._closed=True
        if self._after_id is not None:
            try:self.window.after_cancel(self._after_id)
            except tk.TclError:pass
        if self.player:
            try:self.player.stop();self.player.release()
            except Exception:pass
        self.player=None
        if self.instance:
            try:self.instance.release()
            except Exception:pass
        self.instance=None
        if self.window.winfo_exists():self.window.destroy()
        if self.on_close:self.on_close()
