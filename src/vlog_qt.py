"""AI Vlog Maker v1.5 — PySide6 interface migration.

Runs the original v1.4 scan/analyze/selection/render engine unmodified.
Keeps the v1.4 workspace hash and ui_selected_v441.json file.
The timeline is an editable clip-order overview; frame-edge trimming remains in the VLC dialog.
"""
from __future__ import annotations
from contextlib import closing
import json
import math
import os
from pathlib import Path
import queue
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import threading
from urllib.request import urlopen

from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtGui import QBrush, QColor, QFont, QPen, QPixmap, QShortcut, QKeySequence
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
  QGridLayout, QStackedWidget, QListWidget, QListWidgetItem, QSplitter, QGroupBox, QFormLayout,
  QLineEdit, QLabel, QPushButton, QFileDialog, QMessageBox, QTextEdit, QCheckBox, QComboBox,
  QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView, QProgressBar, QFrame,
  QGraphicsView, QGraphicsScene, QGraphicsRectItem, QGraphicsSimpleTextItem, QGraphicsItem, QSlider)

import qt_store as store
from project_paths import ROOT, SOURCE

FILE_FILTER = '影片與照片 (*.mp4 *.mov *.m4v *.avi *.mkv *.webm *.mts *.m2ts *.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff);;全部 (*)'

STYLE = '''
QMainWindow, QWidget { background:#10151e; color:#e7ebf3; font-family:"Segoe UI", "Microsoft JhengHei"; font-size:12px; }
QWidget#side { background:#151d2a; border-right:1px solid #2b3545; }
QLabel#brand {font-size:21px; font-weight:750; color:#ffffff;}
QLabel#heading {font-size:17px; font-weight:700;}
QLabel#muted {color:#94a3b8;}
QLabel#metric {color:#5eead4; font-size:13px; font-weight:600;}
QListWidget#nav {background:transparent;border:none;outline:0;font-size:14px;}
QListWidget#nav::item {padding:14px 13px;border-radius:9px;margin:3px 5px;}
QListWidget#nav::item:selected {background:#0f766e;color:white;font-weight:600;}
QLineEdit, QComboBox, QTableWidget, QTextEdit, QListWidget, QGraphicsView {background:#182331;border:1px solid #344156;border-radius:7px;padding:5px;color:#e7ebf3;}
QTableWidget {gridline-color:#293647;selection-background-color:#155e63;alternate-background-color:#1c2a39;}
QHeaderView::section {background:#233042;color:#d6e0ee;padding:8px;border:none;border-right:1px solid #354054;}
QPushButton {background:#253246;border:1px solid #3a4b61;border-radius:8px;padding:8px 12px;font-weight:550;}
QPushButton:hover {background:#32445b;}
QPushButton:disabled {color:#6e7c90;background:#192432;border-color:#263343;}
QPushButton#primary {background:#0f766e;border:1px solid #14b8a6;color:#ffffff;font-weight:700;}
QPushButton#primary:hover {background:#0d9488;}
QGroupBox {border:1px solid #324154;border-radius:9px;margin-top:12px;padding:13px 10px 10px 10px;font-weight:600;}
QGroupBox::title {subcontrol-origin:margin;subcontrol-position:top left;padding:0 7px;left:10px;color:#cbd5e1;}
QProgressBar {border:1px solid #344156;border-radius:6px;background:#182331;height:12px;text-align:center;}
QProgressBar::chunk {background:#0d9488;border-radius:5px;}
QSplitter::handle {background:#2b3545;}
QCheckBox {spacing:7px;}
'''

class Bus(QObject):
    thumbnail=Signal(int,str,str)


class ReorderTable(QTableWidget):
    order_changed=Signal(int,int)
    def __init__(self):
        super().__init__()
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setDragEnabled(True);self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDragDropOverwriteMode(False)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
    def dropEvent(self,event):
        src=self.currentRow()
        point=event.position().toPoint()
        dest=self.rowAt(point.y())
        if dest<0:dest=self.rowCount()-1
        if src>=0 and dest>=0 and src!=dest:
            event.acceptProposedAction()
            # Rebuild the table after Qt has finished processing the drag event.
            QTimer.singleShot(0,lambda:self.order_changed.emit(src,dest))
        else:event.ignore()


class EditorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('AI Vlog Maker · v1.5 Qt Preview')
        self.resize(1420,900);self.setMinimumSize(1050,690)
        self.events=queue.Queue();self.bus=Bus();self.bus.thumbnail.connect(self.thumbnail_arrived)
        self.process=None;self.running=False;self.cancel_requested=False;self.current_dialog=None
        self.inputs=[];self.override_workspace=None;self.workspace_dir=None
        self.page=0;self.page_rows={};self.selected_ids=[];self.plan_rows={};self.manual_trims={}
        self.last_source='candidate';self.thumb_serial=0;self.history=[];self.redo_stack=[]
        self.make_ui();self.load_settings()
        # The Windows installer can choose just one model. Prevent a saved
        # balanced-mode preference from silently requesting a missing model.
        selected=[x.strip() for x in os.environ.get('AI_VLOG_REQUIRED_MODELS','').split(',') if x.strip()]
        if len(selected)==1:
            self.model_edit.setText(selected[0])
            self.mode_box.setCurrentIndex(1)  # single-model quality mode
        self.workspace_changed()
        self.timer=QTimer(self);self.timer.timeout.connect(self.drain);self.timer.start(90)
        QShortcut(QKeySequence('Ctrl+Z'),self,activated=self.undo)
        QShortcut(QKeySequence('Ctrl+Y'),self,activated=self.redo)

    @staticmethod
    def button(text,slot,primary=False):
        btn=QPushButton(text)
        if primary:btn.setObjectName('primary')
        btn.clicked.connect(slot)
        return btn

    def section_header(self,title,sub):
        host=QWidget();lay=QVBoxLayout(host);lay.setContentsMargins(0,0,0,7)
        label=QLabel(title);label.setObjectName('heading');lay.addWidget(label)
        hint=QLabel(sub);hint.setObjectName('muted');hint.setWordWrap(True);lay.addWidget(hint)
        return host

    def make_ui(self):
        central=QWidget();self.setCentralWidget(central);whole=QHBoxLayout(central)
        whole.setContentsMargins(0,0,0,0);whole.setSpacing(0)
        sidebar=QWidget();sidebar.setObjectName('side');sidebar.setFixedWidth(218)
        side=QVBoxLayout(sidebar);side.setContentsMargins(13,22,13,18)
        brand=QLabel('AI Vlog Maker');brand.setObjectName('brand');side.addWidget(brand)
        version=QLabel('v1.5 · Smart Timeline');version.setObjectName('muted');side.addWidget(version)
        side.addSpacing(28)
        self.nav=QListWidget();self.nav.setObjectName('nav')
        for item in ('01   素材與 AI 分析','02   剪輯工作台','03   執行紀錄'):
            self.nav.addItem(QListWidgetItem(item))
        side.addWidget(self.nav,1)
        side.addWidget(QLabel('目前工作區'))
        self.workspace_name=QLabel('尚未選擇素材');self.workspace_name.setObjectName('muted');self.workspace_name.setWordWrap(True)
        side.addWidget(self.workspace_name);whole.addWidget(sidebar)

        main=QWidget();ml=QVBoxLayout(main);ml.setContentsMargins(22,18,22,13)
        self.pages=QStackedWidget();ml.addWidget(self.pages,1)
        self.scan_page=QWidget();self.edit_page=QWidget();self.log_page=QWidget()
        for w in (self.scan_page,self.edit_page,self.log_page):self.pages.addWidget(w)
        self.build_scan();self.build_edit();self.build_log()
        footer=QHBoxLayout();ml.addLayout(footer)
        self.progress=QProgressBar();self.progress.setRange(0,100);self.progress.setValue(0);self.progress.setMaximumWidth(255)
        footer.addWidget(self.progress)
        self.progress_label=QLabel('就緒');self.progress_label.setObjectName('muted');footer.addWidget(self.progress_label,1)
        self.status=QLabel('● 就緒');self.status.setObjectName('metric');footer.addWidget(self.status)
        whole.addWidget(main,1)
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex);self.nav.setCurrentRow(0)

    def build_scan(self):
        lay=QVBoxLayout(self.scan_page);lay.setContentsMargins(0,0,0,0)
        lay.addWidget(self.section_header('素材與 AI 分析','第一步：加入旅行影片或照片，讓 AI 建立可供剪輯的候選鏡頭。'))
        sources=QGroupBox('來源素材');s=QVBoxLayout(sources)
        ops=QHBoxLayout();s.addLayout(ops)
        ops.addWidget(self.button('＋ 加入檔案',self.add_files))
        ops.addWidget(self.button('＋ 加入資料夾',self.add_folder))
        ops.addWidget(self.button('移除',self.remove_sources))
        ops.addWidget(self.button('清空',self.clear_sources));ops.addStretch(1)
        self.sources=QListWidget();self.sources.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        s.addWidget(self.sources,1);lay.addWidget(sources,1)
        group=QGroupBox('專案設定');form=QGridLayout(group)
        form.addWidget(QLabel('輸出資料夾'),0,0)
        self.out_edit=QLineEdit(store.DEFAULT_OUT);form.addWidget(self.out_edit,0,1)
        form.addWidget(self.button('選擇…',self.choose_output),0,2)
        self.out_edit.editingFinished.connect(self.workspace_changed)
        form.addWidget(QLabel('AI 複審模型'),1,0)
        self.model_edit=QLineEdit(os.environ.get('AI_VLOG_DEFAULT_MODEL','gemma3:12b'));form.addWidget(self.model_edit,1,1)
        form.addWidget(QLabel('AI 分析策略'),2,0)
        self.mode_box=QComboBox();self.mode_box.addItem('平衡 · 4B 初選＋12B 複審','balanced')
        self.mode_box.addItem('單模型分析','quality');form.addWidget(self.mode_box,2,1)
        if os.environ.get('AI_VLOG_DEFAULT_MODE')=='quality':self.mode_box.setCurrentIndex(1)
        form.addWidget(QLabel('執行配置'),3,0)
        self.hardware_box=QComboBox();self.hardware_box.addItem('CPU 省時','cpu');self.hardware_box.addItem('標準','standard')
        form.addWidget(self.hardware_box,3,1)
        self.temporal_check=QCheckBox('12B 三影格複審');self.temporal_check.setChecked(True)
        form.addWidget(self.temporal_check,4,1)
        self.test_check=QCheckBox('測試模式（最多 20 檔案、50 個候選）');form.addWidget(self.test_check,5,1)
        lay.addWidget(group)
        actions=QHBoxLayout();lay.addLayout(actions)
        self.scan_btn=self.button('開始掃描與 AI 分析',self.start_scan,True);actions.addWidget(self.scan_btn)
        actions.addWidget(self.button('沿用既有分析',self.reuse_results))
        actions.addWidget(self.button('檢查環境',self.check_env));actions.addStretch(1)
        self.stop_scan=self.button('停止任務',self.stop);actions.addWidget(self.stop_scan)
        self.stop_scan.setEnabled(False)

    def build_edit(self):
        lay=QVBoxLayout(self.edit_page);lay.setContentsMargins(0,0,0,0)
        lay.addWidget(self.section_header('剪輯工作台','第二步：AI 先建立片單；你再挑片、拖曳調整順序，雙擊鏡頭進行 In / Out 裁切。'))
        top=QHBoxLayout();lay.addLayout(top)
        self.summary=QLabel('尚未載入分析結果');self.summary.setObjectName('muted');top.addWidget(self.summary,1)
        top.addWidget(self.button('開啟既有工作區',self.open_existing_workspace))
        top.addWidget(self.button('重新整理',lambda:self.load_candidates(reset=True)))
        splitter=QSplitter(Qt.Orientation.Horizontal);lay.addWidget(splitter,1)
        left=QWidget();ll=QVBoxLayout(left);ll.setContentsMargins(4,0,4,0)
        ll.addWidget(QLabel('AI 候選素材'))
        filters=QHBoxLayout();ll.addLayout(filters)
        self.search=QLineEdit();self.search.setPlaceholderText('搜尋檔名或 AI 描述…')
        self.search.returnPressed.connect(lambda:self.load_candidates(reset=True));filters.addWidget(self.search,1)
        self.filter_box=QComboBox();self.filter_box.addItems(store.FILTERS)
        self.filter_box.currentIndexChanged.connect(lambda *_:self.load_candidates(reset=True));filters.addWidget(self.filter_box)
        filters.addWidget(self.button('搜尋',lambda:self.load_candidates(reset=True)))
        self.candidates=QTableWidget(0,5)
        self.candidates.setHorizontalHeaderLabels(['片單','狀態','分數','原片位置','來源檔名'])
        self.setup_table(self.candidates,4)
        self.candidates.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.candidates.itemSelectionChanged.connect(self.candidate_selected)
        self.candidates.itemDoubleClicked.connect(lambda *_:self.open_trim())
        ll.addWidget(self.candidates,1)
        leftops=QHBoxLayout();ll.addLayout(leftops)
        leftops.addWidget(self.button('＋ 加入片單',self.add_selection,True))
        leftops.addWidget(self.button('▶ 預覽／裁切',self.open_trim))
        paging=QHBoxLayout();ll.addLayout(paging)
        paging.addWidget(self.button('← 上頁',lambda:self.page_by(-1)))
        self.page_label=QLabel('第 1 頁');self.page_label.setObjectName('muted');paging.addWidget(self.page_label,1)
        paging.addWidget(self.button('下頁 →',lambda:self.page_by(1)))
        splitter.addWidget(left)

        right=QWidget();rl=QVBoxLayout(right);rl.setContentsMargins(4,0,4,0)
        rl.addWidget(QLabel('本次輸出片單 · 拖曳可排序'))
        self.plan=ReorderTable();self.plan.setColumnCount(4)
        self.plan.setHorizontalHeaderLabels(['#','分數','片長','已選鏡頭'])
        self.setup_table(self.plan,3)
        self.plan.itemSelectionChanged.connect(self.plan_selected)
        self.plan.itemDoubleClicked.connect(lambda *_:self.open_trim())
        self.plan.order_changed.connect(self.drag_reorder)
        rl.addWidget(self.plan,1)
        planops=QHBoxLayout();rl.addLayout(planops)
        planops.addWidget(self.button('移除',self.remove_plan))
        planops.addWidget(self.button('↑',lambda:self.move_plan(-1)))
        planops.addWidget(self.button('↓',lambda:self.move_plan(1)))
        planops.addWidget(self.button('AI 建議預覽',self.auto_plan))
        self.plan_status=QLabel('尚無片單');self.plan_status.setObjectName('muted');self.plan_status.setWordWrap(True)
        rl.addWidget(self.plan_status)
        splitter.addWidget(right);splitter.setSizes([690,480])

        timeline_title=QHBoxLayout();lay.addLayout(timeline_title)
        timeline_title.addWidget(QLabel('剪輯時間軸 · 點擊選取片段'));timeline_title.addStretch(1)
        timeline_title.addWidget(self.button('↶ 復原 Ctrl+Z',self.undo))
        timeline_title.addWidget(self.button('↷ 重做 Ctrl+Y',self.redo))
        self.timeline_scene=QGraphicsScene(self)
        self.timeline=QGraphicsView(self.timeline_scene);self.timeline.setFixedHeight(112)
        self.timeline_scene.selectionChanged.connect(self.timeline_selected)
        lay.addWidget(self.timeline)
        bottom=QSplitter(Qt.Orientation.Horizontal);lay.addWidget(bottom)
        preview=QWidget();pv=QHBoxLayout(preview);pv.setContentsMargins(3,0,3,0)
        self.thumb=QLabel('選取鏡頭\n預覽縮圖');self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setFixedSize(220,126);self.thumb.setStyleSheet('background:#0a1019;border:1px solid #293647;border-radius:6px;')
        pv.addWidget(self.thumb)
        self.details=QLabel('選取候選或片單鏡頭以查看 AI 說明。')
        self.details.setObjectName('muted');self.details.setWordWrap(True);pv.addWidget(self.details,1)
        bottom.addWidget(preview)
        output=QWidget();ov=QVBoxLayout(output);ov.setContentsMargins(4,0,4,0)
        row=QHBoxLayout();ov.addLayout(row)
        row.addWidget(QLabel('目標片長（秒）'))
        self.seconds_edit=QComboBox();self.seconds_edit.setEditable(True)
        self.seconds_edit.addItems(['30','60','180','300','600']);self.seconds_edit.setCurrentText('180')
        self.seconds_edit.lineEdit().editingFinished.connect(self.refresh_plan)
        self.seconds_edit.lineEdit().editingFinished.connect(self.save_settings)
        row.addWidget(self.seconds_edit)
        row.addWidget(QLabel('推薦最低分'))
        self.min_score_box=QComboBox();self.min_score_box.setEditable(True);self.min_score_box.addItems(['20','30','40','50','60','70']);self.min_score_box.setCurrentText('40')
        row.addWidget(self.min_score_box)
        music=QHBoxLayout();ov.addLayout(music)
        music.addWidget(QLabel('背景音樂'))
        self.music_edit=QLineEdit();music.addWidget(self.music_edit,1)
        music.addWidget(self.button('選擇',self.choose_music))
        flags=QHBoxLayout();ov.addLayout(flags)
        self.dissolve=QCheckBox('交叉淡化');self.dissolve.setChecked(True)
        self.ambient=QCheckBox('保留現場聲');self.ambient.setChecked(True)
        self.beat=QCheckBox('配樂節奏對齊');self.beat.setChecked(True)
        for item in (self.dissolve,self.ambient,self.beat):flags.addWidget(item)
        ov.addStretch(1)
        output_actions=QHBoxLayout();ov.addLayout(output_actions)
        self.render_btn=self.button('輸出 MP4',self.start_render,True);output_actions.addWidget(self.render_btn)
        output_actions.addWidget(self.button('開啟輸出目錄',self.open_output))
        bottom.addWidget(output);bottom.setSizes([625,520])

    @staticmethod
    def setup_table(table, stretch_col):
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        for i in range(table.columnCount()):
            table.horizontalHeader().setSectionResizeMode(i,QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(stretch_col,QHeaderView.ResizeMode.Stretch)

    def build_log(self):
        lay=QVBoxLayout(self.log_page);lay.setContentsMargins(0,0,0,0)
        lay.addWidget(self.section_header('執行紀錄','分析進度、FFmpeg 輸出結果與錯誤訊息會顯示在這裡。'))
        bar=QHBoxLayout();lay.addLayout(bar)
        bar.addWidget(self.button('複製紀錄',lambda:QApplication.clipboard().setText(self.logs.toPlainText())))
        bar.addWidget(self.button('檢查環境',self.check_env));bar.addStretch(1)
        self.stop_log=self.button('停止任務',self.stop);bar.addWidget(self.stop_log);self.stop_log.setEnabled(False)
        self.logs=QTextEdit();self.logs.setReadOnly(True)
        font=QFont('Consolas',10);self.logs.setFont(font)
        lay.addWidget(self.logs,1)

    def notice(self,title,message):QMessageBox.information(self,title,message)
    def warn(self,title,message):QMessageBox.warning(self,title,message)
    def error(self,title,message):QMessageBox.critical(self,title,message)

    def log(self,line):
        line=str(line).rstrip()
        self.logs.append(line)
        if self.logs.document().blockCount()>1500:
            cursor=self.logs.textCursor();cursor.movePosition(cursor.MoveOperation.Start)
            for _ in range(250):cursor.select(cursor.SelectionType.BlockUnderCursor);cursor.removeSelectedText();cursor.deleteChar()
        match=re.search(r'\[(FAST|REVIEW|V4\.3 CLIP|V4\.3 GROUP)\s+(\d+)/(\d+)\]',line)
        if match:
            n,total=int(match.group(2)),max(1,int(match.group(3)))
            self.progress.setValue(min(100,round(n*100/total)))
            self.progress_label.setText(f'{match.group(1)} {n}/{total}')
        eta=re.search(r'預估剩餘\s+([\d.]+)\s+分',line)
        if eta:self.progress_label.setText(self.progress_label.text()+f' · 約 {eta.group(1)} 分鐘')

    def add_inputs(self,paths):
        if self.running:return
        keys={os.path.normcase(os.path.abspath(p)) for p in self.inputs}
        for p in paths:
            p=os.path.abspath(p);ident=os.path.normcase(p)
            if ident not in keys:self.inputs.append(p);self.sources.addItem(p);keys.add(ident)
        self.override_workspace=None;self.workspace_changed()

    def add_files(self):
        paths,_=QFileDialog.getOpenFileNames(self,'選擇旅行影片與照片','',''+FILE_FILTER)
        if paths:self.add_inputs(paths)
    def add_folder(self):
        folder=QFileDialog.getExistingDirectory(self,'選擇素材資料夾')
        if folder:self.add_inputs([folder])
    def remove_sources(self):
        if self.running:return
        indexes=sorted({i.row() for i in self.sources.selectedIndexes()},reverse=True)
        for i in indexes:self.sources.takeItem(i);self.inputs.pop(i)
        self.override_workspace=None;self.workspace_changed()
    def clear_sources(self):
        if self.running:return
        self.sources.clear();self.inputs.clear();self.override_workspace=None;self.workspace_changed()
    def choose_output(self):
        if self.running:return
        folder=QFileDialog.getExistingDirectory(self,'選擇工作與輸出資料夾',self.out_edit.text())
        if folder:self.out_edit.setText(folder);self.override_workspace=None;self.workspace_changed()
    def choose_music(self):
        path,_=QFileDialog.getOpenFileName(self,'選擇音樂','','音樂 (*.mp3 *.wav *.m4a *.flac *.aac);;全部 (*)')
        if path:self.music_edit.setText(path);self.save_settings()

    def save_settings(self):
        data={'inputs':self.inputs,'output':self.out_edit.text(),'music':self.music_edit.text(),
              'model':self.model_edit.text(),'seconds':self.seconds_edit.currentText(),
              'min_score':self.min_score_box.currentText(),'test':self.test_check.isChecked(),
              'temporal':self.temporal_check.isChecked(),'analysis_mode':self.mode_box.currentData(),
              'hardware_profile':self.hardware_box.currentData(),'dissolve':self.dissolve.isChecked(),
              'ambient':self.ambient.isChecked(),'beat_sync':self.beat.isChecked()}
        try:store.save_json_atomic(store.CONFIG,data)
        except OSError:pass

    def load_settings(self):
        try:
            data=json.loads(store.CONFIG.read_text(encoding='utf-8'))
            if not isinstance(data,dict):raise ValueError('設定檔格式有誤')
        except (OSError,ValueError,TypeError):data={}
        paths=data.get('inputs',[])
        if isinstance(paths,list):
            for path in paths:
                if isinstance(path,str) and path and path not in self.inputs:
                    self.inputs.append(path);self.sources.addItem(path)
        for key,widget in [('output',self.out_edit),('music',self.music_edit),('model',self.model_edit)]:
            if isinstance(data.get(key),str):widget.setText(data[key])
        for key,box in [('seconds',self.seconds_edit),('min_score',self.min_score_box)]:
            if key in data:box.setCurrentText(str(data[key]))
        for key,widget in [('temporal',self.temporal_check),('dissolve',self.dissolve),
                           ('ambient',self.ambient),('beat_sync',self.beat)]:
            if isinstance(data.get(key),bool):widget.setChecked(data[key])
        for key,combo in [('analysis_mode',self.mode_box),('hardware_profile',self.hardware_box)]:
            if data.get(key) in ('balanced','quality','cpu','standard'):
                ix=combo.findData(data[key]);combo.setCurrentIndex(max(ix,0))
        # Test mode deliberately resets on each launch.

    def workspace_changed(self):
        if self.running:return
        previous=self.workspace_dir
        path=self.out_edit.text().strip()
        self.workspace_dir=(self.override_workspace if self.override_workspace else
                           (store.workspace(self.inputs,path) if self.inputs and path else None))
        self.workspace_name.setText(self.workspace_dir.name if self.workspace_dir else '尚未選擇素材')
        if previous!=self.workspace_dir:
            self.selected_ids=[];self.manual_trims={};self.history.clear();self.redo_stack.clear()
            self.page=0;self.load_candidates(reset=True);self.load_selection_or_recommend()
        self.save_settings()

    def count(self):
        if not self.workspace_dir:return (0,0)
        file=self.workspace_dir/'index.sqlite'
        if not file.is_file():return (0,0)
        try:
            with closing(store.readonly_db(file)) as db:
                return (db.execute('SELECT COUNT(*) FROM candidates').fetchone()[0],
                        db.execute('SELECT COUNT(*) FROM candidates WHERE v2=1').fetchone()[0])
        except sqlite3.Error:return (0,0)

    def load_candidates(self,reset=False):
        if reset:self.page=0
        self.page_rows={};self.candidates.blockSignals(True);self.candidates.setRowCount(0)
        if not self.workspace_dir:
            self.summary.setText('尚未指定來源素材或工作區。');self.page_label.setText('');self.candidates.blockSignals(False);return
        try:total,ready,n,rows,stats=store.candidates_page(self.workspace_dir/'index.sqlite',self.page,self.search.text().strip(),self.filter_box.currentText())
        except sqlite3.Error as exc:
            self.summary.setText('無法讀取候選資料：'+str(exc)+'。舊版 SQLite 請先用 CLI 升級。')
            self.candidates.blockSignals(False);return
        if n and self.page*store.PAGE_SIZE>=n:
            self.candidates.blockSignals(False);self.page=max(0,(n-1)//store.PAGE_SIZE)
            return self.load_candidates()
        self.summary.setText(f'已索引 {stats["media"]} 個素材 · 候選 {total} · AI 完成 {ready} · 跳過 {stats["skipped"]} · 失敗 {stats["failed"]}')
        self.page_label.setText(f'{self.page+1}/{max(1,(n+store.PAGE_SIZE-1)//store.PAGE_SIZE)} 頁 · {n} 筆')
        for r in rows:
            key=r['id'];self.page_rows[key]=r
            row=self.candidates.rowCount();self.candidates.insertRow(row)
            values=['✓' if key in self.selected_ids else '',r['display_status'],
                    '—' if r['score'] is None else f'{r["score"]:.0f}',
                    (f'{r["position"]:.1f}s' if r['kind']=='video' else '照片'),Path(r['path']).name]
            for col,value in enumerate(values):
                cell=QTableWidgetItem(str(value));cell.setData(Qt.ItemDataRole.UserRole,key)
                if col in (0,2,3):cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.candidates.setItem(row,col,cell)
        self.candidates.blockSignals(False)

    def open_existing_workspace(self):
        if self.running:return
        folder=QFileDialog.getExistingDirectory(self,'選擇含 index.sqlite 的工作區')
        if not folder:return
        chosen=Path(folder)
        if not (chosen/'index.sqlite').is_file():return self.warn('找不到工作區','所選資料夾沒有 index.sqlite')
        self.override_workspace=chosen;self.workspace_changed()
        self.load_candidates(reset=True);self.load_selection_or_recommend();self.nav.setCurrentRow(1)

    def page_by(self,delta):
        self.page=max(0,self.page+delta);self.load_candidates()
    def selection_path(self):return self.workspace_dir/store.SELECTION_FILE

    def load_selection_or_recommend(self):
        if not self.workspace_dir:return
        path=self.selection_path()
        if path.is_file():
            try:
                self.selected_ids,self.manual_trims=store.load_selection(path)
                self.refresh_plan();return
            except (OSError,ValueError,TypeError) as exc:self.log('選片記錄無法讀取：'+str(exc))
        self.recommend(quiet=True)

    def recommend(self,quiet=False):
        if not self.workspace_dir or not (self.workspace_dir/'index.sqlite').is_file():return False
        try:
            import vlog_maker as core
            with closing(store.readonly_db(self.workspace_dir/'index.sqlite')) as db:
                excluded_ids=set();excluded_paths=set()
                old=self.workspace_dir/'ui_review_v44.json'
                if old.is_file():
                    review=json.loads(old.read_text(encoding='utf-8'))
                    if isinstance(review,dict):
                        excluded_ids=set(review.get('excluded_ids',[]));excluded_paths=set(review.get('excluded_paths',[]))
                picked=core.choose(db,self.get_length(),5.,int(self.min_score_box.currentText()),excluded_ids,excluded_paths)
            if self.selected_ids:
                preview=self.workspace_dir/'ai_recommendation_preview_v16.json'
                store.save_json_atomic(preview,{'version':'1.6','plan':picked,
                    'note':'推薦預覽；人工片單、順序與裁切保持原樣。'})
                if not quiet:self.notice('AI 建議預覽',f'建議已儲存至 {preview}。既有片單保持原樣，可從素材列表手動加入。')
                return bool(picked)
            self.selected_ids=[x['candidate_id'] for x in picked]
            self.persist_selection();self.refresh_plan()
            return bool(picked)
        except (OSError,ValueError,TypeError,sqlite3.Error) as exc:
            if not quiet:self.error('AI 推薦失敗',str(exc))
            return False

    def get_length(self):
        try:
            n=int(self.seconds_edit.currentText())
            if not 1<=n<=3600:raise ValueError()
            return min(n,30) if self.test_check.isChecked() else n
        except ValueError:raise ValueError('目標片長必須是 1～3600 秒。')

    def persist_selection(self):
        if not self.workspace_dir:return
        store.save_json_atomic(self.selection_path(),{
            'version':'1.4', 'candidate_ids':self.selected_ids,
            'trims':{k:v for k,v in self.manual_trims.items() if k in self.selected_ids}})
        self.save_settings()

    def snapshot(self):
        self.history.append((list(self.selected_ids),{k:dict(v) for k,v in self.manual_trims.items()}))
        if len(self.history)>60:self.history.pop(0)
        self.redo_stack.clear()

    def _restore(self,state):
        self.selected_ids=list(state[0]);self.manual_trims={k:dict(v) for k,v in state[1].items()}
        self.persist_selection();self.refresh_plan();self.load_candidates()

    def undo(self):
        if self.running or not self.history:return
        self.redo_stack.append((list(self.selected_ids),{k:dict(v) for k,v in self.manual_trims.items()}))
        self._restore(self.history.pop())

    def redo(self):
        if self.running or not self.redo_stack:return
        self.history.append((list(self.selected_ids),{k:dict(v) for k,v in self.manual_trims.items()}))
        self._restore(self.redo_stack.pop())

    def prune(self):
        if not self.workspace_dir or self.running or not self.selected_ids:return
        try:
            ids,trims,warnings=store.prune_selection(self.workspace_dir/'index.sqlite',self.selected_ids,self.manual_trims)
        except sqlite3.Error as exc:
            self.plan_status.setText('片單核對失敗：'+str(exc));return
        if warnings:
            backup=self.selection_path()
            if backup.is_file():
                try:shutil.copy2(backup,backup.with_name(backup.name+'.before_prune.bak'))
                except OSError as exc:self.log('[WARN] 片單備份失敗：'+str(exc))
            self.selected_ids=ids;self.manual_trims=trims
            try:self.persist_selection()
            except OSError as exc:self.log('[WARN] 片單無法保存：'+str(exc))
            for warning in warnings:self.log(warning)

    def refresh_plan(self):
        self.plan_rows={};self.plan.blockSignals(True);self.plan.setRowCount(0)
        if not self.workspace_dir:
            self.plan.blockSignals(False);self.draw_timeline([]);return
        self.prune()
        if not self.selected_ids:
            self.plan_status.setText('片單是空的。選取候選片段並點「加入片單」。')
            self.plan.blockSignals(False);self.draw_timeline([]);return
        try:
            import vlog_maker as core
            with closing(store.readonly_db(self.workspace_dir/'index.sqlite')) as db:
                plan=core.choose_selected(db,self.selected_ids,self.get_length(),manual_trims=self.manual_trims)
        except (ValueError,sqlite3.Error,OSError) as exc:
            self.plan_status.setText('片單無法建立：'+str(exc));self.plan.blockSignals(False);return
        for i,part in enumerate(plan):
            key=part['candidate_id'];self.plan_rows[key]=part
            row=self.plan.rowCount();self.plan.insertRow(row)
            values=[str(i+1),f'{float(part.get("score") or 0):.0f}',
                    f'{part["seconds"]:.1f}s'+(' ✂' if part.get('trim_locked') else ''),Path(part['path']).name]
            for col,value in enumerate(values):
                cell=QTableWidgetItem(value);cell.setData(Qt.ItemDataRole.UserRole,key)
                if col in (0,1,2):cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.plan.setItem(row,col,cell)
        seconds=sum(x['seconds'] for x in plan)
        locked=sum(bool(x.get('trim_locked')) for x in plan)
        self.plan_status.setText(f'{len(plan)} 個鏡頭 · 素材合計 {seconds:.1f} 秒 · 鎖定 {locked} 段；交叉淡化會縮短成片')
        self.plan.blockSignals(False);self.draw_timeline(plan)
        for i in range(self.candidates.rowCount()):
            key=self.candidates.item(i,0).data(Qt.ItemDataRole.UserRole)
            self.candidates.item(i,0).setText('✓' if key in self.selected_ids else '')

    def draw_timeline(self,plan):
        self.timeline_scene.blockSignals(True);self.timeline_scene.clear()
        if not plan:
            self.timeline_scene.addText('片單是空的。先從候選素材加入鏡頭。')
            self.timeline_scene.setSceneRect(0,0,550,72)
            self.timeline_scene.blockSignals(False);return
        total=sum(max(0.2,float(x['seconds'])) for x in plan)
        scale=max(7., min(25., 850/max(total,1)))
        x=12
        for i,clip in enumerate(plan):
            width=max(38,clip['seconds']*scale)
            fill=QColor('#0f766e' if clip.get('trim_locked') else ('#2563eb' if i==0 else '#6844aa' if i==len(plan)-1 else '#345c77'))
            block=QGraphicsRectItem(x,8,width,58)
            block.setBrush(QBrush(fill));block.setPen(QPen(QColor('#10151e'),1))
            block.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable,True)
            block.setData(0,clip['candidate_id']);self.timeline_scene.addItem(block)
            label=QGraphicsSimpleTextItem(f'{i+1} · {Path(clip["path"]).stem[:13]}',block)
            label.setBrush(QBrush(QColor('#ffffff')));label.setPos(x+6,14)
            time=QGraphicsSimpleTextItem(f'{clip["seconds"]:.1f}s'+(' ✂' if clip.get('trim_locked') else ''),block)
            time.setBrush(QBrush(QColor('#d1fae5')));time.setPos(x+6,37)
            # child text uses scene coordinates because parent rect is at (0,0)
            x+=width+3
        self.timeline_scene.setSceneRect(0,0,max(550,x+15),76)
        self.timeline_scene.blockSignals(False)

    def timeline_selected(self):
        selected=self.timeline_scene.selectedItems()
        if not selected:return
        key=selected[0].data(0)
        if key in self.selected_ids:
            self.last_source='plan'
            self.plan.blockSignals(True)
            for i in range(self.plan.rowCount()):
                if self.plan.item(i,0).data(Qt.ItemDataRole.UserRole)==key:
                    self.plan.selectRow(i);self.plan.scrollToItem(self.plan.item(i,0));break
            self.plan.blockSignals(False)
            self.show_preview(self.plan_rows.get(key))

    def selected_candidate_ids(self):
        return [self.candidates.item(i,0).data(Qt.ItemDataRole.UserRole) for i in sorted({x.row() for x in self.candidates.selectedIndexes()})]
    def current_key(self):
        if self.last_source=='candidate':
            vals=self.selected_candidate_ids()
            if vals:return vals[0],self.page_rows.get(vals[0])
        row=self.plan.currentRow()
        if row>=0 and self.plan.item(row,0):
            key=self.plan.item(row,0).data(Qt.ItemDataRole.UserRole)
            return key,self.plan_rows.get(key)
        vals=self.selected_candidate_ids()
        if vals:return vals[0],self.page_rows.get(vals[0])
        return None,None

    def candidate_selected(self):
        keys=self.selected_candidate_ids()
        if not keys:return
        self.last_source='candidate';self.plan.blockSignals(True);self.plan.clearSelection();self.plan.blockSignals(False)
        self.show_preview(self.page_rows.get(keys[0]))
    def plan_selected(self):
        row=self.plan.currentRow()
        if row<0 or not self.plan.item(row,0):return
        self.last_source='plan';self.candidates.blockSignals(True);self.candidates.clearSelection();self.candidates.blockSignals(False)
        key=self.plan.item(row,0).data(Qt.ItemDataRole.UserRole)
        self.show_preview(self.plan_rows.get(key))

    def add_selection(self):
        if self.running:return
        ids=[key for key in self.selected_candidate_ids() if key not in self.selected_ids]
        if not ids:return
        self.snapshot();self.selected_ids.extend(ids);self.persist_selection();self.refresh_plan()
    def remove_plan(self):
        if self.running:return
        row=self.plan.currentRow()
        if row<0 or row>=len(self.selected_ids):return
        self.snapshot();key=self.selected_ids.pop(row);self.manual_trims.pop(key,None)
        self.persist_selection();self.refresh_plan()
    def move_plan(self,delta):
        if self.running:return
        row=self.plan.currentRow();destination=row+delta
        self.reorder(row,destination)
    def drag_reorder(self,src,dest):self.reorder(src,dest)
    def reorder(self,src,dest):
        if self.running or not 0<=src<len(self.selected_ids) or not 0<=dest<len(self.selected_ids) or src==dest:return
        self.snapshot();item=self.selected_ids.pop(src);self.selected_ids.insert(dest,item)
        self.persist_selection();self.refresh_plan();self.plan.selectRow(dest)

    def auto_plan(self):
        if self.running:return
        if not self.recommend():self.notice('目前沒有推薦','請先執行 AI 分析，或手動選擇未評分的候選。')

    def show_preview(self,item):
        if not item or not self.workspace_dir:return
        name=Path(item['path']).name
        position=float(item.get('candidate_position',item.get('position',0)))
        score=('%.0f' % float(item['score'])) if item.get('score') is not None else '未評分'
        desc=item.get('description') or '尚無 AI 評語'
        self.details.setText(f'{name}\n位置 {position:.2f}s · AI {score} 分\n{desc[:300]}')
        self.thumb_serial+=1;serial=self.thumb_serial
        self.thumb.setText('正在載入縮圖…');self.thumb.setPixmap(QPixmap())
        key=item.get('candidate_id',item.get('id'))
        folder=self.workspace_dir/'ui_thumbnails_v441';folder.mkdir(parents=True,exist_ok=True)
        dest=folder/(key+'.png')
        old=self.workspace_dir/'thumbnails_v2'/(key+'.jpg')
        source=old if old.is_file() else Path(item['path'])
        def worker():
            temp=None
            try:
                if not dest.is_file():
                    import vlog_maker
                    temp=folder/f'{key}.{serial}.partial.png'
                    cmd=[vlog_maker.exe('ffmpeg'),'-nostdin','-v','error','-y']
                    if source==Path(item['path']) and item['kind']=='video':cmd+=['-ss',str(position)]
                    cmd+=['-i',str(source),'-frames:v','1','-vf',
                          'scale=360:203:force_original_aspect_ratio=decrease,pad=360:203:(ow-iw)/2:(oh-ih)/2',str(temp)]
                    flags=getattr(subprocess,'CREATE_NO_WINDOW',0) if os.name=='nt' else 0
                    subprocess.run(cmd,check=True,stderr=subprocess.PIPE,stdout=subprocess.DEVNULL,
                                   stdin=subprocess.DEVNULL,timeout=45,creationflags=flags)
                    temp.replace(dest)
                self.bus.thumbnail.emit(serial,str(dest),'')
            except (OSError,subprocess.SubprocessError) as exc:self.bus.thumbnail.emit(serial,'',str(exc)[:100])
            finally:
                if temp is not None:temp.unlink(missing_ok=True)
        threading.Thread(target=worker,daemon=True).start()

    def thumbnail_arrived(self,serial,path,error):
        if serial!=self.thumb_serial:return
        if not path:return self.thumb.setText('縮圖無法讀取：'+error)
        pix=QPixmap(path)
        if pix.isNull():return self.thumb.setText('縮圖解碼失敗')
        self.thumb.setPixmap(pix.scaled(self.thumb.size(),Qt.AspectRatioMode.KeepAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation))

    def open_trim(self):
        if self.running:return self.notice('正在執行任務','請等目前掃描或輸出完成後再修改片單。')
        key,item=self.current_key()
        if not item:return self.notice('尚未選取','請先選擇候選素材或片單中的影片。')
        if item.get('kind')!='video':return self.notice('照片素材','In／Out 裁切只適用影片。照片仍由 AI 分配顯示時長。')
        source=Path(item['path'])
        if not source.is_file():return self.error('找不到來源影片',str(source))
        duration=float(item.get('source_duration') or item.get('duration') or 0)
        if duration<=0:return self.error('影片長度不明','請重新掃描來源影片。')
        saved=self.manual_trims.get(key)
        if saved:start,end=float(saved['start']),float(saved['end'])
        elif key in self.plan_rows:
            part=self.plan_rows[key];start=float(part['start']);end=start+float(part['seconds'])
        else:
            center=float(item.get('position') or 0);span=min(5.,duration)
            start=max(0.,min(duration-span,center-span/2));end=start+span
        from qt_video_preview import QtTrimDialog
        def on_save(start,end):
            if self.running:return self.warn('不能修改','任務執行中不可儲存裁切。') or False
            self.snapshot()
            if key not in self.selected_ids:self.selected_ids.append(key)
            self.manual_trims[key]={'start':round(start,3),'end':round(end,3)}
            self.persist_selection();self.refresh_plan();self.load_candidates()
            self.log(f'[TRIM] {source.name} {start:.3f}–{end:.3f}s')
            return True
        dialog=QtTrimDialog(self,source,duration,start,end,on_save)
        self.current_dialog=dialog
        dialog.exec()
        self.current_dialog=None

    def validate_workspace(self,scan=False):
        if self.running:return False
        if not self.inputs and (scan or self.override_workspace is None):
            self.error('缺少素材','請加入素材或選擇既有工作區。');return False
        if scan:
            missing=[p for p in self.inputs if not Path(p).exists()]
            if missing:self.error('來源檔不存在','\n'.join(missing[:6]));return False
        self.workspace_changed()
        if not self.workspace_dir:return False
        try:self.get_length();int(self.min_score_box.currentText())
        except ValueError as exc:self.error('設定不正確',str(exc));return False
        if scan and not self.model_edit.text().strip():self.error('缺少 AI 模型','請輸入模型名稱。');return False
        music=self.music_edit.text().strip()
        if music and not Path(music).is_file():self.error('找不到配樂',music);return False
        self.workspace_dir.mkdir(parents=True,exist_ok=True);self.save_settings();return True

    def start_scan(self):
        self.override_workspace=None
        if not self.validate_workspace(scan=True):return
        scan=['scan']+sum((['--input',p] for p in self.inputs),[])
        if self.test_check.isChecked():scan+=['--scan-limit','20']
        analyze=['analyze','--model',self.model_edit.text().strip(),
                 '--analysis-mode',self.mode_box.currentData(),
                 '--hardware-profile',self.hardware_box.currentData(),
                 '--fast-model','gemma3:4b','--ai-timeout','120']
        if not self.temporal_check.isChecked():analyze+=['--single-frame']
        if self.test_check.isChecked():analyze+=['--analyze-limit','50']
        self.launch([scan,analyze],'scan')

    def reuse_results(self):
        if self.running:return
        self.workspace_changed();self.load_candidates(reset=True)
        self.load_selection_or_recommend();self.nav.setCurrentRow(1)
        if not self.count()[1]:self.notice('尚未完成分析','目前沒有已完成 AI 評分的鏡頭，但仍可手動選取候選素材。')

    def start_render(self):
        if not self.validate_workspace():return
        if not self.selected_ids:return self.warn('還沒有選片','請先把候選素材加入片單。')
        try:
            import vlog_maker as core
            with closing(store.readonly_db(self.workspace_dir/'index.sqlite')) as db:
                core.choose_selected(db,self.selected_ids,self.get_length(),manual_trims=self.manual_trims)
        except (OSError,sqlite3.Error,ValueError) as exc:return self.error('片單無法輸出',str(exc))
        final=self.workspace_dir/'Travel_Vlog_Final_V43.mp4'
        if final.is_file():
            if QMessageBox.question(self,'覆蓋既有作品','這次輸出將覆蓋：\n'+str(final)+'\n來源素材不會修改。')!=QMessageBox.StandardButton.Yes:return
        self.persist_selection()
        render=['render','--selection-file',str(self.selection_path()),'--seconds',str(self.get_length()),
                '--min-score',str(int(self.min_score_box.currentText()))]
        if self.music_edit.text().strip():render+=['--music',self.music_edit.text().strip()]
        if not self.dissolve.isChecked():render+=['--no-dissolve']
        if not self.ambient.isChecked():render+=['--no-ambient']
        if not self.beat.isChecked():render+=['--no-beat-sync']
        self.launch([render],'render')

    def launch(self,tasks,action):
        if self.current_dialog is not None:self.current_dialog.reject();self.current_dialog=None
        self.running=True;self.cancel_requested=False
        self.progress.setValue(0);self.progress_label.setText('準備中…')
        self.scan_btn.setEnabled(False);self.render_btn.setEnabled(False)
        self.stop_scan.setEnabled(True);self.stop_log.setEnabled(True)
        self.status.setText('● 執行中');self.nav.setCurrentRow(2)
        self.log('==== '+('正在掃描與分析' if action=='scan' else '正在輸出 MP4')+' ====')
        out=str(self.workspace_dir)
        threading.Thread(target=self.worker,args=(tasks,action,out),daemon=True).start()

    def worker(self,tasks,action,out):
        try:
            for args in tasks:
                if self.cancel_requested:break
                frozen=getattr(sys,'frozen',False)
                command=([sys.executable,'--cli'] if frozen else
                         [sys.executable,'-u',str(SOURCE/'vlog_maker.py')])
                command += [args[0],'--out',out] + args[1:]
                log_path=None
                if frozen:
                    fd,filename=tempfile.mkstemp(prefix='vlog_cli_',suffix='.log',dir=out)
                    os.close(fd);log_path=Path(filename)
                    command += ['--cli-log',str(log_path)]
                self.events.put(('stage',args[0]))
                env=os.environ.copy();env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
                flags=getattr(subprocess,'CREATE_NO_WINDOW',0) if os.name=='nt' else 0
                try:
                    process=subprocess.Popen(command,stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL if frozen else subprocess.PIPE,
                        stderr=subprocess.DEVNULL if frozen else subprocess.STDOUT,
                        text=not frozen,encoding=None if frozen else 'utf-8',
                        errors=None if frozen else 'replace',bufsize=1,
                        env=env,creationflags=flags)
                    self.process=process
                    if frozen:
                        # Stream log lines from the child even in a windowed EXE.
                        with log_path.open('r',encoding='utf-8',errors='replace') as stream:
                            fragment=''
                            while True:
                                chunk=stream.read()
                                if chunk:
                                    fragment+=chunk
                                    while '\n' in fragment:
                                        line,fragment=fragment.split('\n',1)
                                        self.events.put(('log',line.rstrip()))
                                if process.poll() is not None:
                                    extra=stream.read()
                                    if extra:fragment+=extra
                                    for line in fragment.splitlines():self.events.put(('log',line.rstrip()))
                                    break
                                time.sleep(0.12)
                    else:
                        for line in process.stdout:self.events.put(('log',line.rstrip()))
                    code=process.wait();self.process=None
                finally:
                    if log_path is not None:log_path.unlink(missing_ok=True)
                if self.cancel_requested:break
                if code:raise RuntimeError(f'{args[0]} 失敗（代碼 {code}），請查看執行紀錄。')
            self.events.put(('done',(action,self.cancel_requested)))
        except Exception as exc:self.events.put(('error',str(exc)))
        finally:self.process=None

    def stop(self):
        if not self.running:return
        self.cancel_requested=True
        process=self.process
        if process and process.poll() is None:
            try:
                if os.name=='nt':
                    subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],
                        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=8,
                        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                else:process.terminate()
            except (OSError,subprocess.SubprocessError):pass
        self.status.setText('● 正在停止…')

    def drain(self):
        for _ in range(150):
            try:kind,value=self.events.get_nowait()
            except queue.Empty:break
            if kind=='log':self.log(value)
            elif kind=='stage':
                self.progress.setValue(0)
                self.progress_label.setText({'scan':'掃描素材','analyze':'AI 分析','render':'FFmpeg 輸出'}.get(value,value))
                self.log('>>> '+value)
            elif kind=='env':self.notice('環境檢查',value)
            elif kind in ('done','error'):
                self.running=False
                self.scan_btn.setEnabled(True);self.render_btn.setEnabled(True)
                self.stop_scan.setEnabled(False);self.stop_log.setEnabled(False)
                if kind=='error':
                    self.status.setText('● 執行失敗');self.log('ERROR: '+value)
                    self.load_candidates(reset=True);self.load_selection_or_recommend()
                    self.error('執行失敗',value)
                else:
                    action,stopped=value
                    if stopped:self.status.setText('● 已停止');self.log('任務已停止')
                    else:
                        self.progress.setValue(100);self.status.setText('● 完成')
                        if action=='scan':
                            self.load_candidates(reset=True);self.load_selection_or_recommend()
                            self.nav.setCurrentRow(1)
                            total,ready=self.count()
                            self.notice('AI 分析完成',f'建立 {total} 段候選，其中 {ready} 段完成 AI 評分。')
                        else:self.notice('剪輯已輸出','已輸出至：\n'+str(self.workspace_dir/'Travel_Vlog_Final_V43.mp4'))

    def check_env(self):
        model=self.model_edit.text().strip();mode=self.mode_box.currentData()
        def work():
            results=[]
            for name in ('ffmpeg','ffprobe'):
                local=ROOT/'tools'/(name+'.exe' if os.name=='nt' else name)
                results.append(f'{name}：'+('內附' if local.is_file() else 'PATH 正常' if shutil.which(name) else '缺少'))
            try:
                with urlopen(os.environ.get('AI_VLOG_OLLAMA_URL','http://127.0.0.1:11434').rstrip('/')+'/api/tags',timeout=3) as response:
                    names={str(x.get('name','')).lower() for x in json.load(response).get('models',[])}
                results.append('Ollama：正常')
                for name in [model]+(['gemma3:4b'] if mode=='balanced' else []):
                    results.append(name+'：'+('已安裝' if name.lower() in names else '缺少模型'))
            except Exception:results.append('Ollama：無法連線')
            try:
                from vlc_loader import import_vlc
                import_vlc();results.append('VLC：正常')
            except Exception:results.append('VLC：請安裝 64 位元 VLC + python-vlc')
            self.events.put(('env','\n'.join(results)))
        threading.Thread(target=work,daemon=True).start()

    def open_output(self):
        if not self.workspace_dir or not self.workspace_dir.is_dir():return self.notice('尚未輸出','目前沒有輸出資料夾。')
        if os.name=='nt':os.startfile(str(self.workspace_dir))
        else:self.notice('輸出資料夾',str(self.workspace_dir))

    def closeEvent(self,event):
        if self.running:
            if QMessageBox.question(self,'背景任務執行中','停止背景任務並關閉程式？')!=QMessageBox.StandardButton.Yes:
                event.ignore();return
            self.stop()
        if self.current_dialog is not None:self.current_dialog.reject()
        self.save_settings();event.accept()


def main():
    app=QApplication.instance() or QApplication(sys.argv)
    app.setStyle('Fusion');app.setStyleSheet(STYLE)
    window=EditorWindow();window.show()
    return app.exec()

if __name__=='__main__':raise SystemExit(main())
