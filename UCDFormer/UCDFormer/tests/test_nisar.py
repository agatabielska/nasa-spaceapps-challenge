import sys
import os
os.environ.setdefault("MPLCONFIGDIR","/tmp/nisar-test-matplotlib")
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/".deps")); sys.path.insert(0,str(ROOT))
import tempfile
import unittest
import h5py
import numpy as np
import torch
from nisar.data import read_gcov,physical_features,fit_scaler,apply_scaler,positions,spatial_split,filter_pair_power
from nisar.detection import pseudo_labels,classify
from nisar.model import feature_difference,SARUCDFormer
from nisar.data import fit_standardization


class NISARTests(unittest.TestCase):
    def test_nisar_standardization_shared_dates_training_only(self):
        pre=np.array([[[0.,.2,999]],[[.1,.3,999]],[[.5,.5,999]]],np.float32)
        post=np.array([[[.4,.6,-999]],[[.5,.7,-999]],[[.5,.5,-999]]],np.float32)
        support=np.array([[True,True,False]])
        fitted=fit_standardization(pre,post,support)
        np.testing.assert_allclose(fitted["mean"],[.3,.4,.5],atol=1e-7)
        np.testing.assert_allclose(fitted["std"], [np.sqrt(.05),np.sqrt(.05),1e-6],rtol=1e-6)
        # Exercise the actual VGG boundary without loading large pretrained weights.
        model=SARUCDFormer.__new__(SARUCDFormer)
        torch.nn.Module.__init__(model)
        model.register_buffer("mean",torch.tensor(fitted["mean"]).float().view(1,3,1,1))
        model.register_buffer("std",torch.tensor(fitted["std"]).float().view(1,3,1,1))
        a=model.normalize(torch.from_numpy(pre)[None])
        b=model.normalize(torch.from_numpy(post)[None])
        pooled=torch.cat([a[0,:,support],b[0,:,support]],dim=1)
        np.testing.assert_allclose(pooled.mean(1).numpy(),0,atol=1e-6)
        np.testing.assert_allclose(pooled[:2].std(1,unbiased=False).numpy(),1,atol=1e-6)
        self.assertTrue(torch.isfinite(pooled).all())
        self.assertGreater(float(b[0,0,0,0]),float(a[0,0,0,0]))

    def test_power_filter_preserves_temporal_ratio_without_validating_holes(self):
        before=np.ones((2,25,25),np.float32); after=before*4
        valid=np.ones((25,25),bool); valid[12,12]=False
        before[:,12,12]=np.nan; after[:,12,12]=np.nan
        a,b,support=filter_pair_power(before,after,valid,3)
        self.assertEqual(int((~support).sum()),9)
        self.assertFalse(support[12,12])
        np.testing.assert_allclose(b[:,support]/a[:,support],4)
        self.assertTrue(np.isnan(a[:,~support]).all())

    def test_refined_pseudo_labels_refuse_fabricated_positive_class(self):
        from nisar.refined_detection import refined_classify
        physical=np.zeros((3,64,64),np.float32)
        with self.assertRaisesRegex(ValueError,"lack a class"):
            refined_classify(physical,physical,np.zeros((64,64),np.float32),np.ones((64,64),bool),
                             {"seed":123,"pseudo_local_window":7})

    def test_real_power_units_and_shared_scaling(self):
        pre=np.full((2,4,4),.1,np.float32); post=pre*10
        a,b=physical_features(pre),physical_features(post)
        np.testing.assert_allclose(b[:2]-a[:2],10,atol=1e-5)
        np.testing.assert_allclose(b[2]-a[2],0,atol=1e-5)
        mask=np.ones((4,4),bool); bounds=fit_scaler(a,b,mask)
        self.assertTrue((apply_scaler(b,bounds)[:2]>apply_scaler(a,bounds)[:2]).all())

    def test_quality_mask_and_center_affine(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"synthetic.h5"
            with h5py.File(path,"w") as f:
                g=f.create_group("science/LSAR/GCOV/grids/frequencyA")
                g["xCoordinates"]=15+np.arange(4)*.001; g["yCoordinates"]=38-np.arange(4)*.001
                g["xCoordinateSpacing"]=.001; g["yCoordinateSpacing"]=-.001; g["projection"]=4326
                g["HHHH"]=np.ones((4,4),np.float32); g["HVHV"]=np.ones((4,4),np.float32)
                g["numberOfSubSwaths"]=1
                mask=np.ones((4,4),np.uint8); mask[0,0]=255; mask[0,1]=0; g["mask"]=mask
                exc=np.zeros((4,4),np.uint8); exc[0,2]=2; g["inputDataExceptionMask"]=exc
                g["HHHH"][0,3]=0
                g["HHHH"].attrs["_FillValue"]=999.0
                g["HHHH"][1,0]=999.0
                g["HVHV"][1,1]=-999.0
            _,valid,transform,_,_=read_gcov(path,[14.999,37.996,15.004,38.001])
            self.assertEqual(int(valid.sum()),10)
            self.assertFalse(valid[1,0])  # Positive, explicitly declared fill.
            self.assertFalse(valid[1,1])  # Negative sentinel is never valid power.
            self.assertAlmostEqual((transform*(.5,.5))[0],15)
            self.assertAlmostEqual((transform*(.5,.5))[1],38)

    def test_spatial_split_has_no_shared_support(self):
        train,val,_,metadata=spatial_split(np.ones((498,500),bool))
        self.assertEqual(metadata["gap_pixels"],114)
        train_support=np.zeros((498,500),bool); val_support=train_support.copy()
        for windows,mask in [(train,train_support),(val,val_support)]:
            for y,x,n in windows: mask[y:y+n,x:x+n]=True
        self.assertFalse((train_support&val_support).any())

    def test_sparse_holes_use_smaller_disjoint_training_patches(self):
        valid=np.ones((512,512),bool)
        valid[200,::200]=False; valid[400,::200]=False
        train,val,fit,meta=spatial_split(valid)
        self.assertEqual(meta["train_patch_size"],128)
        tr=np.zeros_like(valid); va=tr.copy()
        for windows,support in [(train,tr),(val,va)]:
            for y,x,n in windows:
                self.assertTrue(valid[y:y+n,x:x+n].all())
                support[y:y+n,x:x+n]=True
        self.assertFalse((tr&va).any())
        self.assertFalse((fit&va).any())
        self.assertGreaterEqual(min(y for y,x,n in val)-max(y+n for y,x,n in train),64)

    def test_border_overlap_preserves_constant(self):
        h,w,n=498,500,256; a=np.zeros((h,w)); weights=a.copy()
        blend=np.outer(np.hanning(n),np.hanning(n)).clip(.01)
        for y in positions(h,n,128):
            for x in positions(w,n,128):
                a[y:y+n,x:x+n]+=7*blend; weights[y:y+n,x:x+n]+=blend
        self.assertTrue((weights>0).all())
        np.testing.assert_allclose(a/weights,7)

    def test_no_forced_change_on_constant_score(self):
        score=np.zeros((64,64),np.float32); valid=np.ones_like(score,bool); valid[0]=False
        labels,_=pseudo_labels(score,valid)
        self.assertTrue((labels[valid]==0).all()); self.assertTrue((labels[~valid]==-1).all())
        values=np.zeros((3,64,64),np.float32)
        mask,_,forest,details=classify(values,values,score,valid)
        self.assertFalse(mask.any()); self.assertIsNone(forest)

    def test_export_preserves_preview_aspect_and_scientific_nodata(self):
        from nisar.export import export
        from PIL import Image
        import rasterio
        n,m=24,32
        valid=np.ones((n,m),bool); valid[-1,-1]=False
        pre=np.ones((3,n,m),np.float32)*.3
        changed=np.zeros((n,m),bool); changed[10:12,12:14]=True
        meta={"transform":[20,0,490000,0,-20,4200000],"crs":"EPSG:32633",
              "before":{"file":"before.h5"},"after":{"file":"after.h5"}}
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            report=export(out,pre,pre,valid,np.zeros((n,m)),changed,np.full((n,m),-1),meta,"test",{})
            with Image.open(out/"before_wgs84.png") as image:
                self.assertEqual(image.size,(m,n))
            self.assertEqual(report["display_shape"],[n,m])
            with rasterio.open(out/"change_mask.tif") as raster:
                values=raster.read(1)
                self.assertEqual(values[-1,-1],255)
                self.assertEqual(int((values==1).sum()),4)
                self.assertEqual(raster.crs.to_epsg(),32633)
            self.assertIn('![', (out/'README.md').read_text())

    def test_invalid_samples_do_not_fit_feature_saturation(self):
        rng=np.random.default_rng(82)
        a=torch.tensor(rng.random((1,3,16,16)),dtype=torch.float32)
        b=torch.tensor(rng.random((1,3,16,16)),dtype=torch.float32)
        valid=np.ones((16,16),bool); valid[12:,12:]=False
        expected=feature_difference([a],[b],valid)
        a[:,:,12:,12:]=1e6; b[:,:,12:,12:]=-1e6
        actual=feature_difference([a],[b],valid)
        np.testing.assert_allclose(actual[valid],expected[valid],rtol=1e-6)

    def test_streamed_score_matches_original_saturation(self):
        rng=np.random.default_rng(123)
        a=[torch.from_numpy(rng.random((1,3,16,16)).astype(np.float32))]
        b=[torch.from_numpy(rng.random((1,3,16,16)).astype(np.float32))]
        def normalized(t):
            x=t[0].numpy().astype(float)
            lo=x.min((1,2),keepdims=True); hi=np.percentile(x,95,axis=(1,2),keepdims=True)
            return np.minimum((x-lo)/(hi-lo+np.exp(-10)),1)
        expected=np.linalg.norm(normalized(a[0])-normalized(b[0]),axis=0)
        np.testing.assert_allclose(feature_difference(a,b),expected,rtol=1e-6,atol=1e-6)


if __name__=="__main__": unittest.main()
