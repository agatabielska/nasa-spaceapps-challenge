"""Data-understanding and prediction plots. Figures are saved to outputs/figures/.

Examples:
  python scripts/visualize.py --plot oscd-scene -c configs/oscd_siamese_bcedice.yaml --city bordeaux
  python scripts/visualize.py --plot oscd-balance -c configs/oscd_siamese_bcedice.yaml
  python scripts/visualize.py --plot oscd-bands -c configs/oscd_siamese_bcedice.yaml --city paris
  python scripts/visualize.py --plot nisar -c configs/nisar_unlabeled.yaml
  python scripts/visualize.py --plot predict -c configs/oscd_siamese_bcedice.yaml --city dubai --ckpt path/to.ckpt
"""
from pathlib import Path

import matplotlib.pyplot as plt

from src.cdet.cli import build_parser, parse_config
from src.cdet.data.nisar import load_nisar_scene
from src.cdet.data.oscd import TEST_CITIES, TRAIN_CITIES, load_scene
from src.cdet.data.transforms import normalized_to_db
from src.cdet.baselines import log_ratio_change
from src.cdet.viz import eda, predictions


def _save(fig, cfg, name: str, show: bool) -> None:
    out = Path(cfg.output_dir) / "figures"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{name}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    print(f"Saved {path}")
    if show:
        plt.show()


def main() -> None:
    parser = build_parser(__doc__)
    parser.add_argument("--plot", required=True, choices=["oscd-scene", "oscd-balance", "oscd-bands", "nisar", "predict"])
    parser.add_argument("--city", default="bordeaux")
    parser.add_argument("--ckpt", default=None, help="checkpoint (predict)")
    parser.add_argument("--threshold", type=float, default=None, help="override decision threshold")
    parser.add_argument("--k", type=float, default=2.0, help="log-ratio baseline: threshold = mean + k*std")
    parser.add_argument("--show", action="store_true", help="also open the figure window")
    cfg, args = parse_config(parser)
    d = cfg.data

    if args.plot == "oscd-scene":
        scene = load_scene(d.data_dir, args.city, tuple(d.bands), d.scale)
        _save(eda.plot_oscd_scene(scene), cfg, f"scene_{args.city}", args.show)
    elif args.plot == "oscd-balance":
        masks = {c: load_scene(d.data_dir, c, tuple(d.bands), d.scale).mask for c in TRAIN_CITIES + TEST_CITIES}
        _save(eda.plot_class_balance(masks), cfg, "class_balance", args.show)
    elif args.plot == "oscd-bands":
        scene = load_scene(d.data_dir, args.city, tuple(d.bands), d.scale)
        _save(eda.plot_band_distributions(scene, list(d.bands)), cfg, f"bands_{args.city}", args.show)
    elif args.plot == "nisar":
        nc = d.nisar
        scene = load_nisar_scene(nc)
        names = list(nc.polarizations)
        _save(eda.plot_sar_scene(scene, names, nc.db_min, nc.db_max), cfg, "nisar_scene", args.show)
        diff, change = log_ratio_change(
            normalized_to_db(scene.t1, nc.db_min, nc.db_max),
            normalized_to_db(scene.t2, nc.db_min, nc.db_max), k=args.k,
        )
        _save(eda.plot_difference_map(diff, change), cfg, "nisar_log_ratio", args.show)
    elif args.plot == "predict":
        if not args.ckpt:
            parser.error("--ckpt is required for 'predict'")
        from src.cdet.inference import load_module, predict_scene

        module = load_module(args.ckpt)
        if d.name == "oscd":
            scene = load_scene(d.data_dir, args.city, tuple(d.bands), d.scale)
        else:
            scene = load_nisar_scene(d.nisar)
        threshold = args.threshold if args.threshold is not None else float(module.hparams.threshold)
        prob = predict_scene(module, scene.t1, scene.t2)
        fig = predictions.plot_prediction(scene.t1, scene.t2, prob, threshold, gt=scene.mask, title=scene.name)
        _save(fig, cfg, f"prediction_{scene.name}", args.show)


if __name__ == "__main__":
    main()
