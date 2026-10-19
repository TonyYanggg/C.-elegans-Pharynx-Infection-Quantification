"""Input validation, project persistence, and exports."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import tifffile

SCHEMA_VERSION = 1
OBJECT_COLUMNS = ["object_id", "label_value", "morphology", "inclusion", "review_status", "accepted_for_tissue_measurement", "pixel_count", "area_um2",
                  "equivalent_diameter_um", "raw_mean_intensity", "raw_integrated_intensity", "background_mean",
                  "background_pixel_count", "corrected_mean_intensity", "corrected_integrated_intensity",
                  "count_contribution", "count_unresolved", "individual_area_unresolved"]


def read_measurement_tiff(path: str | Path) -> tuple[np.ndarray, dict[str, Any]]:
    """Read a grayscale 2D TIFF without converting quantitative pixels."""
    path = Path(path)
    with tifffile.TiffFile(path) as tif:
        series = tif.series[0]
        if len(tif.series) != 1 or len(series.shape) != 2 or series.axes != "YX":
            raise ValueError(f"Only a single two-dimensional grayscale TIFF is supported; found axes={series.axes}, shape={series.shape}.")
        page = series.pages[0]
        if page.samplesperpixel != 1 or page.photometric.name not in {"MINISBLACK", "MINISWHITE"}:
            raise ValueError("RGB and multichannel images are not supported. Open a single-channel grayscale TIFF.")
        image = series.asarray()
        if image.ndim != 2 or not np.issubdtype(image.dtype, np.number):
            raise ValueError("The TIFF did not contain a supported 2D numeric image.")
        if image.size == 0:
            raise ValueError("The TIFF image is empty.")
        if not np.isfinite(image).all():
            raise ValueError("The TIFF contains non-finite pixel values and cannot be measured safely.")
        metadata: dict[str, Any] = {"axes": series.axes, "shape": list(image.shape), "dtype": str(image.dtype)}
        tag_names = ("DateTime", "Make", "Model", "Software", "ImageDescription", "DocumentName", "HostComputer", "Artist", "Copyright")
        metadata["tiff_tags"] = {name: str(page.tags[name].value) for name in tag_names if name in page.tags}
        ome = tif.ome_metadata
        if ome:
            metadata["ome_metadata_xml"] = ome
            import xml.etree.ElementTree as ET
            root = ET.fromstring(ome)
            pixels = next((element for element in root.iter() if element.tag.endswith("Pixels")), None)
            if pixels is not None:
                x, y = pixels.get("PhysicalSizeX"), pixels.get("PhysicalSizeY")
                if x and y and pixels.get("PhysicalSizeXUnit", "µm") in {"µm", "um", "micrometer"} and pixels.get("PhysicalSizeYUnit", "µm") in {"µm", "um", "micrometer"}:
                    pixel_size = [float(y), float(x)]
                    if all(np.isfinite(value) and value > 0 for value in pixel_size):
                        metadata["pixel_size_um"] = pixel_size
        if "pixel_size_um" not in metadata:
            xres, yres = page.tags.get("XResolution"), page.tags.get("YResolution")
            unit = page.tags.get("ResolutionUnit")
            if xres and yres and unit and unit.value in (2, 3):
                per_unit_um = 25400 if unit.value == 2 else 10000
                metadata["pixel_size_um"] = [per_unit_um / float(yres.value), per_unit_um / float(xres.value)]
        return image, metadata


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def blank_project(image_path: str | Path, image: np.ndarray, metadata: dict[str, Any], identifiers: dict[str, Any] | None = None) -> dict[str, Any]:
    path = Path(image_path).resolve()
    return {
        "schema_version": SCHEMA_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "updated_utc": datetime.now(timezone.utc).isoformat(),
        "source": {"path": str(path), "sha256": sha256_file(path), **metadata},
        "identifiers": {"experiment_id": "", "trial_id": "", "strain": "", "worm_id": "", "observation_id": "", "observation_time": "", "study_design": "cross_sectional", "observation_status": "scorable", "coverage_reviewed": False, "count_resolvable": True, **(identifiers or {})},
        "annotations": {},
        "background_suitable": True,
        "measurement_status": "not_run",
        "measurement_stale": True,
    }


def save_project(folder: str | Path, metadata: dict[str, Any], masks: dict[str, np.ndarray], image: np.ndarray) -> Path:
    """Atomically save JSON metadata and lossless masks outside the source folder."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    metadata = dict(metadata)
    metadata["updated_utc"] = datetime.now(timezone.utc).isoformat()
    with tempfile.NamedTemporaryFile(dir=folder, suffix=".npz", delete=False) as handle:
        temp_masks = Path(handle.name)
    try:
        np.savez_compressed(temp_masks, **{k: np.asarray(v) for k, v in masks.items()})
        os.replace(temp_masks, folder / "masks.npz")
    finally:
        temp_masks.unlink(missing_ok=True)
    metadata["mask_file"] = "masks.npz"
    metadata["measurement_status"] = "stale" if metadata.get("measurement_stale", True) else metadata.get("measurement_status", "current")
    target = folder / "project.json"
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=folder, suffix=".json", delete=False) as handle:
        temp_json = Path(handle.name)
        json.dump(metadata, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
    try:
        os.replace(temp_json, target)
    finally:
        temp_json.unlink(missing_ok=True)
    return target


def load_project(project_json: str | Path) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    path = Path(project_json)
    metadata = json.loads(path.read_text(encoding="utf-8"))
    if metadata.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Unsupported project schema version: {metadata.get('schema_version')}")
    masks_path = path.parent / metadata.get("mask_file", "masks.npz")
    with np.load(masks_path, allow_pickle=False) as stored:
        masks = {key: stored[key] for key in stored.files}
    source = Path(metadata["source"]["path"])
    if not source.is_file():
        raise FileNotFoundError(f"Source TIFF is missing: {source}")
    if sha256_file(source) != metadata["source"]["sha256"]:
        raise ValueError("The source TIFF checksum changed since this project was created.")
    return metadata, masks


def export_measurements(folder: str | Path, image: np.ndarray, metadata: dict[str, Any], masks: dict[str, np.ndarray]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from .measurements import estimate_background, measure_observation

    background = estimate_background(image, masks["background"], suitable=metadata.get("background_suitable", True))
    pixel = metadata["source"].get("pixel_size_um")
    object_rows, summary = measure_observation(image, masks, {int(k): v for k, v in metadata.get("annotations", {}).items()}, background=background,
                                               pixel_size_um=tuple(pixel) if pixel else None,
                                               identifiers=metadata.get("identifiers", {}))
    summary.update({"source_path": metadata["source"]["path"], "source_sha256": metadata["source"]["sha256"], "measurement_stale": False})
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    _write_csv(folder / "objects.csv", object_rows)
    _write_csv(folder / "observations.csv", [summary])
    mask_stack = np.stack([np.asarray(masks[name], dtype=np.uint16) for name in ("bulb", "assessable", "objects", "diffuse", "background")])
    tifffile.imwrite(folder / "approved_masks.tif", mask_stack, metadata={"axes": "CYX", "Channel": {"Name": ["bulb", "assessable", "objects", "diffuse", "background"]}})
    _write_qc_overlay(folder / "qc_overlay.tif", image, masks)
    metadata["measurement_status"] = "current"
    metadata["measurement_stale"] = False
    metadata["last_measurement_utc"] = datetime.now(timezone.utc).isoformat()
    metadata["object_measurements"] = object_rows
    metadata["measurement_summary"] = summary
    save_project(folder, metadata, masks, image)
    return object_rows, summary


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        columns = OBJECT_COLUMNS if path.name == "objects.csv" else []
        if not columns:
            path.write_text("\n", encoding="utf-8")
            return
    else:
        columns = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_qc_overlay(path: Path, image: np.ndarray, masks: dict[str, np.ndarray]) -> None:
    raw = np.asarray(image, dtype=np.float64)
    low, high = np.percentile(raw, (1, 99.8))
    gray = np.clip((raw - low) / max(high - low, 1.0), 0, 1)
    rgb = np.repeat(gray[..., None], 3, axis=-1)
    from scipy.ndimage import binary_erosion
    bulb = np.asarray(masks["bulb"], bool)
    edges = bulb & ~binary_erosion(bulb)
    rgb[edges, 1] = 1.0
    obj = np.asarray(masks["objects"]) > 0
    diff = np.asarray(masks["diffuse"], bool)
    bg = np.asarray(masks["background"], bool)
    rgb[obj, 0] = 1.0
    rgb[diff, 0] = 1.0
    rgb[diff, 2] = 1.0
    rgb[bg, 1] = 0.7
    tifffile.imwrite(path, np.round(rgb * 255).astype(np.uint8), photometric="rgb", metadata={"description": "Display-only QC overlay; not quantitative image data"})
