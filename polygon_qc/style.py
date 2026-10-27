"""Consistent class colors for the review layer and buttons."""

from qgis.PyQt.QtGui import QColor
from qgis.core import QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsFillSymbol


COLORS = {
    "turf": "#73b748", "undeveloped lands": "#b3a46c", "roads": "#656b73",
    "unlabelled": "#e35bc0", "structures": "#d46b53", "ground cover": "#b6d97b",
    "concrete": "#bec8d2", "canopy": "#176f42", "bare earth": "#b97e4e",
    "impervious other": "#956aaf", "open water": "#297bc1", "vehicles": "#f2b843",
    "horse corrals": "#825b39", "trampolines": "#48beb1", "pools": "#49cbee",
}


def class_color(name, index=0):
    return QColor(COLORS[name]) if name in COLORS else QColor.fromHsv((index * 137) % 360, 140, 205)


def renderer(classes):
    categories = []
    for index, name in enumerate(classes):
        symbol = QgsFillSymbol.createSimple({
            "color": class_color(name, index).name(), "outline_color": "50,60,65,180",
            "outline_width": "0.12", "outline_width_unit": "MM",
        })
        categories.append(QgsRendererCategory(name, symbol, name))
    return QgsCategorizedSymbolRenderer("class_final", categories)

