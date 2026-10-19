"""napari desktop interface for manually reviewed 2D TIFF measurements."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import tifffile

from .io import blank_project, export_measurements, load_project, read_measurement_tiff, save_project


LAYER_NAMES = ("posterior bulb ROI", "assessable tissue ROI", "objects", "diffuse signal", "background ROI")


def _new_masks(shape: tuple[int, int]) -> dict[str, np.ndarray]:
    return {"bulb": np.zeros(shape, dtype=np.uint8), "assessable": np.zeros(shape, dtype=np.uint8),
            "objects": np.zeros(shape, dtype=np.uint16), "diffuse": np.zeros(shape, dtype=np.uint8),
            "background": np.zeros(shape, dtype=np.uint8)}


class AnnotationPanel:
    """Small Qt dock with study metadata, object review, and project actions."""

    def __init__(self, viewer: Any, image: np.ndarray, image_path: Path, source_metadata: dict[str, Any], napari: Any):
        from qtpy import QtCore, QtWidgets

        self.viewer = viewer
        self.QtCore = QtCore
        self.QtWidgets = QtWidgets
        self.image = image
        self.image_path = image_path
        self.source_metadata = source_metadata
        self.project_dir = image_path.parent / f"{image_path.stem}.cephq"
        self.metadata = blank_project(image_path, image, source_metadata)
        self.masks = _new_masks(image.shape)
        self.dirty = True
        self.object_counter = 0
        self._busy = False
        self.widget = QtWidgets.QWidget()
        root = QtWidgets.QVBoxLayout(self.widget)

        ids_box = QtWidgets.QGroupBox("Observation identifiers")
        ids_form = QtWidgets.QFormLayout(ids_box)
        self.id_inputs: dict[str, Any] = {}
        for key, label in (("experiment_id", "Experiment"), ("trial_id", "Trial"), ("strain", "Strain"), ("worm_id", "Worm ID"), ("observation_id", "Observation ID"), ("observation_time", "Observation time")):
            entry = QtWidgets.QLineEdit()
            self.id_inputs[key] = entry
            ids_form.addRow(label, entry)
            entry.textChanged.connect(self._mark_dirty)
        self.study_design = QtWidgets.QComboBox()
        self.study_design.addItems(["cross_sectional", "longitudinal"])
        ids_form.addRow("Study design", self.study_design)
        self.study_design.currentTextChanged.connect(self._mark_dirty)
        self.observation_status = QtWidgets.QComboBox()
        self.observation_status.addItems(["scorable", "uncertain", "unscorable"])
        ids_form.addRow("Observation status", self.observation_status)
        self.observation_status.currentTextChanged.connect(self._mark_dirty)
        root.addWidget(ids_box)

        self.layer_select = QtWidgets.QComboBox()
        self.layer_select.addItems(LAYER_NAMES)
        root.addWidget(QtWidgets.QLabel("Draw on selected mask layer (paint/polygon tools are in napari):"))
        root.addWidget(self.layer_select)
        self.layer_select.currentTextChanged.connect(self._select_layer)
        self.draw_tip = QtWidgets.QLabel("Select a layer, then use napari's paint or polygon tool. Undo/redo: Ctrl+Z / Ctrl+Shift+Z.")
        self.draw_tip.setWordWrap(True)
        root.addWidget(self.draw_tip)
        self.polygon_button = QtWidgets.QPushButton("Toggle polygon drawing")
        self.polygon_button.setCheckable(True)
        self.polygon_button.toggled.connect(self._toggle_polygon)
        root.addWidget(self.polygon_button)
        polygon_history = QtWidgets.QHBoxLayout()
        self.undo_polygon_button = QtWidgets.QPushButton("Undo last polygon")
        self.redo_polygon_button = QtWidgets.QPushButton("Redo polygon")
        self.undo_polygon_button.clicked.connect(self._undo_polygon)
        self.redo_polygon_button.clicked.connect(self._redo_polygon)
        polygon_history.addWidget(self.undo_polygon_button)
        polygon_history.addWidget(self.redo_polygon_button)
        root.addLayout(polygon_history)

        actions = QtWidgets.QHBoxLayout()
        self.add_object_button = QtWidgets.QPushButton("Add object ID")
        self.add_object_button.clicked.connect(self._new_object)
        self.reference_button = QtWidgets.QPushButton("Open reference separately")
        self.reference_button.clicked.connect(self._open_reference)
        actions.addWidget(self.add_object_button)
        actions.addWidget(self.reference_button)
        root.addLayout(actions)

        root.addWidget(QtWidgets.QLabel("Object review (select a row, then update fields):"))
        self.table = QtWidgets.QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["ID", "Morphology", "Inclusion", "Review", "Count", "Area px", "Raw mean", "Corrected mean"])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self._select_table_object)
        root.addWidget(self.table)
        review_form = QtWidgets.QFormLayout()
        self.morphology = QtWidgets.QComboBox()
        self.morphology.addItems(["uncertain", "discrete_punctum", "diffuse_confluent", "artefact"])
        self.inclusion = QtWidgets.QComboBox()
        self.inclusion.addItems(["uncertain", "tissue_associated", "luminal", "outside_analysis_region"])
        self.reviewed = QtWidgets.QCheckBox("Object reviewed")
        self.shared = QtWidgets.QCheckBox("Shared cluster mask; individual area unresolved")
        self.expert_count = QtWidgets.QSpinBox()
        self.expert_count.setRange(0, 9999)
        self.count_unresolved = QtWidgets.QCheckBox("Count unresolved")
        review_form.addRow("Morphology", self.morphology)
        review_form.addRow("Anatomical inclusion", self.inclusion)
        review_form.addRow("Expert count", self.expert_count)
        review_form.addRow(self.reviewed)
        review_form.addRow(self.shared)
        review_form.addRow(self.count_unresolved)
        root.addLayout(review_form)
        for control in (self.morphology, self.inclusion):
            control.currentTextChanged.connect(self._update_selected_object)
        for control in (self.reviewed, self.shared, self.count_unresolved):
            control.stateChanged.connect(self._update_selected_object)
        self.expert_count.valueChanged.connect(self._update_selected_object)

        self.coverage_reviewed = QtWidgets.QCheckBox("I reviewed the full posterior-bulb region")
        self.count_resolvable = QtWidgets.QCheckBox("Whole-bulb punctum count is resolvable")
        self.count_resolvable.setChecked(True)
        self.background_suitable = QtWidgets.QCheckBox("Background ROIs are suitable for correction")
        self.background_suitable.setChecked(True)
        for control in (self.coverage_reviewed, self.count_resolvable, self.background_suitable):
            control.stateChanged.connect(self._mark_dirty)
            root.addWidget(control)

        footer = QtWidgets.QHBoxLayout()
        open_project = QtWidgets.QPushButton("Open project")
        open_project.clicked.connect(self._open_project)
        save = QtWidgets.QPushButton("Save project")
        save.clicked.connect(self._save)
        measure = QtWidgets.QPushButton("Measure and export")
        measure.clicked.connect(self._measure)
        for button in (open_project, save, measure):
            footer.addWidget(button)
        root.addLayout(footer)
        self.status = QtWidgets.QLabel("Measurements have not been run.")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        root.addStretch(1)

        self.layers: dict[str, Any] = {}
        self.polygon_layers: dict[str, Any] = {}
        self.polygon_counts: dict[str, int] = {}
        self.polygon_history: dict[str, list[tuple[np.ndarray, np.ndarray, np.ndarray]]] = {}
        self.polygon_redo: dict[str, list[tuple[np.ndarray, np.ndarray, np.ndarray]]] = {}
        self.reference_viewers: list[Any] = []
        colors = {"posterior bulb ROI": "lime", "assessable tissue ROI": "cyan", "objects": "red", "diffuse signal": "magenta", "background ROI": "yellow"}
        from napari.utils.colormaps import DirectLabelColormap
        for name in LAYER_NAMES:
            colormap = DirectLabelColormap(color_dict={0: "transparent", None: colors[name]})
            layer = viewer.add_labels(self.masks[self._key(name)], name=name, opacity=0.45, colormap=colormap)
            layer.brush_size = 5
            layer.contour = 1
            layer.mode = "paint"
            layer.events.data.connect(self._layer_changed)
            self.layers[name] = layer
        for name in LAYER_NAMES:
            polygon_layer = viewer.add_shapes([], shape_type="polygon", name=f"polygon drawing: {name}",
                                              edge_color="white", face_color=[1, 1, 1, 0.15], opacity=0.8)
            polygon_layer.visible = False
            polygon_layer.events.data.connect(lambda event, target=name: self._polygon_changed(event, target))
            self.polygon_layers[name] = polygon_layer
            self.polygon_counts[name] = 0
            self.polygon_history[name] = []
            self.polygon_redo[name] = []
        self._select_layer(LAYER_NAMES[0])
        self.autosave_timer = QtCore.QTimer(self.widget)
        self.autosave_timer.setSingleShot(True)
        self.autosave_timer.setInterval(900)
        self.autosave_timer.timeout.connect(self._save_silently)

    @staticmethod
    def _key(layer_name: str) -> str:
        return {"posterior bulb ROI": "bulb", "assessable tissue ROI": "assessable", "objects": "objects", "diffuse signal": "diffuse", "background ROI": "background"}[layer_name]

    def _select_layer(self, name: str) -> None:
        if name in self.layers:
            self.viewer.layers.selection.active = self.layers[name]
            self.layers[name].mode = "paint"
            for polygon_name, polygon_layer in self.polygon_layers.items():
                polygon_layer.visible = bool(self.polygon_button.isChecked() and polygon_name == name)
            if self.polygon_button.isChecked():
                self.viewer.layers.selection.active = self.polygon_layers[name]
                self.polygon_layers[name].mode = "add_polygon"

    def _toggle_polygon(self, enabled: bool) -> None:
        name = self.layer_select.currentText()
        for polygon_name, polygon_layer in self.polygon_layers.items():
            polygon_layer.visible = bool(enabled and polygon_name == name)
        if enabled:
            if name == "objects" and self.layers["objects"].selected_label == 0:
                self._new_object()
            self.viewer.layers.selection.active = self.polygon_layers[name]
            self.polygon_layers[name].mode = "add_polygon"
            self.draw_tip.setText("Draw polygon vertices on the image. The filled polygon is rasterized into the selected mask and saved as pixels.")
        else:
            self._select_layer(name)
            self.draw_tip.setText("Use napari's paint and erase tools on the selected mask layer. Ctrl+Z / Ctrl+Shift+Z undo/redo edits.")

    def _polygon_changed(self, event: Any, target_name: str) -> None:
        if self._busy:
            return
        shapes = event.source.data
        if len(shapes) <= self.polygon_counts[target_name]:
            return
        from skimage.draw import polygon
        self._busy = True
        try:
            for vertices in shapes[self.polygon_counts[target_name]:]:
                before = self.masks[self._key(target_name)].copy()
                if target_name == "objects" and self.layers["objects"].selected_label == 0:
                    self._new_object()
                key = self._key(target_name)
                rr, cc = polygon(np.asarray(vertices)[:, 0], np.asarray(vertices)[:, 1], shape=self.masks[key].shape)
                value = self.layers[target_name].selected_label if target_name == "objects" else 1
                self.masks[key][rr, cc] = value
                self.polygon_history[target_name].append((before, np.asarray(vertices).copy(), self.masks[key].copy()))
                self.polygon_redo[target_name].clear()
            self.polygon_counts[target_name] = len(shapes)
            self.layers[target_name].data = self.masks[self._key(target_name)]
            self._refresh_table()
        finally:
            self._busy = False
        self._mark_dirty()

    def _undo_polygon(self) -> None:
        name = self.layer_select.currentText()
        if not self.polygon_history[name]:
            return
        before, _vertices, _after = self.polygon_history[name].pop()
        current = self.masks[self._key(name)].copy()
        shapes = list(self.polygon_layers[name].data)
        vertices = np.asarray(shapes[-1]).copy() if shapes else np.empty((0, 2))
        self.polygon_redo[name].append((before.copy(), vertices, current))
        self._busy = True
        try:
            if shapes:
                self.polygon_layers[name].data = shapes[:-1]
            self.polygon_counts[name] = max(0, len(shapes) - 1)
            self.masks[self._key(name)] = before
            self.layers[name].data = before
        finally:
            self._busy = False
        self._mark_dirty()

    def _redo_polygon(self) -> None:
        name = self.layer_select.currentText()
        if not self.polygon_redo[name]:
            return
        before, vertices, after = self.polygon_redo[name].pop()
        self._busy = True
        try:
            shapes = list(self.polygon_layers[name].data)
            shapes.append(vertices)
            self.polygon_layers[name].data = shapes
            self.polygon_counts[name] = len(shapes)
            self.masks[self._key(name)] = after
            self.layers[name].data = after
            self.polygon_history[name].append((before, vertices, after.copy()))
        finally:
            self._busy = False
        self._mark_dirty()

    def _layer_changed(self, event: Any) -> None:
        if self._busy:
            return
        self.masks[self._key(event.source.name)] = np.asarray(event.source.data).copy()
        self._mark_dirty()
        if event.source.name == "objects":
            self._refresh_table()

    def _identifiers(self) -> dict[str, Any]:
        return {**{key: widget.text().strip() for key, widget in self.id_inputs.items()},
                "study_design": self.study_design.currentText(),
                "observation_status": self.observation_status.currentText(),
                "coverage_reviewed": self.coverage_reviewed.isChecked(),
                "count_resolvable": self.count_resolvable.isChecked()}

    def _mark_dirty(self, *_: Any) -> None:
        if self._busy or not hasattr(self, "autosave_timer"):
            return
        self.dirty = True
        self.metadata["measurement_stale"] = True
        if hasattr(self, "status"):
            self.status.setText("Annotations or settings changed; previous measurements are stale.")
        self.autosave_timer.start()

    def _new_object(self) -> None:
        self.object_counter = max(self.object_counter, int(np.max(self.masks["objects"]))) + 1
        layer = self.layers["objects"]
        layer.selected_label = self.object_counter
        self.viewer.layers.selection.active = layer
        layer.mode = "paint"
        self.metadata.setdefault("annotations", {}).setdefault(str(self.object_counter), {
            "object_id": f"P{self.object_counter:03d}", "morphology": "uncertain", "inclusion": "uncertain", "review_status": "pending"})
        self._refresh_table(select_label=self.object_counter)
        self._mark_dirty()

    def _object_value(self) -> int | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.table.item(rows[0].row(), 0)
        return int(item.data(self.QtCore.Qt.ItemDataRole.UserRole)) if item else None

    def _select_table_object(self) -> None:
        label = self._object_value()
        if label is None:
            return
        self.viewer.layers.selection.active = self.layers["objects"]
        self.layers["objects"].selected_label = label
        annotation = self.metadata.get("annotations", {}).get(str(label), {})
        self._busy = True
        try:
            self.morphology.setCurrentText(annotation.get("morphology", "uncertain"))
            self.inclusion.setCurrentText(annotation.get("inclusion", "uncertain"))
            self.reviewed.setChecked(annotation.get("review_status") == "reviewed")
            self.shared.setChecked(annotation.get("shared_cluster", False))
            self.expert_count.setValue(int(annotation.get("expert_count") or 0))
            self.count_unresolved.setChecked(annotation.get("count_unresolved", False))
        finally:
            self._busy = False

    def _update_selected_object(self, *_: Any) -> None:
        if self._busy:
            return
        label = self._object_value()
        if label is None:
            return
        self.metadata.setdefault("annotations", {})[str(label)] = {
            "object_id": f"P{label:03d}", "morphology": self.morphology.currentText(),
            "inclusion": self.inclusion.currentText(), "review_status": "reviewed" if self.reviewed.isChecked() else "pending",
            "shared_cluster": self.shared.isChecked(), "expert_count": self.expert_count.value() or None,
            "count_unresolved": self.count_unresolved.isChecked()}
        self._refresh_table(select_label=label)
        self._mark_dirty()

    def _refresh_table(self, select_label: int | None = None, measurements: list[dict[str, Any]] | None = None) -> None:
        values = np.unique(self.masks["objects"])
        labels = [int(v) for v in values if v > 0]
        labels.extend(int(k) for k in self.metadata.get("annotations", {}) if int(k) not in labels)
        self._busy = True
        try:
            self.table.setRowCount(len(labels))
            measured = {int(row["label_value"]): row for row in (measurements if measurements is not None else self.metadata.get("object_measurements", []))}
            chosen_row = None
            for row, label in enumerate(sorted(labels)):
                ann = self.metadata.get("annotations", {}).get(str(label), {})
                metric = measured.get(label, {})
                count = ann.get("expert_count", "") or ""
                values_row = [ann.get("object_id", f"P{label:03d}"), ann.get("morphology", "uncertain"), ann.get("inclusion", "uncertain"), ann.get("review_status", "pending"), str(count),
                              str(metric.get("pixel_count") if metric.get("pixel_count") is not None else ""),
                              f"{metric['raw_mean_intensity']:.3g}" if metric.get("raw_mean_intensity") is not None else "",
                              f"{metric['corrected_mean_intensity']:.3g}" if metric.get("corrected_mean_intensity") is not None else ""]
                for col, value in enumerate(values_row):
                    item = self.QtWidgets.QTableWidgetItem(value)
                    if col == 0:
                        item.setData(self.QtCore.Qt.ItemDataRole.UserRole, label)
                    item.setFlags(item.flags() & ~self.QtCore.Qt.ItemFlag.ItemIsEditable)
                    self.table.setItem(row, col, item)
                if label == select_label:
                    chosen_row = row
            if chosen_row is not None:
                self.table.selectRow(chosen_row)
        finally:
            self._busy = False

    def _open_reference(self) -> None:
        from napari import Viewer
        from napari.qt import get_qapp
        path, _ = self.QtWidgets.QFileDialog.getOpenFileName(self.widget, "Open separate visual reference", str(self.image_path.parent), "TIFF images (*.tif *.tiff)")
        if not path:
            return
        try:
            reference, _metadata = read_measurement_tiff(path)
            ref_viewer = Viewer(title=f"Unregistered reference: {Path(path).name}")
            ref_viewer.add_image(reference, name="visual reference only", colormap="gray")
            self.reference_viewers.append(ref_viewer)
            get_qapp().processEvents()
        except Exception as error:
            self._error(str(error))

    def _open_project(self) -> None:
        path, _ = self.QtWidgets.QFileDialog.getOpenFileName(self.widget, "Open saved project", str(self.image_path.parent), "Project metadata (project.json)")
        if not path:
            return
        try:
            metadata, masks = load_project(path)
            image, source = read_measurement_tiff(metadata["source"]["path"])
            if image.shape != masks["objects"].shape:
                raise ValueError("Project masks do not match the source image dimensions.")
            self._busy = True
            self.metadata, self.masks = metadata, masks
            self.project_dir = Path(path).parent
            self.image, self.image_path, self.source_metadata = image, Path(metadata["source"]["path"]), source
            self.viewer.layers["pure RFP (quantitative pixels)"].data = image
            for name, layer in self.layers.items():
                layer.data = masks[self._key(name)]
            for key, entry in self.id_inputs.items():
                entry.setText(str(metadata.get("identifiers", {}).get(key, "")))
            self.study_design.setCurrentText(metadata.get("identifiers", {}).get("study_design", "cross_sectional"))
            self.observation_status.setCurrentText(metadata.get("identifiers", {}).get("observation_status", "scorable"))
            self.coverage_reviewed.setChecked(metadata.get("identifiers", {}).get("coverage_reviewed", False))
            self.count_resolvable.setChecked(metadata.get("identifiers", {}).get("count_resolvable", True))
            self.background_suitable.setChecked(metadata.get("background_suitable", True))
            self.object_counter = max([int(k) for k in metadata.get("annotations", {})] + [int(np.max(masks["objects"]))])
            self._refresh_table()
            self._busy = False
            self.status.setText("Project reopened. " + ("Previous measurements are stale." if metadata.get("measurement_stale") else "Measurements are current."))
        except Exception as error:
            self._busy = False
            self._error(str(error))

    def _save_silently(self) -> None:
        if not self.dirty:
            return
        try:
            self.metadata["identifiers"] = self._identifiers()
            self.metadata["background_suitable"] = self.background_suitable.isChecked()
            save_project(self.project_dir, self.metadata, self.masks, self.image)
            self.dirty = False
            self.status.setText(f"Autosaved to {self.project_dir}")
        except Exception as error:
            self.status.setText(f"Autosave failed: {error}")

    def _save(self) -> None:
        destination = self.QtWidgets.QFileDialog.getExistingDirectory(self.widget, "Choose project folder (outside the public repository)", str(self.project_dir.parent))
        if destination:
            self.project_dir = Path(destination) / f"{self.image_path.stem}.cephq"
        self._save_silently()

    def _measure(self) -> None:
        self._save_silently()
        try:
            self.metadata["identifiers"] = self._identifiers()
            self.metadata["background_suitable"] = self.background_suitable.isChecked()
            object_rows, _summary = export_measurements(self.project_dir, self.image, self.metadata, self.masks)
            self.dirty = False
            summary = self.metadata["measurement_summary"]
            self._refresh_table(measurements=object_rows)
            self.status.setText(f"Exported to {self.project_dir}. Whole-bulb count: {summary['count_puncta']}; coverage: {summary['review_status']}.")
        except Exception as error:
            self._error(str(error))

    def _error(self, message: str) -> None:
        self.QtWidgets.QMessageBox.critical(self.widget, "Cannot complete action", message)


def main() -> None:
    import napari
    from napari.qt import get_qapp

    app = get_qapp()
    from qtpy import QtWidgets
    path, _ = QtWidgets.QFileDialog.getOpenFileName(None, "Open a 2D pure-RFP TIFF", "", "TIFF images (*.tif *.tiff)")
    if not path:
        return
    try:
        image, source_metadata = read_measurement_tiff(path)
    except Exception as error:
        QtWidgets.QMessageBox.critical(None, "Unsupported image", str(error))
        return
    viewer = napari.Viewer(title=f"C. elegans pharynx quantification — {Path(path).name}")
    viewer.add_image(image, name="pure RFP (quantitative pixels)", colormap="gray", contrast_limits=(float(np.percentile(image, 1)), float(np.percentile(image, 99.8))))
    panel = AnnotationPanel(viewer, image, Path(path), source_metadata, napari)
    viewer.window.add_dock_widget(panel.widget, name="Manual review and measurement", area="right")
    viewer.window._cephq_panel = panel
    app.exec()


if __name__ == "__main__":
    main()
