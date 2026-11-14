"""Shared command-line plumbing for the scripts in ``scripts/``."""
import argparse
from typing import Tuple

from omegaconf import DictConfig

from src.cdet.config import load_config


def build_parser(description: str) -> argparse.ArgumentParser:
    """Parser with the arguments every script shares (configs, run name, overrides)."""
    parser = argparse.ArgumentParser(
        description=description, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "-c", "--config", action="append", default=[],
        help="YAML config; repeat to merge several (later files win)",
    )
    parser.add_argument("--run-name", default=None, help="run name (sets logging.run_name)")
    parser.add_argument(
        "overrides", nargs="*",
        help="dotlist overrides, e.g. optim.lr=0.0003 loss.name=focal logging.mode=offline",
    )
    return parser


def parse_config(parser: argparse.ArgumentParser) -> Tuple[DictConfig, argparse.Namespace]:
    """Parse argv and return the merged config plus the raw argparse namespace."""
    args = parser.parse_args()
    cfg = load_config(args.config, args.overrides)
    if args.run_name:
        cfg.logging.run_name = args.run_name
    return cfg, args
