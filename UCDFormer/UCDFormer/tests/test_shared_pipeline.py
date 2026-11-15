"""Synthetic verification of shared policy and automatic scene geometry."""
import sys
import os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.deps'));sys.path.insert(0,str(ROOT))
os.environ.setdefault('MPLCONFIGDIR','/tmp/nisar-shared-tests')
import json
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import torch
import h5py
from types import SimpleNamespace
from nisar.config import load_inputs,resolve_config,scene_settings
from nisar.data import spatial_split,select_polarizations,physical_features
from nisar.model import legacy


class SharedPipelineTests(unittest.TestCase):
    def test_generic_batch_does_not_rewrite_inputs(self):
        import run_all_locations
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);paths=[]
            for name in ('arbitrary_city_a','arbitrary_city_b'):
                path=root/(name+'.json')
                path.write_text(json.dumps(dict(study_id=name,before='pre.h5',after='post.h5',bbox=[10,20,11,21])))
                paths.append(path)
            original=[path.read_bytes() for path in paths]
            argv=['batch','--inputs',*map(str,paths),'--output-root',str(root/'results')]
            with patch.object(sys,'argv',argv),patch('subprocess.run',return_value=SimpleNamespace(returncode=0)) as launch:
                self.assertEqual(run_all_locations.main(),0)
                self.assertEqual(launch.call_count,2)
                for call in launch.call_args_list:
                    command=call.args[0]
                    self.assertEqual(command[command.index('--settings')+1],'configs/pipeline.json')
            self.assertEqual([path.read_bytes() for path in paths],original)

    def test_preparation_records_keep_data_and_policy_separate(self):
        import run_nisar
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'city.json';out=root/'result'
            data=dict(study_id='new_city',before='pre.h5',after='post.h5',bbox=[10,20,11,21])
            path.write_text(json.dumps(data))
            arrays=np.ones((3,64,64),np.float32);valid=np.ones((64,64),bool)
            meta=dict(transform=[10,0,0,0,-10,0],valid_fraction=1,split={},before={'channels':['VV','VH']})
            argv=['pipeline','--config',str(path),'--output',str(out),'--stage','prepare']
            with patch.object(sys,'argv',argv),patch('run_nisar.prepare',return_value=(arrays,arrays,valid,meta)),patch('run_nisar.baseline'):
                run_nisar.main()
            self.assertEqual(json.loads((out/'input.json').read_text()),data)
            policy=json.loads((out/'pipeline_settings.json').read_text())
            self.assertNotIn('bbox',policy)
            self.assertEqual(json.loads((out/'derived_settings.json').read_text())['input_polarizations'],['VV','VH'])

    def test_all_inputs_are_data_only_and_share_identical_policy(self):
        policies=[]
        for path in (ROOT/'configs').glob('*_run.json'):
            config,data,policy=resolve_config(path)
            policies.append(policy)
            self.assertNotIn('physical_fusion_weight',data)
            self.assertNotIn('morphology_min_area_m2',data)
            self.assertEqual(config['physical_fusion_weight'],.7)
        self.assertGreater(len(policies),1)
        self.assertTrue(all(policy==policies[0] for policy in policies))

    def test_unknown_city_needs_only_data_and_rejects_algorithm_override(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'city.json'
            data=dict(study_id='new_city',before='pre.h5',after='post.h5',bbox=[10,20,11,21])
            path.write_text(json.dumps(data))
            config,loaded,policy=resolve_config(path)
            self.assertEqual(loaded,data)
            self.assertIn('new_city',config['output'])
            data['physical_fusion_weight']=.2;path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'processing settings'):load_inputs(path)

    def test_small_and_narrow_scenes_keep_disjoint_measured_support(self):
        for shape in ((190,170),(64,500),(500,64)):
            valid=np.ones(shape,bool)
            train,val,fit,meta=spatial_split(valid)
            a=np.zeros(shape,bool);b=a.copy()
            for windows,support in ((train,a),(val,b)):
                for y,x,n in windows:support[y:y+n,x:x+n]=True
            self.assertFalse((a&b).any())
            self.assertFalse((fit&b).any())
            self.assertGreaterEqual(meta['gap_pixels'],64)
            self.assertTrue(valid[fit].all())
        with self.assertRaisesRegex(ValueError,'insufficient'):spatial_split(np.ones((60,60),bool))
        with self.assertRaisesRegex(ValueError,'insufficient'):spatial_split(np.zeros((512,512),bool))

    def test_scene_settings_follow_shape_and_spacing(self):
        config=json.loads((ROOT/'configs/pipeline.json').read_text())
        a=scene_settings(config,{'transform':[10,0,0,0,-10,0]},(190,170))
        b=scene_settings(config,{'transform':[20,0,0,0,-20,0]},(500,500))
        self.assertEqual(a['inference_patch'],168)
        self.assertEqual(b['inference_patch'],256)
        self.assertEqual(a['pseudo_local_window'],61)
        self.assertEqual(b['pseudo_local_window'],31)

    def test_polarizations_require_hh_hv_in_both_images(self):
        with tempfile.TemporaryDirectory() as directory:
            files=[Path(directory)/f'{i}.h5' for i in range(2)]
            for path in files:
                with h5py.File(path,'w') as f:
                    g=f.create_group('science/LSAR/GCOV/grids/frequencyA')
                    g['HHHH']=np.ones((2,2));g['HVHV']=np.ones((2,2));g['VVVV']=np.ones((2,2))
            self.assertEqual(select_polarizations(*files),('HH','HV'))
            with h5py.File(files[1],'a') as f:del f['science/LSAR/GCOV/grids/frequencyA/HVHV']
            with self.assertRaisesRegex(ValueError,'requires HH and HV'):select_polarizations(*files)

    def test_translator_decoder_accept_small_automatically_selected_patch(self):
        # Random weights, synthetic tensors only; no real pipeline or pretrained loads.
        torch.set_num_threads(2)
        options=SimpleNamespace(luma_bins=4,channel_multiplier=1,spatial_bin=16,
            n_input_channel=256,n_input_size=64,group_num=16,alpha=1,selection='Ax+b',inter_selection='A1x+b2')
        translator=legacy.StyleFormer(options);decoder=legacy.decoder(options)
        for size in (32,64):
            with torch.no_grad():
                result=decoder(translator(torch.randn(1,256,size//4,size//4),torch.randn(1,256,size//4,size//4)))
            self.assertEqual(result.shape,(1,3,size,size))
            self.assertTrue(torch.isfinite(result).all())


if __name__=='__main__':unittest.main()
