import os
from contextlib import contextmanager
from itertools import chain, islice

from .core import warning
from .ds import read_test_conf, JudgeConf, Test
from .utils import path_cmp

_checkers = []
_interactors = []
_graders = []
_headers = []
ANSFILE_EXTS = ("ans", "out")
def _find_ansfile_strict(path: str):
    if path.endswith(".in"):
        ret = []
        dirpath = os.path.dirname(path)
        for ex in ANSFILE_EXTS:
            if os.path.isfile(p := os.path.join(dirpath, path[:-3] + ex)):
                ret.append(p)
        return ret
    return path.endswith(".ans")
def _find_ansfile_free(path: str):
    dirpath = os.path.dirname(path)
    ret = False
    cwd = os.getcwd()
    for i, val in enumerate(comp := os.path.basename(path).split(".")):
        if val == "in":
            if not isinstance(ret, list):
                ret = []
            for ex in ANSFILE_EXTS:
                if os.path.isfile(p := os.path.join(dirpath, ".".join(chain(islice(comp, i), (ex, ), islice(comp, i+1, None))))):
                    ret.append(p)
        elif val in ANSFILE_EXTS:
            if isinstance(ret, list):
                warning(f"忽略 {repr(os.path.relpath(path, cwd))}，因为无法判断它是输入文件还是输出文件。", True)
                return None
            ret = True
    return ret
_ansfile = set()
_matched_ansfile = set()
def find_testcase(path: str, strict = False):
    component = _find_ansfile_strict(path) if strict else _find_ansfile_free(path)
    if component is None or component is False:
        return
    elif component is True:
        if path in _matched_ansfile:
            _matched_ansfile.remove(path)
        else:
            _ansfile.add(path)
        return
    ansfile = None
    cwd = os.getcwd()
    for p in component:
        if p in _ansfile:
            _ansfile.remove(p)
        else:
            _matched_ansfile.add(p)
        if ansfile is None:
            ansfile = p
        else:
            warning(f"{repr(os.path.relpath(path, cwd))} 匹配多个输出文件，其中忽略 {repr(os.path.relpath(p, cwd))}", True)
    if ansfile is None:
        warning(f"{repr(os.path.relpath(path, cwd))}，没有匹配输出文件，被忽略。", True)
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
    _ansfile.clear()
    _matched_ansfile.clear()
    yield
    global __collected_problem
    __collected_problem = JudgeConf()
    cwd = os.getcwd()
    for p in _ansfile:
        warning(f"{repr(os.path.relpath(p, cwd))} 没有匹配输入文件，被忽略。", True)
    for p in _matched_ansfile:
        warning(f"{repr(os.path.relpath(p, cwd))} 没有匹配输入文件，被忽略。", True)
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
    _checkers.clear()
    _interactors.clear()
    _graders.clear()
    _headers.clear()
    _ansfile.clear()
    _matched_ansfile.clear()
def collected_problem() -> JudgeConf:
    return __collected_problem
