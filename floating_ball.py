#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
桌面悬浮球
==========
类似 360 桌面助手，圆形半透明浮窗显示系统状态：
CPU、内存、GPU、磁盘、网速。
点击打开 Claude Monitor 主窗口。
"""

import sys
import os
import threading
import time
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
BALL_SIZE = 150       # 悬浮球尺寸
UPDATE_INTERVAL = 1500  # 更新间隔(ms)
FONT_DIGITAL = ("Consolas", 11, "bold")
FONT_SMALL = ("Consolas", 8)
FONT_CN = None

# 检测中文字体
try:
    tk.font.Font(family="微软雅黑", size=10).measure("测")
    FONT_CN = ("微软雅黑", 9)
except:
    FONT_CN = ("TkDefaultFont", 9)


class FloatingBall:
    """桌面悬浮球"""

    def __init__(self):
        self.stats_collector = SystemStats()

        # 主窗口
        self.root = tk.Tk()
        self.root.title("系统监控")
        self.root.overrideredirect(True)  # 无边框
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", "#000000")  # 黑色透明

        # 窗口位置（右下角）
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.win_x = sw - BALL_SIZE - 20
        self.win_y = sh - BALL_SIZE - 60
        self.root.geometry(f"{BALL_SIZE}x{BALL_SIZE}+{self.win_x}+{self.win_y}")

        # 数据
        self.stats = {}
        self._gui_process = None
        self._running = True

        # 构建 UI
        self._build_ui()

        # 拖拽
        self._make_draggable()

        # 启动更新
        self.update_stats()

        # 点击打开 GUI
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<Button-3>", self.on_right_click)

    def _build_ui(self):
        """构建悬浮球界面"""
        self.canvas = tk.Canvas(
            self.root, width=BALL_SIZE, height=BALL_SIZE,
            bg="#000000", highlightthickness=0, cursor="hand2"
        )
        self.canvas.pack()

        # 外圈辉光
        r = BALL_SIZE // 2 - 2
        cx = cy = BALL_SIZE // 2
        self.canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            fill="#1a1a2e", outline="#3a3a5e", width=2
        )
        # 内圈
        r2 = r - 12
        self.canvas.create_oval(
            cx - r2, cy - r2, cx + r2, cy + r2,
            fill="#16213e", outline="#2a3a5e", width=1
        )

        # 文本占位
        self.cpu_text = self.canvas.create_text(
            cx, cy - 20, text="CPU:--%", fill="#4ade80",
            font=FONT_DIGITAL, anchor=tk.CENTER
        )
        self.mem_text = self.canvas.create_text(
            cx, cy + 2, text="MEM:--%", fill="#60a5fa",
            font=FONT_SMALL, anchor=tk.CENTER
        )
        self.gpu_text = self.canvas.create_text(
            cx, cy + 18, text="GPU:--%", fill="#f472b6",
            font=FONT_SMALL, anchor=tk.CENTER
        )

        # 网速（左上角）
        self.net_up_text = self.canvas.create_text(
            8, 8, text="▲--K", fill="#fbbf24",
            font=("Consolas", 7), anchor=tk.NW
        )
        self.net_down_text = self.canvas.create_text(
            8, 20, text="▼--K", fill="#34d399",
            font=("Consolas", 7), anchor=tk.NW
        )

        # 磁盘（右上角）
        self.disk_text = self.canvas.create_text(
            BALL_SIZE - 4, 8, text="C:--%", fill="#a78bfa",
            font=("Consolas", 7), anchor=tk.NE
        )

    def _make_draggable(self):
        """让悬浮球可拖动"""
        self._drag_data = {"x": 0, "y": 0}

        def start_drag(event):
            self._drag_data["x"] = event.x_root
            self._drag_data["y"] = event.y_root

        def do_drag(event):
            dx = event.x_root - self._drag_data["x"]
            dy = event.y_root - self._drag_data["y"]
            x = self.root.winfo_x() + dx
            y = self.root.winfo_y() + dy
            self.root.geometry(f"+{x}+{y}")
            self._drag_data["x"] = event.x_root
            self._drag_data["y"] = event.y_root

        self.canvas.bind("<Button-1>", start_drag, add="+")
        self.canvas.bind("<B1-Motion>", do_drag)

    def update_stats(self):
        """定时更新系统状态"""
        if not self._running:
            return

        try:
            self.stats = self.stats_collector.get_all()
            self._render_stats()
        except Exception:
            pass

        self.root.after(UPDATE_INTERVAL, self.update_stats)

    def _render_stats(self):
        """渲染数据到悬浮球"""
        cx = cy = BALL_SIZE // 2
        stats = self.stats

        # CPU
        cpu_percent = stats.get("cpu", {}).get("percent", 0)
        cpu_color = self._load_color(cpu_percent)
        self.canvas.itemconfig(self.cpu_text, text=f"CPU:{cpu_percent:.0f}%", fill=cpu_color)

        # 内存
        mem_percent = stats.get("memory", {}).get("percent", 0)
        mem_color = self._load_color(mem_percent)
        self.canvas.itemconfig(self.mem_text, text=f"MEM:{mem_percent:.0f}%", fill=mem_color)

        # GPU
        gpu = stats.get("gpu")
        if gpu:
            gpu_percent = gpu[0].get("util", 0) if isinstance(gpu, list) else 0
            gpu_color = self._load_color(gpu_percent)
            self.canvas.itemconfig(self.gpu_text, text=f"GPU:{gpu_percent:.0f}%", fill=gpu_color)
        else:
            self.canvas.itemconfig(self.gpu_text, text="GPU:--", fill="#555555")

        # 网速
        net = stats.get("network", {})
        up = net.get("up_kbps", 0)
        down = net.get("down_kbps", 0)
        up_str = f"▲{up:.0f}K" if up < 1000 else f"▲{up/1024:.1f}M"
        down_str = f"▼{down:.0f}K" if down < 1000 else f"▼{down/1024:.1f}M"
        self.canvas.itemconfig(self.net_up_text, text=up_str)
        self.canvas.itemconfig(self.net_down_text, text=down_str)

        # 磁盘（显示占用最高的盘）
        disks = stats.get("disks", [])
        disk_parts = []
        for d in disks[:3]:
            mount = d.get("mount", "")
            if mount:
                label = mount[0] if len(mount) == 1 else mount.replace(":\\", "")
                disk_parts.append(f"{label}:{d.get('percent', 0):.0f}%")
        disk_str = " ".join(disk_parts) if disk_parts else "--"
        self.canvas.itemconfig(self.disk_text, text=disk_str)

    def _load_color(self, percent):
        """根据负载返回颜色（绿→黄→红）"""
        if percent < 50:
            return "#4ade80"  # 绿
        elif percent < 80:
            return "#fbbf24"  # 黄
        return "#ef4444"  # 红

    def on_click(self, event):
        """左键点击 → 打开主 GUI"""
        # 启动 gui.py
        script_dir = Path(__file__).parent
        gui_path = script_dir / "gui.py"
        if gui_path.exists():
            try:
                subprocess.Popen(
                    [sys.executable, str(gui_path)],
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
            except Exception:
                pass

    def on_right_click(self, event):
        """右键点击 → 弹出菜单"""
        menu = tk.Menu(self.root, tearoff=0, bg="#2d2d2d", fg="#dddddd",
                       activebackground="#4a6a8a", activeforeground="#ffffff",
                       font=("微软雅黑", 10) if FONT_CN else ("TkDefaultFont", 10))
        menu.add_command(label="打开主窗口", command=self.open_gui)
        menu.add_separator()
        menu.add_command(label="重新加载", command=lambda: self.root.after(100, self.update_stats))
        menu.add_separator()
        menu.add_command(label="退出", command=self.on_exit)
        menu.post(event.x_root, event.y_root)

    def open_gui(self):
        """打开主 GUI 窗口"""
        self.on_click(None)

    def on_exit(self):
        """退出"""
        self._running = False
        self.root.destroy()

    def run(self):
        """启动主循环"""
        self.root.mainloop()


def main():
    print("启动桌面悬浮球...")
    ball = FloatingBall()
    ball.run()


if __name__ == "__main__":
    import subprocess
    main()
