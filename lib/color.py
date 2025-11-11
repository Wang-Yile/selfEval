__all__ = [
    "RGB", "Text", "plen",
    "Red", "Green", "Yellow", "Blue", "Magenta", "Purple", "Cyan",
    "White", "Black", "Gray", "Orange", "Pink", "Brown", "Violet",
    "Turquoise", "Gold", "Silver", "Lime", "Olive", "Teal", "Navy",
    "Maroon", "Coral", "Salmon", "Plum", "Orchid", "Skyblue",
    "RED", "GREEN", "YELLOW", "BLUE", "MAGENTA", "PURPLE", "CYAN",
    "WHITE", "BLACK", "GRAY", "ORANGE", "PINK", "BROWN", "VIOLET",
    "TURQUOISE", "GOLD", "SILVER", "LIME", "OLIVE", "TEAL", "NAVY",
    "MAROON", "CORAL", "SALMON", "PLUM", "ORCHID", "SKYBLUE",
    "BOLD",
]

# TODO 优化 color 效率

import copy

from wcwidth import wcswidth

class Style:
    ansi = ""
    css = "" # TODO css support
    def __mul__(self, other):
        if isinstance(other, Text):
            return Text([Span(x.content, x.style + [self], x.cell_len) for x in other.lst], _cell_len=other.cell_len)
        elif isinstance(other, Span):
            return Span(other.content, other.style + [self], _cell_len=other.cell_len)
        elif isinstance(other, str):
            return Span(other, [self])
        return NotImplemented
    def __rmul__(self, other):
        return self * other
class Bold(Style):
    ansi = "1"
_ansi_colors = { # TODO: full color support
    # https://www.w3school.com.cn/cssref/css_colors.asp
    "red": "31",
    "green": "32",
    "yellow": "33",
    "blue": "34",
    "magenta": "35",
    "purple": "38;2;128;00;128",
    "cyan": "36",
    "white": "38;2;255;255;255",
    "black": "38;2;0;0;0",
    "grey": "38;2;128;128;128",
    "orange": "38;2;255;165;0",
    "pink": "38;2;255;192;203",
    "brown": "38;2;165;42;42",
    "violet": "38;2;238;130;238",
    "turquoise": "38;2;64;224;208",
    "gold": "38;2;255;215;0",
    "silver": "38;2;192;192;192",
    "lime": "38;2;0;255;0",
    "olive": "38;2;128;128;0",
    "teal": "38;2;0;128;128",
    "navy": "38;2;0;0;128",
    "maroon": "38;2;128;0;0",
    "coral": "38;2;255;127;80",
    "salmon": "38;2;250;128;114",
    "plum": "38;2;221;160;221",
    "orchid": "38;2;218;112;214",
    "skyblue": "38;2;135;206;235",
}
class Color(Style):
    def __init__(self, c: str, /):
        super().__init__()
        self.ansi = _ansi_colors[c]
class RGB(Style):
    def __init__(self, r: float | int, g: float | int, b: float | int, /):
        super().__init__()
        self.ansi = f"38;2;{int(r)};{int(g)};{int(b)}"
class Span():
    def __init__(self, content = "", style: list[Style] = None, *, _cell_len: int = None):
        self.style = [] if style is None else style
        self.content = content
        self.cell_len = wcswidth(content) if _cell_len is None else _cell_len
    def toansi(self):
        return "\033[" + ";".join(x.ansi for x in self.style) + "m" + self.content + "\033[0m"
    def tocss(self): # TODO
        return ""
    def tohtml(self): # TODO
        return self.content
    def copy(self):
        return copy.deepcopy(self)
    def __deepcopy__(self):
        return Span(self.content, self.style.copy(), self.cell_len)
    def __add__(self, other):
        if isinstance(other, Text):
            return Text([self] + other.lst)
        elif isinstance(other, Span):
            return Text([self, other])
        elif isinstance(other, Style):
            return Span(self.content, self.style + [other], _cell_len=self.cell_len)
        elif isinstance(other, str):
            return Text([self, Span(other)])
        return NotImplemented
    def __radd__(self, other):
        if isinstance(other, Style):
            return Span(self.content, self.style + [other], _cell_len=self.cell_len)
        elif isinstance(other, str):
            return Text([Span(other), self])
        return NotImplemented
    def __str__(self):
        return self.content
    def __repr__(self):
        return f"Span({repr(self.content)}, style={self.style})"
