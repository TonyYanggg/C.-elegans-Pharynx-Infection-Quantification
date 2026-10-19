# Measurement specification, schema 1

All arrays are 2D and match the original grayscale quantitative TIFF. Measurements use the original numeric values; display contrast is only for viewing.

## Object measurements

- Pixel area is the number of labeled pixels. Calibrated area is pixel count × pixel size Y × pixel size X when both physical pixel sizes are present.
- Raw mean is the mean original pixel value in the object. Raw integrated intensity is the sum of those values in float64.
- Background is the mean of the union of reviewed background pixels, with pixel count and population standard deviation recorded. This is a constant background estimate.
- Corrected mean = raw mean − background mean. Corrected integrated = raw integrated − pixel count × background mean. Empty or unsuitable background makes corrected values missing; negative values are retained.
- Shared cluster masks can carry an expert count while individual area and diameter are missing.

## Observation measurements

- Tissue-positive area is the union of reviewed tissue-associated object masks and the diffuse signal mask. Overlap is counted once.
- Discrete puncta area and diffuse area are reported separately. Diffuse signal never contributes to punctum count.
- Whole-bulb count is missing unless the user confirms full review, marks count resolvable, and all annotated objects have reviewed, determinate morphology and inclusion. An unresolved shared cluster also needs an expert count.
- An explicitly unscorable observation always has a missing count with reason `unscorable_observation`.
- A partial observation remains `partial`; its count is not represented as a complete bulb count. An empty positive-pixel mean is missing, while the integrated sum of an empty union is zero.
- Positive area fraction uses the manually drawn assessable tissue ROI as denominator and is missing when that ROI is empty.
- `assessable_bulb_fraction` reports assessable ROI pixels divided by posterior-bulb ROI pixels; uncertain or excluded object masks are reported as a separate union area.
- Corrected mean over accepted positive pixels is distinct from whole-tissue or ROI mean.

Missing values are blank in CSV. `count_missing_reason`, `review_status`, `individual_area_unresolved`, and `measurement_stale` describe why a result is unavailable or no longer current. Fluorescence values are not bacterial counts.
