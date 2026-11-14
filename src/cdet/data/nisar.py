"""NISAR scene loading from prepared GeoTIFFs."""
from src.cdet.data.base import Scene
from src.cdet.data.providers import LocalRasterProvider


def load_nisar_scene(cfg) -> Scene:
    provider = LocalRasterProvider()
    t1, crs, transform = provider.load(type("Acq", (), {"date": "T1", "files": tuple(cfg.t1_files)})())
    t2, crs2, _ = provider.load(type("Acq", (), {"date": "T2", "files": tuple(cfg.t2_files)})())
    if t1.shape != t2.shape or crs != crs2:
        raise ValueError("NISAR T1 and T2 must be co-registered with matching CRS")
    return Scene(t1, t2, name="nisar", band_names=tuple(cfg.polarizations), crs=crs, transform=transform)
