import ctypes
import os
import shutil
import signal
import subprocess
import sys
import threading

from . import userconf
from .core import DEBUG_SANDBOX, acquire_cpu, release_cpu, error, warning
from .ds import Program, Limit, Verdict
from .utils import fmemory, hash32, random_hash, stdopen

SANDBOX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sandbox")
SANDBOX_TINY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sandbox-tiny")

# sandbox.h 中定义的常量
EXIT = 0x10000
SIG = 0x20000
TLE = 0x40000
MLE = 0x80000
OLE = 0x100000
FBD = 0x200000

TLE_OVERDUE = 1

RLIMIT_INFINITY = (1 << (8 * ctypes.sizeof(ctypes.c_long))) - 1

class SandboxFatalError(Exception):
    pass

TRUNK = 4096
_cnt = [-1, -1]
def relay(src: int, dst: int, side: int):
    cnt = 0
    w = shutil.get_terminal_size()[0]
    ww = w // 2 // 25 * 8
    w = ww * 3 - 1
    try:
        while True:
            data = os.read(src, TRUNK)
            if not data:
                break
            cnt += len(data)
            try:
                s = data.decode()
            except UnicodeDecodeError:
                pass
            else:
                if side:
                    sys.stdout.write("\033[2;3m")
                sys.stdout.write(s)
                if side:
                    sys.stdout.write("\033[0m")
                sys.stdout.flush()
            try:
                os.write(dst, data)
            except BrokenPipeError:
                break
    except Exception as err:
        error(err)
    _cnt[side] = cnt

class Sandbox():
    def __init__(self, prog: str, args: list[str], limit: Limit = None, cwd: str = None, env: os._Environ = None, stdin = None, stdout = None, stderr = None, permissions: list[tuple[str, int]] = None, isolate = False, trust = False):
        if os.path.isabs(prog):
            self.prog = prog
        elif (s := shutil.which(prog)) is not None:
            self.prog = s
        else:
            raise SandboxFatalError(f"沙箱无法定位文件 {repr(prog)}")
        self.args = args
        self.limit = Limit() if limit is None else limit
        self.cwd = cwd
        self.env = env
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = None if DEBUG_SANDBOX else stderr
        self.permissions = [] if permissions is None else permissions
        self.isolate = isolate
        self.cpu = None
        self.trust = trust
        self._child_safe = True
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.cpu is not None:
            release_cpu(self.cpu)
        self.close()
    def close(self):
        ori = signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            if not self._child_safe:
                try:
                    self.proc.send_signal(signal.SIGCONT)
                except ProcessLookupError:
                    pass
                else:
                    try:
                        self.proc.wait(0.05)
                    except subprocess.TimeoutExpired:
                        try:
                            self.proc.send_signal(signal.SIGALRM)
                        except ProcessLookupError:
                            pass
                self._child_safe = True
        finally:
            signal.signal(signal.SIGINT, ori)
    def start(self):
        if self.trust:
            sandbox = SANDBOX_TINY
        else:
            sandbox = SANDBOX
        self.ret = os.path.join(self.cwd, random_hash(hash32))
        limit_cmdline = [str(min(x, RLIMIT_INFINITY)) for x in self.limit.cmdline()]
        if self.isolate:
            self.cpu = acquire_cpu()
            if self.cpu == -1:
                warning("无可用 CPU，绑定至 CPU 0。")
                cpuset_mask = "1" + "0" * (os.cpu_count() - 1)
            else:
                cpuset_mask = "0" * self.cpu + "1" + "0" * (os.cpu_count() - self.cpu - 1)
        else:
            cpuset_mask = "1" * os.cpu_count()
        permissions_cmdline = [str(len(self.permissions))]
        for file, pm in self.permissions:
            permissions_cmdline.append(file)
            permissions_cmdline.append(str(pm))
        self._child_safe = False
        try:
            self.proc = subprocess.Popen([sandbox, self.prog, self.ret, *limit_cmdline, cpuset_mask, *permissions_cmdline, *self.args], cwd=self.cwd, env=self.env, stdin=self.stdin, stdout=self.stdout, stderr=self.stderr, start_new_session=True)
        except OSError as err:
            raise SandboxFatalError from err
        while True:
            _, stat = os.waitpid(self.proc.pid, os.WUNTRACED)
            if os.WIFSTOPPED(stat) or os.WIFSIGNALED(stat) or os.WIFEXITED(stat):
                break # 不应该出现 EXITED，但是还是处理
    def cont(self):
        try:
            self.proc.send_signal(signal.SIGCONT)
        except ProcessLookupError:
            pass
        self._child_safe = True
    def wait(self):
        if not self._child_safe:
            self.cont()
        if self.proc.wait():
            self.ret = Verdict(verdict="fail")
            return
        try:
            file = open(self.ret)
        except OSError as err:
            error(err)
            self.ret = Verdict(verdict="fail")
            return
        t = int(file.readline()[:-1])
        mem = int(file.readline()[:-1])
        stat = int(file.readline()[:-1])
        msg = ""
        if stat & FBD:
            verdict = "fb"
            msg = f"syscall {stat ^ FBD}"
        elif (stat & TLE) or self.limit.tl(t):
            verdict = "tl"
        elif (stat & MLE) or self.limit.ml(mem):
            stat |= MLE
            verdict = "ml"
        elif stat & OLE:
            verdict = "ol"
        elif stat & SIG:
            verdict = "re"
            msg = f"signal {stat ^ SIG}"
        elif stat & EXIT and stat ^ EXIT:
            verdict = "re"
            msg = f"return {stat ^ EXIT}"
        else:
            verdict = "ok"
        i = 0
        while s := file.readline()[:-1]:
            i += 1
            if i >= 3:
                msg += "\n    "
            else:
                msg += "\n  "
            msg += s
        file.close()
        self.ret = Verdict(verdict=verdict, tm=t, mem=mem, stat=stat, msg=msg)

