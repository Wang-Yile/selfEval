import decimal
import hashlib
import os
import random
import shutil
import tempfile
import zipfile
from functools import cmp_to_key, lru_cache
from itertools import chain
from typing import Callable

from .color import *
from .core import CACHE_DISABLED, error, warning

# 单位转换
# 时间基准单位是微秒
# 空间基准单位是字节
def usec(t: int): return t
def msec(t: int): return t * 1000
def sec(t: int): return t * 1000000
def minute(t: int): return t * 60000000
def Byte(n: int): return int(n)
def KiB(n: int): return int(n * 2**10)
def MiB(n: int): return int(n * 2**20)
def GiB(n: int): return int(n * 2**30)
def TiB(n: int): return int(n * 2**40)

# f- 系列格式化函数的逆运算
# 此部分单位转换函数忽略空格
def isnum(s: str):
    x = s.split(".")
    if len(x) > 2:
        return False
    return x[0].isdigit() and (len(x) == 1 or x[1].isdigit())
def tobool(s: str):
    s = s.lower()
    if s == "true":
        return True
    elif s == "false":
        return False
def totime(s: str):
    s = s.replace(" ", "")
    if s.isdigit():
        return int(s)
    sheet = {
        usec: ("us", "usec", "microsecond"),
        msec: ("ms", "msec", "millisecond"),
        sec: ("s", "sec", "second"),
        minute: ("m", "min", "minute"),
    }
    for foo in sheet:
        for suffix in sheet[foo]:
            if s.endswith(suffix) and isnum(t := s[:-len(suffix)]):
                return int(foo(float(t)))
def tomem(s: str):
    s = s.replace(" ", "")
    if s.isdigit():
        return int(s)
    sheet = {
        Byte: ("B", "Byte"),
        KiB: ("K", "KiB"),
        MiB: ("M", "MiB"),
        GiB: ("G", "GiB"),
        TiB: ("T", "TiB"),
    }
    for foo in sheet:
        for suffix in sheet[foo]:
            if s.endswith(suffix) and isnum(t := s[:-len(suffix)]):
                return int(foo(float(t)))

# 格式化
def ffloat(x: float, prec = 2, eps = 1e-6):
    s = f"{x:.{prec}f}"
    y = float(s)
    if abs(x - y) > eps:
        return s
    s = s.rstrip("0")
    return str(s[:-1]) if s[-1] == "." else s
def ftime(t: int):
    t //= 1000
    return f"{t} ms" if t <= 1500 else f"{ffloat(t/1000)} s"
def fmemory(n: int):
    unit = "TGMK"
    for i in range(len(unit)):
        if n >= (size := 1 << (10 * (len(unit) - i))):
            return f"{ffloat(n/size)} {unit[i]}iB"
    return f"{n} B"

# 高级格式化（基于 color）
def wsetp(s: Text | str, w: int):
    return s if (x := plen(s)) >= w else (w-x)*" " + s
def wsetlp(s: str, w: int):
    return s if (x := plen(s)) >= w else s + (w-x)*" "
def wsetcp(s: str, w: int):
    return s if (x := plen(s)) >= w else (w-x)//2*" " + s + (w-x-(w-x)//2)*" "
_ok = GREEN("OK")
_ac = GREEN("Accepted")
_wa = RED("Wrong Answer")
_pt = YELLOW("Points")
_re = MAGENTA("Runtime Error")
_tl = BLUE("Time Limit Exceed")
_ml = BLUE("Memory Limit Exceed")
_ol = BLUE("Output Limit Exceed")
_il = BLUE("Illegal Interaction Format")
_fb = RED("Forbidden System Call")
_ig = GRAY("Ignored")
_fail = RED("FAIL")
_uke = NAVY("Unknown Error")
def fmt_verdict(s: str):
    if s == "ok": return _ok
    elif s == "ac": return _ac
    elif s == "wa": return _wa
    elif s == "pt": return _pt
    elif s == "re": return _re
    elif s == "tl": return _tl
    elif s == "ml": return _ml
    elif s == "ol": return _ol
    elif s == "il": return _il
    elif s == "fb": return _fb
    elif s == "ig": return _ig
    elif s == "fail": return _fail
    return _uke
