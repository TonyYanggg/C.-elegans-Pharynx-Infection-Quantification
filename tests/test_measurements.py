import numpy as np

from celegans_pharynx_quant.measurements import estimate_background, measure_observation, measure_objects


def test_background_corrected_measurement_uses_float_and_keeps_negative_values():
    image = np.array([[2, 4, 8], [0, 0, 0]], dtype=np.uint16)
    objects = np.zeros(image.shape, dtype=np.uint16)
    objects[0, :2] = 1
    bg = np.zeros(image.shape, dtype=bool)
    bg[1] = True
    bg[0, 2] = True
    estimate = estimate_background(image, bg)
    row = measure_objects(image, objects, {1: {"review_status": "reviewed", "morphology": "discrete_punctum", "inclusion": "tissue_associated"}}, background=estimate)[0]
    assert estimate.mean == 2
    assert row["pixel_count"] == 2
    assert row["area_um2"] is None
    assert row["raw_integrated_intensity"] == 6
    assert row["corrected_integrated_intensity"] == 2
    calibrated = measure_objects(image, objects, {1: {"review_status": "reviewed", "morphology": "discrete_punctum", "inclusion": "tissue_associated"}}, background=estimate, pixel_size_um=(2.0, 3.0))[0]
    assert calibrated["area_um2"] == 12.0
    bg[:] = False
    bg[0, 2] = True
    estimate = estimate_background(image, bg)
    row = measure_objects(image, objects, {1: {"review_status": "reviewed", "morphology": "discrete_punctum", "inclusion": "tissue_associated"}}, background=estimate)[0]
    assert row["corrected_mean_intensity"] < 0


def test_union_avoids_double_counting_and_separates_diffuse_and_luminal():
    image = np.full((8, 8), 20, dtype=np.uint16)
    object_mask = np.zeros((8, 8), dtype=np.uint16)
    object_mask[2:5, 2:5] = 1
    diffuse = np.zeros((8, 8), dtype=np.uint8)
    diffuse[3:6, 3:6] = 1
    labels = {"objects": object_mask, "diffuse": diffuse, "bulb": np.ones((8, 8), dtype=np.uint8),
              "assessable": np.ones((8, 8), dtype=np.uint8), "background": np.zeros((8, 8), dtype=np.uint8)}
    anns = {1: {"morphology": "discrete_punctum", "inclusion": "tissue_associated", "review_status": "reviewed"}}
    _objects, summary = measure_observation(image, labels, anns, background=estimate_background(image, labels["background"]), identifiers={"coverage_reviewed": True})
    assert summary["accepted_tissue_positive_area_px"] == 14
    assert summary["discrete_puncta_area_px"] == 9
    assert summary["diffuse_tissue_area_px"] == 9
    assert summary["count_puncta"] == 1


def test_review_and_coverage_gates_and_shared_cluster_area():
    image = np.full((10, 10), 5, dtype=np.uint16)
    objects = np.zeros(image.shape, dtype=np.uint16)
    objects[2:4, 2:4] = 1
    ann = {1: {"object_id": "P001", "morphology": "discrete_punctum", "inclusion": "tissue_associated",
               "review_status": "reviewed", "shared_cluster": True, "expert_count": 2, "count_unresolved": True}}
    bg = estimate_background(image, np.zeros(image.shape, dtype=bool))
    row = measure_objects(image, objects, ann, background=bg)[0]
    assert row["pixel_count"] is None
    assert row["count_contribution"] == 2
    ann[1]["expert_count"] = None
    row = measure_objects(image, objects, ann, background=bg)[0]
    assert row["count_contribution"] is None
    labels = {"objects": objects, "diffuse": np.zeros_like(objects), "bulb": np.ones_like(objects),
              "assessable": np.zeros_like(objects), "background": np.zeros_like(objects)}
    _, summary = measure_observation(image, labels, ann, background=bg, identifiers={"coverage_reviewed": False})
    assert summary["count_puncta"] is None
    assert summary["review_status"] == "partial"
    assert summary["accepted_tissue_corrected_mean_intensity"] is None


