"""Small synthetic checks only: no downloaded imagery, pretrained weights or GPU."""
import sys
import os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.deps'));sys.path.insert(0,str(ROOT))
os.environ.setdefault('MPLCONFIGDIR','/tmp/nisar-step-tests')
import json
import re
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from nisar.data import prepare
from nisar.detection import pseudo_labels
from nisar.refined_detection import refined_classify
from nisar.step_report import build_report


class StepReportTests(unittest.TestCase):
    def test_feature_saturation_trace_preserves_scores(self):
        import torch
        from nisar.model import feature_difference
        rng=np.random.default_rng(42)
        a=[torch.from_numpy(rng.random((1,4,8,8)).astype(np.float32))]
        b=[torch.from_numpy(rng.random((1,4,8,8)).astype(np.float32))]
        valid=np.ones((8,8),bool);valid[0,0]=False
        trace={}
        actual=feature_difference(a,b,valid,trace)
        np.testing.assert_array_equal(actual,feature_difference(a,b,valid))
        self.assertEqual(trace['score_block_0_saturated_post_first_channels'].shape,(3,8,8))
        self.assertLessEqual(float(trace['score_block_0_saturated_post_first_channels'][:,valid].max()),1)


    def test_preprocessing_trace_matches_real_returned_inputs(self):
        rng=np.random.default_rng(7)
        a=rng.uniform(.01,.3,(2,20,20)).astype(np.float32);b=a*1.4
        valid=np.ones((20,20),bool);fit=valid.copy();fit[8:]=False
        meta={'transform':[20,0,0,0,-20,400],'crs':'EPSG:32633','before':{'file':'before'},'after':{'file':'after'},'bbox_wgs84':[]}
        split=([(0,0,8)],[(12,0,8)],fit,{'gap_pixels':4})
        with tempfile.TemporaryDirectory() as directory:
            with patch('nisar.data.select_polarizations',return_value=('HH','HV')),patch('nisar.data.align_pair',return_value=(a,b,valid,meta)),patch('nisar.data.spatial_split',return_value=split):
                pre,post,support,metadata=prepare(dict(before='unused',after='unused',bbox=[],power_mean_filter_size=3,visualize_steps=True),directory)
            with np.load(Path(directory)/'steps/01_preprocessing.npz') as trace:
                np.testing.assert_array_equal(trace['percentile_scaled_pre'],pre)
                np.testing.assert_array_equal(trace['filtered_valid'],support)
                stats=metadata['vgg_standardization']
                expected=(pre-np.array(stats['mean'])[:,None,None])/np.array(stats['std'])[:,None,None]
                np.testing.assert_allclose(trace['vgg_input_pre'],expected)
                np.testing.assert_allclose(trace['filtered_power_post']/trace['filtered_power_pre'],1.4,rtol=1e-6)

    def test_strict_trace_is_passive_and_agreement_is_exact(self):
        rng=np.random.default_rng(9)
        score=rng.uniform(0,.1,(40,40)).astype(np.float32);score[10:14,10:14]=1
        valid=np.ones(score.shape,bool);valid[0]=False
        trace={}
        labels,details=pseudo_labels(score,valid,pixel_size=20,sigma_m=100,trace=trace)
        reference,_=pseudo_labels(score,valid,pixel_size=20,sigma_m=100)
        np.testing.assert_array_equal(labels,reference)
        np.testing.assert_array_equal(labels==1,(trace['fcm_clusters']==2)&trace['gaussian_adaptive_clean']&valid)
        membership=np.stack([trace[f'fcm_membership_{i}'] for i in range(3)])
        np.testing.assert_allclose(membership[:,valid].sum(0),1,atol=1e-6)
        self.assertTrue(np.isnan(membership[:,~valid]).all())

    def test_refined_trace_matches_seed_vote_and_support_rules(self):
        rng=np.random.default_rng(6)
        pre=np.full((3,40,40),-10,np.float32);pre[2]=0
        post=pre.copy();post[:2,10:14,10:14]+=6
        score=rng.uniform(0,.1,(40,40)).astype(np.float32);score[10:14,10:14]=10
        valid=np.ones(score.shape,bool)
        config=dict(seed=123,pseudo_local_window=15,rf_positive_vote=.8)
        trace={}
        mask,labels,forest,details,extras=refined_classify(pre,post,score,valid,config,trace)
        reference=refined_classify(pre,post,score,valid,config)
        np.testing.assert_array_equal(mask,reference[0])
        np.testing.assert_array_equal(labels,reference[1])
        expected=(labels==1)|((labels==-1)&trace['connected_candidate_support']&trace['rf_vote_binary']&valid)
        np.testing.assert_array_equal(mask,expected)
        self.assertGreater(int((labels==1).sum()),0)
        self.assertGreater(int((labels==0).sum()),0)
        weighted_trace={}
        weighted=refined_classify(pre,post,score,valid,dict(config,physical_fusion_weight=.7),weighted_trace)
        np.testing.assert_allclose(weighted_trace['fused_clustering_score'],
                                   .3*weighted_trace['normalized_feature_score']+
                                   .7*weighted_trace['normalized_physical_score'],rtol=1e-6)
        self.assertEqual(weighted[3]['physical_fusion_weight'],.7)
        self.assertEqual(weighted[3]['rf_features'][-1],'physical_VGG_fused_score')
        with self.assertRaisesRegex(ValueError,'between 0 and 1'):
            refined_classify(pre,post,score,valid,dict(config,physical_fusion_weight=1.1))

    def test_offline_report_has_local_images_metadata_and_training_curve(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory);steps=out/'steps';steps.mkdir()
            np.savez_compressed(steps/'01_preprocessing.npz',percentile_scaled_pre=np.ones((3,6,6)),percentile_scaled_post=np.ones((3,6,6))*.5,filtered_valid=np.ones((6,6),bool))
            np.savez_compressed(steps/'03_detection.npz',fcm_center_history=np.array([[0,.3,.8],[0,.4,1]]),final_mask=np.eye(6,dtype=bool),model_support=np.ones((6,6),bool),rf_feature_importance=np.array([.1,.9]))
            (out/'run.jsonl').write_text(json.dumps(dict(event='validation',step=0,total=3,style=2,content=.001))+'\n')
            report=build_report(out);text=report.read_text()
            self.assertIn('diagnostic comparison',text)
            self.assertIn('training.png',text)
            for name in re.findall(r'src="([^"]+)"',text):self.assertTrue((steps/name).is_file(),name)
            manifest=json.loads((steps/'manifest.json').read_text())
            self.assertTrue(any(r['name']=='final_mask' for r in manifest))
            # Re-rendering is safe and never executes processing.
            self.assertEqual(build_report(out),report)

    def test_runner_refuses_existing_artifacts_before_starting_pipeline(self):
        import run_pipeline_steps
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/'keep.txt').write_text('preserve')
            with patch.object(sys,'argv',['runner','--output',directory]),patch('subprocess.Popen') as start:
                with self.assertRaises(SystemExit):run_pipeline_steps.main()
                start.assert_not_called()
            self.assertEqual((Path(directory)/'keep.txt').read_text(),'preserve')


if __name__=='__main__':unittest.main()
