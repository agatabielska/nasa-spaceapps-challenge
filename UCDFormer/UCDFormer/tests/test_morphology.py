"""Synthetic gaps, speckle and nodata checks; no real imagery runs."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'.deps'),str(ROOT)]
import unittest
import json
import numpy as np
from scipy import ndimage
from nisar.morphology import close_valid,spatial_fcm_candidates,final_cleanup
from nisar.detection import clean


class MorphologyTests(unittest.TestCase):
    def test_shared_detector_keeps_closing_gaps_uncertain_until_final_cleanup(self):
        from nisar.refined_detection import refined_classify
        config=json.loads((ROOT/'configs/pipeline.json').read_text())
        config.update(pixel_area_m2=100,pseudo_local_window=31)
        valid=np.ones((80,80),bool)
        river=np.zeros_like(valid);river[35:38,10:35]=True;river[35:38,37:65]=True
        pre=np.full((3,80,80),-10,np.float32);pre[2]=0
        post=pre.copy();post[:2,river]+=6
        score=np.random.default_rng(7).uniform(0,.05,valid.shape).astype(np.float32);score[river]=10
        trace={}
        mask,labels,_,details,extras=refined_classify(pre,post,score,valid,config,trace)
        self.assertTrue((labels[36,35:37]==-1).all())
        self.assertTrue(extras['candidate_support'][36,35:37].all())
        final,closed,cleanup=final_cleanup(mask,valid,config,100,extras['candidate_support'].astype(bool)&(labels!=0))
        self.assertTrue(final[36,10:65].all())
        self.assertTrue((trace['fcm_spatially_supported']<=trace['fcm_confident_raw']).all())

    def test_closing_fuses_short_break_then_removes_isolated_speckles(self):
        valid=np.ones((64,64),bool)
        mask=np.zeros_like(valid)
        mask[28:31,10:27]=True;mask[28:31,29:50]=True
        mask[8:10,8:10]=True;mask[50,50]=True
        config=dict(physical_closing_radius_m=20,morphology_min_area_m2=3600,morphology_connectivity=8)
        result,closed,details=final_cleanup(mask,valid,config,100)
        self.assertTrue(closed[29,27:29].all())
        self.assertEqual(ndimage.label(result,structure=np.ones((3,3)))[1],1)
        self.assertFalse(result[8:10,8:10].any());self.assertFalse(result[50,50])
        self.assertTrue(result[29,10:50].all())
        self.assertGreater(details['added_pixels'],0)

    def test_closing_never_bridges_nodata_and_respects_allowed_support(self):
        valid=np.ones((40,40),bool);valid[:,20]=False
        mask=np.zeros_like(valid);mask[15:20,10:20]=True;mask[15:20,21:30]=True
        closed=close_valid(mask,valid,2)
        self.assertFalse(closed[:,20].any())
        np.testing.assert_array_equal(closed,mask)
        valid[:]=True;mask[:,20]=False
        closed=close_valid(mask,valid,2,allowed=np.zeros_like(valid))
        np.testing.assert_array_equal(closed,mask)

    def test_narrow_connected_signals_survive_neighbor_rule_but_singletons_do_not(self):
        membership=np.zeros((40,40,3),np.float32);membership[:,:,0]=1
        membership[20,8:30]=[.025,.025,.95]
        membership[8,8]=[.025,.025,.95]
        membership[30,30]=[.2,.2,.6]
        raw,supported,fraction=spatial_fcm_candidates(membership,np.ones((40,40),bool),.75,.15,1,.3)
        self.assertTrue(raw[8,8]);self.assertFalse(supported[8,8])
        self.assertTrue(supported[20,8:30].all())
        self.assertFalse(raw[30,30])

    def test_diagonal_components_share_eight_neighbor_connectivity(self):
        valid=np.ones((12,12),bool);mask=np.eye(12,dtype=bool)
        self.assertFalse(clean(mask,valid,4,4).any())
        self.assertEqual(int(clean(mask,valid,4,8).sum()),12)


if __name__=='__main__':unittest.main()
