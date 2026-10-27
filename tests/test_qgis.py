"""Exercise real QGIS layers, map tools, and widgets without touching a profile."""

from qgis.PyQt.QtCore import QCoreApplication, QEvent, QPoint, Qt
from qgis.PyQt.QtGui import QAction
from qgis.PyQt.QtTest import QTest
from qgis.PyQt.QtWidgets import QMainWindow
from qgis.core import QgsProject, QgsVectorLayer
from qgis.gui import QgsMapCanvas, QgsMessageBar

from polygon_qc.plugin import PolygonQCPlugin, ReviewDock


class TestInterface:
    __test__ = False

    def __init__(self):
        self.window = QMainWindow()
        self.canvas = QgsMapCanvas()
        self.window.setCentralWidget(self.canvas)
        self.bar = QgsMessageBar()
        self.actions = {}
        self.active_layer = None

    def mainWindow(self):
        return self.window

    def mapCanvas(self):
        return self.canvas

    def setActiveLayer(self, layer):
        self.active_layer = layer

    def messageBar(self):
        return self.bar

    def actionPan(self):
        return self.actions.setdefault("pan", QAction("pan", self.window))

    def addDockWidget(self, area, dock):
        self.window.addDockWidget(area, dock)

    def removeDockWidget(self, dock):
        self.window.removeDockWidget(dock)

    def addPluginToVectorMenu(self, *args):
        pass

    def removePluginVectorMenu(self, *args):
        pass

    def addToolBarIcon(self, *args):
        pass

    def removeToolBarIcon(self, *args):
        pass

    def close(self):
        self.canvas.stopRendering()
        self.window.close()
        self.window.deleteLater()
        self.bar.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_review_ui_selection_completion_undo_and_cleanup(qgis_app, package):
    project = QgsProject.instance()
    layer = QgsVectorLayer(f"{package}|layername=superpixels", "test polygons", "ogr")
    project.addMapLayer(layer)
    iface = TestInterface()
    iface.canvas.setLayers([layer])
    iface.canvas.setDestinationCrs(layer.crs())
    iface.window.resize(1000, 700)
    plugin = PolygonQCPlugin(iface)
    plugin.initGui()
    plugin.show()
    dock = plugin.dock
    dock.layer_choice.setLayer(layer)
    dock.attach()
    try:
        assert dock.store is not None, dock.message.text()
        assert layer.readOnly()
        assert not layer.startEditing()
        assert layer.featureCount() == 2
        assert dock.plot == 1
        layer.selectByIds([1])
        assert dock.class_buttons[0].isEnabled()
        dock.assign("canopy")
        assert layer.getFeature(1)["class_final"] == "canopy"
        assert layer.getFeature(1)["reviewed"] == 2
        assert not layer.selectedFeatureCount()
        dock.plot_choice.setCurrentIndex(1)
        dock.choose_plot(1)
        assert dock.plot == 1
        assert "Complete the current plot" in dock.message.text()
        dock.complete()
        assert dock.plot == 2
        assert dock.progress.value() == 1
        dock.undo()
        assert dock.plot == 1
        assert dock.progress.value() == 0
        assert layer.getFeature(1)["reviewed"] == 2
        assert layer.getFeature(2)["reviewed"] == 0
        dock.undo()
        assert layer.getFeature(1)["class_final"] == "turf"
        dock.detach()
        assert layer.subsetString() == ""
        assert not layer.readOnly()
        assert layer.featureCount() == 4
        assert iface.canvas.mapTool() is not dock.tool or dock.tool is None
    finally:
        plugin.unload()
        plugin.unload()  # Repeated unload must not reuse deleted Qt actions.
        iface.canvas.setLayers([])
        project.clear()
        iface.close()


def test_saved_session_filter_can_resume(qgis_app, package):
    project = QgsProject.instance()
    layer = QgsVectorLayer(f"{package}|layername=superpixels", "test polygons", "ogr")
    layer.setSubsetString('"plot_id" = 2')
    layer.setCustomProperty(ReviewDock.FILTER_PROPERTY, layer.subsetString())
    project.addMapLayer(layer)
    iface = TestInterface()
    iface.canvas.setDestinationCrs(layer.crs())
    plugin = PolygonQCPlugin(iface)
    plugin.initGui()
    plugin.show()
    plugin.dock.layer_choice.setLayer(layer)
    plugin.dock.attach()
    try:
        assert plugin.dock.store is not None, plugin.dock.message.text()
        assert plugin.dock.plot == 1
    finally:
        plugin.unload()
        assert layer.subsetString() == ""
        project.clear()
        iface.close()


def test_click_tool_toggles_whole_features(qgis_app, package):
    project = QgsProject.instance()
    layer = QgsVectorLayer(f"{package}|layername=superpixels", "test polygons", "ogr")
    project.addMapLayer(layer)
    iface = TestInterface()
    iface.canvas.setLayers([layer])
    iface.canvas.setDestinationCrs(layer.crs())
    iface.window.resize(1000, 700)
    plugin = PolygonQCPlugin(iface)
    plugin.initGui()
    plugin.show()
    plugin.dock.layer_choice.setLayer(layer)
    plugin.dock.attach()
    iface.window.show()
    qgis_app.processEvents()
    try:
        dock = plugin.dock
        dock.zoom_to_plot()
        qgis_app.processEvents()
        point = iface.canvas.getCoordinateTransform().transform(5, 5)
        position = QPoint(round(point.x()), round(point.y()))
        QTest.mouseClick(iface.canvas.viewport(), Qt.MouseButton.LeftButton, pos=position)
        assert layer.selectedFeatureIds() == [1]
        QTest.mouseClick(iface.canvas.viewport(), Qt.MouseButton.LeftButton, pos=position)
        assert not layer.selectedFeatureIds()
    finally:
        plugin.unload()
        iface.canvas.setLayers([])
        project.clear()
        iface.close()
