"""Dock interface and lifecycle for fixed-polygon QC."""

from pathlib import Path

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon, QPixmap
from qgis.PyQt.QtWidgets import (
    QAction, QCheckBox, QComboBox, QDockWidget, QGridLayout, QHBoxLayout,
    QLabel, QProgressBar, QPushButton, QScrollArea, QSizePolicy, QSlider, QVBoxLayout, QWidget,
)
from qgis.core import (
    Qgis, QgsCoordinateTransform, QgsMapLayerProxyModel, QgsProject,
    QgsProviderRegistry, QgsRectangle,
)
from qgis.gui import QgsMapLayerComboBox

from .map_tool import ToggleSelectTool
from .store import ReviewError, ReviewStore
from .style import class_color, renderer


class PolygonQCPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.dock = None
        self.action = None

    def initGui(self):
        self.action = QAction("Polygon QC", self.iface.mainWindow())
        self.action.triggered.connect(self.show)
        self.iface.addPluginToVectorMenu("Polygon QC", self.action)
        self.iface.addToolBarIcon(self.action)

    def show(self):
        if self.dock is None:
            self.dock = ReviewDock(self.iface)
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock)
        self.dock.show()
        self.dock.raise_()

    def unload(self):
        if self.dock is not None:
            self.dock.detach()
            QgsProject.instance().layersWillBeRemoved.disconnect(self.dock.layers_removed)
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None
        if self.action is not None:
            self.iface.removePluginVectorMenu("Polygon QC", self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action.deleteLater()
            self.action = None


class ReviewDock(QDockWidget):
    FILTER_PROPERTY = "polygon_qc/session_filter"

    def __init__(self, iface):
        super().__init__("Polygon QC", iface.mainWindow())
        self.setObjectName("PolygonQCReviewDock")
        self.setMinimumWidth(320)
        self.iface = iface
        self.layer = None
        self.store = None
        self.plot = None
        self.tool = None
        self.original = None
        self.class_buttons = []

        root = QWidget()
        layout = QVBoxLayout(root)
        self.layer_choice = QgsMapLayerComboBox()
        self.layer_choice.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        layout.addWidget(QLabel("Review layer"))
        layout.addWidget(self.layer_choice)
        self.start = QPushButton("Start review")
        self.start.clicked.connect(self.attach)
        layout.addWidget(self.start)

        self.session = QWidget()
        session_layout = QVBoxLayout(self.session)
        session_layout.setContentsMargins(0, 0, 0, 0)
        self.progress = QProgressBar()
        session_layout.addWidget(self.progress)
        self.plot_choice = QComboBox()
        self.plot_choice.activated.connect(self.choose_plot)
        session_layout.addWidget(self.plot_choice)
        self.plot_info = QLabel()
        session_layout.addWidget(self.plot_info)

        select_row = QHBoxLayout()
        self.click_select = QPushButton("Click")
        self.click_select.setToolTip("Click to add a polygon; click it again to remove it. No modifier key needed.")
        self.click_select.clicked.connect(self.use_click_tool)
        select_row.addWidget(self.click_select)
        for text, action_name in (("Rectangle", "actionSelectRectangle"),
                                  ("Polygon", "actionSelectPolygon"),
                                  ("Freehand", "actionSelectFreehand")):
            button = QPushButton(text)
            button.setToolTip("Use QGIS selection. Hold Shift to add to the selection.")
            button.clicked.connect(lambda checked=False, name=action_name: self.use_native_tool(name))
            select_row.addWidget(button)
        session_layout.addLayout(select_row)
        selection_row = QHBoxLayout()
        self.selection_info = QLabel("0 polygons selected")
        selection_row.addWidget(self.selection_info)
        clear = QPushButton("Clear")
        clear.clicked.connect(lambda: self.layer.removeSelection() if self.layer else None)
        selection_row.addWidget(clear)
        session_layout.addLayout(selection_row)

        session_layout.addWidget(QLabel("Apply class to selected polygons"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMinimumHeight(240)
        self.palette = QWidget()
        self.palette_layout = QGridLayout(self.palette)
        self.palette_layout.setContentsMargins(2, 2, 2, 2)
        scroll.setWidget(self.palette)
        session_layout.addWidget(scroll, 1)

        self.overlay = QCheckBox("Show class overlay")
        self.overlay.setChecked(True)
        self.overlay.toggled.connect(self.set_opacity)
        session_layout.addWidget(self.overlay)
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(QLabel("Opacity"))
        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(10, 100)
        self.opacity.setValue(45)
        self.opacity.valueChanged.connect(self.set_opacity)
        opacity_row.addWidget(self.opacity)
        session_layout.addLayout(opacity_row)

        self.finish = QPushButton("Complete plot && next")
        self.finish.setToolTip("Accept the remaining polygons, save this plot as complete, and open the next pending plot.")
        self.finish.clicked.connect(self.complete)
        session_layout.addWidget(self.finish)
        bottom = QHBoxLayout()
        self.undo_button = QPushButton("Undo last action")
        self.undo_button.clicked.connect(self.undo)
        bottom.addWidget(self.undo_button)
        zoom = QPushButton("Zoom to plot")
        zoom.clicked.connect(self.zoom_to_plot)
        bottom.addWidget(zoom)
        session_layout.addLayout(bottom)
        stop = QPushButton("End session")
        stop.setToolTip("Changes are already saved. Restore the layer display and end session undo history.")
        stop.clicked.connect(self.detach)
        session_layout.addWidget(stop)
        note = QLabel("Changes save immediately. Undo is available until this session ends.")
        note.setWordWrap(True)
        session_layout.addWidget(note)
        layout.addWidget(self.session, 1)
        self.session.setEnabled(False)
        self.message = QLabel("Choose a working copy of your polygon GeoPackage.")
        self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.PlainText)
        layout.addWidget(self.message)
        self.setWidget(root)
        QgsProject.instance().layersWillBeRemoved.connect(self.layers_removed)

    def report_error(self, exc):
        self.message.setText(str(exc))
        self.iface.messageBar().pushMessage("Polygon QC", str(exc), level=Qgis.Warning, duration=8)

    def attach(self):
        layer = self.layer_choice.currentLayer()
        try:
            if layer is None or not layer.isValid() or layer.providerType() != "ogr":
                raise ReviewError("Choose a valid GeoPackage polygon layer.")
            if layer.isEditable():
                raise ReviewError("Save or discard the layer's existing QGIS edits, then turn editing off.")
            saved_filter = layer.customProperty(self.FILTER_PROPERTY, "")
            if layer.subsetString() and layer.subsetString() != saved_filter:
                raise ReviewError("Clear the layer's existing filter before starting plot review.")
            uri = QgsProviderRegistry.instance().decodeUri("ogr", layer.source())
            path = uri.get("path", "")
            if Path(path).suffix.lower() != ".gpkg":
                raise ReviewError("This version supports local .gpkg files.")
            table = uri.get("layerName")
            if not table:
                raise ReviewError("Load the named polygon layer from the GeoPackage in the QGIS Browser.")
            store = ReviewStore(path, table)
            # Another editable layer referring to the same file could hold pending writes.
            for other in QgsProject.instance().mapLayers().values():
                if hasattr(other, "isEditable") and other.isEditable():
                    other_uri = QgsProviderRegistry.instance().decodeUri(other.providerType(), other.source())
                    if other_uri.get("path") and Path(other_uri["path"]).resolve() == store.path:
                        raise ReviewError("End editing on other layers from this GeoPackage first.")
            # A project saved during review can contain our temporary plot filter.
            # Treat that as session state, not a user-supplied layer filter.
            original_filter = "" if saved_filter else layer.subsetString()
            self.original = (original_filter, layer.readOnly(), layer.renderer().clone(), layer.opacity())
            if not layer.setReadOnly(True):
                raise ReviewError("Could not disable normal editing on this layer.")
            self.layer = layer
            self.store = store
            layer.setRenderer(renderer(store.classes))
            self.set_opacity()
            layer.selectionChanged.connect(self.selection_changed)
            self.tool = ToggleSelectTool(self.iface.mapCanvas(), layer)
            self.build_palette()
            self.start.setEnabled(False)
            self.start.hide()
            self.layer_choice.setEnabled(False)
            self.session.setEnabled(True)
            _, completed = store.summary()
            pending = [p for p in store.plots if p not in completed]
            self.activate_plot(pending[0] if pending else store.plots[0])
            self.use_click_tool()
            self.message.setText("Select incorrect polygons, then click their correct class. Changes save immediately.")
        except (ReviewError, OSError) as exc:
            if self.layer:
                self.detach()
            self.report_error(exc)

    def build_palette(self):
        while self.palette_layout.count():
            item = self.palette_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.class_buttons = []
        for index, name in enumerate(self.store.classes):
            button = QPushButton(name.replace(" ", "\n") if len(name) > 14 else name)
            swatch = QPixmap(14, 14)
            swatch.fill(class_color(name, index))
            button.setIcon(QIcon(swatch))
            button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            button.setMinimumHeight(44 if len(name) > 14 else 32)
            button.setToolTip(f"Set selected polygons to {name}")
            button.clicked.connect(lambda checked=False, target=name: self.assign(target))
            self.palette_layout.addWidget(button, index // 2, index % 2)
            self.class_buttons.append(button)

    def selection_changed(self, *args):
        count = self.layer.selectedFeatureCount() if self.layer else 0
        self.selection_info.setText(f"{count} polygon{'s' if count != 1 else ''} selected")
        for button in self.class_buttons:
            button.setEnabled(count > 0)

    def refresh_progress(self):
        counts, completed = self.store.summary()
        self.progress.setMaximum(len(self.store.plots))
        self.progress.setValue(len(completed))
        self.progress.setFormat(f"{len(completed)} / {len(self.store.plots)} plots complete")
        self.plot_choice.blockSignals(True)
        self.plot_choice.clear()
        for plot in self.store.plots:
            status = "complete" if plot in completed else "pending"
            self.plot_choice.addItem(f"Plot {plot} — {status}", plot)
        self.plot_choice.setCurrentIndex(self.store.plots.index(self.plot))
        self.plot_choice.blockSignals(False)
        self.plot_info.setText(f"{counts[self.plot]} polygons in this plot")
        self.undo_button.setEnabled(bool(self.store.history))
        self.selection_changed()

    def activate_plot(self, plot):
        self.layer.removeSelection()
        if not self.layer.setSubsetString(f'"plot_id" = {int(plot)}'):
            raise ReviewError("QGIS could not filter to this plot.")
        self.layer.setCustomProperty(self.FILTER_PROPERTY, self.layer.subsetString())
        self.plot = plot
        self.iface.setActiveLayer(self.layer)
        self.layer.reload()
        self.refresh_progress()
        self.zoom_to_plot()

    def choose_plot(self, index):
        target = self.plot_choice.itemData(index)
        try:
            _, completed = self.store.summary()
            if target != self.plot and self.plot not in completed:
                raise ReviewError("Complete the current plot before moving to another plot.")
            self.activate_plot(target)
            self.message.setText("Reviewing a completed plot reopens it when you change a class.")
        except ReviewError as exc:
            self.plot_choice.setCurrentIndex(self.store.plots.index(self.plot))
            self.report_error(exc)

    def use_click_tool(self):
        if self.layer:
            self.iface.setActiveLayer(self.layer)
            self.iface.mapCanvas().setMapTool(self.tool)

    def use_native_tool(self, name):
        if self.layer:
            self.iface.setActiveLayer(self.layer)
            getattr(self.iface, name)().trigger()

    def set_opacity(self, *args):
        if self.layer:
            self.layer.setOpacity(self.opacity.value() / 100 if self.overlay.isChecked() else 0)
            self.layer.triggerRepaint()

    def zoom_to_plot(self):
        if not self.layer:
            return
        extent = QgsRectangle(self.layer.extent())
        transform = QgsCoordinateTransform(self.layer.crs(), self.iface.mapCanvas().mapSettings().destinationCrs(),
                                           QgsProject.instance())
        extent = transform.transformBoundingBox(extent)
        extent.scale(1.12)
        self.iface.mapCanvas().setExtent(extent)
        self.iface.mapCanvas().refresh()

    def reload(self):
        self.layer.removeSelection()
        self.layer.reload()
        self.layer.triggerRepaint()
        self.refresh_progress()

    def assign(self, target):
        try:
            count = self.layer.selectedFeatureCount()
            changed = self.store.assign(self.plot, self.layer.selectedFeatureIds(), target)
            self.reload()
            self.message.setText(f"Saved: {count} polygons → {target}." if changed else "Selection already has that class and review state.")
        except ReviewError as exc:
            self.report_error(exc)

    def complete(self):
        try:
            previous = self.plot
            self.store.complete(previous)
            self.reload()
            _, completed = self.store.summary()
            pending = [p for p in self.store.plots if p not in completed]
            if pending:
                following = next((p for p in pending if p > previous), pending[0])
                self.activate_plot(following)
                self.message.setText(f"Plot {previous} saved as complete. Review plot {following}.")
            else:
                self.message.setText("All plots complete and saved. You can revisit plots using the plot list.")
        except ReviewError as exc:
            self.report_error(exc)

    def undo(self):
        try:
            change = self.store.undo()
            self.activate_plot(change.plot)
            self.message.setText(f"Undid {change.label} on plot {change.plot}. Saved.")
        except ReviewError as exc:
            self.report_error(exc)

    def layers_removed(self, ids):
        if self.layer and self.layer.id() in ids:
            self.detach()

    def detach(self):
        if self.layer:
            self.layer.selectionChanged.disconnect(self.selection_changed)
            canvas = self.iface.mapCanvas()
            if canvas.mapTool() is self.tool:
                canvas.unsetMapTool(self.tool)
                self.iface.actionPan().trigger()
            self.layer.removeSelection()
            subset, readonly, original_renderer, opacity = self.original
            self.layer.setSubsetString(subset)
            self.layer.removeCustomProperty(self.FILTER_PROPERTY)
            self.layer.setReadOnly(readonly)
            self.layer.setRenderer(original_renderer)
            self.layer.setOpacity(opacity)
            self.layer.reload()
            self.layer.triggerRepaint()
        if self.tool:
            self.tool.deleteLater()
        self.layer = self.store = self.plot = self.tool = self.original = None
        self.session.setEnabled(False)
        self.start.setEnabled(True)
        self.start.show()
        self.layer_choice.setEnabled(True)
        self.message.setText("Session ended. Changes are saved; start again to resume pending plots.")

    def closeEvent(self, event):
        self.detach()
        super().closeEvent(event)
