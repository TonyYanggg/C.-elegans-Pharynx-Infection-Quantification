# Validation record

Eleven software tests pass using generated images and masks with known values. They check background subtraction, negative corrected values, object area/intensity, overlap union, luminal exclusion, diffuse area/count separation, shared clusters, incomplete review, missing calibration, empty masks, source checksums, and unsupported RGB/stack inputs. The synthetic demo CLI completed and exported expected values.

The napari 0.9.2 viewer and annotation dock initialized on Windows. A GUI smoke check created a labeled polygon and confirmed undo and redo restore the expected mask pixel counts. This verifies widget and API compatibility, not a complete user-guided session.

The included demo is fully synthetic and is not biological validation. No representative microscope TIFF was supplied for this first implementation. The TIFF reader, microscope calibration interpretation, napari editing behavior, autosave recovery, and Fiji comparison still need a real user-run acceptance session before scientific use. CZI and 3D are outside this version.