def test_pending_or_luminal_object_is_not_counted_as_tissue_punctum():
    image = np.ones((4, 4), dtype=np.uint16)
    labels = np.ones((4, 4), dtype=np.uint16)
    ann = {1: {"morphology": "discrete_punctum", "inclusion": "luminal", "review_status": "reviewed"}}
    row = measure_objects(image, labels, ann, background=estimate_background(image, np.zeros((4, 4), bool)))[0]
    assert row["count_contribution"] == 0
    assert row["morphology"] == "discrete_punctum"
    labels = {"objects": labels, "diffuse": np.zeros((4, 4), dtype=np.uint8), "bulb": np.ones((4, 4), dtype=np.uint8),
              "assessable": np.ones((4, 4), dtype=np.uint8), "background": np.zeros((4, 4), dtype=np.uint8)}
    ann[1]["inclusion"] = "tissue_associated"
    ann[1]["review_status"] = "pending"
    _rows, summary = measure_observation(image, labels, ann, background=estimate_background(image, labels["background"]),
                                         identifiers={"coverage_reviewed": True})
    assert summary["accepted_tissue_positive_area_px"] == 0
    assert summary["count_puncta"] is None


def test_expert_count_for_shared_cluster_and_missing_expert_count():
    image = np.full((6, 6), 9, dtype=np.uint16)
    objects = np.zeros((6, 6), dtype=np.uint16)
    objects[2:4, 2:4] = 1
    labels = {"objects": objects, "diffuse": np.zeros_like(objects), "bulb": np.ones_like(objects),
              "assessable": np.ones_like(objects), "background": np.zeros_like(objects)}
    ann = {1: {"morphology": "discrete_punctum", "inclusion": "tissue_associated", "review_status": "reviewed",
               "shared_cluster": True, "expert_count": 2, "count_unresolved": True}}
    kwargs = {"background": estimate_background(image, labels["background"]), "identifiers": {"coverage_reviewed": True}}
    _rows, summary = measure_observation(image, labels, ann, **kwargs)
    assert summary["count_puncta"] == 2
    assert summary["count_confirmed_unresolved_clusters"] == 1
    ann[1]["expert_count"] = None
    _rows, summary = measure_observation(image, labels, ann, **kwargs)
    assert summary["count_puncta"] is None
    assert summary["count_missing_reason"] == "count_unresolvable"


def test_empty_positive_mask_and_unscorable_observation_are_missing():
    image = np.zeros((5, 5), dtype=np.uint16)
    labels = {"objects": np.zeros((5, 5), dtype=np.uint16), "diffuse": np.zeros((5, 5), dtype=np.uint8),
              "bulb": np.ones((5, 5), dtype=np.uint8), "assessable": np.zeros((5, 5), dtype=np.uint8),
              "background": np.zeros((5, 5), dtype=np.uint8)}
    rows, summary = measure_observation(image, labels, {}, background=estimate_background(image, labels["background"]),
                                         identifiers={"coverage_reviewed": True, "observation_status": "unscorable"})
    assert rows == []
    assert summary["accepted_tissue_raw_mean_intensity"] is None
    assert summary["count_puncta"] is None
    assert summary["count_missing_reason"] == "unscorable_observation"
    assert summary["tissue_positive_fraction"] is None


def test_reviewed_artifact_is_not_accepted_as_tissue_positive():
    image = np.full((4, 4), 20, dtype=np.uint16)
    objects = np.zeros(image.shape, dtype=np.uint16)
    objects[1:3, 1:3] = 1
    labels = {"objects": objects, "diffuse": np.zeros_like(objects), "bulb": np.ones_like(objects),
              "assessable": np.ones_like(objects), "background": np.zeros_like(objects)}
    annotations = {1: {"morphology": "artefact", "inclusion": "tissue_associated", "review_status": "reviewed"}}
    _rows, summary = measure_observation(image, labels, annotations, background=estimate_background(image, labels["background"]),
                                         identifiers={"coverage_reviewed": True})
    assert summary["accepted_tissue_positive_area_px"] == 0
    assert summary["count_puncta"] == 0
    assert summary["uncertain_or_excluded_area_px"] == 4
