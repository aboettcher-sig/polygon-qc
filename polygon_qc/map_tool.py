"""Click to toggle whole polygons in the current (filtered) review layer."""

from qgis.PyQt.QtCore import Qt
from qgis.core import QgsFeatureRequest, QgsGeometry, QgsPointXY
from qgis.gui import QgsMapTool


class ToggleSelectTool(QgsMapTool):
    def __init__(self, canvas, layer):
        super().__init__(canvas)
        self.layer = layer
        self.setCursor(Qt.CrossCursor)

    def canvasReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        point = self.toLayerCoordinates(self.layer, event.pos())
        geometry = QgsGeometry.fromPointXY(QgsPointXY(point))
        request = QgsFeatureRequest().setFilterRect(geometry.boundingBox())
        hits = [feature.id() for feature in self.layer.getFeatures(request)
                if feature.geometry().intersects(geometry)]
        if hits:
            # Boundary clicks can touch two polygons: use a stable single target.
            fid = min(hits)
            if fid in self.layer.selectedFeatureIds():
                self.layer.deselect(fid)
            else:
                self.layer.select(fid)

