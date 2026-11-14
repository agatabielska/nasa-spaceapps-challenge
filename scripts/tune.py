"""Optuna search (K-fold over cities). Writes the best parameters to configs/tuned/<study>.yaml.

Example:
  python scripts/tune.py -c configs/oscd_siamese_bcedice.yaml tune.n_trials=30 tune.study_name=bcedice_v1
Then train with the result:
  python scripts/train.py -c configs/oscd_siamese_bcedice.yaml -c configs/tuned/bcedice_v1.yaml
"""
from src.cdet.cli import build_parser, parse_config
from src.cdet.tuning import run_study


def main() -> None:
    cfg, _ = parse_config(build_parser(__doc__))
    run_study(cfg)


if __name__ == "__main__":
    main()
