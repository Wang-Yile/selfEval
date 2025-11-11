import math
import sys
import time
from typing import NamedTuple

from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PySide6.QtGui import QPainter, QColor, QMouseEvent
from PySide6.QtCore import Qt, QPointF, QRectF, QPropertyAnimation, QEasingCurve, Property, QTimer, Signal

from .color import *

def lighter(col: QColor, x = 25):
    return QColor(
        min(col.red() + x, 255),
        min(col.green() + x, 255),
        min(col.blue() + x, 255),
        col.alpha()
    )

R = 3
class SwitcherItem(NamedTuple):
    text: str = ""
    background: QColor = QColor()
    foreground: QColor = QColor()
    width: int = 1
class ExSwitcher(QWidget):
    itemChanged = Signal(int)
    def __init__(self, items: list[SwitcherItem] = None, /, parent = None, *, standout = False):
        super().__init__(parent)
        if items is None:
            items = []
        self._items = items
        self._standout = standout
        self._current = 0
        self._slider_pos = 0
        self._slider_width = 0
        self._anim = None
        self._width_anim = None
        self._dragging = False
        self._drag_st = None
        self._drag_start_pos = None
        self._drag_start_width = None
        self._drag_timer = QTimer()
        self._drag_timer.timeout.connect(self._updateDragAnim)
        self._target_pos = 0
        self._target_width = 0
        self._ratio_sum = 0
        self._recalcPositions()
        self.init_animation()
        self._slider_pos = self._calcTargetPos() if self._items else 0
        self._slider_width = self._calcTargetWidth() if self._items else 0
        getTheme().colorChanged.connect(self.update)
    def init_animation(self):
        self._fps = 60
        self._ease_factor = 0.2
        self._ease_duration = 50
        self._ease_eps = 1e-3
        self._ease_n = math.log(self._ease_eps, self._ease_factor) / self._ease_duration
        self._last_anim = None
        self._anim = QPropertyAnimation(self, b"sliderPos")
        self._anim.setDuration(100)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._width_anim = QPropertyAnimation(self, b"sliderWidth")
        self._width_anim.setDuration(100)
        self._width_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    def _recalcPositions(self):
        self._ratio_sum = sum(item.width for item in self._items)
        self._item_positions = [0]
        for item in self._items:
            self._item_positions.append(self._item_positions[-1] + item.width)
    def clear(self):
        self._items.clear()
        self._recalcPositions()
        self._current = 0
        self._slider_pos = 0
        self._slider_width = 0
    def insertItem(self, index: int, text: str = "", background: QColor = None, foreground: QColor = None, width: int = 1):
        self._items.insert(index, SwitcherItem(text, QColor() if background is None else background, QColor() if foreground is None else foreground, width))
        self._recalcPositions()
        self.update()
    def removeItem(self, index: int):
        if 0 <= index < len(self._items):
            del self._items[index]
            self._recalcPositions()
            self._current = min(self._current, len(self._items) - 1)
            self._slider_pos = self._calcTargetPos()
            self._slider_width = self._calcTargetWidth()
            self.update()
    def currentIndex(self):
        return self._current
    def currentItem(self):
        return self._items[self._current]
    def setCurrentIndex(self, index: int, *, _anim = True):
        if 0 <= index < len(self._items):
            old = self._current
            self._current = index
            if _anim:
                if self._anim.state() == QPropertyAnimation.Running:
                    self._anim.setCurrentTime(self._anim.duration())
                self._anim.setStartValue(self._slider_pos)
                self._anim.setEndValue(self._calcTargetPos())
                self._anim.start()
                if self._width_anim.state() == QPropertyAnimation.Running:
                    self._width_anim.setCurrentTime(self._width_anim.duration())
                self._width_anim.setStartValue(self._slider_width)
                self._width_anim.setEndValue(self._calcTargetWidth())
                self._width_anim.start()
            if old != index:
                self.itemChanged.emit(index)
    def _real(self, x: float, width: int = None):
        if width is None:
            width = self.width()
        return x * width / self._ratio_sum
    def _virtual(self, x: float, width: int = None):
        if width is None:
            width = self.width()
        return x * self._ratio_sum / width
    def _calcTargetPos(self):
        " 计算目标位置 "
        return self._real(self._item_positions[self._current])
    def _calcTargetWidth(self):
        " 计算目标宽度 "
        return self._real(self._items[self._current].width)
    def _calcIndexFromPos(self, position: float):
        " 根据位置计算状态 "
        norm_pos = self._virtual(position)
        for i in range(len(self._item_positions) - 1):
            if self._item_positions[i] <= norm_pos < self._item_positions[i + 1]:
                return i
        return len(self._items) - 1
    def _getSliderColor(self, index: int):
        " 获取滑块颜色 "
        if 0 <= index < len(self._items):
            return lighter(self._items[index].background)
        return QColor("#e6e6e6")
    def _startDrag(self, pos: QPointF):
        self._dragging = True
        self._drag_st = pos
        self._drag_start_pos = self._slider_pos
        self._drag_start_width = self._slider_width
        # 停止动画
        if self._anim.state() == QPropertyAnimation.Running:
            self._anim.setCurrentTime(self._anim.duration())
        if self._width_anim.state() == QPropertyAnimation.Running:
            self._width_anim.setCurrentTime(self._width_anim.duration())
        # 初始化目标值
        self._target_pos = self._slider_pos
        self._target_width = self._slider_width
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setCurrentIndex(self._calcIndexFromPos(event.position().x()))
            event.accept()
        return super().mousePressEvent(event)
    def mouseMoveEvent(self, event: QMouseEvent):
        if not self._dragging and event.button() == Qt.MouseButton.NoButton and self._items:
            self.setCurrentIndex(self._calcIndexFromPos(event.position().x()))
            self._startDrag(event.position())
        if self._dragging:
            # 计算拖动距离
            delta_x = event.position().x() - self._drag_st.x()
            # 计算新的滑块中心位置
            orig_center = self._drag_start_pos + self._drag_start_width / 2
            new_center = orig_center + delta_x
            new_center = min(max(new_center, 0), self.width())
            new_index = self._calcIndexFromPos(new_center)
            new_width = self._real(self._items[new_index].width)
            new_pos = new_center - new_width / 2
            new_pos = max(0, min(new_pos, self.width() - new_width))
            # 如果状态改变，设置新状态
            if new_index != self._current:
                self.setCurrentIndex(new_index, _anim = False)
            # 更新目标值
            self._target_pos = new_pos
            self._target_width = new_width
            self._startDragAnim()
            event.accept()
        return super().mouseMoveEvent(event)
    def _startDragAnim(self):
        if not self._drag_timer.isActive():
            self._drag_timer.start(1000 / self._fps)
    def _updateDragAnim(self, *, _onego: bool = False):
        if not self._dragging:
            self._drag_timer.stop()
            return
        if _onego:
            self._slider_pos = self._target_pos
            self._slider_width = self._target_width
            self._drag_timer.stop()
            return
        coef = 1 - pow(1 - self._ease_factor, 0 if self._last_anim is None else (time.monotonic() - self._last_anim) * 1000 * self._ease_n)
        pos_diff = self._target_pos - self._slider_pos
        width_diff = self._target_width - self._slider_width
        self._slider_pos += pos_diff * coef
        self._slider_width += width_diff * coef
        self.update()
        if abs(pos_diff) < 0.1 and abs(width_diff) < 0.1:
            self._drag_timer.stop()
        self._last_anim = time.monotonic()
    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._dragging and event.button() == Qt.LeftButton:
            self._updateDragAnim(_onego=True)
            self._dragging = False
            # 根据滑块中心确定状态
            slider_center = self._slider_pos + self._slider_width / 2
            new_index = self._calcIndexFromPos(slider_center)
            # 如果状态改变，设置新状态
            if new_index != self._current:
                self.setCurrentIndex(new_index)
            else:
                # 状态未改变，动画到精确位置
                target_pos = self._calcTargetPos()
                target_width = self._calcTargetWidth()
                if self._anim.state() == QPropertyAnimation.Running:
                    self._anim.stop()
                self._anim.setStartValue(self._slider_pos)
                self._anim.setEndValue(target_pos)
                self._anim.start()
                if self._width_anim.state() == QPropertyAnimation.Running:
                    self._width_anim.stop()
                self._width_anim.setStartValue(self._slider_width)
                self._width_anim.setEndValue(target_width)
                self._width_anim.start()
            event.accept()
        return super().mouseReleaseEvent(event)
    def resizeEvent(self, event):
        if self._anim.state() == QPropertyAnimation.Running:
            self._anim.setCurrentTime(self._anim.duration())
        self._anim.setStartValue(self._slider_pos)
        self._anim.setEndValue(self._calcTargetPos())
        self._anim.start()
        if self._width_anim.state() == QPropertyAnimation.Running:
            self._width_anim.setCurrentTime(self._width_anim.duration())
        self._width_anim.setStartValue(self._slider_width)
        self._width_anim.setEndValue(self._calcTargetWidth())
        self._width_anim.start()
        return super().resizeEvent(event)
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        width = self.width()
        height = self.height()
        # 绘制背景
        self._drawBackground(painter, width, height)
        if not self._items:
            return
        # 绘制状态文本
        self._drawItemText(painter, width, height)
        # 绘制滑块
        self._drawSlider(painter, width, height)
    def _drawBackground(self, painter: QPainter, width: int, height: int):
        " 绘制背景 "
        painter.save()
        painter.setPen(Qt.NoPen)
        for i in range(len(self._items)):
            item = self._items[i]
            st = self._real(self._item_positions[i], width)
            ed = self._real(self._item_positions[i+1], width)
            rect = QRectF(st, 0, ed-st, height)
            painter.setBrush(item.background)
            if 0 < i < len(self._items) - 1:
                painter.drawRect(rect)
            else:
                painter.drawRoundedRect(rect, R, R)
            if i == 0 and i != len(self._items) - 1:
                painter.drawRect(QRectF(st+ed-st-R, 0, R, height))
            if i != 0 and i == len(self._items) - 1:
                painter.drawRect(QRectF(st, 0, R, height))
        painter.setBrush(Qt.NoBrush)
        if len(self._items) == 1:
            painter.setPen(lighter(self._items[0].background))
            painter.drawRoundedRect(QRectF(0, 0, width, height), R, R)
        else:
            ed = self._real(self._item_positions[1], width)
            painter.setPen(lighter(self._items[0].background))
            painter.drawLine(R, 0, ed, 0)
            painter.drawLine(R, height, ed, height)
            painter.drawLine(0, R, 0, height-R)
            painter.drawArc(0, 0, 2*R, 2*R, 90*16, 90*16)
            painter.drawArc(0, height-2*R, 2*R, 2*R, 180*16, 90*16)
            st = self._real(self._item_positions[-2], width)
            painter.setPen(lighter(self._items[-1].background))
            painter.drawLine(st, 0, width-R, 0)
            painter.drawLine(st, height, width-R, height)
            painter.drawLine(width, R, width, height-R)
            painter.drawArc(width-2*R, 0, 2*R, 2*R, 0, 90*16)
            painter.drawArc(width-2*R, height-2*R, 2*R, 2*R, 270*16, 90*16)
        for i in range(1, len(self._items)-1):
            item = self._items[i]
            st = self._real(self._item_positions[i], width)
            ed = self._real(self._item_positions[i+1], width)
            painter.setPen(lighter(item.background))
            painter.drawLine(st, 0, ed, 0)
            painter.drawLine(st, height, ed, height)
        painter.restore()
    def _drawItemText(self, painter: QPainter, width: int, height: int):
        " 绘制状态文本 "
        painter.save()
        # 计算状态像素位置
        for i in range(len(self._items)):
            st = self._real(self._item_positions[i], width)
            ed = self._real(self._item_positions[i + 1], width)
            painter.setPen(self._items[i].foreground)
            painter.drawText(QRectF(st, 0, ed-st, height), Qt.AlignCenter, self._items[i].text)
        painter.restore()
    def _drawSlider(self, painter: QPainter, width: int, height: int):
        " 绘制滑块 "
        slider_height = height
        slider_y = 0
        # 根据滑块中心确定状态
        cur = self._calcIndexFromPos(self._slider_pos + self._slider_width / 2)
        rect = QRectF(self._slider_pos + 2, slider_y, self._slider_width - 4, slider_height)
        # 滑块
        slider_color = self._getSliderColor(cur)
        painter.save()
        if self._standout:
            painter.setPen(color("gray"))
        else:
            painter.setPen(lighter(slider_color))
        painter.setBrush(slider_color)
        painter.setOpacity(0.8)
        painter.drawRoundedRect(rect, R, R)
        painter.restore()
        # 滑块文本
        painter.save()
        painter.setPen(self._items[cur].foreground)
        painter.drawText(rect, Qt.AlignCenter, self._items[cur].text)
        painter.restore()
    def getSliderPos(self):
        return self._slider_pos
    def setSliderPos(self, pos):
        self._slider_pos = pos
        self.update()
    def getSliderWidth(self):
        return self._slider_width
    def setSliderWidth(self, width):
        # 计算当前中心点
        current_center = self._slider_pos + self._slider_width / 2
        # 更新宽度
        self._slider_width = width
        # 根据新宽度调整位置，保持中心点不变
        self._slider_pos = current_center - self._slider_width / 2
        self.update()
    sliderPos = Property(float, getSliderPos, setSliderPos)
    sliderWidth = Property(float, getSliderWidth, setSliderWidth)

