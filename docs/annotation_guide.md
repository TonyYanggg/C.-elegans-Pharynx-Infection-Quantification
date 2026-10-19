# Annotation guide

1. Open a pure-RFP, single-channel, two-dimensional grayscale TIFF. Confirm it is the quantitative image. Unsupported RGB, multi-page stacks and other dimensions produce an error; the viewer does not flatten them.
2. Draw the posterior-bulb ROI and assessable-tissue ROI as separate masks. The second ROI defines the denominator of positive-area fraction.
3. Create an object ID, draw one discrete focus or a shared cluster mask, then set morphology and anatomical inclusion independently. Select `reviewed` only after checking the outline and classification.
4. Use the diffuse-signal layer for widespread/confluent tissue signal. It is area, not a large punctum. Mark objects luminal or outside the region when appropriate; those remain morphology annotations but are excluded from accepted tissue measurements.
5. Draw reviewed background regions on the quantitative TIFF. Use the background suitability checkbox only when these regions represent background and do not contain tissue-positive signal. If correction is unsuitable, raw measurements remain available and corrected fields are blank.
6. Mark full bulb review only after examining the whole relevant region. Unreviewed or unresolved objects keep the total count missing. A count-known shared cluster needs an expert count; its individual boundary and area remain unresolved.
7. Save the project and run measurement. Any later mask or metadata change marks existing measurements stale; run measurement again to refresh exports.

Brush and polygon tools modify raster masks. Use the dock's polygon undo/redo buttons for polygon actions; use napari's Ctrl+Z / Ctrl+Shift+Z for brush edits. Editing labels allows manual splitting and merging. Reference images open in an independent viewer; account for movement by drawing every analysis annotation on pure RFP. Coordinates are never copied between images.
