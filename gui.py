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
        self.root.overrideredirect(False)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # 窗口尺寸
        self.win_w, self.win_h = 480, 440
        self.root.minsize(self.win_w, self.win_h)

        # 居中显示
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - self.win_w) // 2
        y = (sh - self.win_h) // 2
        self.root.geometry(f"{self.win_w}x{self.win_h}+{x}+{y}")

        self._make_draggable()

        # 初始化组件
        self.detector = StateDetector()
        self.serial_mgr = SerialManager(CONFIG)
        self._build_ui()

        # 串口连接
        self.serial_connected = self.serial_mgr.connect()
        self.serial_retry = 0

        # 状态追踪
        self._last_serial_code = -1
        self._running = True

        # Token 追踪
        self.token_tracker = None
        if CONFIG.get("enable_token_tracking", True) and TOKEN_TRACKER_AVAILABLE:
            try:
                self.token_tracker = TokenTracker()
                self.token_tracker.poll()
            except Exception:
                pass
        self._token_poll_counter = 0

        # 对话日志
        self.conversation_logger = None
        if LOGGER_AVAILABLE:
            try:
                self.conversation_logger = ConversationLogger()
                self.conversation_logger.poll()
            except Exception:
                pass
        self._log_poll_counter = 0

        # 定时更新
        self.update_status()

    def _make_draggable(self):
        """让窗口可拖动"""
        self._drag_data = {"x": 0, "y": 0}

        def start_drag(event):
            self._drag_data["x"] = event.x
            self._drag_data["y"] = event.y

        def do_drag(event):
            dx = event.x - self._drag_data["x"]
            dy = event.y - self._drag_data["y"]
            x = self.root.winfo_x() + dx
            y = self.root.winfo_y() + dy
            self.root.geometry(f"+{x}+{y}")

        self.root.bind("<Button-1>", start_drag)
        self.root.bind("<B1-Motion>", do_drag)

    def _build_ui(self):
        """构建界面"""
        self.root.configure(bg="#1e1e1e")

        # 主容器
        main = tk.Frame(self.root, bg="#1e1e1e", padx=24, pady=16)
        main.pack(fill=tk.BOTH, expand=True)

        # 标题栏
        title_frame = tk.Frame(main, bg="#1e1e1e")
        title_frame.pack(fill=tk.X, pady=(0, 8))

        tk.Label(title_frame, text="Claude Code 状态监控",
                 font=FONT_TITLE, fg="#ffffff", bg="#1e1e1e").pack(side=tk.LEFT)

        self.serial_indicator = tk.Canvas(title_frame, width=12, height=12,
                                           bg="#1e1e1e", highlightthickness=0)
        self.serial_indicator.pack(side=tk.RIGHT, padx=(5, 0))
        self._serial_dot = self.serial_indicator.create_oval(1, 1, 11, 11,
                                                              fill="#555555", outline="")

        tk.Label(title_frame, text="串口",
                 font=FONT_SMALL, fg="#888888", bg="#1e1e1e").pack(side=tk.RIGHT)

        # 分割线
        sep = tk.Frame(main, height=1, bg="#333333")
        sep.pack(fill=tk.X, pady=(0, 12))

        # 状态主显示区 (垂直居中)
        status_area = tk.Frame(main, bg="#1e1e1e")
        status_area.pack(expand=True, fill=tk.BOTH)

        self.status_icon_label = tk.Label(status_area, text="●",
                                          font=FONT_ICON, bg="#1e1e1e")
        self.status_icon_label.pack(pady=(12, 2))

        self.status_cn_label = tk.Label(status_area, text="空闲",
                                        font=FONT_STATUS, bg="#1e1e1e")
        self.status_cn_label.pack()

        self.status_en_label = tk.Label(status_area, text="IDLE",
                                        font=FONT_EN, bg="#1e1e1e")
        self.status_en_label.pack(pady=(4, 6))

        self.status_code_label = tk.Label(status_area, text="状态码: 0",
                                          font=FONT_EN_SM, bg="#1e1e1e", fg="#888888")
        self.status_code_label.pack()

        # 详情栏
        detail_frame = tk.Frame(main, bg="#252525", padx=14, pady=10)
        detail_frame.pack(fill=tk.X, pady=(10, 0))

        self.cpu_label = tk.Label(detail_frame, text="CPU: --",
                                  font=FONT_EN, bg="#252525", fg="#aaaaaa")
        self.cpu_label.pack(anchor=tk.W)

        self.proc_label = tk.Label(detail_frame, text="进程: --",
                                   font=FONT_EN_SM, bg="#252525", fg="#777777")
        self.proc_label.pack(anchor=tk.W, pady=(2, 0))

        # Token 统计栏
        token_frame = tk.Frame(main, bg="#1a2a1a", padx=14, pady=8)
        token_frame.pack(fill=tk.X, pady=(6, 0))

        self.token_label = tk.Label(token_frame, text="Token: 等待数据...",
                                    font=FONT_EN_SM, bg="#1a2a1a", fg="#88cc88")
        self.token_label.pack(anchor=tk.W)

        self.token_cost_label = tk.Label(token_frame, text="",
                                         font=FONT_EN_SM, bg="#1a2a1a", fg="#66aa66")
        self.token_cost_label.pack(anchor=tk.W, pady=(1, 0))

        # 底部按钮
        btn_frame = tk.Frame(main, bg="#1e1e1e")
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        self.status_bar = tk.Label(btn_frame, text="就绪",
                                   font=FONT_SMALL, fg="#666666", bg="#1e1e1e")
        self.status_bar.pack(side=tk.LEFT)

        # 右侧按钮组（从右到左排列）
        self.quit_btn = tk.Button(btn_frame, text="退出", command=self.on_close,
                                  font=FONT_SMALL, bg="#5c1a1a", fg="#cccccc",
                                  relief=tk.FLAT, padx=14, pady=2, cursor="hand2")
        self.quit_btn.pack(side=tk.RIGHT, padx=(4, 0))

        self.tray_btn = tk.Button(btn_frame, text="托盘", command=self.toggle_tray,
                                  font=FONT_SMALL, bg="#3a3a5a", fg="#cccccc",
                                  relief=tk.FLAT, padx=10, pady=2, cursor="hand2")
        self.tray_btn.pack(side=tk.RIGHT, padx=(4, 0))

        self.chart_btn = tk.Button(btn_frame, text="趋势图", command=self.open_chart,
                                   font=FONT_SMALL, bg="#5a3a5a", fg="#cccccc",
                                   relief=tk.FLAT, padx=10, pady=2, cursor="hand2")
        self.chart_btn.pack(side=tk.RIGHT, padx=(4, 0))

        self.web_btn = tk.Button(btn_frame, text="Web 日志", command=self.open_web_viewer,
                                 font=FONT_SMALL, bg="#3a5a3a", fg="#cccccc",
                                 relief=tk.FLAT, padx=10, pady=2, cursor="hand2")
        self.web_btn.pack(side=tk.RIGHT, padx=(4, 0))

        self.sound_btn = tk.Button(btn_frame, text="音效:开", command=self.toggle_sound,
                                   font=FONT_SMALL, bg="#5a5a3a", fg="#cccccc",
                                   relief=tk.FLAT, padx=10, pady=2, cursor="hand2")
        self.sound_btn.pack(side=tk.RIGHT, padx=(4, 0))

        self.log_btn = tk.Button(btn_frame, text="查看日志", command=self.open_log_viewer,
                                 font=FONT_SMALL, bg="#2a5a5a", fg="#cccccc",
                                 relief=tk.FLAT, padx=14, pady=2, cursor="hand2")
        self.log_btn.pack(side=tk.RIGHT, padx=(4, 0))

        self.pin_btn = tk.Button(btn_frame, text="置顶", command=self.toggle_pin,
                                 font=FONT_SMALL, bg="#333333", fg="#cccccc",
                                 relief=tk.FLAT, padx=14, pady=2, cursor="hand2")
        self.pin_btn.pack(side=tk.RIGHT, padx=(4, 0))
        self.quit_btn.pack(side=tk.RIGHT, padx=(4, 0))

        self._is_pinned = False

    def toggle_pin(self):
        self._is_pinned = not self._is_pinned
        self.root.attributes("-topmost", self._is_pinned)
        self.pin_btn.config(text="取消置顶" if self._is_pinned else "置顶",
                            bg="#3a5c3a" if self._is_pinned else "#333333")

    def update_status(self):
        """定时更新状态显示"""
        if not self._running:
            return

        # 检测状态
        old_code = self.detector.last_status
        code = self.detector.detect()
        self.detector.last_status = code

        # 状态变更时播放提示音
        if code != old_code:
            if code == DONE:
                try:
                    from sound_manager import play, SOUND_DONE
                    play(SOUND_DONE)
                except Exception:
                    pass
                self._log_action("任务完成")
            elif code == WAITING:
                try:
                    from sound_manager import play, SOUND_ACTION
                    play(SOUND_ACTION)
                except Exception:
                    pass
                self._log_action("等待用户操作")
            elif code == ERROR:
                try:
                    from sound_manager import play, SOUND_ERROR
                    play(SOUND_ERROR)
                except Exception:
                    pass
                self._log_action("错误状态")

        en, cn, icon = STATUS[code]
        bg_color, fg_color = STATUS_COLORS[code]

        # 更新主显示
        display_icon = "●"
        self.status_icon_label.config(text=display_icon, fg=fg_color)
        self.status_cn_label.config(text=cn, fg=fg_color)
        self.status_en_label.config(text=en, fg=fg_color)
        self.status_code_label.config(text=f"状态码: {code}", fg=fg_color)

        # 窗口背景微调
        self.root.configure(bg=bg_color)

        # 更新详情
        cpu = self.detector.last_cpu
        pid = self.detector.last_pid
        pname = self.detector.last_proc_name

        if self.detector.get_current_processes():
            self.cpu_label.config(text=f"CPU: {cpu:.1f}%")
            self.proc_label.config(text=f"进程: {pname} (PID: {pid})")
        else:
            self.cpu_label.config(text="CPU: --")
            self.proc_label.config(text="进程: --")

        # 更新 Token 统计
        if self.token_tracker:
            self._token_poll_counter += 1
            if self._token_poll_counter >= 4:  # ~2秒刷新一次
                self.token_tracker.poll()
                self._token_poll_counter = 0

            tstats = self.token_tracker.get_stats()
            if tstats["total"] > 0:
                short = self.token_tracker.get_short_summary()
                self.token_label.config(text=short)
                cost_str = f"模型:{tstats['model'][:20]}  消息:{tstats['messages']}  耗时:{tstats['elapsed_hours']:.1f}h"
                self.token_cost_label.config(text=cost_str)
            else:
                self.token_label.config(text="Token: 等待数据...")
                self.token_cost_label.config(text="Claude 运行后自动统计")

        # 更新对话日志（每 5 秒轮询一次）
        if self.conversation_logger:
            self._log_poll_counter += 1
            if self._log_poll_counter >= 10:
                self.conversation_logger.poll()
                self._log_poll_counter = 0

        # 更新串口指示器
        if self.serial_connected:
            self.serial_indicator.itemconfig(self._serial_dot, fill="#4ade80")
            self.status_bar.config(text=f"串口: {self.serial_mgr.port or '已连接'}", fg="#4ade80")
        else:
            self.serial_indicator.itemconfig(self._serial_dot, fill="#ff6b6b")
            self.status_bar.config(text="串口: 未连接", fg="#ff6b6b")

        # 发送到 Arduino
        if code != self._last_serial_code and self.serial_connected:
            self.serial_mgr.send(code)
            self._last_serial_code = code

        # 串口重连
        if not self.serial_connected:
            self.serial_retry += 1
            if self.serial_retry >= 60:  # 每 30 秒重试
                self.serial_connected = self.serial_mgr.try_reconnect()
                self.serial_retry = 0

        # 继续更新
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
