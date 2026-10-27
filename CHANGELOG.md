# Changelog

## 0.2.1

- Package the plugin as `polygon_QC` to match its QGIS registry entry.
- Use literal SQL for the fixed plot-completion table and document the existing
  identifier quoting with narrowly scoped Bandit B608 false-positive annotations.
- Test layer names containing quotes and SQL syntax, and class labels containing
  SQL syntax, through editing, completion, and undo.

The review behavior, geometry protection, original classes, and saved progress
are unchanged. No data migration is needed. Earlier registry uploads were blocked
by the scanner; this patch addresses the reproduced Bandit findings.

## 0.2.0

- Support QGIS 4 / Qt 6 while retaining QGIS 3.40+ compatibility.
- Use scoped Qt and QGIS enums and the current `QAction` import location.
- Exercise click selection through Qt's event system on both Qt versions.
- Clean up test widgets and use QGIS's test application lifecycle on exit.
- Add a QGIS 4 test and ZIP-build workflow for GitHub Actions.

The classification fields, review states, geometry protection, selection options,
and plot-completion workflow are unchanged. No data migration is needed.

Verified on Linux with QGIS 3.40.15 / Qt 5.15.18 and QGIS 4.2.3 / Qt 6.9.2:
14 automated tests pass on each, including the full-sample protected-data check.
The packaged desktop smoke test also passes on both versions with clean exits.

## 0.1.0

Initial release for QGIS 3.40–3.x.

- Review existing polygon classifications one plot at a time.
- Select individual polygons or use QGIS's rectangle, polygon, and freehand selection.
- Change `class_final` and `reviewed` while preserving geometry and `class_auto`.
- Complete a plot to accept its remaining polygons and advance.
- Save each action immediately, resume pending plots, and undo within a session.

Verified on QGIS 3.40.15 / Qt 5 with 14 automated tests and a packaged desktop
smoke test. QGIS 4 compatibility is not declared for this release.
