"""PySide6 In/Out trimming dialog with embedded LibVLC (Windows HWND)."""
from __future__ import annotations
import sys
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel,
    QPushButton, QSlider, QLineEdit, QFormLayout, QMessageBox, QGroupBox)
from vlc_loader import import_vlc
from trim_times import parse_time, validate_times, display_time


class QtTrimDialog(QDialog):
    def __init__(self,parent,source,duration,start,end,on_save):
        super().__init__(parent)
        self.source=Path(source);self.duration=float(duration);self.on_save=on_save
        self.player=None;self.instance=None;self.vlc=None
        self.range_end=None;self.seek_pending=False;self.dragging=False;self.initial_attempts=0
        self.setWindowTitle('預覽與裁切 · '+self.source.name)
        self.setMinimumSize(800,620);self.resize(960,690)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose,True)
        body=QVBoxLayout(self)
        header=QLabel(self.source.name);header.setObjectName('heading');body.addWidget(header)
        self.notice=QLabel('播放器載入中…');self.notice.setWordWrap(True);body.addWidget(self.notice)
        self.screen=QWidget();self.screen.setAttribute(Qt.WidgetAttribute.WA_NativeWindow,True)
        self.screen.setStyleSheet('background:#070b13;border-radius:8px;')
        self.screen.setMinimumHeight(310);body.addWidget(self.screen,1)
        bar=QHBoxLayout();body.addLayout(bar)
        self.play_btn=QPushButton('▶ 播放');bar.addWidget(self.play_btn)
        stop=QPushButton('■ 停止');bar.addWidget(stop)
        range_btn=QPushButton('▶ 播放裁切區間');bar.addWidget(range_btn)
        self.clock=QLabel(display_time(start)+' / '+display_time(duration));bar.addWidget(self.clock,1)
        bar.addWidget(QLabel('音量'))
        self.volume=QSlider(Qt.Orientation.Horizontal);self.volume.setRange(0,100);self.volume.setValue(70)
        self.volume.setMaximumWidth(140);bar.addWidget(self.volume)
        self.seek=QSlider(Qt.Orientation.Horizontal);self.seek.setRange(0,max(1,round(duration*1000)))
        self.seek.setValue(round(start*1000));body.addWidget(self.seek)
        help_label=QLabel('拖動進度條定位；按「設為目前時間」即可指定裁切起點或終點。')
        help_label.setObjectName('muted');body.addWidget(help_label)
        edits=QGroupBox('裁切區間（MM:SS.mmm）');form=QFormLayout(edits);body.addWidget(edits)
        inbar=QHBoxLayout();self.in_edit=QLineEdit(display_time(start));inbar.addWidget(self.in_edit)
        self.mark_in_btn=QPushButton('設為目前時間');inbar.addWidget(self.mark_in_btn)
        form.addRow('開始 In',inbar)
        outbar=QHBoxLayout();self.out_edit=QLineEdit(display_time(end));outbar.addWidget(self.out_edit)
        self.mark_out_btn=QPushButton('設為目前時間');outbar.addWidget(self.mark_out_btn)
        form.addRow('結束 Out',outbar)
        actions=QHBoxLayout();body.addLayout(actions);actions.addStretch(1)
        cancel=QPushButton('取消');actions.addWidget(cancel)
        self.apply_btn=QPushButton('套用裁切並加入片單');self.apply_btn.setObjectName('primary');actions.addWidget(self.apply_btn)
        cancel.clicked.connect(self.reject);self.apply_btn.clicked.connect(self.save)
        self.play_btn.clicked.connect(self.toggle);stop.clicked.connect(self.stop);range_btn.clicked.connect(self.play_range)
        self.seek.sliderPressed.connect(lambda:setattr(self,'dragging',True))
        self.seek.sliderReleased.connect(self.seek_release)
        self.mark_in_btn.clicked.connect(lambda:self.in_edit.setText(display_time(self.current_position())))
        self.mark_out_btn.clicked.connect(lambda:self.out_edit.setText(display_time(self.current_position())))
        self.volume.valueChanged.connect(lambda val:self.player.audio_set_volume(val) if self.player else None)
        self.timer=QTimer(self);self.timer.setInterval(80);self.timer.timeout.connect(self.tick)
        QTimer.singleShot(80,self.start_vlc)

    def start_vlc(self):
        try:
            self.vlc=import_vlc();self.instance=self.vlc.Instance('--quiet','--no-video-title-show')
            if not self.instance:raise RuntimeError('LibVLC 無法初始化')
            self.player=self.instance.media_player_new()
            self.screen.winId()
            if sys.platform=='win32':self.player.set_hwnd(int(self.screen.winId()))
            elif sys.platform.startswith('linux'):self.player.set_xwindow(int(self.screen.winId()))
            else:raise RuntimeError('目前僅支援 Windows / Linux LibVLC 嵌入')
            media=self.instance.media_new(str(self.source));self.player.set_media(media)
            self.player.audio_set_volume(0)
            if self.player.play()==-1:raise RuntimeError('VLC 無法載入影片')
            self.notice.setText('已載入影片，可精確輸入裁切時間。')
            self.timer.start();QTimer.singleShot(130,self.seek_initial)
        except Exception as exc:
            self.notice.setText('VLC 播放不可用：'+str(exc)+'。仍可直接輸入裁切時間。')
            self.play_btn.setEnabled(False)

    def seek_initial(self):
        if not self.player:return
        try:
            if self.player.is_seekable():
                self.player.set_time(int(parse_time(self.in_edit.text())*1000))
                self.player.set_pause(1)
                self.player.audio_set_volume(self.volume.value())
                return
        except Exception:pass
        self.initial_attempts+=1
        if self.initial_attempts<45:QTimer.singleShot(100,self.seek_initial)
        else:
            self.player.set_pause(1);self.player.audio_set_volume(self.volume.value())
            self.notice.setText('影片尚無法定位；可直接輸入 In／Out。')

    def current_position(self):
        if self.player:
            try:
                ms=self.player.get_time()
                if ms>=0:return ms/1000
            except Exception:pass
        return self.seek.value()/1000

    def tick(self):
        if not self.player:return
        try:
            ms=self.player.get_time()
            if ms>=0:
                if not self.dragging:
                    self.seek.blockSignals(True);self.seek.setValue(min(self.seek.maximum(),ms));self.seek.blockSignals(False)
                self.clock.setText(display_time(ms/1000)+' / '+display_time(self.duration))
                if self.range_end is not None and ms/1000>=self.range_end:
                    self.player.set_pause(1);self.range_end=None
                    self.play_btn.setText('▶ 播放')
            if not self.player.is_playing():self.play_btn.setText('▶ 播放')
        except Exception:pass

    def seek_release(self):
        self.dragging=False
        if self.player:self.player.set_time(self.seek.value())

    def toggle(self):
        if not self.player:return
        try:
            if self.player.is_playing():
                self.player.set_pause(1);self.play_btn.setText('▶ 播放')
            else:
                self.range_end=None
                state=self.player.get_state()
                if state in (self.vlc.State.Stopped,self.vlc.State.Ended,self.vlc.State.Error):
                    at=self.seek.value()
                    self.player.stop();self.player.play()
                    QTimer.singleShot(200,lambda:self.player.set_time(at) if self.player else None)
                else:self.player.set_pause(0)
                self.play_btn.setText('Ⅱ 暫停')
        except Exception as exc:self.notice.setText('播放失敗：'+str(exc))

    def stop(self):
        self.range_end=None
        if self.player:self.player.stop()
        self.play_btn.setText('▶ 播放')

    def play_range(self):
        try:start,end=validate_times(parse_time(self.in_edit.text()),parse_time(self.out_edit.text()),self.duration)
        except ValueError as exc:return QMessageBox.warning(self,'裁切區間錯誤',str(exc))
        if not self.player:return
        self.range_end=end
        try:
            if self.player.get_state() in (self.vlc.State.Stopped,self.vlc.State.Ended,self.vlc.State.Error):
                self.player.play();QTimer.singleShot(180,lambda:self._seek_range(start))
            else:self._seek_range(start)
            self.play_btn.setText('Ⅱ 暫停')
        except Exception as exc:self.notice.setText(str(exc))

    def _seek_range(self,start,attempt=0):
        if not self.player:return
        if self.player.is_seekable():
            self.player.set_time(round(start*1000));self.player.set_pause(0)
        elif attempt<35:QTimer.singleShot(100,lambda:self._seek_range(start,attempt+1))
        else:self.notice.setText('來源檔尚未準備好定位')

    def save(self):
        try:start,end=validate_times(parse_time(self.in_edit.text()),parse_time(self.out_edit.text()),self.duration)
        except ValueError as exc:return QMessageBox.warning(self,'裁切區間錯誤',str(exc))
        try:
            if self.on_save(start,end) is not False:self.accept()
        except Exception as exc:QMessageBox.critical(self,'無法儲存裁切',str(exc))

    def done(self,result):
        self.timer.stop()
        try:
            if self.player:
                self.player.stop();self.player.release();self.player=None
            if self.instance:
                self.instance.release();self.instance=None
        except Exception:pass
        super().done(result)
