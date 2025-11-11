import os
import sys
import subprocess

# YES = (sys.argv[1].lower() == "y") if len(sys.argv) > 1 else False
YES = False
def press_any():
    if not YES:
        input("按回车继续")

failed = []
tests = [
    # ("hello-world", 0),
    # ("err", 0),
    # ("check-with-points", 0),
    # ("makefile", 0),
    # ("grader", 0),
    # ("subtask", 0),
    ("interactive", 0),
]
try:
    for test, ex in tests:
        cwd = os.path.join(os.getcwd(), "demo", test)
        if os.path.isfile(p := os.path.join(cwd, "README")):
            with open(p) as file:
                print(file.read())
        for file in os.listdir(cwd):
            if file.endswith(".cpp"):
                print(f"测试 {file}")
                p = os.path.join(cwd, file)
                resp = subprocess.run(["python3.13", os.path.abspath("selfeval.py"), p, *sys.argv[1:]], stdin=subprocess.DEVNULL, cwd=cwd)
                if resp.returncode:
                    failed.append(p)
                    print("\033[31;1m失败\033[0m，退出状态为", resp.returncode)
                    press_any()
                else:
                    print("\033[32;1m成功\033[0m")
                    if ex:
                        press_any()
except (KeyboardInterrupt, EOFError):
    print("手动停止了测试。")
print()
if not tests:
    print("没有测试。")
elif failed:
    print("失败的测试：\n" + "\n".join(failed))
else:
    print("测试全部成功。")
