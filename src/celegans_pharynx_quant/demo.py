"""Generate a clearly synthetic demo project and its expected measurements."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import tifffile

from .io import blank_project, export_measurements, save_project


def make_demo(output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    yy, xx = np.mgrid[:96, :128]
    image = np.full((96, 128), 12, dtype=np.uint16)
    image += ((xx + yy) % 4).astype(np.uint16)
    bulb = ((xx - 62) / 45) ** 2 + ((yy - 48) / 34) ** 2 <= 1
    assessable = bulb & (xx < 95)
    objects = np.zeros(image.shape, dtype=np.uint16)
    objects[(xx - 42) ** 2 + (yy - 42) ** 2 <= 4] = 1
    objects[(xx - 75) ** 2 + (yy - 53) ** 2 <= 6] = 2
    diffuse = ((xx - 65) / 20) ** 2 + ((yy - 47) / 11) ** 2 <= 1
    background = ~bulb & (xx > 8) & (xx < 30) & (yy > 8) & (yy < 30)
    image[objects == 1] = 112
    image[objects == 2] = 72
    image[diffuse] = 36
    source = output / "synthetic_demo_pure_rfp.tif"
    tifffile.imwrite(source, image, metadata={"axes": "YX", "Description": "SYNTHETIC demo data; not biological data"})
    masks = {"bulb": bulb.astype(np.uint8), "assessable": assessable.astype(np.uint8), "objects": objects,
             "diffuse": diffuse.astype(np.uint8), "background": background.astype(np.uint8)}
    metadata = blank_project(source, image, {"axes": "YX", "shape": list(image.shape), "dtype": str(image.dtype)},
                             {"experiment_id": "SYNTHETIC", "trial_id": "SYNTHETIC", "worm_id": "SYNTHETIC-001",
                              "observation_id": "SYNTHETIC-T0", "coverage_reviewed": True})
    metadata["annotations"] = {
        "1": {"object_id": "P001", "morphology": "discrete_punctum", "inclusion": "tissue_associated", "review_status": "reviewed"},
        "2": {"object_id": "P002", "morphology": "discrete_punctum", "inclusion": "luminal", "review_status": "reviewed"},
    }
    project = output / "synthetic_demo.cephq"
    save_project(project, metadata, masks, image)
    export_measurements(project, image, metadata, masks)
    (project / "SYNTHETIC_DATA_NOTICE.txt").write_text("This is synthetic software demonstration data. It is not microscopy data and is not biological validation.\n", encoding="utf-8")
    return project


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a public-safe synthetic example project.")
    parser.add_argument("output", type=Path, help="Output directory")
    args = parser.parse_args()
    project = make_demo(args.output)
    print(f"Created SYNTHETIC demo project: {project}")
