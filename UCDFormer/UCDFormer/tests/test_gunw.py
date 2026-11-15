"""Synthetic optional-GUNW checks; no real-data pipeline execution."""
import sys,os,json,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'.deps'),str(ROOT)]
os.environ.setdefault('MPLCONFIGDIR','/tmp/nisar-gunw-tests')
import numpy as np
import h5py
from unittest.mock import patch
from rasterio.warp import transform_bounds
from nisar.gunw import load_gunw,incoherence_support,augment_physical_support,save_review,POLICY
from nisar.config import resolve_config
from nisar.refined_detection import refined_classify


class GUNWTests(unittest.TestCase):
    def test_optional_comparison_saves_true_binary_eligibility(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            valid=np.ones((12,12),bool);eligible=valid.copy();eligible[2:4,2:4]=False
            baseline=np.zeros_like(valid);baseline[5,3:8]=True
            result=baseline.copy();result[5,8]=True
            save_review(directory,dict(valid=eligible,coherence=np.full(valid.shape,.2,np.float32)),
                        valid,baseline,result,result&~baseline)
            with Image.open(Path(directory)/'gunw_valid_binary.png') as image:
                values=np.asarray(image)
                self.assertEqual(set(np.unique(values)),{0,255})
                np.testing.assert_array_equal(values==255,eligible)
            self.assertTrue((Path(directory)/'gunw_comparison.png').is_file())

    def test_walkthrough_forwards_flag_without_editing_data_config(self):
        import run_pipeline_steps
        from types import SimpleNamespace
        source=ROOT/'configs/nepal_rasuwagadhi_run.json';original=source.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)/'new_run'
            process=SimpleNamespace(stdout=[],wait=lambda:0)
            argv=['walkthrough','--config',str(source),'--output',str(out),'--gunw','example_gunw.h5']
            with patch.object(sys,'argv',argv),patch('subprocess.Popen',return_value=process) as start,patch('nisar.step_report.build_report',return_value=out/'steps/index.html'):
                self.assertEqual(run_pipeline_steps.main(),0)
            command=start.call_args.args[0]
            self.assertEqual(command[command.index('--gunw')+1],'example_gunw.h5')
            self.assertEqual(source.read_bytes(),original)

    def test_loader_masks_gcov_holes_but_keeps_measured_zero_coherence_and_ignores_phase(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);paths=[root/'before.h5',root/'after.h5'];gpath=root/'gunw.h5'
            common=dict(trackNumber=98,frameNumber=16,lookDirection='Left',orbitPassDirection='Ascending')
            dates=['2026-08-19T23:39:18','2026-08-31T23:39:18']
            for path,date in zip(paths,dates):
                with h5py.File(path,'w') as f:
                    ident=f.create_group('science/LSAR/identification')
                    for key,value in dict(common,zeroDopplerStartTime=date).items():ident[key]=value
            with h5py.File(gpath,'w') as f:
                ident=f.create_group('science/LSAR/identification')
                for key,value in dict(common,productType='GUNW',compositeReleaseId='TEST',referenceZeroDopplerStartTime=dates[0],secondaryZeroDopplerStartTime=dates[1]).items():ident[key]=value
                group=f.create_group('science/LSAR/GUNW/grids/frequencyA/wrappedInterferogram')
                group['projection']=32645;group['xCoordinates']=10+np.arange(8)*20;group['yCoordinates']=150-np.arange(8)*20
                group['xCoordinateSpacing']=20;group['yCoordinateSpacing']=-20
                group['mask']=np.full((8,8),11,np.uint32)
                values=np.full((8,8),.9,np.float32);values[0,0]=0;values[3,3]=0;values[5,5]=-999
                group['HH/coherenceMagnitude']=values
                # Unsupported unwrapped phase must not erase valid coherence.
                phase=f.create_group('science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram/HH')
                phase['connectedComponents']=np.zeros((2,2),np.uint16);phase['unwrappedPhase']=np.full((2,2),np.nan)
            meta=dict(shape=[16,16],transform=[10,0,0,0,-10,160],crs='EPSG:32645')
            valid=np.ones((16,16),bool);valid[0,0]=False
            bbox=transform_bounds('EPSG:32645','EPSG:4326',0,0,160,160)
            config=dict(before=str(paths[0]),after=str(paths[1]),bbox=list(bbox))
            with patch('nisar.data.align_pair',return_value=(None,None,valid,meta)):
                data,details,native=load_gunw(gpath,config,meta)
            self.assertFalse(data['valid'][:2,:2].any())
            self.assertTrue(np.isnan(data['coherence'][:2,:2]).all())
            self.assertTrue(data['valid'][6:8,6:8].all())
            self.assertTrue(data['candidate'][6:8,6:8].all())
            self.assertFalse(native['valid'][5,5])
            self.assertFalse(details['phase_used']);self.assertFalse(details['minimum_coherence_cutoff_used'])
            self.assertTrue(details['same_acquisition_dates'])
            self.assertEqual(details['threshold_fit']['fitted_native_valid_pixels'],62)
            with h5py.File(gpath,'a') as f:f['science/LSAR/identification/trackNumber'][...]=99
            with self.assertRaisesRegex(ValueError,'trackNumber'):
                load_gunw(gpath,config,meta)

    def test_threshold_excludes_invalid_values_and_low_coherence_is_evidence(self):
        coherence=np.array([[.9,.9,.9],[.9,.1,0],[.9,.9,-999]],np.float32)
        valid=np.ones((3,3),bool);valid[2,2]=False
        good,candidate,details=incoherence_support(coherence,valid,POLICY)
        self.assertTrue(candidate[1,1]);self.assertTrue(candidate[1,2]);self.assertFalse(good[2,2])
        self.assertEqual(details['fitted_native_valid_pixels'],8)

    def test_support_adds_only_uncertain_physical_seed_connected_corridors(self):
        valid=np.ones((20,30),bool);weak=np.zeros_like(valid);weak[10,3:9]=True;weak[10,12:18]=True
        positives=np.zeros_like(valid);positives[10,5]=True
        labels=np.full(valid.shape,-1,np.int8);labels[positives]=1
        physical=np.zeros(valid.shape,np.float32);physical[10,3:18]=.06
        low=np.full(valid.shape,.075,np.float32)
        gunw=dict(valid=valid.copy(),candidate=np.zeros_like(valid));gunw['candidate'][10,9:12]=True
        result,added,_=augment_physical_support(weak,physical,low,labels,positives,valid,gunw,8,POLICY)
        self.assertTrue(result[10,3:18].all());self.assertEqual(int(added.sum()),3)
        labels[10,10]=0
        result,_,_=augment_physical_support(weak,physical,low,labels,positives,valid,gunw,8,POLICY)
        self.assertFalse(result[10,12:18].any())
        labels[10,10]=-1;gunw['valid'][10,10]=False
        result,_,_=augment_physical_support(weak,physical,low,labels,positives,valid,gunw,8,POLICY)
        self.assertFalse(result[10,12:18].any())

    def test_no_flag_policy_unchanged_and_gunw_source_is_data_not_settings(self):
        path=ROOT/'configs/nepal_rasuwagadhi_run.json'
        shared=(ROOT/'configs/pipeline.json').read_bytes();original=path.read_bytes()
        baseline,inputs,settings=resolve_config(path)
        self.assertNotIn('gunw',baseline);self.assertNotIn('gunw_support_policy',settings)
        with tempfile.NamedTemporaryFile(suffix='.h5') as source:
            config,optional_inputs,optional_settings=resolve_config(path,gunw=source.name)
            self.assertEqual(optional_inputs['gunw'],source.name)
            self.assertNotIn('gunw',optional_settings)
            self.assertEqual(config['gunw_support_policy'],POLICY)
        self.assertEqual(shared,(ROOT/'configs/pipeline.json').read_bytes());self.assertEqual(original,path.read_bytes())

    def test_no_gunw_candidates_reproduces_original_masks_seeds_and_rf(self):
        config=dict(seed=123,pseudo_local_window=15,rf_positive_vote=.8)
        pre=np.full((3,40,40),-10,np.float32);pre[2]=0
        post=pre.copy();post[:2,10:14,10:14]+=6
        score=np.random.default_rng(6).uniform(0,.1,(40,40)).astype(np.float32);score[10:14,10:14]=10
        valid=np.ones((40,40),bool)
        reference=refined_classify(pre,post,score,valid,config)
        gunw=dict(valid=np.ones_like(valid),candidate=np.zeros_like(valid),coherence=np.full(valid.shape,.9,np.float32),threshold=.5)
        optional=refined_classify(pre,post,score,valid,config,gunw=gunw)
        np.testing.assert_array_equal(reference[0],optional[0]);np.testing.assert_array_equal(reference[1],optional[1])
        np.testing.assert_array_equal(reference[4]['rf_votes'],optional[4]['rf_votes'])
        np.testing.assert_array_equal(reference[2].feature_importances_,optional[2].feature_importances_)
        self.assertFalse(optional[3]['gunw_support']['training_seeds_changed'])


if __name__=='__main__':unittest.main()