_OK = GREEN("OK")
_AC = GREEN("AC")
_WA = RED("WA")
_PT = YELLOW("PT")
_RE = MAGENTA("RE")
_TL = BLUE("TLE")
_ML = BLUE("MLE")
_OL = BLUE("OLE")
_IL = BLUE("IL")
_FB = RED("FBD")
_IG = GRAY("IGN")
_FAIL = RED("FAIL")
_UKE = NAVY("UKE Error")
def fmt_Verdict(s: str):
    if s == "ok": return _OK
    elif s == "ac": return _AC
    elif s == "wa": return _WA
    elif s == "pt": return _PT
    elif s == "re": return _RE
    elif s == "tl": return _TL
    elif s == "ml": return _ML
    elif s == "ol": return _OL
    elif s == "il": return _IL
    elif s == "fb": return _FB
    elif s == "ig": return _IG
    elif s == "fail": return _FAIL
    return _UKE
def _fmt_score(x: decimal.Decimal, _half = decimal.Decimal(0.5)):
    if x <= _half:
        return RGB(255, max(int(x*510), 0), 0)
    return RGB(max(int((1-x)*510), 0), 255, 0)
def fmt_score(x: decimal.Decimal):
    s = str(x*100)
    if (i := s.rfind(".")) != -1:
        s = s[:i+3].rstrip("0").rstrip(".")
    return BOLD(_fmt_score(x) * s)
def _fmt_table(a: list[int], w: int, sep = 1):
    if not a:
        return []
    for c in range(min(len(a), w), 0, -1):
        r = int(len(a) / c)
        ret = []
        sum = (c-1)*sep
        for i in range(c):
            sum += (x := max(a[k] for j in range(r) if (k := i+j*c) < len(a)))
            if sum > w:
                break
            ret.append(x)
        else:
            return ret
    return [max(a)]
def fmt_table(a: list[Text | str], w: int, /, pre: Text | str = "    ", sep: Text | str = "    "):
    if not a:
        return Text()
    wpre = plen(pre)
    wsep = plen(sep)
    wd = _fmt_table([plen(x) for x in a], w - wpre, wsep)
    ret = Text()
    r = len(a) // len(wd)
    for i in range(r):
        if i:
            ret += "\n"
        ret += pre
        ret += sep.join(wsetlp(a[i*len(wd)+j], wd[j]) for j in range(min(len(wd), len(a)-i*len(wd))))
    return ret

# 此部分所有哈希函数都不能用于安全领域
def hash32(obj):
    return hashlib.sha3_256(obj).hexdigest()[2:10]
def random_hash(func) -> str:
    return func(random.randbytes(128))
def get_unique_path(cwd: str, func = hash32, ed = "a"):
    """
    在目录 cwd 下使用随机方法生成唯一文件名，返回完整路径。如果文件名已被占用，解决方法是在末尾加入字符 ed。此函数生成的文件名在多进程下可能不唯一。
    """
    ret = os.path.join(cwd, random_hash(func))
    while os.path.exists(ret):
        ret += ed
    return ret

# hashlib 扩展
def hash_file(path: str, func: Callable[[], "hashlib._Hash"] = hashlib.md5, /, trunk = 8192):
    ret = func()
    with open(path, "rb") as file:
        while block := file.read(trunk):
            ret.update(block)
    return ret

# TODO 改用 pathlib
# 文件操作（基于路径）
def stdopen(path: str, mode = "r", encoding = "utf-8", newline = None):
    """
    标准文件打开方式，跟随符号连接，仅打开路径字符串，对于其它任何类型的 path 原样返回。
    """
    if mode.find("b") != -1:
        encoding = None
    return open(path, mode, encoding=encoding, newline=newline) if isinstance(path, str) else path
def is_xok(path: str, strict = True):
    if not os.access(path, os.X_OK):
        return False
    if not strict:
        return True
    with stdopen(path, "rb") as file:
        return file.read(4) == 0x7f454c46.to_bytes(4, "big")
