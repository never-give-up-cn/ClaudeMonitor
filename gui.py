#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude Code 工作状态监控 — 桌面窗口版
========================================
Tkinter GUI 窗口实时显示 Claude Code 工作状态，
支持中文显示，自动检测 Arduino 串口并发送状态码。
"""

import sys
import time
import os
import threading
import logging
import subprocess
from datetime import datetime
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import ttk, font
except ImportError:
    print("错误: 需要 tkinter。请安装 python3-tk")
    sys.exit(1)

try:
    import psutil
except ImportError:
    print("错误: 需要 psutil。请运行: pip install psutil")
    sys.exit(1)

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("错误: 需要 pyserial。请运行: pip install pyserial")
    sys.exit(1)

try:
    from token_tracker import TokenTracker
    TOKEN_TRACKER_AVAILABLE = True
except ImportError:
    TOKEN_TRACKER_AVAILABLE = False

try:
    from conversation_logger import ConversationLogger
    LOGGER_AVAILABLE = True
except ImportError:
    LOGGER_AVAILABLE = False

try:
    from sound_manager import play, SOUND_DONE, SOUND_ACTION, SOUND_ERROR
    SOUND_AVAILABLE = True
except ImportError:
    SOUND_AVAILABLE = False

try:
    from log_viewer import LogViewer, ChartWindow
    VIEWER_AVAILABLE = True
except ImportError:
    VIEWER_AVAILABLE = False

try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False

try:
    from single_instance import SingleInstance
    SINGLE_OK = True
except ImportError:
    SINGLE_OK = False

try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False


# ============================================================
# 配置
# ============================================================
CONFIG = {
    "serial_port": "auto",
    "baud_rate": 115200,
    "check_interval": 0.5,
    "watch_dirs": [str(Path.home() / "Desktop")],
    "idle_timeout": 15,
    "startup_timeout": 15,
    "done_display_time": 3,
    "cpu_think_threshold": 8.0,
    "cpu_low_threshold": 1.0,
    "enable_token_tracking": True,
}

# ============================================================
# 状态定义
# ============================================================
STATUS = [
    ("IDLE",       "空闲",     "[.]"),
    ("LOADING",    "启动",     "[~]"),
    ("THINKING",   "思考",     "[*]"),
    ("READING",    "读文件",   "[R]"),
    ("WRITING",    "写代码",   "[W]"),
    ("SEARCHING",  "搜索",     "[?]"),
    ("BUILDING",   "编译",     "[B]"),
    ("COMMAND",    "命令",     "[C]"),
    ("WAITING",    "等待输入", "[_]"),
    ("PROCESSING", "处理中",   "[#]"),
    ("DONE",       "完成",     "[v]"),
    ("ERROR",      "错误",     "[x]"),
]

(IDLE, LOADING, THINKING, READING, WRITING, SEARCHING,
 BUILDING, COMMAND, WAITING, PROCESSING, DONE, ERROR) = range(12)

# 每个状态对应的颜色 (background, foreground)
STATUS_COLORS = {
    IDLE:      ("#4a4a4a", "#cccccc"),  # 灰
    LOADING:   ("#8b7300", "#fff6b0"),  # 黄
    THINKING:  ("#1a5276", "#aed6f1"),  # 蓝
    READING:   ("#0e6655", "#a3e4d7"),  # 青
    WRITING:   ("#1e6b3e", "#a9dfbf"),  # 绿
    SEARCHING: ("#6e4a1a", "#f5cba7"),  # 橙
    BUILDING:  ("#4a1a6e", "#d7bde2"),  # 紫
    COMMAND:   ("#6e3a1a", "#f0b27a"),  # 橙
    WAITING:   ("#3d3d3d", "#b0b0b0"),  # 浅灰
    PROCESSING:("#2c3e50", "#aeb6bf"),  # 蓝灰
    DONE:      ("#1e6b3e", "#a9dfbf"),  # 绿
    ERROR:     ("#7b241c", "#f1948a"),  # 红
}


# ============================================================
# 串口管理
# ============================================================
class SerialManager:
    def __init__(self, config):
        self.config = config
        self.port = None
        self.serial = None
        self._lock = threading.Lock()
        self._last_send = -1
        self.connected = False

    def find_arduino_port(self):
        ports = serial.tools.list_ports.comports()
        arduino_vids = {0x2341, 0x2A03, 0x1A86, 0x10C4, 0x239A}
        for p in ports:
            if p.vid in arduino_vids:
                return p.device
        for p in ports:
            desc = (p.description or "").lower()
            if "arduino" in desc or "ch340" in desc or "cp210" in desc:
                return p.device
        if ports:
            return ports[0].device
        return None

    def connect(self):
        port_name = self.config["serial_port"]
        if port_name == "auto":
            port_name = self.find_arduino_port()
        if not port_name:
            self.connected = False
            return False
        try:
            self.port = port_name
            self.serial = serial.Serial(
                port=port_name,
                baudrate=self.config["baud_rate"],
                timeout=0.1
            )
            time.sleep(2)
            self.connected = True
            return True
        except serial.SerialException:
            self.serial = None
            self.connected = False
            return False

    def send(self, status_code):
        if status_code == self._last_send:
            return
        self._last_send = status_code
        with self._lock:
            if self.serial and self.serial.is_open:
                try:
                    data = f"{status_code},0\n"
                    self.serial.write(data.encode())
                    self.serial.flush()
                except serial.SerialException:
                    self.connected = False
                    self.serial = None

    def try_reconnect(self):
        return self.connect()

    def close(self):
        with self._lock:
            if self.serial and self.serial.is_open:
                try:
                    self.serial.close()
                except:
                    pass
            self.serial = None


# ============================================================
# Claude Code 进程检测
# ============================================================
def find_claude_processes():
    claude_procs = []
    try:
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                name = (proc.info["name"] or "").lower()
                cmdline = " ".join(proc.info["cmdline"] or []).lower()
                is_claude = False
                if "claude" in name and "code" in name:
                    is_claude = True
                elif name == "claude.exe":
                    is_claude = True
                elif name in ("node.exe", "node") and ("claude" in cmdline or "anthropic" in cmdline):
                    is_claude = True
                elif "claude" in name and name.endswith(".exe"):
                    is_claude = True
                if is_claude:
                    claude_procs.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception:
        pass
    return claude_procs


def get_claude_subprocesses(parent_procs):
    children = []
    try:
        for pp in parent_procs:
            try:
                proc = psutil.Process(pp.info["pid"])
                kids = proc.children(recursive=True)
                children.extend(kids)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception:
        pass
    return children


# ============================================================
# 状态检测引擎
# ============================================================
class StateDetector:
    def __init__(self):
        self._cpu_prev = {}
        self._idle_since = None
        self._was_running = False
        self._done_counter = 0
        self._processes = []
        self.last_cpu = 0.0
        self.last_status = IDLE
        self.last_pid = 0
        self.last_proc_name = ""
        self.last_cmdline = ""

    def _calc_cpu(self, pid):
        try:
            now = time.time()
            p = psutil.Process(pid)
            ct = p.cpu_times()
            if pid in self._cpu_prev:
                prev_u, prev_s, prev_t = self._cpu_prev[pid]
                dt = now - prev_t
                if dt > 0:
                    cpu = ((ct.user - prev_u) + (ct.system - prev_s)) / dt * 100.0
                    self._cpu_prev[pid] = (ct.user, ct.system, now)
                    return min(cpu, 100.0)
            self._cpu_prev[pid] = (ct.user, ct.system, now)
            return 0.0
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            self._cpu_prev.pop(pid, None)
            return 0.0

    def detect(self):
        procs = find_claude_processes()
        self._processes = procs
        is_running = len(procs) > 0

        if not is_running:
            return self._handle_no_process()
        return self._handle_running(procs)

    def _handle_no_process(self):
        self._idle_since = None
        if self._was_running:
            self._was_running = False
            self._done_counter = CONFIG["done_display_time"]
            return DONE
        elif self._done_counter > 0:
            self._done_counter -= 1
            return DONE
        return IDLE

    def _handle_running(self, procs):
        self._was_running = True
        self._done_counter = 0

        main_proc = procs[0]
        pid = main_proc.info["pid"]
        self.last_pid = pid
        self.last_proc_name = main_proc.info["name"] or ""
        self.last_cmdline = " ".join(main_proc.info["cmdline"] or [""])[:80]

        try:
            p = psutil.Process(pid)
            uptime = time.time() - p.create_time()
        except:
            return ERROR

        cpu_percent = self._calc_cpu(pid)
        self.last_cpu = cpu_percent

        children = get_claude_subprocesses(procs)

        if uptime < CONFIG["startup_timeout"]:
            return LOADING

        if children:
            child_str = " ".join((c.name() or "").lower() for c in children)
            if any(t in child_str for t in ["npm", "node", "webpack", "tsc", "babel",
                                              "vite", "rollup", "esbuild", "ng", "vue"]):
                return BUILDING
            elif any(t in child_str for t in ["git", "svn", "hg"]):
                return COMMAND
            return COMMAND

        if cpu_percent > CONFIG["cpu_think_threshold"]:
            self._idle_since = None
            return THINKING

        if cpu_percent < CONFIG["cpu_low_threshold"]:
            if self._idle_since is None:
                self._idle_since = time.time()
            idle_sec = time.time() - self._idle_since
            return WAITING if idle_sec > CONFIG["idle_timeout"] else PROCESSING

        self._idle_since = None
        return PROCESSING

    def get_current_processes(self):
        return self._processes


# ============================================================
# 主窗口 (字体定义)
# ============================================================

# 检测可用字体：优先微软雅黑，回退默认
try:
    font.Font(family="微软雅黑", size=10).measure("测")
    FONT_CN = ("微软雅黑", 10)
    FONT_CN_BOLD = ("微软雅黑", 10, "bold")
    FONT_TITLE = ("微软雅黑", 11, "bold")
    FONT_ICON = ("微软雅黑", 40)
    FONT_STATUS = ("微软雅黑", 26, "bold")
    FONT_SMALL = ("微软雅黑", 9)
except:
    FONT_CN = ("TkDefaultFont", 10)
    FONT_CN_BOLD = ("TkDefaultFont", 10, "bold")
    FONT_TITLE = ("TkDefaultFont", 11, "bold")
    FONT_ICON = ("TkDefaultFont", 40)
    FONT_STATUS = ("TkDefaultFont", 26, "bold")
    FONT_SMALL = ("TkDefaultFont", 9)

FONT_EN = ("Consolas", 10)
FONT_EN_SM = ("Consolas", 9)


class ClaudeMonitorGUI:
    def __init__(self):
        # 单例检测
        if SINGLE_OK:
            self._instance = SingleInstance("gui")
            if not self._instance.acquire():
                self._instance.bring_to_front()
                sys.exit(0)
            self._instance.cleanup_on_exit()
            self._instance.start_server(on_message=self._on_ipc_message)
        else:
            self._instance = None

        self.root = tk.Tk()
        self.root.title("Claude Code 状态监控")
        self.root.overrideredirect(True)  # 自定义标题栏
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.configure(bg="#18191C")

        # 上次日志轮数（用于检测新完成的任务）
        self._last_log_turns = 0
        self._last_done_sound = 0
        self._start_time = time.time()
        self._ring_angle = 0

        # 窗口尺寸
        self.win_w, self.win_h = 640, 420
        self.root.minsize(self.win_w, self.win_h)

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - self.win_w) // 2
        y = (sh - self.win_h) // 2
        self.root.geometry(f"{self.win_w}x{self.win_h}+{x}+{y}")

        # 初始化组件
        self.detector = StateDetector()
        self.serial_mgr = SerialManager(CONFIG)
        self._build_ui()

        self.serial_connected = self.serial_mgr.connect()
        self.serial_retry = 0
        self._last_serial_code = -1
        self._running = True

        self.token_tracker = None
        if CONFIG.get("enable_token_tracking", True) and TOKEN_TRACKER_AVAILABLE:
            try:
                self.token_tracker = TokenTracker()
                self.token_tracker.poll()
            except Exception:
                pass
        self._token_poll_counter = 0

        self.conversation_logger = None
        if LOGGER_AVAILABLE:
            try:
                self.conversation_logger = ConversationLogger()
                self.conversation_logger.poll()
            except Exception:
                pass
        self._log_poll_counter = 0

        self.update_status()

    # ========== Custom Title Bar ==========

    def _make_draggable(self, widget=None):
        """让指定控件可拖动窗口"""
        if widget is None:
            widget = self.root
        data = {"x": 0, "y": 0}
        def start_drag(event):
            data["x"] = event.x_root
            data["y"] = event.y_root
        def do_drag(event):
            dx = event.x_root - data["x"]
            dy = event.y_root - data["y"]
            x = self.root.winfo_x() + dx
            y = self.root.winfo_y() + dy
            self.root.geometry(f"+{x}+{y}")
            data["x"] = event.x_root
            data["y"] = event.y_root
        widget.bind("<Button-1>", start_drag, add="+")
        widget.bind("<B1-Motion>", do_drag, add="+")

    def _title_btn(self, parent, text, cmd, hover_bg="#3B414E"):
        """统一标题栏按钮"""
        btn = tk.Label(parent, text=text, font=("Consolas", 12), fg="#A0A8B8",
                       bg="#18191C", padx=8, pady=2, cursor="hand2")
        btn.pack(side=tk.RIGHT, padx=(0, 0))
        btn.bind("<Button-1>", lambda e: cmd())
        btn.bind("<Enter>", lambda e: btn.configure(fg="#56E3F5"))
        btn.bind("<Leave>", lambda e: btn.configure(fg="#A0A8B8"))
        return btn

    def _build_ui(self):
        """构建全新界面"""
        root = self.root

        # ===== 1. Custom Title Bar =====
        title_bar = tk.Frame(root, bg="#18191C", height=34)
        title_bar.pack(fill=tk.X)
        title_bar.pack_propagate(False)

        self._title_close = self._title_btn(title_bar, "×", self.on_close, "#5C3A3A")
        self._title_max = self._title_btn(title_bar, "—", self._toggle_minimize, "#3B414E")
        self._title_min = self._title_btn(title_bar, "─", self._minimize_to_tray, "#3B414E")

        tk.Label(title_bar, text="Claude Code 监控", font=("Consolas", 12, "bold"),
                 fg="#F0F4FB", bg="#18191C", padx=14).pack(side=tk.LEFT)

        # 串口状态在标题栏右侧
        self.title_serial = tk.Label(title_bar, text="● 串口", font=("Consolas", 9),
                                     fg="#777E8C", bg="#18191C")
        self.title_serial.pack(side=tk.RIGHT)

        self._make_draggable(title_bar)

        # ===== 2. Main Container =====
        main = tk.Frame(root, bg="#18191C", padx=16, pady=8)
        main.pack(fill=tk.BOTH, expand=True)

        # ===== 3. Status Bar =====
        status_bg = "#282C34"
        status_frame = tk.Frame(main, bg=status_bg, padx=14, pady=10)
        status_frame.pack(fill=tk.X)

        # Left: animated ring canvas
        self.ring_canvas = tk.Canvas(status_frame, width=40, height=40,
                                      bg=status_bg, highlightthickness=0)
        self.ring_canvas.pack(side=tk.LEFT, padx=(0, 12))
        self._ring_arc = self.ring_canvas.create_arc(4, 4, 36, 36, start=0, extent=270,
                                                       outline="#56E3F5", width=3, style="arc")

        # Middle: status text
        status_text_frame = tk.Frame(status_frame, bg=status_bg)
        status_text_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.status_label = tk.Label(status_text_frame, text="空闲 IDLE",
                                     font=("Consolas", 18, "bold"), fg="#56E3F5",
                                     bg=status_bg, anchor=tk.W)
        self.status_label.pack(anchor=tk.W)

        self.status_sub = tk.Label(status_text_frame, text="状态码: 0 · Claude 未运行",
                                   font=("Consolas", 9), fg="#777E8C",
                                   bg=status_bg, anchor=tk.W)
        self.status_sub.pack(anchor=tk.W, pady=(2, 0))

        # Right: CPU
        cpu_frame = tk.Frame(status_frame, bg="#1E2128", padx=12, pady=6, relief="flat")
        cpu_frame.pack(side=tk.RIGHT)
        self.cpu_label = tk.Label(cpu_frame, text="CPU 0.0%", font=("Consolas", 13, "bold"),
                                  fg="#56E3F5", bg="#1E2128")
        self.cpu_label.pack()
        self.proc_label = tk.Label(cpu_frame, text="进程: --", font=("Consolas", 8),
                                   fg="#777E8C", bg="#1E2128")
        self.proc_label.pack()

        # ===== 4. Hardware Card =====
        hw_card = tk.Frame(main, bg="#282C34", padx=14, pady=10)
        hw_card.pack(fill=tk.X, pady=(10, 0))

        # Card header
        hw_header = tk.Frame(hw_card, bg="#282C34")
        hw_header.pack(fill=tk.X)
        tk.Label(hw_header, text="硬件负载", font=("Consolas", 10, "bold"),
                 fg="#A0A8B8", bg="#282C34").pack(side=tk.LEFT)
        self.mem_label = tk.Label(hw_header, text="MEM --%", font=("Consolas", 10),
                                  fg="#A0A8B8", bg="#282C34")
        self.mem_label.pack(side=tk.RIGHT)

        # CPU bar row
        hw_cpu = tk.Frame(hw_card, bg="#282C34")
        hw_cpu.pack(fill=tk.X, pady=(8, 0))
        tk.Label(hw_cpu, text="CPU", font=("Consolas", 10), fg="#A0A8B8",
                 bg="#282C34", width=4, anchor=tk.W).pack(side=tk.LEFT)
        self.cpu_bar_canvas = tk.Canvas(hw_cpu, height=6, bg="#1E2128",
                                         highlightthickness=0)
        self.cpu_bar_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))
        self.cpu_bar = self.cpu_bar_canvas.create_rectangle(0, 0, 0, 6, fill="#56E3F5", width=0)
        self.cpu_bar_width = 0

        # GPU bar row
        hw_gpu = tk.Frame(hw_card, bg="#282C34")
        hw_gpu.pack(fill=tk.X, pady=(4, 0))
        tk.Label(hw_gpu, text="GPU", font=("Consolas", 10), fg="#A0A8B8",
                 bg="#282C34", width=4, anchor=tk.W).pack(side=tk.LEFT)
        self.gpu_bar_canvas = tk.Canvas(hw_gpu, height=6, bg="#1E2128",
                                         highlightthickness=0)
        self.gpu_bar_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))
        self.gpu_bar = self.gpu_bar_canvas.create_rectangle(0, 0, 0, 6, fill="#FFC864", width=0)
        self.gpu_bar_width = 0

        # Memory bar row
        hw_mem = tk.Frame(hw_card, bg="#282C34")
        hw_mem.pack(fill=tk.X, pady=(4, 0))
        tk.Label(hw_mem, text="MEM", font=("Consolas", 10), fg="#A0A8B8",
                 bg="#282C34", width=4, anchor=tk.W).pack(side=tk.LEFT)
        self.mem_bar_canvas = tk.Canvas(hw_mem, height=6, bg="#1E2128",
                                         highlightthickness=0)
        self.mem_bar_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))
        self.mem_bar = self.mem_bar_canvas.create_rectangle(0, 0, 0, 6, fill="#4CD079", width=0)
        self.mem_bar_width = 0

        # ===== 5. Token & Model Card =====
        token_card = tk.Frame(main, bg="#1A2428", padx=14, pady=10)
        token_card.pack(fill=tk.X, pady=(10, 0))

        # Two-column layout
        token_cols = tk.Frame(token_card, bg="#1A2428")
        token_cols.pack(fill=tk.X)

        # Left: Traffic
        left_col = tk.Frame(token_cols, bg="#1A2428")
        left_col.pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Label(left_col, text="流量统计", font=("Consolas", 10, "bold"),
                 fg="#56E3F5", bg="#1A2428").pack(anchor=tk.W)

        flow_row = tk.Frame(left_col, bg="#1A2428")
        flow_row.pack(fill=tk.X, pady=(6, 0))
        self.tok_in = tk.Label(flow_row, text="IN: --", font=("Consolas", 13, "bold"),
                               fg="#56E3F5", bg="#1A2428")
        self.tok_in.pack(side=tk.LEFT, padx=(0, 16))
        self.tok_out = tk.Label(flow_row, text="OUT: --", font=("Consolas", 13, "bold"),
                                fg="#56E3F5", bg="#1A2428")
        self.tok_out.pack(side=tk.LEFT)

        self.tok_total = tk.Label(left_col, text="总量: --", font=("Consolas", 10),
                                  fg="#777E8C", bg="#1A2428")
        self.tok_total.pack(anchor=tk.W, pady=(2, 0))

        # Right: Params
        right_col = tk.Frame(token_cols, bg="#1A2428")
        right_col.pack(side=tk.RIGHT, fill=tk.X, expand=True)

        tk.Label(right_col, text="运行参数", font=("Consolas", 10, "bold"),
                 fg="#A0A8B8", bg="#1A2428").pack(anchor=tk.W)

        self.tok_model = tk.Label(right_col, text="模型: --", font=("Consolas", 10),
                                  fg="#A0A8B8", bg="#1A2428")
        self.tok_model.pack(anchor=tk.W, pady=(2, 0))
        self.tok_cost = tk.Label(right_col, text="费用: --", font=("Consolas", 11, "bold"),
                                 fg="#FFC864", bg="#1A2428")
        self.tok_cost.pack(anchor=tk.W, pady=(2, 0))
        self.tok_msgs = tk.Label(right_col, text="消息: --", font=("Consolas", 10),
                                 fg="#777E8C", bg="#1A2428")
        self.tok_msgs.pack(anchor=tk.W, pady=(2, 0))

        # ===== 6. Bottom Button Bar =====
        btn_frame = tk.Frame(main, bg="#18191C")
        btn_frame.pack(fill=tk.X, pady=(12, 0))

        # Left: serial status tag
        self.serial_tag = tk.Label(btn_frame, text="● 串口 未连接",
                                   font=("Consolas", 9), fg="#F55C5C", bg="#18191C")
        self.serial_tag.pack(side=tk.LEFT)

        # Right buttons (uniform style)
        def mk_btn(text, cmd, color="#2C313A"):
            btn = tk.Button(btn_frame, text=text, command=cmd,
                           font=("Consolas", 9), bg=color, fg="#A0A8B8",
                           relief="flat", padx=8, pady=4, cursor="hand2",
                           activebackground="#3B414E", activeforeground="#56E3F5")
            btn.pack(side=tk.RIGHT, padx=(4, 0))
            btn.bind("<Enter>", lambda e: btn.configure(bg="#3B414E", fg="#56E3F5"))
            btn.bind("<Leave>", lambda e: btn.configure(bg=color, fg="#A0A8B8"))
            return btn

        mk_btn("退出", self.on_close, "#2C313A")
        self.tray_btn = mk_btn("托盘", self.toggle_tray)
        mk_btn("趋势图", self.open_chart)
        mk_btn("Web日志", self.open_web_viewer)
        self.sound_btn = mk_btn("音效:开", self.toggle_sound)
        mk_btn("查看日志", self.open_log_viewer)
        mk_btn("置顶", self.toggle_pin)
        self._is_pinned = False

        self._is_pinned = not self._is_pinned
        self.root.attributes("-topmost", self._is_pinned)

    def toggle_pin(self):
        self._is_pinned = not self._is_pinned
        self.root.attributes("-topmost", self._is_pinned)

    def _toggle_minimize(self):

        self.root.iconify()

    def _minimize_to_tray(self):
        self.toggle_tray()

    def _update_ring(self, color="#56E3F5", spinning=False):
        try:
            self._ring_angle = (self._ring_angle + 30) % 360
            if spinning:
                self.ring_canvas.itemconfig(self._ring_arc, outline=color,
                                             start=self._ring_angle, extent=270)
            else:
                self.ring_canvas.itemconfig(self._ring_arc, outline=color, start=0, extent=359)
        except Exception:
            pass

    def _update_progress_bar(self, canvas, bar_item, pct, color="#56E3F5"):
        try:
            w = canvas.winfo_width() - 4
            fw = max(2, int(w * min(pct, 100) / 100))
            canvas.coords(bar_item, 2, 1, 2 + fw, 5)
            canvas.itemconfig(bar_item, fill=color)
        except Exception:
            pass

    def update_status(self):
        if not self._running:
            return
        old_code = self.detector.last_status
        code = self.detector.detect()
        self.detector.last_status = code
        now = time.time()
        try:
            from sound_manager import play, SOUND_DONE, SOUND_ACTION, SOUND_ERROR
        except Exception:
            pass
        should_play_done = False
        if code != old_code:
            ACTIVE = {THINKING, READING, WRITING, BUILDING, COMMAND, LOADING}
            DONE_SET = {PROCESSING, WAITING, DONE}
            if code == ERROR:
                play(SOUND_ERROR); self._log_action("错误状态")
            elif code == WAITING:
                play(SOUND_ACTION); self._log_action("等待用户操作")
            elif old_code in ACTIVE and code in DONE_SET:
                should_play_done = True
            elif code == DONE:
                should_play_done = True
        if self.conversation_logger:
            try:
                s = self.conversation_logger.get_summary()
                t = s.get("turns", 0)
                if t > self._last_log_turns:
                    if self._last_log_turns > 0:
                        should_play_done = True
                    self._last_log_turns = t
            except Exception:
                pass
        if should_play_done and now - self._start_time > 15 and now - self._last_done_sound > 8:
            self._last_done_sound = now
            try: play(SOUND_DONE)
            except: pass

        en, cn, icon = STATUS[code]
        _, fg_color = STATUS_COLORS[code]
        self.status_label.config(text=f"{cn} {en}", fg=fg_color)
        hints = {IDLE:"Claude 未运行",LOADING:"进程初始化中",THINKING:"模型推理中",
                 READING:"读取文件中",WRITING:"写入代码",SEARCHING:"搜索代码库",
                 BUILDING:"编译中",COMMAND:"执行命令",WAITING:"等待用户操作",
                 PROCESSING:"处理中",DONE:"任务刚完成",ERROR:"异常状态"}
        self.status_sub.config(text=f"状态码: {code} · {hints.get(code, '')}")
        is_active = code in {THINKING,READING,WRITING,BUILDING,COMMAND,LOADING,PROCESSING}
        self._update_ring(fg_color, spinning=is_active)

        cpu = self.detector.last_cpu
        pid = self.detector.last_pid
        pname = self.detector.last_proc_name
        if self.detector.get_current_processes():
            cc = "#FF4444" if cpu > 80 else "#56E3F5"
            self.cpu_label.config(text=f"CPU {cpu:.1f}%", fg=cc)
            self.proc_label.config(text=f"{pname} ({pid})")
            self._update_progress_bar(self.cpu_bar_canvas, self.cpu_bar, cpu, cc)
        else:
            self.cpu_label.config(text="CPU --", fg="#777E8C")
            self.proc_label.config(text="进程: --")
        try:
            mem = psutil.virtual_memory().percent
            mc = "#FF4444" if mem > 80 else "#4CD079"
            self.mem_label.config(text=f"MEM {mem:.0f}%", fg=mc)
            self._update_progress_bar(self.mem_bar_canvas, self.mem_bar, mem, mc)
        except Exception:
            pass

        if self.token_tracker:
            self._token_poll_counter += 1
            if self._token_poll_counter >= 4:
                self.token_tracker.poll()
                self._token_poll_counter = 0
            t = self.token_tracker.get_stats()
            if t["total"] > 0:
                inp = f"{t['input']//1000}K" if t['input'] >= 1000 else str(t['input'])
                out = f"{t['output']//1000}K" if t['output'] >= 1000 else str(t['output'])
                total = f"{t['total']//1000}K" if t['total'] >= 1000 else str(t['total'])
                self.tok_in.config(text=f"IN: {inp}")
                self.tok_out.config(text=f"OUT: {out}")
                self.tok_total.config(text=f"总量: {total}")
                self.tok_model.config(text=f"模型: {t['model'][:28]}")
                self.tok_cost.config(text=f"费用: ${t['cost']:.4f}")
                self.tok_msgs.config(text=f"消息: {t['messages']}  |  耗时: {t['elapsed_hours']:.1f}h")
            else:
                self.tok_in.config(text="IN: --")
                self.tok_out.config(text="OUT: --")
                self.tok_total.config(text="总量: --")

        port_str = self.serial_mgr.port or ""
        if self.serial_connected:
            self.title_serial.config(text=f"● {port_str}", fg="#4CD079")
            self.serial_tag.config(text=f"● 串口 {port_str}", fg="#4CD079")
        else:
            self.title_serial.config(text="● 串口 断开", fg="#F55C5C")
            self.serial_tag.config(text="● 串口 未连接", fg="#F55C5C")

        if code != self._last_serial_code and self.serial_connected:
            self.serial_mgr.send(code)
            self._last_serial_code = code
        if not self.serial_connected:
            self.serial_retry += 1
            if self.serial_retry >= 60:
                self.serial_connected = self.serial_mgr.try_reconnect()
                self.serial_retry = 0

        if self.conversation_logger:
            self._log_poll_counter += 1
            if self._log_poll_counter >= 10:
                self.conversation_logger.poll()
                self._log_poll_counter = 0

        self.root.after(int(CONFIG["check_interval"] * 1000), self.update_status)

    def open_log_viewer(self):
        """打开对话日志查看器（单例）"""
        if hasattr(self, '_log_win') and self._log_win:
            try:
                if self._log_win.winfo_exists():
                    self._log_win.lift()
                    self._log_win.focus_force()
                    return
            except Exception:
                self._log_win = None
        try:
            from log_viewer import LogViewer
            lv = LogViewer(parent=self.root, logger=self.conversation_logger)
            self._log_win = lv.win
        except Exception as e:
            import tkinter.messagebox as mb
            mb.showerror("错误", f"无法打开日志查看器:\n{e}")

    def open_chart(self):
        """打开 Token 趋势图（单例）"""
        if hasattr(self, '_chart_win') and self._chart_win:
            try:
                if self._chart_win.winfo_exists():
                    self._chart_win.lift()
                    self._chart_win.focus_force()
                    return
            except Exception:
                self._chart_win = None
        if not VIEWER_AVAILABLE:
            import tkinter.messagebox as mb
            mb.showinfo("提示", "请先打开日志查看器")
            return
        try:
            cw = ChartWindow(self.root, self.conversation_logger)
            self._chart_win = cw.win
        except Exception as e:
            import tkinter.messagebox as mb
            mb.showerror("错误", f"无法打开趋势图:\n{e}")

    def open_web_viewer(self):
        """启动 Web 版日志查看器"""
        try:
            from web_viewer import start_web_viewer
            start_web_viewer(self.conversation_logger)
        except ImportError:
            import tkinter.messagebox as mb
            mb.showinfo("提示", "Web 查看器未安装（web_viewer.py）")
        except Exception as e:
            import tkinter.messagebox as mb
            mb.showerror("错误", f"无法启动 Web 查看器:\n{e}")

    def toggle_sound(self):
        """切换音效开关"""
        try:
            from sound_manager import ENABLED as sound_enabled
            from sound_manager import play, SOUND_NOTIFY
            new_state = not sound_enabled
            import sound_manager
            sound_manager.ENABLED = new_state
            self.sound_btn.config(text=f"音效:{'开' if new_state else '关'}",
                                  bg="#5a5a3a" if new_state else "#3a3a3a")
            if new_state:
                play(SOUND_NOTIFY)
            self._log_action(f"音效 {'开启' if new_state else '关闭'}")
        except Exception:
            pass

    def toggle_tray(self):
        """最小化到系统托盘"""
        if not HAS_TRAY:
            import tkinter.messagebox as mb
            mb.showinfo("提示", "系统托盘需要 pystray 库:\npip install pystray Pillow")
            return

        try:
            from tray_manager import setup_tray, remove_tray

            if hasattr(self, '_tray_active') and self._tray_active:
                # 恢复窗口
                self.root.deiconify()
                self.root.lift()
                remove_tray()
                self._tray_active = False
                self.tray_btn.config(text="托盘", bg="#3a3a5a")
            else:
                # 最小化到托盘
                def on_show():
                    self.root.deiconify()
                    self.root.lift()
                    self._tray_active = False
                    self.tray_btn.config(text="托盘", bg="#3a3a5a")
                    remove_tray()

                def on_quit():
                    remove_tray()
                    self.on_close()

                ok = setup_tray(self, on_show=on_show, on_quit=on_quit)
                if ok:
                    self.root.withdraw()
                    self._tray_active = True
                    self.tray_btn.config(text="窗口", bg="#2a5a2a")
        except Exception as e:
            import tkinter.messagebox as mb
            mb.showerror("错误", f"托盘设置失败:\n{e}")

    def _on_ipc_message(self, msg):
        """收到 IPC 消息：显示窗口到前台"""
        if msg == "show":
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()

    def _log_action(self, action):
        """记录用户操作到对话日志"""
        if not self.conversation_logger:
            return
        try:
            import json
            from datetime import datetime
            log_file = self.conversation_logger.log_file
            if not log_file:
                return
            # 写入一条操作记录（id=-1 标记操作用，后续忽略即可）
            record = {
                "id": -(int(time.time()) % 1000000),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "user_input": f"[操作] {action}",
                "assistant_output": "",
                "assistant_thinking": "",
                "model": "",
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "cost": 0,
                "session_id": "",
            }
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def on_close(self):
        self._running = False
        try:
            from tray_manager import remove_tray
            remove_tray()
        except Exception:
            pass
        self.serial_mgr.close()
        if self.token_tracker:
            self.token_tracker.stop()
        if self.conversation_logger:
            self.conversation_logger.stop()
        if self._instance:
            self._instance.stop()
        try:
            self._log_action("退出监控")
        except Exception:
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


# ============================================================
# 启动
# ============================================================
def main():
    print("=" * 45)
    print("  Claude Code 工作状态监控 — 桌面窗口版")
    print(f"  启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 45)
    print("  状态码说明:")
    for i, (en, cn, icon) in enumerate(STATUS):
        print(f"    [{i:2d}] {en:10s} {cn}")
    print("=" * 45)
    print()

    gui = ClaudeMonitorGUI()
    gui.run()


if __name__ == "__main__":
    main()
