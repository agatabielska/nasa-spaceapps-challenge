"""Pluggable satellite data sources and common scene containers."""

from src.cdet.data.base import Scene
from src.cdet.data.providers import (
    LocalRasterProvider,
    RasterAcquisition,
    TemporalSeries,
    build_temporal_series,
)

__all__ = [
    "Scene",
    "LocalRasterProvider",
    "RasterAcquisition",
    "TemporalSeries",
    "build_temporal_series",
]
