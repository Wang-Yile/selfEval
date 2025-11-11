import copy
import decimal
import os
import shutil
import subprocess

from . import userconf
from .core import DEBUG, error
from .ds import Program, Limit, TestConf, JudgeConf, Verdict, Test
from .fmt import LiveStream
from .sandbox import run, run_interactive
from .utils import sec, get_unique_path, is_xok, copy_to, cache_add, cache_get

# TODO: 如果 headers 和 graders 中存在相同名字的文件/文件夹，应该报错
def _compile_cpp(cwd: str, source: str, output: str, graders: list[str], args: list[str]):
    return Program(output) if (ret := run(Program("g++", *args, source, *graders, "-o", output), Limit(time=sec(10)), cwd, stderr=None, trust=True)).verdict == "ok" else ret
def _compile_cpp_makefile(cwd: str, usage: str):
    return Program(os.path.join(cwd, usage)) if (ret := run(Program("make", usage), Limit(time=sec(10)), cwd, stdout=None, stderr=None, trust=True)).verdict == "ok" else ret
def compile_program(cwd: str, source: str, lang: str, headers: list[str], graders: list[str], /, usage = "program"):
    if is_xok(source):
        return Program(source)
    wd = get_unique_path(cwd)
    os.mkdir(wd)
    for file in headers:
        copy_to(file, wd)
    for file in graders:
        copy_to(file, wd)
    if (x := lang.find(":")) != -1:
        typ = lang[:x]
        flags = lang[x+1:].split(",")
    else:
        typ = lang
        flags = []
    if typ.startswith("c++"):
        if typ == "c++":
            std = "c++14"
        elif typ == "c++20":
            std = "c++2a"
        elif typ == "c++23":
            std = "c++2b"
        elif typ == "c++26":
            std = "c++2c"
        else:
            std = typ
        args = [f"-std={std}", "-Wall", "-Wextra", "-Wshadow", "-Wconversion"]
        makefile = False
        for flag in flags:
            flag = flag.strip()
            if flag.startswith("O"):
                args.append("-" + flag)
            elif flag == "Makefile":
                makefile = True
            else:
                error(f"未知的 C++ 语言标记 {repr(flag)}")
        if makefile:
            if not os.path.isfile(p := os.path.join(os.path.dirname(source), "Makefile")):
                error("打上了 Makefile 标签，但未找到 Makefile。")
                return
            shutil.copyfile(p, os.path.join(wd, "Makefile"))
            shutil.copyfile(source, os.path.join(wd, usage + ".cpp"))
            return _compile_cpp_makefile(wd, usage)
        else:
            p = os.path.join(wd, "a.cpp")
            try:
                if (tmp := cache_get([source, *graders, *headers], args, "")) is not None:
                    shutil.copy(tmp, p := get_unique_path(wd))
                    os.remove(tmp)
                    return Program(p)
            except Exception as err:
                err.add_note("尝试读取缓存时发生异常。")
                error(err)
            shutil.copyfile(source, p)
            ret = _compile_cpp(wd, p, get_unique_path(wd), graders, args)
            if isinstance(ret, Program):
                try:
                    cache_add(ret.prog, [source, *graders, *headers], args, "")
                except Exception as err:
                    err.add_note("尝试创建缓存时发生异常。")
                    error(err)
            return ret
    # elif typ == "customized": # TODO 自定义编译
    #     pass
    else:
        error(f"未知的编程语言 {lang}")

def read_checklog(resp: Verdict, path: str, /, name = "校验器"):
    try:
        with open(path) as file:
            msg = file.readline()[:-1]
    except OSError as err:
        error(err, True)
    from .sandbox import EXIT
    score = None
    normal = True
    if resp.verdict == "re" and (resp.stat & EXIT):
        verdict = "wa"
        if (resp.stat ^ EXIT) == 7: # testlib 部分分
            verdict = "pt"
            msg = msg.removeprefix("points ")
            if msg.find(" ") == -1:
                score = msg
            else:
                score, msg = msg.split(" ", 1)
            try:
                score = decimal.Decimal(score)
            except decimal.DecimalException as err:
                error(err)
                score = decimal.Decimal(0)
        elif msg.startswith("wrong answer "):
            verdict = "wa"
            msg = msg.removeprefix("wrong answer ")
        elif msg.startswith("wrong output format "):
            verdict = "wa"
            msg = msg.removeprefix("wrong output format ")
            normal = False
        elif msg.startswith("unexpected eof "):
            verdict = "wa"
            msg = msg.removeprefix("unexpected eof ")
            normal = False
        else:
            verdict = "wa"
            msg = msg
            normal = False
    elif resp.verdict == "ok":
        verdict = "ac"
        msg = msg.removeprefix("ok ")
    else:
        verdict = "fail"
        msg = name + "运行失败 " + repr(resp)
    return verdict, msg, score, normal
