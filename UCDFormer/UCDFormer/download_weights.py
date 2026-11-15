"""Fetch original initialization weights into the workspace only."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/".deps"))
import hashlib
import torch
import gdown

out=ROOT/"weights"; out.mkdir(exist_ok=True)
vgg=out/"vgg16-397923af.pth"
if not vgg.exists():
    torch.hub.download_url_to_file("https://download.pytorch.org/models/vgg16-397923af.pth",str(vgg)+".part",hash_prefix="397923af")
    Path(str(vgg)+".part").replace(vgg)
print("VGG_READY",vgg,flush=True)
generator=out/"gen_00794001.pt"
if not generator.exists():
    result=gdown.download(id="1E-0uBlHWBCwwNpydbKjDYsFnEZWtbubB",output=str(generator)+".part",quiet=False)
    if not result: raise RuntimeError("Original generator download unavailable")
    Path(result).replace(generator)
print("GENERATOR_READY",generator,flush=True)