def run(prog: Program, limit: Limit, cwd: str, env: os._Environ = None, stdin = subprocess.DEVNULL, stdout = subprocess.DEVNULL, stderr = subprocess.DEVNULL, permissions: list[tuple[str, int]] = None, *, trust = False) -> Verdict:
    """
    需要在调用此函数前自行处理权限。
    """
    try:
        with Sandbox(prog.prog, prog.args, limit, cwd, env, stdopen(stdin), stdopen(stdout, "w"), stdopen(stderr, "w"), permissions, userconf.acquire_judge_isolate(), trust) as box:
            box.start()
            box.wait()
    except KeyboardInterrupt as err:
        try:
            box.proc.send_signal(signal.SIGALRM)
        except:
            warning("对沙箱发送 SIGALRM 失败。")
            err.add_note("对沙箱发送 SIGALRM 失败。")
        else:
            err.add_note("对沙箱发送了 SIGALRM。")
        raise
    return box.ret
def run_interactive(prog: Program, interactor: Program, limit: Limit, cwd: str, env: os._Environ = None, stdin = subprocess.DEVNULL, stdout = subprocess.DEVNULL, stderr = subprocess.DEVNULL, tlog = subprocess.DEVNULL, permissions_prog: list[tuple[str, int]] = None, permissions_interactor: list[tuple[str, int]] = None, *, trust_prog = False, trust_interactor = False) -> tuple[Verdict, Verdict]:
    """
    需要在调用此函数前自行处理权限。
    """
    if not isinstance(stdout, str):
        raise ValueError("run_interactive 的 stdout 参数必须是 str 类型。")
    isolate = userconf.acquire_judge_isolate()
    if userconf.acquire_interactor_fast_sandbox():
        trust_prog = trust_interactor = True
    try:
        if userconf.acquire_interactor_echo():
            global _cnt
            _cnt = [-1, -1]
            with (
                Sandbox(prog.prog, prog.args, limit, cwd, env, subprocess.PIPE, subprocess.PIPE, stdopen(stderr, "w"), permissions_prog, isolate, trust_prog) as box1,
                Sandbox(interactor.prog, interactor.args + [stdin, stdout], limit, cwd, env, subprocess.PIPE, subprocess.PIPE, stdopen(tlog, "w"), permissions_interactor, isolate, trust_interactor) as box2,
            ):
                box1.start()
                box2.start()
                t1 = threading.Thread(target=relay, args=(box1.proc.stdout.fileno(), box2.proc.stdin.fileno(), 0))
                t2 = threading.Thread(target=relay, args=(box2.proc.stdout.fileno(), box1.proc.stdin.fileno(), 1))
                t1.start()
                t2.start()
                box1.cont()
                box2.cont()
                box1.wait()
                box2.wait()
                t1.join()
                t2.join()
            print(f"选手程序发送 {"未知大小" if _cnt[0] == -1 else fmemory(_cnt[0])}，接收 {"未知大小" if _cnt[1] == -1 else fmemory(_cnt[1])}")
        else:
            with Sandbox(prog.prog, prog.args, limit, cwd, env, subprocess.PIPE, subprocess.PIPE, stdopen(stderr, "w"), permissions_prog, isolate, trust_prog) as box1:
                box1.start()
                with Sandbox(interactor.prog, interactor.args + [stdin, stdout], limit, cwd, env, box1.proc.stdout, box1.proc.stdin, stdopen(tlog, "w"), permissions_interactor, isolate, trust_interactor) as box2:
                    box2.start()
                    box1.cont()
                    box2.cont()
                    box1.wait()
                    box2.wait()
    except KeyboardInterrupt as err:
        try:
            box1.proc.send_signal(signal.SIGALRM)
        except:
            warning("对沙箱发送 SIGALRM 失败。")
            err.add_note("对沙箱发送 SIGALRM 失败。")
        else:
            err.add_note("对沙箱发送了 SIGALRM。")
        try:
            box2.proc.send_signal(signal.SIGALRM)
        except:
            warning("对沙箱发送 SIGALRM 失败。")
            err.add_note("对沙箱发送 SIGALRM 失败。")
        else:
            err.add_note("对沙箱发送了 SIGALRM。")
        raise
    return box1.ret, box2.ret
