"""Optional integration against a supplied real GeoPackage; writes only a temp copy."""

import hashlib
import os
from pathlib import Path
import sqlite3

import pytest
from qgis.core import QgsVectorLayer

from polygon_qc.store import ReviewStore


SAMPLE = os.environ.get("QC_SAMPLE")
pytestmark = pytest.mark.skipif(not SAMPLE, reason="Set QC_SAMPLE to a sample GeoPackage to run this integration.")


def row_digest(path, exclude=()):
    digest = hashlib.sha256()
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        columns = [row[1] for row in db.execute('PRAGMA table_info("superpixels")') if row[1] not in exclude]
        fields = ",".join('"' + name.replace('"', '""') + '"' for name in columns)
        for row in db.execute(f"SELECT {fields} FROM superpixels ORDER BY fid"):
            for value in row:
                data = value if isinstance(value, bytes) else repr(value).encode()
                digest.update(len(data).to_bytes(8, "little"))
                digest.update(data)
    return digest.hexdigest()


def test_real_sample_preserves_all_other_fields_geometry_and_source(qgis_app, tmp_path):
    source = Path(SAMPLE).resolve()
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    working = tmp_path / "working.gpkg"
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as src:
        with sqlite3.connect(working) as dst:
            src.backup(dst)
    before = row_digest(working)
    protected = row_digest(working, ("class_final", "reviewed"))
    store = ReviewStore(working)
    layer = QgsVectorLayer(f"{working}|layername=superpixels", "working", "ogr")
    assert layer.isValid()
    assert layer.setReadOnly(True)
    plot = store.plots[0]
    layer.setSubsetString(f'"plot_id"={plot}')
    selected = [feature.id() for feature in list(layer.getFeatures())[:5]]
    first = layer.getFeature(selected[0])
    target = next(c for c in store.classes if c != first["class_auto"])
    store.assign(plot, selected, target)
    layer.reload()
    assert layer.getFeature(selected[0])["class_final"] == target
    assert layer.getFeature(selected[0])["reviewed"] == 2
    store.complete(plot)
    assert plot in ReviewStore(working).summary()[1]
    assert row_digest(working, ("class_final", "reviewed")) == protected
    store.undo()
    store.undo()
    assert row_digest(working) == before
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash

