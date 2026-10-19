"""Batch remeasurement of saved, reviewed projects."""

from __future__ import annotations

import argparse
from pathlib import Path

from .io import export_measurements, load_project, read_measurement_tiff


def main() -> None:
    parser = argparse.ArgumentParser(description="Remeasure an existing celegans-pharynx-quant project.")
    parser.add_argument("project", type=Path, help="Path to project.json")
    args = parser.parse_args()
    metadata, masks = load_project(args.project)
    image, _ = read_measurement_tiff(metadata["source"]["path"])
    _objects, summary = export_measurements(args.project.parent, image, metadata, masks)
    print(f"Updated {args.project.parent}: status={summary['review_status']}, puncta={summary['count_puncta']}")