class Text():
    def __init__(self, lst: str | list[Span] = None, *, _cell_len: int = None):
        if isinstance(lst, str):
            lst = [Span(lst)]
        self.lst = [] if lst is None else lst
        self.cell_len = sum(x.cell_len for x in self.lst) if _cell_len is None else _cell_len
    def toansi(self):
        return "".join(x.toansi() for x in self.lst)
    def tocss(self): # TODO
        return ""
    def tohtml(self):
        return "".join(x.tohtml() for x in self.lst)
    def copy(self):
        return copy.deepcopy(self)
    # TODO 支持各种字符串方法
    def find(self, c: "Text | str"):
        raise NotImplementedError
    def rfind(self, c: "Text | str"):
        raise NotImplementedError
    def join(self, lst: list["Text | str"]):
        if not lst:
            return Text()
        ret = lst[0].lst.copy()
        for i in range(1, len(lst)):
            ret += self.lst + lst[i].lst
        return Text(ret, _cell_len=sum(x.cell_len for x in lst) + (len(lst)-1) * self.cell_len)
    def __deepcopy__(self):
        return Text(copy.deepcopy(self.lst), _cell_len=self.cell_len)
    def __add__(self, other):
        if isinstance(other, Text):
            return Text(self.lst + other.lst)
        elif isinstance(other, Span):
            return Text(self.lst + [other])
        elif isinstance(other, str):
            w = wcswidth(other)
            return Text(self.lst + [Span(other, _cell_len=w)], _cell_len=self.cell_len + w)
        return NotImplemented
    def __iadd__(self, other):
        if isinstance(other, Text):
            self.lst += other.lst
            self.cell_len += other.cell_len
            return self
        elif isinstance(other, Span):
            self.lst += [other]
            self.cell_len += other.cell_len
            return self
        elif isinstance(other, str):
            w = wcswidth(other)
            self.lst += [Span(other, _cell_len=w)]
            self.cell_len += w
            return self
        return NotImplemented
    def __radd__(self, other):
        if isinstance(other, str):
            w = wcswidth(other)
            return Text(self.lst + [Span(other, _cell_len=w)], _cell_len=self.cell_len + w)
        return NotImplemented
    def __str__(self):
        return "".join(str(span) for span in self.lst)
    def __repr__(self):
        return f"Text({self.lst})"

_red = Color("red")
_green = Color("green")
_yellow = Color("yellow")
_blue = Color("blue")
_magenta = Color("magenta")
_purple = Color("purple")
_cyan = Color("cyan")
_white = Color("white")
_black = Color("black")
_grey = Color("grey")
_orange = Color("orange")
_pink = Color("pink")
_brown = Color("brown")
_violet = Color("violet")
_turquoise = Color("turquoise")
_gold = Color("gold")
_silver = Color("silver")
_lime = Color("lime")
_olive = Color("olive")
_teal = Color("teal")
_navy = Color("navy")
_maroon = Color("maroon")
_coral = Color("coral")
_salmon = Color("salmon")
_plum = Color("plum")
_orchid = Color("orchid")
_skyblue = Color("skyblue")
_bold = Bold()

