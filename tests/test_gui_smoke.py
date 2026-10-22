"""Tk smoke test: run under a virtual display on Linux, or normal Windows."""
import json
from pathlib import Path
import sys
import tempfile
import tkinter as tk
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import vlog_maker as core
import vlog_gui
import video_preview

class PreviewGuiSmoke(unittest.TestCase):
    def test_plan_preview_save(self):
        with tempfile.TemporaryDirectory() as folder:
            temp=Path(folder)
            video=temp/'demo.mp4';video.write_bytes(b'placeholder')
            work=temp/'AI_Vlog_test'
            db=core.connect(work)
            db.execute('INSERT INTO media(path,kind,duration,size,mtime,width,height,error) VALUES(?,?,?,?,?,?,?,?)',
                (str(video),'video',8.,500,1.,320,180,None))
            db.execute('INSERT INTO candidates(id,path,position,score,event,v2) VALUES(?,?,?,?,?,?)',
                ('gui-clip',str(video),5.,84.,55.,1))
            db.commit();db.close()
            root=tk.Tk();root.withdraw()
            app=vlog_gui.Application(root)
            app.override_workspace=work
            app.update_workspace()
            app.load_candidates(reset=True)
            app.selected_ids=['gui-clip']
            app.refresh_plan()
            app.plan_tree.selection_set('gui-clip')
            captured=[]
            original=video_preview.VideoTrimDialog.__init__
            def wrapper(self,*a,**kw):
                original(self,*a,**kw);captured.append(self)
            video_preview.VideoTrimDialog.__init__=wrapper
            try:
                app.open_trim_preview()
                self.assertEqual(len(captured),1)
                dialog=captured[0]
                dialog.start_str.set('00:04.200')
                dialog.end_str.set('00:06.400')
                dialog.save()
                payload=json.loads(app.selection_path().read_text('utf-8'))
                self.assertAlmostEqual(payload['trims']['gui-clip']['start'],4.2)
                self.assertAlmostEqual(payload['trims']['gui-clip']['end'],6.4)
                self.assertAlmostEqual(app.plan_rows['gui-clip']['seconds'],2.2)
                self.assertTrue(app.plan_rows['gui-clip']['trim_locked'])
            finally:
                video_preview.VideoTrimDialog.__init__=original
                root.destroy()

if __name__=='__main__':unittest.main()
