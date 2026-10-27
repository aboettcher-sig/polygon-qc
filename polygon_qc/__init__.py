"""QGIS entry point; importing the storage module needs no QGIS runtime."""


def classFactory(iface):
    from .plugin import PolygonQCPlugin

    return PolygonQCPlugin(iface)

