# Changelog

## 0.1.0

Initial release for QGIS 3.40–3.x.

- Review existing polygon classifications one plot at a time.
- Select individual polygons or use QGIS's rectangle, polygon, and freehand selection.
- Change `class_final` and `reviewed` while preserving geometry and `class_auto`.
- Complete a plot to accept its remaining polygons and advance.
- Save each action immediately, resume pending plots, and undo within a session.

Verified on QGIS 3.40.15 / Qt 5 with 14 automated tests and a packaged desktop
smoke test. QGIS 4 compatibility is not declared for this release.
