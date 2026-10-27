"""Small, valid GeoPackages exercise the same triggers as production data."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from osgeo import gdal, ogr, osr

gdal.UseExceptions()
ogr.UseExceptions()
osr.UseExceptions()


def create_package(path):
    source = ogr.GetDriverByName("GPKG").CreateDataSource(str(path))
    crs = osr.SpatialReference()
    crs.ImportFromEPSG(3857)
    layer = source.CreateLayer("superpixels", crs, ogr.wkbPolygon)
    for name, kind in (("plot_id", ogr.OFTInteger), ("class_auto", ogr.OFTString),
                       ("class_final", ogr.OFTString), ("reviewed", ogr.OFTInteger),
                       ("notes", ogr.OFTString)):
        layer.CreateField(ogr.FieldDefn(name, kind))
    for fid, plot, automatic in ((1, 1, "turf"), (2, 1, "roads"), (3, 2, "canopy"), (4, 2, "turf")):
        feature = ogr.Feature(layer.GetLayerDefn())
        feature.SetFID(fid)
        for name, value in (("plot_id", plot), ("class_auto", automatic),
                            ("class_final", automatic), ("reviewed", 0), ("notes", "keep this")):
            feature.SetField(name, value)
        x = (fid - 1) * 10
        feature.SetGeometry(ogr.CreateGeometryFromWkt(
            f"POLYGON (({x} 0, {x+10} 0, {x+10} 10, {x} 10, {x} 0))"
        ))
        layer.CreateFeature(feature)
        feature = None
    layer = None
    source = None
    return Path(path)


@pytest.fixture
def package(tmp_path):
    return create_package(tmp_path / "test.gpkg")


@pytest.fixture(scope="session")
def qgis_app():
    from qgis.testing import start_app

    # QGIS owns initialization and orderly provider cleanup before Qt teardown.
    yield start_app()
