# Development instructions

This project is a human-guided 2D TIFF measurement tool. The human permanently determines anatomy, tissue/lumen inclusion, ambiguous objects, splits/merges, diffuse signal and uncertainty. Measurements and any later puncta model use pure-RFP pixels only. A separate reference is visual context; never register it, transfer coordinates, or measure it.

Keep original quantitative pixels unchanged. Preserve negative corrected values; do not call an image-defined punctum a bacterial cell. Keep uncertainty and incomplete review explicit. Do not publish private images, annotations, outputs, paths, manuscripts or model weights. Do not edit research Word documents or SOPs unless asked.

Session start: read this file, `PROJECT_STATE.md`, and the relevant docs; inspect Git status, branch and remotes before editing. Preserve unrelated changes and stage only task files. Record new user requirements in affected docs and tests. Keep README for users and AGENTS for development.

Commands after installing the package in a virtual environment:

- `python -m pytest`
- `celegans-pharynx-quant`
- `cephq-demo <output-directory>`
- `cephq-measure <project.json>`

Definition of done: code and documentation agree; meaningful checks pass; staged files are reviewed for private content; the task changes are committed and pushed on the authorized branch; remote state is verified. Do not change ownership, license, identity, remotes, protection or history without authorization. License remains pending confirmation.
