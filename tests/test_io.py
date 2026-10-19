import numpy as np
import pytest
import tifffile
import csv

from celegans_pharynx_quant.io import blank_project, load_project, read_measurement_tiff, save_project, _write_csv


def test_project_reopen_preserves_masks_and_checks_source(tmp_path):
    source = tmp_path / "source.tif"
    image = np.arange(80, dtype=np.uint16).reshape(8, 10)
    tifffile.imwrite(source, image, metadata={"axes": "YX"})
    image_read, source_info = read_measurement_tiff(source)
    masks = {name: np.zeros(image.shape, dtype=np.uint8) for name in ("bulb", "assessable", "diffuse", "background")}
    masks["objects"] = np.zeros(image.shape, dtype=np.uint16)
    masks["objects"][1:3, 4:6] = 1
    metadata = blank_project(source, image_read, source_info)
    save_project(tmp_path / "project.cephq", metadata, masks, image)
    loaded_metadata, loaded_masks = load_project(tmp_path / "project.cephq" / "project.json")
    assert loaded_metadata["schema_version"] == 1
    np.testing.assert_array_equal(loaded_masks["objects"], masks["objects"])
    tifffile.imwrite(source, image + 1, metadata={"axes": "YX"})
    with pytest.raises(ValueError, match="checksum"):
        load_project(tmp_path / "project.cephq" / "project.json")


def test_tiff_reader_rejects_rgb_and_stacks(tmp_path):
    rgb = tmp_path / "rgb.tif"
    stack = tmp_path / "stack.tif"
    tifffile.imwrite(rgb, np.zeros((5, 6, 3), dtype=np.uint8), photometric="rgb")
    tifffile.imwrite(stack, np.zeros((2, 5, 6), dtype=np.uint16), metadata={"axes": "ZYX"})
    with pytest.raises(ValueError, match="two-dimensional"):
        read_measurement_tiff(stack)
    with pytest.raises(ValueError, match="two-dimensional"):
        read_measurement_tiff(rgb)


def test_empty_object_export_still_has_stable_headers(tmp_path):
    destination = tmp_path / "objects.csv"
    _write_csv(destination, [])
    with destination.open(encoding="utf-8-sig", newline="") as handle:
        assert "object_id" in next(csv.reader(handle))