def Red(s: Text | Span | str) -> Text | Span: return s * _red
def Green(s: Text | Span | str) -> Text | Span: return s * _green
def Yellow(s: Text | Span | str) -> Text | Span: return s * _yellow
def Blue(s: Text | Span | str) -> Text | Span: return s * _blue
def Magenta(s: Text | Span | str) -> Text | Span: return s * _magenta
def Purple(s: Text | Span | str) -> Text | Span: return s * _purple
def Cyan(s: Text | Span | str) -> Text | Span: return s * _cyan
def White(s: Text | Span | str) -> Text | Span: return s * _white
def Black(s: Text | Span | str) -> Text | Span: return s * _black
def Gray(s: Text | Span | str) -> Text | Span: return s * _grey
def Orange(s: Text | Span | str) -> Text | Span: return s * _orange
def Pink(s: Text | Span | str) -> Text | Span: return s * _pink
def Brown(s: Text | Span | str) -> Text | Span: return s * _brown
def Violet(s: Text | Span | str) -> Text | Span: return s * _violet
def Turquoise(s: Text | Span | str) -> Text | Span: return s * _turquoise
def Gold(s: Text | Span | str) -> Text | Span: return s * _gold
def Silver(s: Text | Span | str) -> Text | Span: return s * _silver
def Lime(s: Text | Span | str) -> Text | Span: return s * _lime
def Olive(s: Text | Span | str) -> Text | Span: return s * _olive
def Teal(s: Text | Span | str) -> Text | Span: return s * _teal
def Navy(s: Text | Span | str) -> Text | Span: return s * _navy
def Maroon(s: Text | Span | str) -> Text | Span: return s * _maroon
def Coral(s: Text | Span | str) -> Text | Span: return s * _coral
def Salmon(s: Text | Span | str) -> Text | Span: return s * _salmon
def Plum(s: Text | Span | str) -> Text | Span: return s * _plum
def Orchid(s: Text | Span | str) -> Text | Span: return s * _orchid
def Skyblue(s: Text | Span | str) -> Text | Span: return s * _skyblue

def RED(s: Text | Span | str) -> Text | Span: return s * _red * _bold
def GREEN(s: Text | Span | str) -> Text | Span: return s * _green * _bold
def YELLOW(s: Text | Span | str) -> Text | Span: return s * _yellow * _bold
def BLUE(s: Text | Span | str) -> Text | Span: return s * _blue * _bold
def MAGENTA(s: Text | Span | str) -> Text | Span: return s * _magenta * _bold
def PURPLE(s: Text | Span | str) -> Text | Span: return s * _purple * _bold
def CYAN(s: Text | Span | str) -> Text | Span: return s * _cyan * _bold
def WHITE(s: Text | Span | str) -> Text | Span: return s * _white * _bold
def BLACK(s: Text | Span | str) -> Text | Span: return s * _black * _bold
def GRAY(s: Text | Span | str) -> Text | Span: return s * _grey * _bold
def ORANGE(s: Text | Span | str) -> Text | Span: return s * _orange * _bold
def PINK(s: Text | Span | str) -> Text | Span: return s * _pink * _bold
def BROWN(s: Text | Span | str) -> Text | Span: return s * _brown * _bold
def VIOLET(s: Text | Span | str) -> Text | Span: return s * _violet * _bold
def TURQUOISE(s: Text | Span | str) -> Text | Span: return s * _turquoise * _bold
def GOLD(s: Text | Span | str) -> Text | Span: return s * _gold * _bold
def SILVER(s: Text | Span | str) -> Text | Span: return s * _silver * _bold
def LIME(s: Text | Span | str) -> Text | Span: return s * _lime * _bold
def OLIVE(s: Text | Span | str) -> Text | Span: return s * _olive * _bold
def TEAL(s: Text | Span | str) -> Text | Span: return s * _teal * _bold
def NAVY(s: Text | Span | str) -> Text | Span: return s * _navy * _bold
def MAROON(s: Text | Span | str) -> Text | Span: return s * _maroon * _bold
def CORAL(s: Text | Span | str) -> Text | Span: return s * _coral * _bold
def SALMON(s: Text | Span | str) -> Text | Span: return s * _salmon * _bold
def PLUM(s: Text | Span | str) -> Text | Span: return s * _plum * _bold
def ORCHID(s: Text | Span | str) -> Text | Span: return s * _orchid * _bold
def SKYBLUE(s: Text | Span | str) -> Text | Span: return s * _skyblue * _bold

def BOLD(s: Text | Span | str) -> Text | Span: return s  * _bold

def plen(s: Text | Span | str) -> Text | Span:
    if isinstance(s, str):
        return wcswidth(s)
    return s.cell_len
