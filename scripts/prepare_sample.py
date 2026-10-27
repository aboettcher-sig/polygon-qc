#!/usr/bin/env python3
"""Create the ignored local test project. Run with QGIS's Python environment."""

import argparse
import os
from pathlib import Path
import sqlite3
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qgis.PyQt.QtGui import QColor
from qgis.core import QgsApplication, QgsProject, QgsRasterLayer, QgsReferencedRectangle, QgsVectorLayer
from polygon_qc.store import ReviewStore
from polygon_qc.style import renderer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path,
                        default=ROOT / "2025-05-12_us-co-denver-2025_sample_one")
    args = parser.parse_args()
    source = args.data.resolve() / "superpixels.gpkg"
    raster = args.data.resolve() / f"{args.data.name}.tif"
    destination = ROOT / "dev" / "review.gpkg"
    project_path = ROOT / "dev" / "sample_qc.qgz"
    if not source.exists() or not raster.exists():
        parser.error("Expected superpixels.gpkg and a TIFF named after the sample directory.")
    if destination.exists() or project_path.exists():
        parser.error("dev/review.gpkg or dev/sample_qc.qgz already exists. Existing review work was preserved. "
                     "To reset, close QGIS and explicitly remove those two files before running again.")
    destination.parent.mkdir(exist_ok=True)
    # SQLite backup includes any committed WAL data and never edits the original.
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as src:
        with sqlite3.connect(destination) as dst:
            src.backup(dst)
    store = ReviewStore(destination)
    app = QgsApplication([], False)
    app.initQgis()
    project = QgsProject.instance()
    imagery = QgsRasterLayer(str(raster), "RGB imagery")
    polygons = QgsVectorLayer(f"{destination}|layername=superpixels", "Polygon QC — working copy", "ogr")
    if not imagery.isValid() or not polygons.isValid():
        raise RuntimeError("QGIS could not load the sample layers.")
    polygons.setReadOnly(True)
    polygons.setRenderer(renderer(store.classes))
    polygons.setOpacity(0.45)
    project.addMapLayer(imagery)
    project.addMapLayer(polygons)
    project.setCrs(polygons.crs())
    project.setBackgroundColor(QColor("#eef0f2"))
    project.setSelectionColor(QColor(255, 225, 30, 190))
    project.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(polygons.extent(), polygons.crs()))
    project.setTitle("Polygon QC local test")
    if not project.write(str(project_path)):
        raise RuntimeError("Could not save the sample project.")
    print(f"Project: {project_path}\nWorking data: {destination}\nSource data left unchanged.")
    project.clear()
    # Keep QGIS initialized until process exit, avoiding provider teardown order issues.


if __name__ == "__main__":
    main()
