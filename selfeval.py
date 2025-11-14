import atexit
import copy
import os
import resource
import shutil
import sys
import tempfile

# import rich.traceback
# rich.traceback.install(show_locals=True)

from lib.collect import process_file, collect_tests, collect_problem, collected_problem
from lib.color import *
from lib.core import VERSION, DEBUG, startup_recall, error, fatal, _remind, tick, tock
from lib.ds import TestConf, JudgeConf, read_judge_conf, Verdict, Test
from lib.fmt import LiveStream
from lib.jury import compile_program, jury_test
from lib.sandbox import SandboxFatalError
from lib.utils import fmemory, path_cmp, cache_clear

print(BOLD("selfeval").toansi(), VERSION)

# cache_path = os.path.abspath(".eval")
cache_path = tempfile.mkdtemp(prefix="selfeval-main-cache-")
# testlib_path = os.path.abspath("testlib.h")
testlib_path = "/home/noilinux/selfeval/testlib.h"

cmd_testconf = TestConf()

def main(source: str, data: list[str]):
    tests: list[Test] = []
    testconf = TestConf()
    with collect_problem(): # 一般题目只有一个数据文件夹，但是为了实现当前目录下不递归地收集数据，实现成允许收集多个文件夹的方式
        for d, flag in data:
            if not os.path.isdir(d):
                continue
            if flag:
                ts, cnf = collect_tests(d)
                tests += ts
                if cnf is not None:
                    testconf.update(cnf)
            else:
                for file in os.listdir(d):
                    process_file(os.path.join(d, file), testcase=False)
    testconf.update(cmd_testconf)
    tests.sort(key=lambda x: path_cmp(x.tests[0][0]))
    if not tests:
        print("无数据。")
        return
    problem = collected_problem()
    # TODO 如果 manifest.json 在校验器/交互库之后被修改，需要重新编译（见 ds 模块的 ResourceDependency）
    # TODO 当获取到的配置不合常理（例如时间限制 1ms）时，需要弹出提示
    for d, flag in data:
        if os.path.isfile(p := os.path.join(d, "manifest.json")):
            if (cnf := read_judge_conf(p)) is not None:
                problem.update(cnf)
    if problem.name is not None and problem.interactor is not None:
        error("使用文件读写时不能使用交互库。")
        return
    prog = compile_program(cache_path, source, None, "c++14:O2", problem.headers, problem.graders, "program")
    if prog is None:
        error("编译失败。")
        return
    if isinstance(prog, Verdict):
        error(f"编译失败，编译器退出状态为 {repr(prog)}")
        return
    # TODO 支持自定义编译选项
    # TODO 缓存编译结果
    # TODO 收集数据文件夹中的 testlib
    checker = problem.checker
    if checker is not None:
        problem.checker = compile_program(cache_path, checker, problem.checker_backup, problem.checker_conf.lang, [testlib_path], [], "checker")
        if problem.get_real("checker") is None:
            error(f"校验器 {checker} 编译失败。")
            return
        if isinstance(problem.get_real("checker"), Verdict):
            error(f"校验器 {checker} 编译失败，编译器退出状态为 {repr(problem.get_real("checker"))}")
            return
    if (interactor := problem.interactor) is not None:
        problem.interactor = compile_program(cache_path, interactor, problem.interactor_backup, problem.interactor_conf.lang, [testlib_path], [], "interactor")
        if problem.get_real("interactor") is None:
            error(f"交互库 {interactor} 编译失败。")
            return
        if isinstance(problem.get_real("interactor"), Verdict):
            error(f"交互库 {interactor} 编译失败，编译器退出状态为 {repr(problem.get_real("interactor"))}")
            return
    startup_recall()
    live = LiveStream(tests)
    for test in tests:
        jury_test(cache_path, prog, copy.deepcopy(testconf), problem, test, live)
    print()
    live.print_conclusion()

def parse_argv(argv: list[str]):
    i = -1
    raw = False
    lst = []
    while True:
        i += 1
        if i == len(argv):
            break
        arg = argv[i]
        print(repr(arg))
        if raw:
            lst.append(arg)
            continue
        if not arg.startswith("-"):
            lst.append(arg)
            continue
        if arg == "-":
            raw = True
        elif arg in ("-h", "--help"):
            pass
        elif arg in ("-v", "--version"):
            pass
        elif arg == "--clean":
            cache_clear()
        elif arg == "--ignore-recall":
            atexit.unregister(_remind)
        elif arg.startswith("--") and arg.find("=") != -1:
            key, val = arg[2:].split("=", 1)
            if cmd_testconf.isvalid(key):
                if val.isdigit():
                    val = int(val)
                ori = cmd_testconf.get_real(key)
                cmd_testconf._throw_on_invalid = True
                try:
                    setattr(cmd_testconf, key, val)
                except ValueError as err:
                    setattr(cmd_testconf, key, ori)
                    err.add_note(f"选项 --{key}={val} 无效。")
                    error(err, True)
                finally:
                    cmd_testconf._throw_on_invalid = False
            else:
                error(f"未知选项 {repr(arg)}", True)
        else:
            error(f"未知选项 {repr(arg)}", True)
    return lst
def starter():
    lst = parse_argv(sys.argv[1:])
    if os.path.isdir(cache_path):
        shutil.rmtree(cache_path)
    os.mkdir(cache_path)
    if not DEBUG:
        atexit.register(lambda: shutil.rmtree(cache_path))
    prog = os.path.abspath("1.cpp" if len(lst) < 1 else lst[0])
    # data = [os.path.join(os.path.dirname(prog), path) for path in (["data"] if len(lst) < 2 else lst[1:])]
    data = [
        (os.path.abspath("data"), True),
        (os.getcwd(), False),
    ]
    if len(lst) > 2:
        for x in range(2, len(lst)):
            error(f"冗余参数 {repr(lst[x])}")
    try:
        main(prog, data)
    except KeyboardInterrupt:
        print()
        print("评测被打断。")

if __name__ == "__main__":
    tick()
    try:
        starter()
    except SandboxFatalError as err:
        fatal(err)
    tock("用时")
    print("内存用量", fmemory(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024))
