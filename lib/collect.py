import os
from contextlib import contextmanager

from .core import warning
from .ds import read_test_conf, JudgeConf, Test
from .utils import path_cmp

_checkers = []
_interactors = []
_graders = []
_headers = []
def find_testcase(path: str, strict = False):
    dirpath = os.path.dirname(path)
    infile = os.path.basename(path)
    if strict:
        component = infile.rsplit(".", 1)
        i = 1
    else:
        component = infile.split(".")
        i = 0
    ansfile = None
    ok = False
    cwd = os.getcwd()
    while i < len(component):
        if component[i] == "in":
            ok = True
            for ex in ("ans", "out"):
                component[i] = ex
                if os.path.isfile(p := os.path.join(dirpath, ".".join(component))):
                    if ansfile is None:
                        ansfile = p
                    else:
                        warning(f"{repr(os.path.relpath(path, cwd))} 匹配多个输出文件，忽略 {repr(os.path.relpath(p, cwd))}")
        i += 1
    if ok:
        if ansfile is None:
            warning(f"{repr(os.path.relpath(path, cwd))} 没有匹配输出文件，被忽略。")
        else:
            return (path, ansfile)
def process_file(path: str, strict = False, testcase = True):
    name = os.path.basename(path)
    base, ext = os.path.splitext(name)
    if base in ("checker", "chk"):
        _checkers.append(path)
    elif base in ("interactor", ):
        _interactors.append(path)
    elif base in ("grader", ):
        _graders.append(path)
    elif ext in (".h", ".hpp"):
        _headers.append(path)
    elif testcase:
        return find_testcase(path, strict)
def collect_test(src: str, strict = False):
    ret = [tc for dirpath, dirnames, filenames in os.walk(src) for file in filenames if (tc := process_file(os.path.join(dirpath, file), strict))]
    if not ret:
        return None
    ret.sort(key=lambda x: path_cmp(x[0]))
    t = Test(tests=ret)
    if os.path.isfile(path := os.path.join(src, "config.json")):
        t.conf = read_test_conf(path)
    return t
def collect_tests(src: str, strict = False):
    ret: list[Test] = []
    for name in os.listdir(src):
        path = os.path.join(src, name)
        if os.path.isdir(path):
            if tc := collect_test(path, strict):
                ret.append(tc)
        elif tc := process_file(path):
            ret.append(Test(tests=[tc]))
    return ret, read_test_conf(path) if os.path.isfile(path := os.path.join(src, "config.json")) else None
__collected_problem = None
@contextmanager
def collect_problem():
    _checkers.clear()
    _interactors.clear()
    _graders.clear()
    _headers.clear()
    yield
    global __collected_problem
    __collected_problem = JudgeConf()
    cwd = os.getcwd()
    if _checkers:
        checker = __collected_problem.checker
        for x in _checkers:
            if checker is None:
                checker = x
                continue
            # TODO 如果使用 Makefile 且 Makefile 在可执行文件之后发生改变，需要抛出警告
            if os.stat(x).st_mtime_ns > os.stat(checker).st_mtime_ns:
                warning(f"找到多个校验器，使用更新的 {repr(os.path.relpath(x, cwd))} 覆盖 {repr(os.path.relpath(checker, cwd))}", True)
                checker = x
            else:
                warning(f"找到多个校验器，忽略 {repr(os.path.relpath(x, cwd))}", True)
        __collected_problem.checker = checker
    if _interactors:
        interactor = __collected_problem.interactor
        for x in _interactors:
            if interactor is None:
                interactor = x
                continue
            if os.stat(x).st_mtime_ns > os.stat(interactor).st_mtime_ns:
                warning(f"找到多个交互库，使用更新的 {repr(os.path.relpath(x, cwd))} 覆盖 {repr(os.path.relpath(interactor, cwd))}", True)
                interactor = x
            else:
                warning(f"找到多个交互库，忽略 {repr(os.path.relpath(x, cwd))}", True)
        __collected_problem.interactor = interactor
    if _graders:
        __collected_problem.graders += _graders
    if _headers:
        __collected_problem.headers += _headers
def collected_problem():
    return __collected_problem
