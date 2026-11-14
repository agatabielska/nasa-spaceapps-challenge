"""Evaluate a checkpoint on the test split using the validation-optimal threshold.

Example:
  python scripts/evaluate.py -c configs/oscd_siamese_bcedice.yaml --ckpt outputs/oscd/<run>/checkpoints/best-epoch042.ckpt
"""
from src.cdet.cli import build_parser, parse_config
from src.cdet.evaluate import evaluate_checkpoint
from src.cdet.logging_utils import resolve_run_name


def main() -> None:
    parser = build_parser(__doc__)
    parser.add_argument("--ckpt", required=True, help="path to a .ckpt file")
    cfg, args = parse_config(parser)
    run_name = resolve_run_name(cfg, template="eval_{model}_{loss}_{timestamp}")
    print(evaluate_checkpoint(cfg, args.ckpt, run_name))


if __name__ == "__main__":
    main()