def ensure_removed(path: str, /, ignore = True):
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
        elif os.path.isfile(path) or os.path.islink(path):
            os.remove(path)
        else:
            error(f"ensure_removed 无法识别 {repr(path)}，这可能是一个挂载点。", True)
    except OSError as err:
        if ignore:
            error(err)
        else:
            err.add_note(f"ensure_removed 无法删除 {repr(path)}")
            raise
def copy_to(src: str, dst: str):
    """
    将 src 拷贝到 dst 目录下。
    """
    if os.path.isdir(src):
        shutil.copytree(src, os.path.join(dst, os.path.basename(src)))
    else:
        shutil.copyfile(src, os.path.join(dst, os.path.basename(src)))

# 路径排序
path_sort_type = tuple[str, list[str | int]]
@lru_cache(8192)
def path_cut_for_sort(path: str):
    def _foo(x: str):
        ret: list[str] = []
        for c in x:
            if not ret or ret[-1].isdigit() != c.isdigit() or ret[-1] == "." or c == ".":
                ret.append(c)
            else:
                ret[-1] += c
        for i in range(len(ret)):
            if ret[i].isdigit():
                ret[i] = int(ret[i])
        return ret
    return os.path.dirname(path), _foo(os.path.basename(path))
def path_cmp(x: str, y: str):
    x = path_cut_for_sort(x)
    y = path_cut_for_sort(y)
    def _foo(a, b):
        if a < b:
            return -1
        elif b < a:
            return 1
        return 0
    if x[0] != y[0]:
        return _foo(x[0], y[0])
    for i in range(min(len(x[1]), len(y[1]))):
        if x[1][i] != y[1][i]:
            if x[1][i] == ".":
                return -1
            if y[1][i] == ".":
                return 1
            if type(x[1][i]) != type(y[1][i]):
                return 1 if isinstance(x[1][i], int) else -1
            return _foo(x[1][i], y[1][i])
    return _foo(len(x[1]), len(y[1]))
path_cmp = cmp_to_key(path_cmp)

# 存档管理
_cache_dir = os.path.expanduser("~/.cache/selfeval-persistent-cache")
_cache_magic = b"EVAL\x01\x05\x00\x00"
_cache_comment = b"This file is automatically generated by selfeval version 1.5.0 for cache usage. Please DO NOT modify it unless you know what you're doing. You can remove it from your computer safely. "
def _cache_hash(files: list[str], args: list[str], info: str):
    try:
        sha512 = hashlib.sha3_512()
        for x in sorted(map(lambda x: int(x.hexdigest(), 16), chain((hash_file(file, hashlib.sha3_512) for file in files), (hashlib.sha3_512(arg.encode()) for arg in args), (hashlib.sha3_512(info.encode()), )))):
            sha512.update(x.to_bytes(512))
        sha512 = sha512.hexdigest()
    except TypeError as err:
        err.add_note("无法创建哈希。")
        error(err)
        return
    return sha512
def cache_init():
    if CACHE_DISABLED:
        return
    if not os.path.isdir(_cache_dir):
        if os.path.exists(_cache_dir):
            ensure_removed(_cache_dir)
        try:
            os.mkdir(_cache_dir, 0o700)
        except FileExistsError:
            if os.path.isdir(_cache_dir):
                warning("无法创建缓存，路径被占用。")
            else:
                error("无法创建缓存，路径被占用且不是目录。", True)
def cache_clear():
    if os.path.exists(_cache_dir):
        ensure_removed(_cache_dir)
def cache_add(path: str, files: list[str], args: list[str], info: str, /, comment: str = _cache_comment):
    if CACHE_DISABLED:
        return
    cache_init()
    if not os.path.isdir(_cache_dir):
        return
    if (sha512 := _cache_hash(files, args, info)) is None:
        return
    try:
        with open(path, "rb") as file:
            content = file.read()
    except OSError as err:
        err.add_note(f"无法读取要存档的文件 {repr(path)}")
        error(err)
        return
    try:
        with open(os.path.join(_cache_dir, sha512), "wb") as file:
            file.write(_cache_magic)
            file.write((os.stat(path).st_mode & 0o777).to_bytes(2))
            file.write(len(comment).to_bytes(2))
            file.write(comment)
            file.write(len(content).to_bytes(8))
            file.write(content)
    except OSError as err:
        err.add_note("无法创建存档。")
        error(err)
        return
