import unittest
from candidate_engine import intervals, representatives, frame_metrics, technical_summary, near_duplicate


class CandidateTests(unittest.TestCase):
    def test_fixed_and_scene_bounds(self):
        self.assertEqual(intervals(20,maximum=2),[(0.,10.),(10.,20.)])
        self.assertEqual(intervals(10,'scene',cuts=[8,2,2,-1,20]),[(0.,2.),(2.,8.),(8.,10.)])
        self.assertEqual(representatives(0,10),[2,5,8])
        for value in (0,-1,float('nan')):
            with self.assertRaises(ValueError):intervals(value)

    def test_dark_frame_keeps_uncertain_scene(self):
        summary=technical_summary([bytes(64*36),bytes([150])*(64*36)])
        self.assertIn('dark_representative',summary['flags'])
        self.assertFalse(summary['reject']);self.assertIsNone(summary['camera_shake'])
        self.assertEqual(frame_metrics(bytes(64*36))['brightness'],0)

    def test_multiframe_duplicates_and_flat_uncertainty(self):
        def sample(h,contrast=30):return dict(dhash=h,contrast=contrast)
        a={'frames':[sample('0123456789abcdef'),sample('fedcba9876543210')]}
        self.assertTrue(near_duplicate(a,a))
        self.assertFalse(near_duplicate(a,{'frames':[sample('0'*16),sample('0'*16)]}))
        flat={'frames':[sample('0'*16,0)]*3}
        self.assertFalse(near_duplicate(flat,flat))
