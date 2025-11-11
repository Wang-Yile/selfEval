import json
import os
import shutil
import subprocess
import sys
from functools import lru_cache, partial

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QFrame, QLineEdit, QTextEdit, QLabel, QPushButton, QCheckBox, QListWidget,
    QMessageBox, QDialog, QDialogButtonBox, QFileDialog
)
from PySide6.QtGui import QFont, QFontDatabase, QTextCharFormat, QMouseEvent
from PySide6.QtCore import Qt

from lib.collect import collect_tests, collect_problem, collected_problem
from lib.core import VERSION, _fexc, error, tick, tock
from lib.ds import ModelNULL, TestConf, JudgeConf, Test
from lib.utils import stdopen, path_cmp, backup as _backup, restore as _restore
from libg.color import *
from libg.switcher import ExSwitcher, SwitcherItem

def xdgopen(path: str):
    try:
        subprocess.Popen(["nautilus", path], start_new_session=True)
    except subprocess.SubprocessError as err:
        error(err)
    except FileNotFoundError as err:
        error(err)
        try:
            subprocess.Popen(["xdg-open", path if os.path.isdir(path) else os.path.dirname(path)], start_new_session=True)
        except subprocess.SubprocessError as err:
            error(err)

@lru_cache
def _read_truncated(path: str, *, trunc = 1000):
    with stdopen(path) as file:
        x = file.read(trunc)
        if file.read(1):
            x += "\n<truncated>"
        return x
def read_truncated(path: str, *, trunc = 1000):
    try:
        return _read_truncated(path, trunc=trunc)
    except Exception as err:
        return f"无法读取 {repr(path)}\n" + str(_fexc(err))

# FONT = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
# FONT.setPointSize(10)
FONT = QFont(["Consolas", "monospace"], 10)
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

_extra = "冗余"
_invalid = "无法解析"
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QTextCharFormat, QColor

class FMTTheme():
    def update(self):
        self.fmt_normal = QTextCharFormat()
        self.fmt_key = QTextCharFormat()
        self.fmt_key.setForeground(color("green"))
        self.fmt_value = QTextCharFormat()
        self.fmt_value.setForeground(color("orange"))
        self.fmt_delete = QTextCharFormat()
        self.fmt_delete.setFontStrikeOut(True)
        self.fmt_delete.setForeground(color("gray"))
        self.fmt_comment = QTextCharFormat()
        self.fmt_comment.setFontUnderline(True)
        self.fmt_comment.setForeground(color("gray"))
        self.fmt_extra = QTextCharFormat()
        self.fmt_extra.setForeground(color("black"))
        self.fmt_extra.setBackground(color("yellow"))
        self.fmt_invalid = QTextCharFormat()
        self.fmt_invalid.setForeground(color("white"))
        self.fmt_invalid.setBackground(color("red"))