def cache_get(files: list[str], args: list[str], info: str, /, dst: str = None):
    cache_init()
    if CACHE_DISABLED or not os.path.isdir(_cache_dir):
        return
    if (sha512 := _cache_hash(files, args, info)) is None:
        return
    if not os.path.isfile(path := os.path.join(_cache_dir, sha512)):
        return
    try:
        with open(path, "rb") as file:
            if (head := file.read(8)) != _cache_magic:
                warning(f"读取的存档头无法识别 {head} != {_cache_magic}，将忽略存档。")
                return
            mode = int.from_bytes(file.read(2))
            if (mode & 0o777) != mode:
                warning(f"读取的存档权限位 {mode} 无法识别，将忽略存档。")
                return
            comment = file.read(x := int.from_bytes(file.read(2)))
            content = file.read(x := int.from_bytes(file.read(8)))
            if len(content) != x:
                warning(f"期望读取 {x} 字节的存档，实际读取 {len(content)} 字节，将忽略存档。")
                return
    except (OSError, ValueError) as err:
        err.add_note("无法读取存档。")
        error(err)
        return
    fd, path = tempfile.mkstemp(prefix="selfeval-archive-extract-cache-", dir=dst)
    try:
        os.fchmod(fd, mode)
    except PermissionError as err:
        err.add_note("无法设置权限位，将忽略存档。")
        ensure_removed(path)
        return
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(content)
    except OSError as err:
        err.add_note("无法写入提取出的存档，将忽略存档。")
        ensure_removed(path)
        return
    return path

# 数据管理
def backup(src: str, dst: str, compression=0, compresslevel=None):
    try:
        with zipfile.ZipFile(dst, "w", compression=compression, compresslevel=compresslevel) as zipf:
            for dirpath, dirnames, filenames in os.walk(src):
                for name in filenames + dirnames:
                    zipf.write(path := os.path.join(dirpath, name), os.path.relpath(path, src))
    except (OSError, zipfile.BadZipFile) as err:
        error(err)
        return err
def _restore(src: str, dst: str, encoding=None):
    with zipfile.ZipFile(src, "r", metadata_encoding=encoding) as zipf:
        zipf.extractall(dst)
def restore(src: str, dst: str, encoding=None, *, strong=True):
    """
    使用 strong=True 时有强异常安全保证，即任何情况下数据都不会丢失。这通过提前将目录备份到临时文件夹实现。

    如果创建备份时出错，返回 -1，此时 dst 的数据没有变化；
    如果清除旧文件时出错，返回一个字符串表示备份到的目录，此时该目录的数据仍然有效；
    如果还原时出错，回滚文件操作并返回该错误；
    如果回滚文件操作时出错，返回一个字符串表示备份到的目录，此时该目录的数据仍然有效；
    如果回滚成功，备份会被自动清除，如果清除备份过程中出错，这意味着你的系统多了一点垃圾文件。
    """
    if not strong:
        try:
            _restore(src, dst, encoding)
        except Exception as err:
            error(err)
            return err
        return
    temp_base = temp_dir = None
    if os.path.exists(dst):
        try:
            temp_base = tempfile.mkdtemp(prefix="selfeval-restore-bak-")
            temp_dir = os.path.join(temp_base, "data")
            shutil.copytree(dst, temp_dir)
        except Exception as err:
            error(err)
            if temp_base and os.path.isdir(temp_base):
                try:
                    ensure_removed(temp_base)
                except Exception as e:
                    error(e)
            return -1
    try:
        ensure_removed(dst)
    except Exception as err:
        error(err)
        return temp_base
    try:
        _restore(src, dst, encoding)
    except Exception as err:
        error(err)
        try:
            if os.path.exists(dst):
                ensure_removed(dst)
            if os.path.exists(temp_dir):
                shutil.copytree(temp_dir, dst)
        except Exception as e:
            error(e)
            return temp_base
        else:
            try:
                ensure_removed(temp_base)
            except Exception as e:
                error(e)
            return err
    else:
        try:
            ensure_removed(temp_base)
        except Exception as e:
            error(e)
def export_uoj(): ... # TODO
def export_lemon(): ... # TODO
def export_luogu(): ... # TODO
