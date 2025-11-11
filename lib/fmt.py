import decimal
import os
import shutil

from .color import *
from .core import error
from .ds import Test
from .utils import ftime, fmemory, fmt_score, fmt_verdict, fmt_Verdict, fmt_table

class LiveStream():
    def __init__(self, tests: list[Test] = None):
        self.tests: list[Test] = [] if tests is None else tests
        self.pre: list[list[tuple[str, int]]] = []
        self.width = 0
        cwd = os.getcwd()
        idw = len(str(len(self.tests)))
        for i in range(len(self.tests)):
            self.width = max(self.width, len(f"Subtask {i}"))
            self.pre.append([])
            for infile, _ in self.tests[i].tests:
                if not self.pre[-1]:
                    text = f"#{i+1:<{idw}} "
                else:
                    text = " " * (idw+2)
                text += Magenta(os.path.relpath(infile, cwd))
                self.width = max(self.width, text.cell_len)
                self.pre[-1].append((text, text.cell_len))
        self.x = 0
        self.y = 0
    def end(self):
        return self.x == len(self.tests)
    def println(self):
        print(self.pre[self.x][self.y][0].toansi(), (self.width - self.pre[self.x][self.y][1]) * " ", sep="", end=" | ")
        ret = self.tests[self.x].result[self.y]
        if ret.verdict == "ig":
            print(" " * 25, end=" ")
        else:
            from .sandbox import TLE, MLE
            print(((">" if ret.stat & TLE else "") + ftime(ret.tm)).rjust(12), end=" ")
            print(((">" if ret.stat & MLE else "") + fmemory(ret.mem)).rjust(12), end=" ")
        if ret.verdict == "pt":
            print(fmt_score(ret.score).toansi(), end=" ")
        print(fmt_verdict(ret.verdict).toansi(), end="")
        if ret.msg:
            print("", ret.msg, end="")
        print()
        self.y += 1
        while self.x < len(self.tests) and self.y == len(self.tests[self.x].tests):
            self.x += 1
            self.y = 0
    def print_test(self):
        o = self.x
        while self.x == o:
            self.println()
    def print_conclusion(self, typ = 1):
        statistic: dict[str, list[tuple[int, int]]] = {}
        flag = False
        score = decimal.Decimal()
        for i in range(len(self.tests)):
            x = self.tests[i]
            sc = decimal.Decimal(1)
            for j in range(len(x.result)):
                t = x.result[j]
                if t.verdict == "pt":
                    flag = True
                    sc = min(sc, t.score)
                    key = f"pt-{t.score}"
                    if key not in statistic:
                        statistic[key] = []
                    statistic[key].append((i, j))
                    if "pt" not in statistic:
                        statistic["pt"] = []
                    statistic["pt"].append((i, j))
                else:
                    if t.verdict != "ac":
                        flag = True
                        sc = 0
                    if t.verdict not in statistic:
                        statistic[t.verdict] = []
                    statistic[t.verdict].append((i, j))
            score += sc
        score /= len(self.tests)
        def _print_conclusion():
            print(CYAN("CONCLUSION").toansi())
            for key in statistic:
                if statistic[key]:
                    if key.find("-") == -1:
                        print(fmt_Verdict(key).toansi(), len(statistic[key]), end=" ")
            if not self.tests:
                print("无数据。")
                return
            print()
            print(f"在 {len(self.tests)} 个测试点中得到 " + fmt_score(score).toansi() + " 分")
        def _print_detail():
            print(CYAN("DETAIL").toansi())
            cwd = os.getcwd()
            for key in statistic:
                if key != "ac" and key != "ig" and key != "pt" and statistic[key]:
                    if key.find("-") == -1:
                        print(fmt_verdict(key).toansi())
                    elif key.startswith("pt-"):
                        print(fmt_verdict("pt").toansi(), fmt_score(decimal.Decimal(key[3:])).toansi())
                    a = [repr(os.path.relpath(self.tests[i].tests[j][0], cwd)) + ", " + repr(os.path.relpath(self.tests[i].tests[j][1], cwd)) for i, j in statistic[key]]
                    print(fmt_table(a, shutil.get_terminal_size().columns - 8).toansi())
        match typ:
            case 1:
                _print_conclusion()
                if flag:
                    print()
                    _print_detail()
            case 2:
                if flag:
                    _print_detail()
                    print()
                _print_conclusion()
            case 3:
                _print_conclusion()
            case _:
                error(f"不支持的总结类型 {typ}")
    def tohtml(self):
        raise NotImplementedError
    def topdf(self):
        raise NotImplementedError
    def toexcel(self):
        raise NotImplementedError
