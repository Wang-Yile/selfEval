VERSION = "1.5.0"
BUILD = "rev23"

import atexit
import fcntl
import os
import queue
import sys
import threading
import time

from .color import *

CACHE_DISABLED = False

DEBUG = False
DEBUG_DS = False
DEBUG_SANDBOX = False

# TODO 优化异常打印，支持 DEBUG_EXC 打印调用栈
# 打印异常
REMIND_MAX = 100
_rmd: list[Text] = []
def _fexc(err: Exception, *, _prompt = "") -> Text:
    ret = MAGENTA(err.__class__.__qualname__) + " " + _prompt + " " + str(err)
    if hasattr(err, "__notes__"):
        for x in err.__notes__:
            ret += "\n" + x
    return ret
def _remember(s: Text):
    if len(_rmd) < REMIND_MAX:
        _rmd.append(s)
    elif len(_rmd) == REMIND_MAX:
        _rmd.append(YELLOW("Warning") + " 异常记录达到上限，因此有异常被忽略。")
def _get_prompt(dep = 0):
    return Gray(f"{os.path.relpath(sys._getframe(dep+1).f_code.co_filename)}:{sys._getframe(dep+1).f_lineno}")
def fatal(msg: Exception | str):
    _rmd.clear()
    print()
    print((RED("FATAL") + " " + (_fexc(msg) if isinstance(msg, Exception) else msg)).toansi())
    print()
def error(msg: Exception | str, remind = False):
    s = (_fexc(msg, _prompt = _get_prompt(1)) if isinstance(msg, Exception) else RED("Error") + " " + _get_prompt(1) + " " + msg)
    if remind or DEBUG:
        _remember(s)
    print(s.toansi())
def warning(msg: str, remind = False):
    s = YELLOW("Warning") + " " + _get_prompt(1) + " " + msg
    if remind or DEBUG:
        _remember(s)
    print(s.toansi())
def _remind():
    if _rmd:
        print()
        print(CYAN("RECALL").toansi())
        for x in _rmd:
            print(x.toansi())
atexit.register(_remind)

# CPU 亲和性调度
# 不要在运行过程中修改 CPU 核心数！！！
CPU_LOGICAL = False
CPU_PIPE = "/tmp/selfeval-cpu-manage-pipe"
def _get_cpus() -> list[int]:
    if CPU_LOGICAL:
        return [x for x in range(os.cpu_count())]
    mp = {}
    for x in range(os.cpu_count()):
        with open(f"/sys/devices/system/cpu/cpu{x}/topology/core_id") as file:
            mp[int(file.read())] = x
    return list(mp.values())
cpus = _get_cpus()
def _add_lock_ex(fd: int):
    retry = 3
    while retry >= 0:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            retry -= 1
            time.sleep(0.005)
        else:
            return True
    return False
def acquire_cpu():
    try:
        with open(CPU_PIPE, "xb") as file:
            for x in cpus:
                file.write(x.to_bytes(4))
    except FileExistsError:
        pass
    with open(CPU_PIPE, "r+b") as file:
        if not _add_lock_ex(file.fileno()):
            return -1
        try:
            pos = file.seek(-4, os.SEEK_END)
        except OSError:
            return -1
        else:
            ret = int.from_bytes(file.read(4))
            file.truncate(pos)
            return ret
        finally:
            fcntl.flock(file.fileno(), fcntl.LOCK_UN)
def release_cpu(x: int, /):
    if x == -1:
        return
    with open(CPU_PIPE, "ab") as file:
        if not _add_lock_ex(file.fileno()):
            error(f"无法获取 CPU 管道的独占锁，释放的 CPU {x} 没有正确写入管道。", True)
            return
        file.write(x.to_bytes(4))
        fcntl.flock(file.fileno(), fcntl.LOCK_UN)

# 计时
_ticket = []
def tick():
    _ticket.append(time.monotonic())
def tock(prompt: str = None):
    t = time.monotonic()-_ticket[-1]
    if prompt is None:
        print(t, "s")
    else:
        print(prompt, t, "s")
    _ticket.pop()

# 处理回调函数
_callback_pool = queue.SimpleQueue()
class Callback():
    def __init__(self, func, *args, **kwargs):
        self._func = func
        self._args = args
        self._kwargs = kwargs
    def call(self, *args, **kwargs):
        self._func(*self._args, *args, **self._kwargs, **kwargs)
class AsyncCallback(Callback):
    def call(self, *args, **kwargs):
        if len(kwargs) < len(self._kwargs):
            self._kwargs.update(kwargs)
            kwargs = self._kwargs
        else:
            kwargs.update(self._kwargs)
        _callback_pool.append((self._func, self._args + args, kwargs))
def _callback_main():
    while True:
        func, args, kwargs = _callback_pool.get()
        try:
            func(*args, **kwargs)
        except (StopIteration, StopAsyncIteration) as err:
            pass
        except Exception as err:
            err.add_note("回调函数出现了错误。")
            error(err)
_callback_th = threading.Thread(target=_callback_main, daemon=True)
_callback_th.start()
