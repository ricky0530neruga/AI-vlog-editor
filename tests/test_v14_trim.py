import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
"""Run: py -m unittest discover -s tests -v (requires FFmpeg for integration test)."""
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import vlog_maker as core
from video_preview import parse_time, validate_times

class TrimTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work=Path(self.tmp.name)
        self.source=self.work/'input.mp4'
        self.db=core.connect(self.work/'work')
        self.addCleanup(self.db.close)
        self.db.execute('INSERT INTO media(path,kind,duration,size,mtime,width,height,error) VALUES(?,?,?,?,?,?,?,?)',
                        (str(self.source),'video',8.,900,10.,320,180,None))
        self.db.execute('INSERT INTO candidates(id,path,position,score,event,v2) VALUES(?,?,?,?,?,?)',
                        ('clip-1',str(self.source),6.5,88.,80.,1))
        self.db.commit()
        self.source.write_bytes(b'placeholder')

    def test_parse_time(self):
        self.assertEqual(parse_time('01:02.500'),62.5)
        self.assertEqual(parse_time('00:01:02.500'),62.5)
        with self.assertRaises(ValueError):parse_time('1:77')
        with self.assertRaises(ValueError):validate_times(7.,6.,8.)
        with self.assertRaises(ValueError):validate_times(7.9,8.,8.)

    def test_locked_trim_survives_target(self):
        trims={'clip-1':{'start':5.1,'end':6.7}}
        for target in (1,180,600):
            plan=core.choose_selected(self.db,['clip-1'],target,manual_trims=trims)
            self.assertEqual(len(plan),1)
            self.assertTrue(plan[0]['trim_locked'])
            self.assertAlmostEqual(plan[0]['start'],5.1)
            self.assertAlmostEqual(plan[0]['seconds'],1.6)
        with self.assertRaises(ValueError):
            core.choose_selected(self.db,['clip-1'],180,manual_trims={'clip-1':{'start':7.,'end':9.}})

    def test_locked_clips_not_nudged_by_music_or_target(self):
        import cinematic_editor as ce
        locked={'kind':'video','start':5.0,'seconds':2.0,'trim_locked':True,'source_duration':8.0,'candidate_position':6.5}
        unlocked={'kind':'video','start':2.0,'seconds':2.0,'source_duration':8.0,'candidate_position':3.0}
        clips=[locked.copy(),unlocked.copy()]
        ce._extend_for_crossfades(clips,20.,True)
        ce._nudge_cuts_to_onsets(clips,[7.12,11.1])
        self.assertEqual(clips[0]['start'],5.0)
        self.assertEqual(clips[0]['seconds'],2.0)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg not found')
    def test_actual_video_is_trimmed(self):
        self.source.unlink()
        # First 4 seconds red, next 4 seconds green. Trim must pick green only.
        subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i','color=red:s=320x180:r=30:d=4',
                        '-f','lavfi','-i','color=green:s=320x180:r=30:d=4',
                        '-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0[v]',
                        '-map','[v]','-c:v','libx264','-pix_fmt','yuv420p',str(self.source)],check=True)
        workspace=self.work/'work'
        selection=workspace/'ui_selected_v441.json'
        selection.write_text(json.dumps({'version':'1.4','candidate_ids':['clip-1'],
            'trims':{'clip-1':{'start':5.,'end':7.}}}),encoding='utf-8')
        result=subprocess.run([sys.executable,str(Path(core.__file__)),'render','--out',str(workspace),
                 '--selection-file',str(selection),'--seconds','180','--no-dissolve',
                 '--no-beat-sync','--no-ambient'],capture_output=True,text=True,timeout=130)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
        out=workspace/'Travel_Vlog_Final_V43.mp4'
        self.assertTrue(out.is_file())
        duration=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration',
                 '-of','default=noprint_wrappers=1:nokey=1',str(out)],text=True).strip())
        self.assertAlmostEqual(duration,2.,delta=.12)
        frame=subprocess.check_output(['ffmpeg','-nostdin','-v','error','-ss','0.8','-i',str(out),
                '-frames:v','1','-vf','crop=8:8:956:536,scale=1:1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'])
        self.assertGreater(frame[1],frame[0]+12)
        self.assertGreater(frame[1],frame[2]+12)
        plan=json.loads((workspace/'edit_plan_v43.json').read_text(encoding='utf-8'))
        self.assertTrue(plan['plan'][0]['trim_locked'])
        self.assertAlmostEqual(plan['plan'][0]['start'],5.)
        self.assertAlmostEqual(plan['plan'][0]['seconds'],2.)

if __name__=='__main__':unittest.main()
