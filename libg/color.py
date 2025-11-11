__all__ = [
    "initColor",
    "getTheme",
    "color",
]

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor
from PySide6.QtCore import QObject, Signal

class Theme(QObject):
    sheet: dict[str, str | tuple[str, str]] = {
        "black": "#000000",
        "gray": "#a0a0a0",
        "white": "#ffffff",
        "red": "#ff0000",
        "yellow": "#ffff00",
        "silver": ("#c0c0c0", "#606060"),
        "tianyi": "#66ccff", # 天依！
        "orange": ("#b87333", "#ffa500"),
        "green": ("#228b22", "#00dd00"),
    }
    colorChanged = Signal()
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.app.paletteChanged.connect(self.update)
        self.update()
    def update(self):
        self.dark = self.app.palette().window().color().lightness() < 128
        self.colorChanged.emit()
    def hexcolor(self, name: str, /, dark: bool = None): # TODO 将这个加入 lib.color
        if not name in self.sheet or name.startswith("#"):
            return name
        if dark is None:
            dark = self.dark
        if isinstance(col := self.sheet[name], tuple):
            return col[dark]
        return col
    def color(self, name: str, /, dark: bool = None):
        return QColor(self.hexcolor(name, dark))
_theme: Theme
def initColor(app: QApplication):
    global _theme
    _theme = Theme(app)
def getTheme():
    return _theme
def color(name: str, /, dark: bool = None):
    return _theme.color(name, dark)