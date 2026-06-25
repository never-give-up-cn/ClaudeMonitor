#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
桌面悬浮球 v2
=============
类似 360 桌面助手：
- 圆形浮窗显示 CPU/内存/GPU/网速/磁盘
- 拖拽到边缘自动吸附，自动隐藏为标签
- 鼠标悬停滑出
- 左键点击打开主 GUI
- 右键菜单
"""

import sys
import os
import subprocess
import time
import threading
from pathlib import Path
from datetime import datetime

try:
    import tkinter as tk
    from tkinter import font
except ImportError:
    print("需要 tkinter")
    sys.exit(1)

try:
    import psutil
except ImportError:
    print("需要 psutil")
    sys.exit(1)

try:
    from system_stats import SystemStats
except ImportError:
    print("需要 system_stats.py")
    sys.exit(1)

# ============================================================
# 配置
# ============================================================
BALL_SIZE = 140        # 展开尺寸
TAB_SIZE = 16          # 吸附后标签宽度
SNAP_DIST = 40         # 边缘吸附距离阈值
UPDATE_MS = 1500       # 更新间隔
FONT_DIGITAL = ("Consolas", 11, "bold")
FONT_SMALL = ("Consolas", 8)
FONT_TINY = ("Consolas", 7)

# 检测中文字体
try:
    tk.font.Font(family="微软雅黑", size=10).measure("测")
    FONT_LABEL = ("微软雅黑", 9)
except:
    FONT_LABEL = ("TkDefaultFont", 9)


def _load_color(pct):
    """负载颜色: 绿→黄→红"""
    if pct < 50:
        return "#4ade80"
    elif pct < 80:
        return "#fbbf24"
    return "#ef4444"


class FloatingBall:
    """桌面悬浮球"""

    def __init__(self):
        self.stats = SystemStats()
        self._running = True
        self._drag_start = None  # (x, y) 拖拽起点
        self._is_dragging = False
        self._snapped = False     # 是否吸附在边缘
        self._snap_edge = ""      # top/bottom/left/right
        self._hidden_mode = False # 是否隐藏为标签
        self._leave_timer = None  # 鼠标离开定时器

        # 窗口
        self.root = tk.Tk()
        self.root.title("系统监控")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", "#000000")

        # 屏幕尺寸
        self.sw = self.root.winfo_screenwidth()
        self.sh = self.root.winfo_screenheight()
        self._default_x = self.sw - BALL_SIZE - 20
        self._default_y = self.sh - BALL_SIZE - 60

        # Canvas
        self.canvas = tk.Canvas(
            self.root, width=BALL_SIZE, height=BALL_SIZE,
            bg="#000000", highlightthickness=0, cursor="hand2"
        )
        self.canvas.pack()

        # 画静态元素
        self._draw_ball()

        # 事件
        self.canvas.bind("<Button-1>", self._on_btn1)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Button-3>", self._on_right)
        self.canvas.bind("<Enter>", self._on_enter)
        self.canvas.bind("<Leave>", self._on_leave)

        # 定位
        self.root.geometry(f"+{self._default_x}+{self._default_y}")

        # 定时更新
        self.update_stats()

    def _draw_ball(self, size=BALL_SIZE, snapped=False):
        """绘制悬浮球"""
        self.canvas.delete("all")
        cx = cy = size // 2

        if snapped:
            # 吸附状态：只画一个小标签
            r = size // 2 - 1
            self.canvas.create_oval(
                cx - r, cy - r, cx + r, cy + r,
                fill="#1a1a2e", outline="#3a3a5e", width=1
            )
            self.canvas.create_text(
                cx, cy, text="CC", fill="#888888",
                font=("Consolas", 7, "bold"), anchor=tk.CENTER
            )
            return

        # 外圈辉光
        r = size // 2 - 2
        self.canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            fill="#1a1a2e", outline="#3a3a5e", width=2
        )
        r2 = r - 10
        self.canvas.create_oval(
            cx - r2, cy - r2, cx + r2, cy + r2,
            fill="#16213e", outline="#2a3a5e", width=1
        )

        # 文本占位
        self.cpu_t = self.canvas.create_text(
            cx, cy - 18, text="CPU:--%", fill="#4ade80",
            font=FONT_DIGITAL, anchor=tk.CENTER
        )
        self.mem_t = self.canvas.create_text(
            cx, cy + 2, text="MEM:--%", fill="#60a5fa",
            font=FONT_SMALL, anchor=tk.CENTER
        )
        self.gpu_t = self.canvas.create_text(
            cx, cy + 16, text="GPU:--%", fill="#f472b6",
            font=FONT_SMALL, anchor=tk.CENTER
        )
        # 网速
        self.net_up_t = self.canvas.create_text(
            6, 6, text="▲--K", fill="#fbbf24",
            font=FONT_TINY, anchor=tk.NW
        )
        self.net_dn_t = self.canvas.create_text(
            6, 18, text="▼--K", fill="#34d399",
            font=FONT_TINY, anchor=tk.NW
        )
        # 磁盘
        self.disk_t = self.canvas.create_text(
            size - 4, 6, text="C:--%", fill="#a78bfa",
            font=FONT_TINY, anchor=tk.NE
        )

    # ---- 事件处理 ----

    def _on_btn1(self, event):
        """鼠标按下：记录起点"""
        self._drag_start = (event.x_root, event.y_root)
        self._is_dragging = False

    def _on_drag(self, event):
        """拖拽中"""
        if not self._drag_start:
            return
        dx = event.x_root - self._drag_start[0]
        dy = event.y_root - self._drag_start[1]
        if abs(dx) > 5 or abs(dy) > 5:
            self._is_dragging = True
        x = self.root.winfo_x() + dx
        y = self.root.winfo_y() + dy
        self.root.geometry(f"+{x}+{y}")
        self._drag_start = (event.x_root, event.y_root)

    def _on_release(self, event):
        """鼠标释放：吸附检测 或 点击"""
        if self._is_dragging:
            # 拖拽结束 → 吸附检测
            self._is_dragging = False
            self._snap_check()
        else:
            # 没拖拽 → 当作点击
            self._on_click()
        self._drag_start = None

    def _on_click(self):
        """左键点击：打开主 GUI"""
        if self._hidden_mode:
            return
        gui_path = Path(__file__).parent / "gui.py"
        if gui_path.exists():
            try:
                subprocess.Popen(
                    [sys.executable, str(gui_path)],
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
            except Exception:
                pass

    def _on_right(self, event):
        """右键：弹出菜单"""
        menu = tk.Menu(self.root, tearoff=0, bg="#2d2d2d", fg="#dddddd",
                       activebackground="#4a6a8a", activeforeground="#ffffff",
                       font=FONT_LABEL if FONT_LABEL else ("TkDefaultFont", 10))
        menu.add_command(label="打开主窗口", command=self._open_gui)
        menu.add_command(label="重新加载", command=lambda: self.update_stats())
        if self._snapped:
            menu.add_command(label="解除吸附", command=self._unsnap)
        menu.add_separator()
        menu.add_command(label="退出", command=self.on_exit)
        menu.post(event.x_root, event.y_root)

    def _open_gui(self):
        self._on_click()

    # ---- 边缘吸附 ----

    def _snap_check(self):
        """检查是否需要吸附到边缘"""
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        cx = x + BALL_SIZE // 2
        cy = y + BALL_SIZE // 2
        w, h = BALL_SIZE, BALL_SIZE

        # 找最近的边缘
        dist_left = cx
        dist_right = self.sw - cx
        dist_top = cy
        dist_bottom = self.sh - cy

        min_dist = min(dist_left, dist_right, dist_top, dist_bottom)
        if min_dist > SNAP_DIST:
            if self._snapped:
                self._unsnap()
            return

        self._snapped = True
        if min_dist == dist_left:
            self._snap_edge = "left"
            self.root.geometry(f"{TAB_SIZE}x{h}+0+{y}")
        elif min_dist == dist_right:
            self._snap_edge = "right"
            self.root.geometry(f"{TAB_SIZE}x{h}+{self.sw - TAB_SIZE}+{y}")
        elif min_dist == dist_top:
            self._snap_edge = "top"
            self.root.geometry(f"{w}x{TAB_SIZE}+{x}+0")
        else:
            self._snap_edge = "bottom"
            self.root.geometry(f"{w}x{TAB_SIZE}+{x}+{self.sh - TAB_SIZE}")

        self._hidden_mode = True
        self._draw_ball(TAB_SIZE, snapped=True)

    def _unsnap(self):
        """解除吸附"""
        self._snapped = False
        self._snap_edge = ""
        self._hidden_mode = False
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        self.root.geometry(f"{BALL_SIZE}x{BALL_SIZE}+{x}+{y}")
        self._draw_ball(BALL_SIZE)

    def _on_enter(self, event):
        """鼠标进入：滑出"""
        if not self._snapped or not self._hidden_mode:
            return
        if self._leave_timer:
            self.root.after_cancel(self._leave_timer)
            self._leave_timer = None
        self._slide_out()

    def _on_leave(self, event):
        """鼠标离开：延迟隐藏"""
        if not self._snapped or not self._hidden_mode:
            return
        if self._leave_timer:
            self.root.after_cancel(self._leave_timer)
        self._leave_timer = self.root.after(1500, self._slide_in)

    def _slide_out(self):
        """滑出显示"""
        if not self._snapped:
            return
        self._hidden_mode = False
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        edge = self._snap_edge

        if edge == "left":
            self.root.geometry(f"{BALL_SIZE}x{BALL_SIZE}+0+{y}")
        elif edge == "right":
            self.root.geometry(f"{BALL_SIZE}x{BALL_SIZE}+{self.sw - BALL_SIZE}+{y}")
        elif edge == "top":
            self.root.geometry(f"{BALL_SIZE}x{BALL_SIZE}+{x}+0")
        elif edge == "bottom":
            self.root.geometry(f"{BALL_SIZE}x{BALL_SIZE}+{x}+{self.sh - BALL_SIZE}")

        self._draw_ball(BALL_SIZE)

    def _slide_in(self):
        """滑入隐藏为标签"""
        if not self._snapped or self._hidden_mode:
            return
        # 检查鼠标是否还在窗口内
        try:
            wx, wy = self.root.winfo_pointerxy()
            rx, ry = self.root.winfo_x(), self.root.winfo_y()
            rw, rh = BALL_SIZE, BALL_SIZE
            if rx <= wx <= rx + rw and ry <= wy <= ry + rh:
                return  # 鼠标还在，不隐藏
        except Exception:
            pass

        self._hidden_mode = True
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        edge = self._snap_edge

        if edge == "left":
            self.root.geometry(f"{TAB_SIZE}x{BALL_SIZE}+0+{y}")
        elif edge == "right":
            self.root.geometry(f"{TAB_SIZE}x{BALL_SIZE}+{self.sw - TAB_SIZE}+{y}")
        elif edge == "top":
            self.root.geometry(f"{BALL_SIZE}x{TAB_SIZE}+{x}+0")
        elif edge == "bottom":
            self.root.geometry(f"{BALL_SIZE}x{TAB_SIZE}+{x}+{self.sh - TAB_SIZE}")

        self._draw_ball(TAB_SIZE, snapped=True)

    # ---- 数据更新 ----

    def update_stats(self):
        """定时刷新数据"""
        if not self._running:
            return
        try:
            data = self.stats.get_all()
            self._render(data)
        except Exception:
            pass
        self.root.after(UPDATE_MS, self.update_stats)

    def _render(self, data):
        """渲染数据"""
        if self._hidden_mode:
            return  # 标签模式不显示数据

        cpu = data.get("cpu", {}).get("percent", 0)
        mem = data.get("memory", {}).get("percent", 0)
        gpu_data = data.get("gpu")

        self._set_text(self.cpu_t, f"CPU:{cpu:.0f}%", _load_color(cpu))
        self._set_text(self.mem_t, f"MEM:{mem:.0f}%", _load_color(mem))

        if gpu_data and isinstance(gpu_data, list) and len(gpu_data) > 0:
            gp = gpu_data[0].get("util", 0)
            self._set_text(self.gpu_t, f"GPU:{gp:.0f}%", _load_color(gp))
        else:
            self._set_text(self.gpu_t, "GPU:--", "#555555")

        net = data.get("network", {})
        up = net.get("up_kbps", 0)
        dn = net.get("down_kbps", 0)
        self._set_text(self.net_up_t, f"▲{up:.0f}K" if up < 999 else f"▲{up/1024:.1f}M", "#fbbf24")
        self._set_text(self.net_dn_t, f"▼{dn:.0f}K" if dn < 999 else f"▼{dn/1024:.1f}M", "#34d399")

        disks = data.get("disks", [])
        parts = []
        for d in disks[:2]:
            label = d.get("mount", "")[0]
            parts.append(f"{label}:{d.get('percent', 0):.0f}%")
        self._set_text(self.disk_t, " ".join(parts) if parts else "--", "#a78bfa")

    def _set_text(self, item, text, color):
        """安全更新文本"""
        try:
            self.canvas.itemconfig(item, text=text, fill=color)
        except Exception:
            pass

    def on_exit(self):
        """退出"""
        self._running = False
        self.root.destroy()


def main():
    ball = FloatingBall()
    ball.root.mainloop()


if __name__ == "__main__":
    main()
