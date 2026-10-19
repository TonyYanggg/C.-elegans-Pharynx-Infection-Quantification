# Local project format, schema 1

A project is a `.cephq` directory outside the public repository. `project.json` stores schema/version fields, original source path and SHA-256, image dimensions/dtype/acquisition calibration when available, study identifiers, review decisions, and measurement state. `masks.npz` stores lossless 2D arrays named `bulb`, `assessable`, `objects`, `diffuse`, and `background`. The original TIFF is referenced in place, not copied into the project.

Exports are `objects.csv` (one row per labeled object), `observations.csv` (one row per worm observation), `approved_masks.tif`, and `qc_overlay.tif`. The QC overlay is a display rendering and is never used for measurement. Object labels retain numeric mask values; displayed IDs use `P001`, `P002`, and so forth. Project loading checks the source-file checksum and refuses a changed/missing source instead of silently measuring different pixels.

The project preserves experiment, trial, strain, worm, observation, time, and cross-sectional/longitudinal design fields. It does not synthesize timepoints or independent sample counts. Schema changes require a version increment and a migration note.