_fmt = FMTTheme()
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.data_dir = os.path.abspath("data")
        self.tests: list[Test] = []
        self.testconf: TestConf = None
        self.judgeconf: JudgeConf = None
        self.init_ui()
    def init_ui(self):
        widget = QWidget()
        self.setCentralWidget(widget)
        self.setWindowTitle("selfeval 数据配置向导")
        self.setMinimumSize(400, 200)
        self.resize(600, 400)
        # Frame
        container_problem = QFrame()
        container_problem.setFixedHeight(40)
        container_subtask = QFrame()
        container_tests = QFrame()
        container_tests.setMaximumHeight(200)
        container_op = QFrame()
        container_op.setFixedHeight(20)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(3)
        layout.addWidget(container_problem)
        layout.addWidget(container_subtask)
        layout.addWidget(container_tests)
        layout.addWidget(container_op)
        # Subtask
        self.lst_subtask = QListWidget()
        self.lst_subtask.setSelectionMode(QListWidget.ExtendedSelection)
        self.lst_subtask.setMaximumWidth(300)
        self.lst_test = QListWidget()
        self.lst_test.setSelectionMode(QListWidget.ExtendedSelection)
        self.lst_test.setMaximumWidth(300)
        self.subtask_detail = QTextEdit()
        self.subtask_detail.setReadOnly(True)
        self.subtask_detail.setFont(FONT)
        subtask_layout = QHBoxLayout(container_subtask)
        subtask_layout.setContentsMargins(0, 0, 0, 0)
        subtask_layout.setSpacing(3)
        subtask_layout.addWidget(self.lst_subtask, 1)
        subtask_layout.addWidget(self.lst_test, 1)
        subtask_layout.addWidget(self.subtask_detail, 2)
        # Test
        self.test_detail1 = QTextEdit()
        self.test_detail1.setReadOnly(True)
        self.test_detail1.setFont(FONT)
        self.test_detail2 = QTextEdit()
        self.test_detail2.setReadOnly(True)
        self.test_detail2.setFont(FONT)
        test_layout = QHBoxLayout(container_tests)
        test_layout.setContentsMargins(0, 0, 0, 0)
        test_layout.setSpacing(3)
        test_layout.addWidget(self.test_detail1)
        test_layout.addWidget(self.test_detail2)
        # Operation
        op_layout = QHBoxLayout(container_op)
        op_layout.setContentsMargins(0, 0, 0, 0)
        op_layout.setSpacing(3)
        btn = QPushButton("重新加载")
        btn.setToolTip("从磁盘重新加载数据")
        btn.clicked.connect(self.reload)
        op_layout.addWidget(btn)
        btn = QPushButton("刷新")
        btn.setToolTip("刷新显示框架")
        btn.clicked.connect(self.update_all)
        op_layout.addWidget(btn)
        btn = QPushButton("数据")
        btn.clicked.connect(lambda: xdgopen(self.data_dir))
        op_layout.addWidget(btn)
        btn.setToolTip("打开数据文件夹")
        btn = QPushButton("备份")
        btn.clicked.connect(self.backup)
        btn.setToolTip("备份磁盘数据\n建议在保存前备份原数据\n此方法只操作在磁盘上的数据，如果有未保存的修改，这些修改不会应用于备份的数据")
        op_layout.addWidget(btn)
        btn = QPushButton("还原")
        btn.clicked.connect(self.restore)
        btn.setToolTip("从磁盘上的备份还原数据")
        op_layout.addWidget(btn)
        # btn = QPushButton("导出")
        # btn.clicked.connect(self.export)
        # btn.setToolTip("导出为其它格式")
        # op_layout.addWidget(btn)
        self.btn_config = QPushButton("编辑")
        self.btn_config.clicked.connect(self.edit_testconf)
        self.btn_config.setEnabled(False)
        self.btn_config.setToolTip("修改子任务配置")
        op_layout.addWidget(self.btn_config)
        self.init_menubar()
        self.init_signal()
    def init_menubar(self):
        menubar = self.menuBar()
        # File
        file_menu = menubar.addMenu("文件")
        file_menu.addAction("从磁盘重新加载", self.reload)
        file_menu.addAction("刷新显示框架", self.update_all)
        file_menu.addSeparator()
        file_menu.addAction("打开数据文件夹", lambda: xdgopen(self.data_dir))
        file_menu.addSeparator()
        export_menu = file_menu.addMenu("导出为...")
        export_menu.addAction("UOJ", self.export_uoj)
        export_menu.addAction("LemonLime", self.export_lemon)
        export_menu.addAction("洛谷", self.export_luogu)
        file_menu.addSeparator()
        file_menu.addAction("备份", self.backup)
        file_menu.addAction("还原", self.restore)
        file_menu.addSeparator()
        file_menu.addAction("退出", self.close)
        # Help
        help_menu = menubar.addMenu("帮助")
        help_menu.addAction("打开安装文件夹", lambda: xdgopen(__file__))
        help_menu.addSeparator()
        help_menu.addAction("报告问题")
        help_menu.addSeparator()
        help_menu.addAction("查看许可证", self.license)
        help_menu.addAction("关于 Qt", app.aboutQt)
        help_menu.addAction("关于本向导", self.about)
    def init_signal(self):
        self.lst_subtask.itemSelectionChanged.connect(self.update_subtask)
        self.lst_subtask.itemDoubleClicked.connect(self.on_subtask_double_click)
        self.lst_test.itemSelectionChanged.connect(self.update_test)
        self.lst_test.itemDoubleClicked.connect(self.on_test_double_click)
        getTheme().colorChanged.connect(self.update_subtask_detail)
    def getroot(self, path: str):
        root = os.path.relpath(path, self.data_dir)
        if (x := root.find("/")) != -1:
            return root[:x]
        return root
    def isvirtualsub(self, sub: int):
        return self.getroot(t := self.tests[sub].tests[0][0]) == os.path.relpath(t, self.data_dir)
    def reload(self):
        tick()
        _read_truncated.cache_clear()
        self.lst_subtask.clear()
        if os.path.isdir(self.data_dir):
            tick()
            with collect_problem():
                self.tests, self.testconf = collect_tests(self.data_dir)
            self.tests.sort(key=lambda x: path_cmp(x.tests[0][0]))
            tock("collect & sort")
            self.judgeconf = collected_problem()
            tick()
            for i in range(len(self.tests)):
                self.lst_subtask.addItem(f"#{i+1}. {self.getroot(self.tests[i].tests[0][0])}")
            tock("insert")
        tock("reload")
        self.update_all()
    def get_backup_name(self):
        ret = self.data_dir + ".bak.zip"
        x = 1
        while os.path.exists(ret):
            x += 1
            ret = self.data_dir + f"({x}).bak.zip"
        return ret
    def backup(self):
        if (dst := QFileDialog.getSaveFileName(self, "备份", self.get_backup_name(), "备份文件(*.bak.zip);;所有文件(*)")[0]):
            if e := _backup(self.data_dir, dst):
                QMessageBox.critical(self, "错误", f"备份时出现错误\n{_fexc(e)}", QMessageBox.Ok, QMessageBox.Ok)
    def get_restore_name(self):
        ret = self.data_dir + ".bak.zip"
        if not os.path.exists(ret):
            return os.path.dirname(self.data_dir)
        x = 2
        while os.path.exists(nxt := self.data_dir + f"({x}).bak.zip"):
            ret = nxt
            x += 1
        return ret
    def restore(self):
        if (src := QFileDialog.getOpenFileName(self, "还原", self.get_restore_name(), "备份文件(*.bak.zip);;所有文件(*)")[0]):
            if QMessageBox.question(self, "还原", "将覆盖当前数据，是否确认？", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                if e := _restore(src, self.data_dir):
                    if isinstance(e, int):
                        QMessageBox.critical(self, "错误", "无法开始还原")
                    elif isinstance(e, str):
                        QMessageBox.critical(self, "错误", f"还原时出现错误，数据已备份到\n{repr(e)}")
                    else:
                        QMessageBox.critical(self, "错误", f"还原时出现错误\n{_fexc(e)}")
                self.reload()
    def export_uoj(self):
        pass
    def export_lemon(self):
        pass
    def export_luogu(self):
        pass
    def export(self):
        pass
    def _edit_testconf(self, conf: TestConf):
        dlg = QDialog(self)
        dlg.setWindowTitle("修改")
        layout = QGridLayout(dlg)
        keys = list(conf.validkeys())
        op: dict[str, ExSwitcher] = {}
        label: dict[str, QLabel] = {}
        edit: dict[str, QLineEdit | ExSwitcher] = {}
        preview: dict[str, QLabel] = {}
        def update():
            for key in keys:
                if op[key].currentIndex() == 0:
                    label[key].setStyleSheet("color:gray;text-decoration:line-through")
                    if isinstance(edit[key], QLineEdit):
                        edit[key].setStyleSheet("color:gray;text-decoration:line-through")
                        edit[key].setReadOnly(True)
                elif op[key].currentIndex() == 1:
                    label[key].setStyleSheet("color:gray")
                    if isinstance(edit[key], QLineEdit):
                        edit[key].setStyleSheet("")
                        edit[key].setReadOnly(False)
                else:
                    label[key].setStyleSheet("")
                    if isinstance(edit[key], QLineEdit):
                        edit[key].setStyleSheet("")
                        edit[key].setReadOnly(False)
                if not key in preview:
                    continue
                preview[key].setStyleSheet("")
                preview[key].clear()
                if not (x := edit[key].text().strip()):
                    continue
                x = int(x) if x.isdigit() else conf.get_import(key, x)
                if x == ModelNULL:
                    preview[key].setText(_invalid)
                    fm = _fmt.fmt_invalid
                else:
                    preview[key].setText(conf.get_export(key, x))
                    fm = _fmt.fmt_comment
                sty = f"color:{fm.foreground().color().name()}"
                if (x := fm.background().color().name()) == color("red"):
                    sty += ";background:#ff0000"
                preview[key].setStyleSheet(sty)
        def update_switcher(key: str):
            if edit[key].currentIndex() != 1:
                op[key].setCurrentIndex(2)
            else:
                op[key].setCurrentIndex(1)
            update()
        def update_edit(key: str):
            if edit[key].text():
                op[key].setCurrentIndex(2)
            else:
                op[key].setCurrentIndex(1)
            update()
        label["time"] = QLabel("时间限制")
        label["time_redundancy"] = QLabel("时间冗余")
        label["memory"] = QLabel("空间限制")
        label["memory_redundancy"] = QLabel("空间冗余")
        label["stack"] = QLabel("栈空间限制")
        label["fsize"] = QLabel("IO 量限制")
        label["keep"] = QLabel("强制测试全部测试点")
        for i in range(len(keys)):
            key = keys[i]
            op[key] = ExSwitcher([
                SwitcherItem("x", color("silver"), color("red")),
                SwitcherItem("-", color("silver")),
                SwitcherItem("o", color("tianyi"), color("white")),
            ])
            op[key].setFixedSize(60, 20)
            op[key].setCurrentIndex(1)
            layout.addWidget(op[key], i, 0)
            layout.addWidget(label[key], i, 1)
            if bool in conf.get_types_of(key):
                edit[key] = ExSwitcher([
                    SwitcherItem("False", color("silver")),
                    SwitcherItem("", color("silver")),
                    SwitcherItem("True", color("tianyi"), color("white")),
                ])
                edit[key].setFixedHeight(20)
                if key in conf:
                    op[key].setCurrentIndex(2)
                    edit[key].setCurrentIndex(2 if getattr(conf, key) else 0)
                layout.addWidget(edit[key], i, 2, 2, 1)
                edit[key].itemChanged.connect(partial(lambda x, y: update_switcher(x), key))
            else:
                edit[key] = QLineEdit()
                if x := conf.get_real(key):
                    op[key].setCurrentIndex(2)
                    edit[key].setText(str(x))
                edit[key].setMaxLength(15)
                def foo(key: str, event: QMouseEvent):
                    if event.button() == Qt.MouseButton.LeftButton and op[key].currentIndex() == 0:
                        op[key].setCurrentIndex(2)
                        edit[key].setReadOnly(False)
                    super(QLineEdit, edit[key]).mouseDoubleClickEvent(event)
                edit[key].mouseDoubleClickEvent = partial(lambda x, y: foo(x, y), key)
                preview[key] = QLabel()
                layout.addWidget(edit[key], i, 2)
                layout.addWidget(preview[key], i, 3)
                edit[key].textChanged.connect(partial(lambda x, y: update_edit(x), key))
            op[key].itemChanged.connect(update)
        btn_wash = QCheckBox("清除冗余项目") # TODO
        layout.addWidget(btn_wash, 1500, 0)
        # btn = QPushButton("Debug Button")
        # btn.clicked.connect(lambda: dlg.resize(1000 if dlg.width() < 500 else 400, dlg.height()))
        # layout.addWidget(btn, 1500, 0)
        btn = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn.accepted.connect(dlg.accept)
        btn.rejected.connect(dlg.reject)
        layout.addWidget(btn, 2000, 0, 1, 4)
        update()
        dlg.resize(480, dlg.height())
        getTheme().colorChanged.connect(update)
        code = dlg.exec()
        getTheme().colorChanged.disconnect(update)
        if not code:
            return {}, []
        dic = {}
        rem = []
        for key in keys:
            if op[key].currentIndex() == 0:
                rem.append(key)
                continue
            if op[key].currentIndex() == 1:
                continue
            if isinstance(edit[key], ExSwitcher):
                if (x := edit[key].currentIndex()) >= 2:
                    dic[key] = x == 2
                elif x == 0:
                    rem.append(key)
            elif x := edit[key].text().strip():
                dic[key] = int(x) if x.isdigit() else x
        if btn_wash.isChecked():
            for key in conf.keys():
                if not conf.isvalid(key):
                    rem.append(key)
        return dic, rem
    def edit_testconf(self):
        if (sub := self.subtasks_selected()) and all(not self.isvirtualsub(x) for x in sub):
            if len(sub) == 1:
                dic, rem = self._edit_testconf(self.tests[sub[0]].conf)
            else:
                dic, rem = self._edit_testconf(TestConf())
            for x in sub:
                self.tests[x].conf.update(dic)
                for key in rem:
                    if key in self.tests[x].conf:
                        setattr(self.tests[x].conf, key, ModelNULL)
            self.update_subtask_detail()
    def license(self):
        text = QTextEdit("selfeval")
        text.setReadOnly(True)
        try:
            with stdopen(os.path.join(ROOT_DIR, "COPYING")) as file:
                text.insertPlainText(file.read())
        except OSError as err:
            text.insertPlainText("错误\n")
            text.insertPlainText("无法打开许可证：\n")
            text.insertPlainText(str(err))
        dlg = QDialog(self)
        dlg.setWindowTitle("许可证")
        dlg.setFixedWidth(360)
        layout = QVBoxLayout(dlg)
        layout.addWidget(text)
        dlg.exec()
    def about(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("关于 selfeval 数据配置向导")
        dlg.setFixedWidth(360)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel(f"version {VERSION}"))
        layout.addWidget(QLabel("本程序是 selfeval 的一部分，用于预览数据配置情况，并执行简单的修改。"))
        layout.addWidget(QLabel("本程序由 selfeval 开发者维护。"))
        dlg.exec()
    def update_subtask_detail(self):
        if (sub := self.subtask_selected()) is None:
            self.subtask_detail.setText("无法显示详细信息")
            return
        self.subtask_detail.clear()
        conf = self.tests[sub].conf
        def _insert_preview(key: str, val):
            if not conf.isvalid(key):
                pre = _extra
            elif conf.get_import(key, val) == ModelNULL:
                pre = _invalid
            else:
                pre = conf.get_export(key)
            if pre != _extra:
                self.subtask_detail.setCurrentCharFormat(_fmt.fmt_key)
            else:
                self.subtask_detail.setCurrentCharFormat(_fmt.fmt_delete)
            self.subtask_detail.insertPlainText(key)
            if pre != _extra:
                self.subtask_detail.setCurrentCharFormat(_fmt.fmt_normal)
            self.subtask_detail.insertPlainText(" = ")
            if pre != _extra:
                if pre == _invalid:
                    self.subtask_detail.setCurrentCharFormat(_fmt.fmt_delete)
                else:
                    self.subtask_detail.setCurrentCharFormat(_fmt.fmt_value)
            self.subtask_detail.insertPlainText(repr(val))
            self.subtask_detail.setCurrentCharFormat(_fmt.fmt_normal)
            if pre:
                self.subtask_detail.insertPlainText("  ")
                if pre == _extra:
                    self.subtask_detail.setCurrentCharFormat(_fmt.fmt_extra)
                elif pre == _invalid:
                    self.subtask_detail.setCurrentCharFormat(_fmt.fmt_invalid)
                else:
                    self.subtask_detail.setCurrentCharFormat(_fmt.fmt_comment)
                self.subtask_detail.insertPlainText(pre)
            self.subtask_detail.setCurrentCharFormat(_fmt.fmt_normal)
        if self.testconf is None:
            self.subtask_detail.insertPlainText("没有题目配置文件\n")
        else:
            self.subtask_detail.insertPlainText("题目配置文件\n")
            for key in self.testconf:
                _insert_preview(key, self.testconf.get_real(key))
                self.subtask_detail.insertPlainText("\n")
        self.subtask_detail.insertPlainText("\n")
        if self.isvirtualsub(sub):
            self.subtask_detail.insertPlainText("这是一个测试点\n")
            # self.subtask_detail.insertPlainText("它只在逻辑上被视为子任务，因此不支持测试点配置文件\n")
            # self.subtask_detail.insertPlainText("如果需要配置，请先使用“合并”功能将其变为真实子任务。\n")
        else:
            self.subtask_detail.insertPlainText("子任务配置文件\n")
            for key in conf:
                _insert_preview(key, conf.get_real(key))
                self.subtask_detail.insertPlainText("\n")
    def update_subtask(self):
        self.lst_test.clear()
        cur = self.subtasks_selected()
        if len(cur) == 1:
            sub = cur[0]
            for t in self.tests[sub].tests:
                self.lst_test.addItem(os.path.relpath(t[0], os.path.join(self.data_dir, self.getroot(t[0]))))
            if self.isvirtualsub(sub):
                self.btn_config.setEnabled(False)
            else:
                self.btn_config.setEnabled(True)
        else:
            if cur and all(not self.isvirtualsub(x) for x in cur):
                self.btn_config.setEnabled(True)
            else:
                self.btn_config.setEnabled(False)
        self.update_subtask_detail()
    def update_test(self):
        self.test_detail1.clear()
        self.test_detail2.clear()
        if (tc := self.tests_selected()):
            sub, tc = tc
            infile = self.tests[sub].tests[tc[0]][0]
            ansfile = self.tests[sub].tests[tc[0]][1]
            self.test_detail1.setText(read_truncated(infile))
            self.test_detail2.setText(read_truncated(ansfile))
    def update_all(self):
        self.update_subtask()
    def subtasks_selected(self):
        return [x.row() for x in self.lst_subtask.selectedIndexes()]
    def subtask_selected(self):
        return cur[0].row() if len(cur := self.lst_subtask.selectedIndexes()) == 1 else None
    def tests_selected(self):
        return (sub, [x.row() for x in tcs]) if (sub := self.subtask_selected()) is not None and (tcs := self.lst_test.selectedIndexes()) else None
    def on_subtask_double_click(self):
        if (sub := self.subtask_selected()) is not None:
            xdgopen(os.path.join(self.data_dir, self.getroot(self.tests[sub].tests[0][0])))
    def on_test_double_click(self):
        if tc := self.tests_selected():
            xdgopen(self.tests[tc[0]].tests[tc[1][0]][0])

if __name__ == "__main__":
    tick()
    app = QApplication(sys.argv)
    initColor(app)
    getTheme().colorChanged.connect(_fmt.update)
    _fmt.update()
    win = MainWindow()
    tock("init qt")
    tick()
    win.reload()
    tock("startup")
    win.show()
    app.exec()
