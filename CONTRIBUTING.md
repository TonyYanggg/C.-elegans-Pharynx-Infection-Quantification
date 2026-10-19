# Contributing

Keep changes small, tested, and limited to this application's stated 2D manual workflow. Preserve source TIFF values and make any measurement-affecting change explicit in `docs/measurement_spec.md`, `docs/decisions.md`, tests, and `CHANGELOG.md`.

Create a virtual environment, install `python -m pip install -e ".[dev]"`, then run `python -m pytest`. Use synthetic examples for public tests. Do not add real microscopy data, private annotations, trained weights, manuscript material, or personal computer paths. Do not describe synthetic checks as biological validation.

Before proposing a feature, check the current scope and validation limits in `README.md` and `PROJECT_STATE.md`. The project license is pending confirmation; do not assume permission to relicense contributions.
