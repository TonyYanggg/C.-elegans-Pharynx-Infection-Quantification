# Decisions

## First release

- Use napari to provide image display, layers, brush/erase editing, zoom, and independent viewing of a reference image.
- Limit input to single-channel, grayscale, 2D TIFF/OME-TIFF. Keep original pixel values; reject unsupported shape/color instead of flattening or converting.
- Save manually reviewed labels as raster masks with project metadata outside the public repository.
- Keep the first release detector-free. Model proposals and training are future work after the manual workflow is used.
- Use a reviewed-background-mask mean as the initial constant background method; let the human mark it unsuitable.
- Project repository: `TonyYanggg/C.-elegans-Pharynx-Infection-Quantification`; public code only. Repository license remains pending confirmation.
