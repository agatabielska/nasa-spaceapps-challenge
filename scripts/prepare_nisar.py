"""Download NISAR GCOV granules (ASF) and convert / crop them to GeoTIFFs.

Examples:
  python scripts/prepare_nisar.py -c configs/nisar_unlabeled.yaml --download --extract
  python scripts/prepare_nisar.py -c configs/nisar_unlabeled.yaml --extract data.nisar.bbox=[699000,6168000,705000,6175000]

Granules are processed in chronological order: earliest = T1, latest = T2. Output files
are the ones listed in data.nisar.t1_files / t2_files (same order as data.nisar.polarizations).
"""
from pathlib import Path

from src.cdet.cli import build_parser, parse_config
from src.cdet.data.nisar_preprocess import acquisition_time, download_granules, extract_gcov_to_geotiff


def main() -> None:
    parser = build_parser(__doc__)
    parser.add_argument("--download", action="store_true", help="download granules from ASF")
    parser.add_argument("--extract", action="store_true", help="convert .h5 -> cropped GeoTIFFs")
    cfg, args = parse_config(parser)
    nc = cfg.data.nisar
    if (args.download or args.extract) and len(nc.granules) != 2:
        parser.error(
            "data.nisar.granules must contain exactly two granule IDs "
            "(configure them in your NISAR YAML file)"
        )
    granules = sorted(nc.granules, key=acquisition_time)  # T1 = earliest

    if args.download:
        download_granules(granules, nc.raw_dir)
    if args.extract:
        for granule, tif_list in zip(granules, (nc.t1_files, nc.t2_files)):
            out_paths = dict(zip(nc.polarizations, tif_list))
            extract_gcov_to_geotiff(
                str(Path(nc.raw_dir) / f"{granule}.h5"), out_paths,
                frequency=nc.frequency, bbox=list(nc.bbox) if nc.bbox else None, epsg=nc.epsg,
            )


if __name__ == "__main__":
    main()
