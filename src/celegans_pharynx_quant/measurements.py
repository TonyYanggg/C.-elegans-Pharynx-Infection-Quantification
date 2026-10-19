"""Deterministic measurements from human-approved two-dimensional masks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from skimage.measure import regionprops


@dataclass(frozen=True)
class BackgroundResult:
    pixel_count: int
    mean: float | None
    standard_deviation: float | None
    suitable: bool
    reason: str | None = None


def estimate_background(image: np.ndarray, background_mask: np.ndarray, *, suitable: bool = True) -> BackgroundResult:
    """Estimate constant background from the union of reviewed background ROIs."""
    pixels = np.asarray(image)[np.asarray(background_mask, dtype=bool)]
    if pixels.size == 0:
        return BackgroundResult(0, None, None, False, "no_reviewed_background_pixels")
    if not suitable:
        return BackgroundResult(int(pixels.size), float(np.mean(pixels, dtype=np.float64)),
                                float(np.std(pixels, dtype=np.float64)), False,
                                "background_marked_unsuitable")
    values = pixels.astype(np.float64, copy=False)
    return BackgroundResult(int(values.size), float(values.mean()), float(values.std()), True)


def measure_objects(
    image: np.ndarray,
    object_labels: np.ndarray,
    annotations: dict[int, dict[str, Any]],
    *,
    background: BackgroundResult,
    pixel_size_um: tuple[float, float] | None = None,
) -> list[dict[str, Any]]:
    """Measure labeled object masks using original image pixels."""
    image = np.asarray(image)
    labels = np.asarray(object_labels)
    if image.ndim != 2 or labels.shape != image.shape:
        raise ValueError("image and object labels must be matching two-dimensional arrays")
    if pixel_size_um is not None and (len(pixel_size_um) != 2 or min(pixel_size_um) <= 0):
        raise ValueError("pixel_size_um must contain two positive values")

    result: list[dict[str, Any]] = []
    for prop in regionprops(labels.astype(np.int32, copy=False)):
        label = int(prop.label)
        annotation = annotations.get(label, {})
        morphology = annotation.get("morphology", "uncertain")
        inclusion = annotation.get("inclusion", "uncertain")
        included = (inclusion == "tissue_associated" and annotation.get("review_status") == "reviewed"
                    and morphology not in {"uncertain", "artefact"})
        discrete = morphology == "discrete_punctum"
        count = annotation.get("expert_count")
        individual_area_valid = not annotation.get("shared_cluster", False)
        pixels = image[labels == label].astype(np.float64, copy=False)
        raw_mean = float(pixels.mean())
        raw_integrated = float(pixels.sum(dtype=np.float64))
        record: dict[str, Any] = {
            "object_id": annotation.get("object_id", f"P{label:03d}"),
            "label_value": label,
            "morphology": morphology,
            "inclusion": inclusion,
            "review_status": annotation.get("review_status", "pending"),
            "accepted_for_tissue_measurement": included,
            "pixel_count": int(prop.area) if individual_area_valid else None,
            "area_um2": (float(prop.area * pixel_size_um[0] * pixel_size_um[1])
                         if pixel_size_um and individual_area_valid else None),
            "equivalent_diameter_um": (float(prop.equivalent_diameter_area * np.sqrt(pixel_size_um[0] * pixel_size_um[1]))
                                       if pixel_size_um and individual_area_valid else None),
            "raw_mean_intensity": raw_mean,
            "raw_integrated_intensity": raw_integrated,
            "background_mean": background.mean if background.suitable else None,
            "background_pixel_count": background.pixel_count,
            "corrected_mean_intensity": raw_mean - background.mean if background.suitable and background.mean is not None else None,
            "corrected_integrated_intensity": raw_integrated - prop.area * background.mean
            if background.suitable and background.mean is not None else None,
            "count_contribution": (int(count) if count is not None and included and discrete
                                   else (None if included and discrete and annotation.get("shared_cluster", False)
                                         else (1 if included and discrete and annotation.get("review_status") == "reviewed" else 0))),
            "count_unresolved": bool(annotation.get("count_unresolved", False)),
            "individual_area_unresolved": not individual_area_valid,
        }
        result.append(record)
    return result


def measure_observation(
    image: np.ndarray,
    labels: dict[str, np.ndarray],
    annotations: dict[int, dict[str, Any]],
    *,
    background: BackgroundResult,
    pixel_size_um: tuple[float, float] | None = None,
    identifiers: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Measure object records and a one-row observation summary."""
    object_rows = measure_objects(image, labels["objects"], annotations,
                                  background=background, pixel_size_um=pixel_size_um)
    tissue = np.zeros(np.shape(image), dtype=bool)
    puncta = np.zeros_like(tissue)
    uncertain_excluded = np.zeros_like(tissue)
    diffuse = np.asarray(labels["diffuse"], dtype=bool)
    for row in object_rows:
        mask = np.asarray(labels["objects"]) == row["label_value"]
        if row["accepted_for_tissue_measurement"]:
            tissue |= mask
            if row["morphology"] == "discrete_punctum":
                puncta |= mask
        else:
            uncertain_excluded |= mask
    tissue |= diffuse
    bulb = np.asarray(labels["bulb"], dtype=bool)
    assessable = np.asarray(labels["assessable"], dtype=bool)
    accepted_pixels = np.asarray(image, dtype=np.float64)[tissue]
    raw_integrated = float(accepted_pixels.sum(dtype=np.float64)) if accepted_pixels.size else 0.0
    coverage = float(np.count_nonzero(assessable) / np.count_nonzero(bulb)) if np.any(bulb) else None
    reviewed = bool((identifiers or {}).get("coverage_reviewed", False))
    observation_status = (identifiers or {}).get("observation_status", "scorable")
    status = observation_status if observation_status in {"uncertain", "unscorable"} else ("complete" if reviewed and np.any(bulb) else "partial")
    objects_reviewed = all(row["review_status"] == "reviewed" and row["morphology"] != "uncertain" and row["inclusion"] != "uncertain" for row in object_rows)
    clusters_counted = all(not row["count_unresolved"] or row["count_contribution"] for row in object_rows)
    count_valid = bool(reviewed and status == "complete" and observation_status == "scorable" and objects_reviewed and clusters_counted and (identifiers or {}).get("count_resolvable", True))
    included_discrete = [r for r in object_rows if r["morphology"] == "discrete_punctum" and r["accepted_for_tissue_measurement"]]
    count_unresolved = sum(1 for r in included_discrete if r["count_unresolved"])
    count = sum(int(r["count_contribution"] or 0) for r in included_discrete) if count_valid else None
    summary: dict[str, Any] = {
        **(identifiers or {}),
        "review_status": status,
        "count_puncta": count,
        "count_missing_reason": None if count is not None else ("unscorable_observation" if observation_status == "unscorable" else ("uncertain_observation" if observation_status == "uncertain" else ("partial_coverage" if status != "complete" else "count_unresolvable"))),
        "count_confirmed_unresolved_clusters": count_unresolved,
        "discrete_puncta_area_px": int(np.count_nonzero(puncta)),
        "diffuse_tissue_area_px": int(np.count_nonzero(diffuse)),
        "accepted_tissue_positive_area_px": int(np.count_nonzero(tissue)),
        "posterior_bulb_area_px": int(np.count_nonzero(bulb)),
        "assessable_tissue_area_px": int(np.count_nonzero(assessable)),
        "assessable_bulb_fraction": coverage,
        "uncertain_or_excluded_area_px": int(np.count_nonzero(uncertain_excluded)),
        "tissue_positive_fraction": float(np.count_nonzero(tissue & assessable) / np.count_nonzero(assessable)) if np.any(assessable) else None,
        "accepted_tissue_raw_mean_intensity": float(accepted_pixels.mean()) if accepted_pixels.size else None,
        "accepted_tissue_raw_integrated_intensity": raw_integrated,
        "accepted_tissue_corrected_mean_intensity": float(accepted_pixels.mean() - background.mean)
        if accepted_pixels.size and background.suitable and background.mean is not None else None,
        "accepted_tissue_corrected_integrated_intensity": raw_integrated - accepted_pixels.size * background.mean
        if background.suitable and background.mean is not None else None,
        "background_mean": background.mean if background.suitable else None,
        "background_pixel_count": background.pixel_count,
        "background_standard_deviation": background.standard_deviation,
        "pixel_size_y_um": pixel_size_um[0] if pixel_size_um else None,
        "pixel_size_x_um": pixel_size_um[1] if pixel_size_um else None,
    }
    return object_rows, summary
