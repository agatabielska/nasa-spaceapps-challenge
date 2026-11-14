"""Train one model.

Examples:
  python scripts/train.py -c configs/oscd_siamese_bcedice.yaml
  python scripts/train.py -c configs/oscd_siamese_bcedice.yaml --run-name my_run optim.lr=0.0003
  python scripts/train.py -c configs/oscd_siamese_focal.yaml logging.mode=disabled trainer.fast_dev_run=true
"""
from src.cdet.cli import build_parser, parse_config
from src.cdet.logging_utils import resolve_run_name
from src.cdet.training.runner import run_training


def main() -> None:
    cfg, _ = parse_config(build_parser(__doc__))
    run_name = resolve_run_name(cfg)
    result = run_training(cfg, run_name=run_name)
    print(f"\nRun '{result.run_name}' finished. Best {cfg.trainer.monitor}: {result.best_score:.4f}")
    print(f"Best checkpoint: {result.best_ckpt_path}")
    for metrics in result.test_metrics:
        print("Test:", metrics)


if __name__ == "__main__":
    main()