def jury(cwd: str, prog: Program, testconf: TestConf, judgeconf: JudgeConf, infile: str, ansfile: str):
    name = judgeconf.name
    retry = judgeconf.retry
    while True:
        wd = get_unique_path(cwd)
        os.mkdir(wd)
        for file in judgeconf.additional:
            copy_to(file, wd)
        permissions = []
        if name:
            stdin = stdout = subprocess.DEVNULL
            shutil.copyfile(infile, os.path.join(wd, name + ".in"))
            permissions.append((os.path.join(wd, name + ".in"), 0))
            permissions.append((os.path.join(wd, name + ".out"), 1))
        else:
            stdin = get_unique_path(wd)
            shutil.copyfile(infile, stdin)
            stdout = get_unique_path(wd)
            permissions.append((stdin, 0))
            permissions.append((stdout, 1))
        if (interactor := judgeconf.interactor):
            checklog = get_unique_path(wd)
            permissions.append((checklog, 1))
            ret, ret_interactor = run_interactive(prog, interactor, testconf.limit(), wd, None, stdin, stdout, subprocess.DEVNULL, checklog, None, permissions, judgeconf.isolate)
        else:
            ret = run(prog, testconf.limit(), wd, None, stdin, stdout, subprocess.DEVNULL, permissions, judgeconf.isolate)
        if name:
            stdin = os.path.join(wd, name + ".in")
            stdout = os.path.join(wd, name + ".out")
        from .sandbox import TLE
        if ret.verdict == "tl" and not (ret.stat & TLE) and retry > 0:
            if not DEBUG:
                shutil.rmtree(wd)
            retry -= 1
            continue
        break
    from .sandbox import SIG, MLE, OLE, FBD
    if interactor and (ret_interactor.stat & (SIG | MLE | OLE | FBD)):
        ret.verdict = "fail"
        ret.msg = "交互器运行失败 " + repr(ret_interactor)
    elif interactor and ret_interactor.verdict != "ok":
        ret.verdict, ret.msg, ret.score, _ = read_checklog(ret_interactor, checklog, "交互器")
        if not _ or ret.verdict != "ok":
            ret.verdict = "il"
    elif ret.verdict == "ok":
        checker: Program = copy.deepcopy(judgeconf.checker)
        lim = judgeconf.checker_limit()
        if checker is None:
            resp = run(Program("diff", "-Z", "-q", "--strip-trailing-cr", stdout, ansfile), lim, cwd, trust=True)
            from .sandbox import EXIT
            if resp.verdict == "re" and (resp.stat ^ EXIT) == 1:
                ret.verdict = "wa"
            elif resp.verdict == "ok":
                ret.verdict = "ac"
            else:
                ret.verdict = "fail"
                ret.msg = "diff 运行失败 " + repr(resp)
        else:
            checklog = get_unique_path(wd)
            checker.args += [infile, stdout, ansfile]
            resp = run(checker, lim, cwd, stderr=checklog, permissions=[(infile, 0), (stdout, 0), (ansfile, 0), (checklog, 1)])
            ret.verdict, ret.msg, ret.score, _ = read_checklog(resp, checklog)
    if not DEBUG:
        shutil.rmtree(wd)
    return ret
def jury_test(cwd: str, prog: Program, testconf: TestConf, conf: JudgeConf, test: Test, live: LiveStream = None):
    if test.conf:
        testconf.update(test.conf)
    jump = False
    for tc in test.tests:
        if jump:
            test.result.append(Verdict(verdict="ig"))
            if live:
                live.println()
            continue
        ret = jury(cwd, prog, testconf, conf, tc[0], tc[1])
        test.result.append(ret)
        if ret.verdict != "ac" and (ret.verdict != "pt" or ret.score <= 0):
            if not testconf.keep:
                jump = True
        if live:
            live.println()