# 测试用例
class DemoWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        
    def initUI(self):
        self.setWindowTitle("ExSwitcher 演示")
        self.setFixedSize(500, 600)
        
        layout = QVBoxLayout()
        
        # 标题
        title = QLabel("ExSwitcher - 支持多状态和动画")
        title.setStyleSheet("font-size: 14pt; font-weight: bold; margin-bottom: 20px;")
        layout.addWidget(title)
        
        # 示例1: 默认三态开关
        example1 = QLabel("示例1: 默认三态开关")
        example1.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(example1)
        states1 = [
                SwitcherItem("否", QColor(255, 100, 100), width=1),
                SwitcherItem("关", QColor(200, 200, 200), width=1),
                SwitcherItem("是", QColor(100, 200, 100), width=1),
            ]

        self.switcher1 = ExSwitcher()
        self.state_label1 = QLabel("状态: 0")
        self.switcher1.itemChanged.connect(lambda s: self.state_label1.setText(f"状态: {s}"))
        
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("开关1:"))
        h1.addWidget(self.switcher1)
        h1.addWidget(self.state_label1)
        h1.addStretch()
        layout.addLayout(h1)
        
        # 示例2: 五态开关，不同宽度
        example2 = QLabel("示例2: 五态开关，不同宽度")
        example2.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(example2)
        
        states2 = [
            SwitcherItem("很差", QColor(255, 150, 150), width=1),
            SwitcherItem("较差", QColor(255, 200, 150), width=1),
            SwitcherItem("一般", QColor(255, 255, 150), width=2),
            SwitcherItem("较好", QColor(200, 255, 150), width=1),
            SwitcherItem("很好", QColor(150, 255, 150), width=3),
        ]
        self.switcher2 = ExSwitcher(states2)
        self.state_label2 = QLabel("状态: 2")
        self.switcher2.itemChanged.connect(lambda s: self.state_label2.setText(f"状态: {s}"))
        
        h2 = QHBoxLayout()
        h2.addWidget(QLabel("开关2:"))
        h2.addWidget(self.switcher2)
        h2.addWidget(self.state_label2)
        h2.addStretch()
        layout.addLayout(h2)
        
        # 示例3: 四态开关，不同宽度
        example3 = QLabel("示例3: 四态开关，不同宽度")
        example3.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(example3)
        
        states3 = [
            SwitcherItem("短", QColor(200, 200, 255), width=1),
            SwitcherItem("中", QColor(150, 200, 255), width=2),
            SwitcherItem("长", QColor(100, 150, 255), width=3),
            SwitcherItem("中", QColor(50, 100, 255), width=2),
        ]
        self.switcher3 = ExSwitcher(states3)
        self.state_label3 = QLabel("状态: 0")
        self.switcher3.itemChanged.connect(lambda s: self.state_label3.setText(f"状态: {s}"))
        
        h3 = QHBoxLayout()
        h3.addWidget(QLabel("开关3:"))
        h3.addWidget(self.switcher3)
        h3.addWidget(self.state_label3)
        h3.addStretch()
        layout.addLayout(h3)
        
        # 示例4
        example4 = QLabel("示例4")
        example4.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(example4)
        
        states4 = []
        for i in range(64, 256, 16):
            states4.append(SwitcherItem(background=QColor(0, i, 0), width=1+i/256))
        self.switcher4 = ExSwitcher(states4)
        self.state_label4 = QLabel("状态: 0")
        self.switcher4.itemChanged.connect(lambda s: self.state_label4.setText(f"状态: {s}"))
        # self.tm = QTimer()
        # self.tm.timeout.connect(lambda: (self.switcher4.addState(QColor("blue")), self.tm.stop()))
        # self.tm.setInterval(2000)
        # self.tm.start()
        
        h4 = QHBoxLayout()
        h4.addWidget(QLabel("开关4:"))
        h4.addWidget(self.switcher4)
        h4.addWidget(self.state_label4)
        h4.addStretch()
        layout.addLayout(h4)
        
        # 说明
        info = QLabel(
            "交互说明:\n"
            "- 点击状态区域 -> 切换到对应状态\n"
            "- 拖动滑块 -> 滑块颜色和宽度会平滑过渡\n"
            "- 每个状态可以有不同的颜色、宽度和文本"
        )
        info.setStyleSheet("color: blue; margin-top: 20px; padding: 10px; border-radius: 5px;")
        layout.addWidget(info)
        
        # 控制按钮
        ctrl_layout = QHBoxLayout()
        ctrl_layout.addWidget(QLabel("控制开关2:"))
        
        btn0 = QPushButton("状态0")
        btn1 = QPushButton("状态1")
        btn2 = QPushButton("状态2")
        btn3 = QPushButton("状态3")
        btn4 = QPushButton("状态4")
        
        btn0.clicked.connect(lambda: self.switcher2.setCurrentIndex(0))
        btn1.clicked.connect(lambda: self.switcher2.setCurrentIndex(1))
        btn2.clicked.connect(lambda: self.switcher2.setCurrentIndex(2))
        btn3.clicked.connect(lambda: self.switcher2.setCurrentIndex(3))
        btn4.clicked.connect(lambda: self.switcher2.setCurrentIndex(4))
        
        ctrl_layout.addWidget(btn0)
        ctrl_layout.addWidget(btn1)
        ctrl_layout.addWidget(btn2)
        ctrl_layout.addWidget(btn3)
        ctrl_layout.addWidget(btn4)
        ctrl_layout.addStretch()
        
        layout.addLayout(ctrl_layout)
        
        self.setLayout(layout)


if __name__ == "__main__":
    # import os
    # offscreen, eglfs, vkkhrdisplay, linuxfb, xcb, minimalegl, minimal, vnc, wayland-brcm, wayland-egl, wayland
    # os.environ["QT_QPA_PLATFORM"] = "wayland"
    app = QApplication(sys.argv)
    # print(app.platformName())
    
    window = DemoWindow()
    window.show()
    
    sys.exit(app.exec())