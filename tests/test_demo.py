import csv
import numpy as np
import tifffile

from celegans_pharynx_quant.demo import make_demo


def test_synthetic_demo_exports_are_marked_and_have_expected_values(tmp_path):
    project = make_demo(tmp_path)
    with (project / "observations.csv").open(encoding="utf-8-sig", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["experiment_id"] == "SYNTHETIC"
    assert row["count_puncta"] == "1"
    assert int(row["accepted_tissue_positive_area_px"]) > int(row["discrete_puncta_area_px"])
    assert (project / "SYNTHETIC_DATA_NOTICE.txt").is_file()
    masks = tifffile.imread(project / "approved_masks.tif")
    assert masks.dtype == np.uint16
    assert masks.shape[0] == 5
