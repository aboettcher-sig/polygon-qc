"""Load the built ZIP in real QGIS with a temporary profile and data copy.

Run after build.py and prepare_sample.py. Optional: --preview dev/plugin-preview.png
"""

import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
from tempfile import TemporaryDirectory
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
STARTUP = '''
import json, traceback
from pathlib import Path
from qgis.PyQt.QtCore import QTimer
from qgis.core import QgsProject
import qgis.utils
from qgis.utils import iface

def finish():
    iface.mapCanvas().stopRendering()
    if 'polygon_qc' in qgis.utils.plugins:
        if not qgis.utils.unloadPlugin('polygon_qc'):
            Path(RESULT).write_text(json.dumps({'ok': False, 'error': 'Plugin unload failed'}))
    # QGIS treats files under /tmp as temporary layers and otherwise prompts on exit.
    QgsProject.instance().removeAllMapLayers()
    def close():
        QgsProject.instance().setDirty(False)
        iface.mainWindow().close()
    QTimer.singleShot(200, close)

def run():
    try:
        assert qgis.utils.loadPlugin('polygon_qc'), 'loadPlugin failed'
        assert qgis.utils.startPlugin('polygon_qc'), 'startPlugin failed'
        plugin = qgis.utils.plugins['polygon_qc']
        plugin.show()
        dock = plugin.dock
        layer = next(l for l in QgsProject.instance().mapLayers().values() if l.name().startswith('Polygon QC'))
        layer.setDataSource(WORKING + '|layername=superpixels', layer.name(), 'ogr')
        dock.layer_choice.setLayer(layer)
        dock.attach()
        assert dock.store is not None, dock.message.text()
        starting_plot = dock.plot
        starting_progress = dock.progress.value()
        for name in ('actionSelectRectangle', 'actionSelectPolygon', 'actionSelectFreehand'):
            dock.use_native_tool(name)
            assert iface.mapCanvas().mapTool() is not None
        dock.use_click_tool()
        first = next(layer.getFeatures())
        old = first['class_final']
        target = next(c for c in dock.store.classes if c != old)
        layer.selectByIds([first.id()])
        dock.assign(target)
        assert layer.getFeature(first.id())['class_final'] == target
        dock.complete()
        assert dock.progress.value() == starting_progress + 1
        dock.undo()
        dock.undo()
        assert dock.plot == starting_plot
        assert layer.getFeature(first.id())['class_final'] == old
        assert dock.progress.value() == starting_progress
        iface.mainWindow().resize(1400, 940)
        iface.messageBar().clearWidgets()
        iface.mapCanvas().refresh()
        def snapshot():
            try:
                if PREVIEW:
                    assert iface.mainWindow().grab().save(PREVIEW)
                Path(RESULT).write_text(json.dumps({'ok': True, 'features_in_plot': layer.featureCount(), 'plots': len(dock.store.plots)}))
            except Exception:
                Path(RESULT).write_text(json.dumps({'ok': False, 'error': traceback.format_exc()}))
            finally:
                finish()
        QTimer.singleShot(1800, snapshot)
    except Exception:
        Path(RESULT).write_text(json.dumps({'ok': False, 'error': traceback.format_exc()}))
        finish()

QTimer.singleShot(1200, run)
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", type=Path)
    args = parser.parse_args()
    with TemporaryDirectory(prefix="polygon-qc-desktop-") as directory:
        temp = Path(directory)
        with ZipFile(ROOT / "dist/polygon_qc.zip") as archive:
            archive.extractall(temp / "plugins")
        with sqlite3.connect((ROOT / "dev/review.gpkg").as_uri() + "?mode=ro", uri=True) as source:
            with sqlite3.connect(temp / "review.gpkg") as target:
                source.backup(target)
        result_path = temp / "result.json"
        values = {"WORKING": str(temp / "review.gpkg"), "RESULT": str(result_path),
                  "PREVIEW": str(args.preview.resolve()) if args.preview else ""}
        script = temp / "smoke.py"
        script.write_text("\n".join(f"{key} = {value!r}" for key, value in values.items()) + "\n" + STARTUP)
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QGIS_PLUGINPATH=str(temp / "plugins"))
        try:
            process = subprocess.run(
                ["qgis", "--nologo", "--noversioncheck", "--noplugins", "--profiles-path", str(temp / "profiles"),
                 "--profile", "smoke", "--project", str(ROOT / "dev/sample_qc.qgz"), "--code", str(script)],
                env=env, text=True, capture_output=True, timeout=25,
            )
        except subprocess.TimeoutExpired as exc:
            print(result_path.read_text() if result_path.exists() else "No result recorded")
            print(exc.stderr)
            raise SystemExit("QGIS did not exit after the smoke test")
        result = json.loads(result_path.read_text()) if result_path.exists() else {"ok": False, "error": "No result recorded"}
        print(json.dumps({"qgis_exit": process.returncode, **result}, indent=2))
        if process.returncode or not result.get("ok"):
            print(process.stdout[-6000:])
            print(process.stderr[-6000:])
            raise SystemExit(1)


if __name__ == "__main__":
    main()
