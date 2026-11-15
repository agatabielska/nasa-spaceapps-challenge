"""Synthetic score equivalence and reuse checks; no imagery or model weights."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.deps'));sys.path.insert(0,str(ROOT))
import unittest
import numpy as np
import torch
from torch import nn
from nisar.model import feature_difference,tensor_feature_scores,SARUCDFormer


class InferenceDeviceTests(unittest.TestCase):
    def check_scores(self,device):
        rng=np.random.default_rng(123)
        sizes=[(35,24),(5,12),(3,6)]
        groups=[[torch.tensor(rng.random((1,c,n,n)),dtype=torch.float32) for c,n in sizes] for _ in range(3)]
        pre,post,translated=groups
        valid=np.ones((24,24),bool);valid[:4,:4]=False
        expected=feature_difference(translated,post,valid)
        expected_raw=feature_difference(pre,post,valid)
        groups=[[a.to(device) for a in group] for group in groups]
        trace={}
        result,raw=tensor_feature_scores(groups[0],groups[1],groups[2],valid,trace)
        self.assertEqual(result.device.type,device)
        np.testing.assert_allclose(result.cpu().numpy(),expected,rtol=2e-6,atol=2e-6)
        np.testing.assert_allclose(raw.cpu().numpy(),expected_raw,rtol=2e-6,atol=2e-6)
        self.assertIn('score_block_0_saturated_post_first_channels',trace)
        # Constant and single-observation support must match NumPy too.
        one=np.zeros_like(valid);one[10,10]=True
        result,_=tensor_feature_scores(groups[0],groups[1],valid=one)
        np.testing.assert_allclose(result.cpu().numpy(),feature_difference(pre,post,one),rtol=2e-6,atol=2e-6)
        const=[torch.ones((1,3,8,8),device=device)]
        result,_=tensor_feature_scores(const,const)
        self.assertFalse(result.any())
        with self.assertRaisesRegex(ValueError,'No valid'):
            tensor_feature_scores(groups[0],groups[1],valid=np.zeros_like(valid))

    def test_tensor_scoring_matches_reference_on_cpu(self):self.check_scores('cpu')

    @unittest.skipUnless(torch.cuda.is_available(),'CUDA is not exposed in this environment')
    def test_tensor_scoring_matches_reference_on_cuda(self):self.check_scores('cuda')

    def test_score_pair_encodes_each_image_only_once(self):
        class Encoder(nn.Module):
            def __init__(self):super().__init__();self.calls=0
            def forward(self,x):self.calls+=1;return [x,x,x,x]
        class Translator(nn.Module):
            def forward(self,style,content):return content
        model=SARUCDFormer.__new__(SARUCDFormer);nn.Module.__init__(model)
        model.encoder=Encoder();model.translator=Translator();model.decoder=nn.Identity()
        model.register_buffer('mean',torch.zeros(1,3,1,1));model.register_buffer('std',torch.ones(1,3,1,1))
        torch.manual_seed(12);pre=torch.rand(1,3,16,16);post=torch.rand_like(pre)
        expected_main=model.score(pre,post);expected_raw=model.score(pre,post,translate=False)
        model.encoder.calls=0;trace={}
        main,raw=model.score_pair(pre,post,trace=trace)
        self.assertEqual(model.encoder.calls,3)
        np.testing.assert_allclose(main,expected_main,rtol=2e-6,atol=2e-6)
        np.testing.assert_allclose(raw,expected_raw,rtol=2e-6,atol=2e-6)
        self.assertIn('vgg_pre_block_0_first_channels',trace)
        # Fixed training targets use the same score but keep the mixing map on device.
        trace={}
        target=model.target(pre,post,trace=trace)
        expected=feature_difference([pre]*4,[post]*4)
        expected=(expected-expected.min())/(expected.max()-expected.min()+np.exp(-10))
        np.testing.assert_allclose(trace['change_weight'],expected,rtol=2e-6,atol=2e-6)
        self.assertEqual(target['content'].device,pre.device)


if __name__=='__main__':unittest.main()
