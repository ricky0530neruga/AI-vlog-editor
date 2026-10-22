"""V1.4 stability hotfix regression tests. Run: python -m unittest discover -s tests -v"""
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import vlog_gui
import vlog_maker
import video_preview


class FakeTree:
    def __init__(self, selection=()):self.selected=list(selection)
    def selection(self):return tuple(self.selected)
    def selection_remove(self,ids):self.selected=[x for x in self.selected if x not in ids]


class HotfixTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.work=self.root/'work';self.work.mkdir()

    def test_preview_from_left_uses_plan_row(self):
        source=self.root/'source.mp4';source.write_bytes(b'x')
        key='candidate-1'
        app=vlog_gui.Application.__new__(vlog_gui.Application)
        app.running=False;app.last_selection='available';app.trim_dialog=None
        app.available=FakeTree([key]);app.plan_tree=FakeTree()
        app.page_rows={key:dict(id=key,kind='video',path=str(source),duration=20.0,position=10.)}
        app.plan_rows={key:dict(candidate_id=key,kind='video',path=str(source),start=7.,seconds=3.,source_duration=20.)}
        app.manual_trims={};app.selected_ids=[key];app.root=None
        recorded=[]
        class Dummy:
            def __init__(self,*args,**kwargs):recorded.append((args,kwargs));self.window=SimpleNamespace(winfo_exists=lambda:True)
        with mock.patch.object(video_preview,'VideoTrimDialog',Dummy):
            app.open_trim_preview()
        self.assertEqual(len(recorded),1)
        self.assertEqual(recorded[0][0][3:5],(7.,10.))

    def test_trim_save_is_denied_while_rendering(self):
        source=self.root/'source.mp4';source.write_bytes(b'x')
        key='candidate-1'
        app=vlog_gui.Application.__new__(vlog_gui.Application)
        app.running=False;app.last_selection='available';app.trim_dialog=None
        app.available=FakeTree([key]);app.plan_tree=FakeTree()
        app.page_rows={key:dict(id=key,kind='video',path=str(source),duration=20.,position=10.)}
        app.plan_rows={};app.manual_trims={};app.selected_ids=[];app.root=None
        captured=[]
        class Dummy:
            def __init__(self,*args,**kwargs):captured.append(kwargs.get('on_save',args[5]));self.window=SimpleNamespace(winfo_exists=lambda:True)
        with mock.patch.object(video_preview,'VideoTrimDialog',Dummy):app.open_trim_preview()
        app.running=True
        with mock.patch.object(vlog_gui.messagebox,'showwarning') as warn:
            self.assertFalse(captured[0](2.,6.))
            warn.assert_called_once()
        self.assertEqual(app.selected_ids,[])
        self.assertEqual(app.manual_trims,{})

    def test_prune_selection_preserves_other_items_and_backup(self):
        good=self.root/'valid.mp4';good.write_bytes(b'x')
        other=self.root/'other.mp4';other.write_bytes(b'x')
        missing=self.root/'missing.mp4'
        with closing(vlog_maker.connect(self.work)) as db:
            for idx,file in enumerate((good,other,missing),1):
                db.execute('INSERT INTO media(path,kind,size,mtime,duration,width,height,error) VALUES(?,?,?,?,?,?,?,NULL)',
                           (str(file),'video',1,1.,8.,100,100))
                db.execute('INSERT INTO candidates(id,path,position) VALUES(?,?,?)',
                           (f'id{idx}',str(file),2.))
            db.commit()
        selection={'candidate_ids':['id1','id2','id3','gone'],
                   'trims':{'id1':{'start':1.,'end':3.},'id2':{'start':7.,'end':10.}}}
        (self.work/vlog_gui.SELECTION_FILE).write_text(json.dumps(selection),encoding='utf8')
        app=vlog_gui.Application.__new__(vlog_gui.Application)
        app.workspace_dir=self.work;app.running=False
        app.selected_ids=list(selection['candidate_ids']);app.manual_trims=dict(selection['trims'])
        logs=[];app.log_line=logs.append;app.save_settings=lambda:None
        app.plan_status=SimpleNamespace(config=lambda **kw:None)
        app.prune_selection()
        self.assertEqual(app.selected_ids,['id1','id2'])
        self.assertEqual(app.manual_trims,{'id1':{'start':1.,'end':3.}})
        self.assertTrue((self.work/(vlog_gui.SELECTION_FILE+'.before_prune.bak')).exists())
        self.assertTrue(any('[PRUNE]' in line for line in logs))
        saved=json.loads((self.work/vlog_gui.SELECTION_FILE).read_text(encoding='utf8'))
        self.assertEqual(saved['candidate_ids'],['id1','id2'])

    def test_scan_invalidates_old_thumbnail_caches(self):
        image=self.root/'photo.jpg';image.write_bytes(b'old photo')
        with closing(vlog_maker.connect(self.work)) as db:
            vlog_maker.scan(db,[image],self.work,None)
            vlog_maker.candidates(db,8.,3)
            key=db.execute('SELECT id FROM candidates').fetchone()[0]
            (self.work/'thumbnails_v2').mkdir(exist_ok=True)
            (self.work/'ui_thumbnails_v441').mkdir(exist_ok=True)
            for filename in (f'thumbnails_v2/{key}.jpg',f'thumbnails_v2/{key}_seq0.jpg',f'ui_thumbnails_v441/{key}.png'):
                (self.work/filename).write_bytes(b'cached old frames')
            image.write_bytes(b'new source image contents')
            vlog_maker.scan(db,[image],self.work,None)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM candidates').fetchone()[0],0)
        for filename in (f'thumbnails_v2/{key}.jpg',f'thumbnails_v2/{key}_seq0.jpg',f'ui_thumbnails_v441/{key}.png'):
            self.assertFalse((self.work/filename).exists(),filename)
        self.assertEqual(image.read_bytes(),b'new source image contents')

    def test_player_restart_from_stopped(self):
        class States:
            Stopped='stop';Ended='end';NothingSpecial='empty';Error='error'
        class FakePlayer:
            def __init__(self):self.played=0
            def is_playing(self):return False
            def get_state(self):return 'stop'
            def play(self):self.played+=1;return 0
        dlg=video_preview.VideoTrimDialog.__new__(video_preview.VideoTrimDialog)
        dlg.player=FakePlayer();dlg.vlc=SimpleNamespace(State=States)
        dlg._range_play=True;dlg.play_button=SimpleNamespace(configure=lambda **kw:None)
        dlg.toggle_play()
        self.assertEqual(dlg.player.played,1)
        self.assertFalse(dlg._range_play)

    def test_json_nonobject_is_rejected_without_crash(self):
        cfg=self.root/'gui_settings.json';cfg.write_text('[1,2]',encoding='utf8')
        app=vlog_gui.Application.__new__(vlog_gui.Application)
        fake=lambda:SimpleNamespace(set=lambda v:None)
        for name in ('output','music','model','seconds','min_score','temporal','mode','hardware','dissolve','ambient','beat'):
            setattr(app,name,fake())
        app.inputs=[];app.input_list=SimpleNamespace(insert=lambda *a:None)
        with mock.patch.object(vlog_gui,'CONFIG',cfg),mock.patch.object(vlog_gui,'DEFAULT_IN',str(self.root/'nonexistent')):
            app.load_settings()
        self.assertEqual(app.inputs,[])


if __name__=='__main__':unittest.main()
