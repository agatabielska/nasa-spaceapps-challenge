"""Synthetic checks for conservative cross-product validity; no pipeline runs."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'.deps'),str(ROOT)]
import unittest
import numpy as np
from experiments.gunw_rasuwagadhi.mask_gcov_holes import project_gcov_valid,apply_gcov_valid


class GCOVMaskTests(unittest.TestCase):
    def test_one_missing_fine_pixel_excludes_the_coarse_pixel(self):
        src=dict(transform=[10,0,0,0,-10,80],crs='EPSG:32645',shape=[8,8])
        dst=dict(transform=[20,0,0,0,-20,80],crs='EPSG:32645',shape=[4,4])
        valid=np.ones((8,8),bool)
        result,fraction=project_gcov_valid(valid,src,dst)
        self.assertTrue(result.all());np.testing.assert_allclose(fraction,1)
        valid[1,1]=False
        result,fraction=project_gcov_valid(valid,src,dst)
        self.assertFalse(result[0,0]);self.assertEqual(int((~result).sum()),1)
        self.assertAlmostEqual(float(fraction[0,0]),.75)
        dst80=dict(transform=[80,0,0,0,-80,80],crs='EPSG:32645',shape=[1,1])
        result,_=project_gcov_valid(valid,src,dst80);self.assertFalse(result[0,0])

    def test_outside_coverage_and_native_gunw_invalidity_remain_excluded(self):
        src=dict(transform=[10,0,0,0,-10,80],crs='EPSG:32645',shape=[8,8])
        dst=dict(transform=[20,0,-10,0,-20,80],crs='EPSG:32645',shape=[4,4])
        result,fraction=project_gcov_valid(np.ones((8,8),bool),src,dst)
        self.assertFalse(result[:,0].any());np.testing.assert_allclose(fraction[:,0],.5)
        native=np.ones((4,4),bool);native[1,1]=False
        arrays={'coherenceMagnitude':np.full((4,4),.2,np.float32),'unwrappedPhase':np.ones((4,4))}
        masked,combined=apply_gcov_valid(arrays,native,result)
        self.assertTrue(np.isnan(masked['coherenceMagnitude'][~combined]).all())
        self.assertTrue(np.isnan((1-masked['coherenceMagnitude'])[~combined]).all())
        self.assertTrue(np.isnan(masked['unwrappedPhase'][~combined]).all())
        self.assertFalse(combined[1,1])


if __name__=='__main__':unittest.main()
