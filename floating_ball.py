#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
桌面悬浮球 v3
=============
双模式悬浮球：
  Style 1 - 圆形简约，CPU/内存/GPU/网速/磁盘
  Style 2 - 数据面板，Token实时 + CPU/内存/GPU/网速/磁盘
支持设置面板、自定义音效、开机自启。
"""

import sys, os, json, subprocess, time, threading
from pathlib import Path
from datetime import datetime

try:
    import tkinter as tk
    from tkinter import ttk, font, filedialog, messagebox
except ImportError:
    print("需要 tkinter"); sys.exit(1)
try:
    import psutil
except ImportError:
    print("需要 psutil"); sys.exit(1)
try:
    from system_stats import SystemStats
except ImportError:
    print("需要 system_stats.py"); sys.exit(1)
try:
    from single_instance import SingleInstance
    SINGLE_OK = True
except ImportError:
    SINGLE_OK = False
try:
    from token_tracker import TokenTracker
    TOKEN_OK = True
except ImportError:
    TOKEN_OK = False
try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False

# ===== 路径 =====
SCRIPT_DIR = Path(__file__).parent
SETTINGS_FILE = SCRIPT_DIR / "ball_settings.json"

DEFAULT_SETTINGS = {
    "style": 1,
    "font_size_cpu": 13,
    "font_size_mem": 9,
    "font_size_gpu": 9,
    "font_size_net": 7,
    "font_size_disk": 7,
    "sound_done_file": "",
    "sound_action_file": "",
    "sound_error_file": "",
    "sound_enabled": True,
    "auto_start": False,
    "snap_distance": 40,
}

SNAP_DIST = 40
SIZE_1 = 140   # Style 1 尺寸
SIZE_2 = 175   # Style 2 尺寸
TAB_SIZE = 16
UPDATE_MS = 1500


def _load_color(pct):
    if pct < 50: return "#4ade80"
    elif pct < 80: return "#fbbf24"
    return "#ef4444"


def get_settings():
    try:
        if SETTINGS_FILE.exists():
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            merged = DEFAULT_SETTINGS.copy()
            merged.update(data)
            return merged
    except Exception:
        pass
    return DEFAULT_SETTINGS.copy()


def save_settings(settings):
    try:
        SETTINGS_FILE.write_text(
            json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def play_sound(sound_type="done"):
    if not HAS_WINSOUND:
        return
    s = get_settings()
    if not s.get("sound_enabled", True):
        return
    wav_key = f"sound_{sound_type}_file"
    wav = s.get(wav_key, "")
    if wav and os.path.isfile(wav):
        try:
            winsound.PlaySound(wav, winsound.SND_FILENAME | winsound.SND_ASYNC)
            return
        except Exception:
            pass
    try:
        if sound_type == "done":
            threading.Thread(target=lambda: (
                winsound.Beep(880, 200), time.sleep(0.15), winsound.Beep(1320, 300)
            ), daemon=True).start()
        elif sound_type == "action":
            threading.Thread(target=lambda: (
                winsound.Beep(660, 100), time.sleep(0.15), winsound.Beep(660, 100)
            ), daemon=True).start()
        elif sound_type == "error":
            winsound.Beep(330, 400)
        elif sound_type == "notify":
            winsound.Beep(880, 80)
    except Exception:
        pass


def toggle_auto_start(enable=True):
    try:
        startup = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        startup.mkdir(parents=True, exist_ok=True)
        vbs_dest = startup / "ClaudeMonitor_Ball.vbs"
        if not enable:
            if vbs_dest.exists(): vbs_dest.unlink()
            return True
        vbs_src = SCRIPT_DIR / "start_ball.vbs"
        if not vbs_src.exists(): return False
        vbs_dest.write_text(vbs_src.read_text(encoding="utf-8"), encoding="utf-8")
        return vbs_dest.exists()
    except Exception:
        return False


# ============================================================
# 设置面板
# ============================================================
class SettingsDialog:
    def __init__(self, parent, callback=None):
        self.parent = parent
        self.callback = callback
        self.settings = get_settings()
        self.win = tk.Toplevel(parent)
        self.win.title("悬浮球设置")
        self.win.geometry("520x620")
        self.win.resizable(False, False)
        self.win.configure(bg="#1e1e1e")
        self.win.transient(parent)
        self.win.grab_set()
        self._build_ui()
        self.win.wait_window()

    def _draw_preview(self, canvas, style):
        """在 Canvas 上绘制样式预览图"""
        canvas.delete("all")
        cw, ch = 160, 120
        cx, cy = cw // 2, 45
        s = self.settings

        # 外框
        canvas.create_rectangle(2, 2, cw - 2, ch - 2, outline="#3a3a5e", fill="#16213e", width=1)

        if style == 1:
            # Style 1: 圆形简约
            r = 30
            canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#3a3a5e", fill="#1a1a2e", width=1)
            canvas.create_text(cx, cy - 10, text="CPU:45%", fill="#4ade80",
                               font=("Consolas", 7, "bold"), anchor=tk.CENTER)
            canvas.create_text(cx, cy + 3, text="MEM:57%", fill="#60a5fa",
                               font=("Consolas", 6), anchor=tk.CENTER)
            canvas.create_text(cx, cy + 13, text="GPU:12%", fill="#f472b6",
                               font=("Consolas", 6), anchor=tk.CENTER)
            canvas.create_text(8, 6, text="▲1.2K", fill="#fbbf24",
                               font=("Consolas", 6), anchor=tk.NW)
            canvas.create_text(8, 16, text="▼3.4K", fill="#34d399",
                               font=("Consolas", 6), anchor=tk.NW)
            canvas.create_text(cw - 8, 6, text="C:86%", fill="#a78bfa",
                               font=("Consolas", 6), anchor=tk.NE)
            # 标签
            canvas.create_text(cx, ch - 14, text="简约圆形 · 系统状态", fill="#888888",
                               font=("微软雅黑", 8), anchor=tk.CENTER)
        else:
            # Style 2: Token 数据面板
            canvas.create_text(cx, 12, text="IN:1.2K  OUT:0.5K", fill="#88cc88",
                               font=("Consolas", 7, "bold"), anchor=tk.CENTER)
            canvas.create_text(cx, 26, text="COST:$0.0215", fill="#fbbf24",
                               font=("Consolas", 6), anchor=tk.CENTER)
            # 左右分栏
            canvas.create_text(cx - 35, 44, text="CPU:45%", fill="#4ade80",
                               font=("Consolas", 7), anchor=tk.W)
            canvas.create_text(cx + 5, 44, text="MEM:57%", fill="#60a5fa",
                               font=("Consolas", 7), anchor=tk.W)
            canvas.create_text(cx - 35, 60, text="▲1.2K", fill="#fbbf24",
                               font=("Consolas", 6), anchor=tk.W)
            canvas.create_text(cx + 5, 60, text="▼3.4K", fill="#34d399",
                               font=("Consolas", 6), anchor=tk.W)
            canvas.create_text(cx - 35, 76, text="GPU:12%", fill="#f472b6",
                               font=("Consolas", 6), anchor=tk.W)
            canvas.create_text(cx + 5, 76, text="C:86%", fill="#a78bfa",
                               font=("Consolas", 6), anchor=tk.W)
            canvas.create_text(cx, 96, text="C:86% / E:28%", fill="#a78bfa",
                               font=("Consolas", 6), anchor=tk.CENTER)
            canvas.create_text(cx, ch - 12, text="数据面板 · Token + 系统状态", fill="#888888",
                               font=("微软雅黑", 8), anchor=tk.CENTER)

    def _build_ui(self):
        s = self.settings
        main = tk.Frame(self.win, bg="#1e1e1e", padx=18, pady=14)
        main.pack(fill=tk.BOTH, expand=True)

        # ---- 样式选择 ----
        tk.Label(main, text="悬浮球样式", font=("微软雅黑", 13, "bold"),
                 fg="#88cc88", bg="#1e1e1e").pack(anchor=tk.W, pady=(0, 6))

        style_frame = tk.Frame(main, bg="#1e1e1e")
        style_frame.pack(fill=tk.X)

        self.style_var = tk.IntVar(value=s.get("style", 1))

        for sid in [1, 2]:
            card = tk.Frame(style_frame, bg="#252525", padx=10, pady=8,
                            highlightbackground="#3a3a5e", highlightthickness=1,
                            cursor="hand2")
            card.pack(side=tk.LEFT, padx=8, fill=tk.BOTH, expand=True)

            # 标题
            lbl = f"样式 {sid}"
            tk.Label(card, text=lbl, font=("微软雅黑", 10, "bold"),
                     fg="#ffffff", bg="#252525").pack(anchor=tk.W)

            # 预览 Canvas
            prev = tk.Canvas(card, width=160, height=120, bg="#1a1a2e",
                             highlightthickness=0)
            prev.pack(pady=(4, 6))
            self._draw_preview(prev, sid)

            # Radio
            rb = tk.Radiobutton(card, text="  选择" if sid == 1 else "  选择",
                                variable=self.style_var, value=sid,
                                font=("微软雅黑", 10), fg="#dddddd", bg="#252525",
                                selectcolor="#2d2d2d", activebackground="#252525",
                                activeforeground="#ffffff",
                                command=lambda: self._update_preview())
            rb.pack(anchor=tk.CENTER)

        # ---- 字体设置 ----
        sep = ttk.Separator(main, orient="horizontal")
        sep.pack(fill=tk.X, pady=10)

        tk.Label(main, text="字体大小", font=("微软雅黑", 11, "bold"),
                 fg="#88aacc", bg="#1e1e1e").pack(anchor=tk.W, pady=(0, 4))

        font_grid = tk.Frame(main, bg="#1e1e1e")
        font_grid.pack(fill=tk.X)

        self._font_vars = {}
        fonts = [("CPU", "font_size_cpu", 8, 24), ("MEM", "font_size_mem", 6, 20),
                 ("GPU", "font_size_gpu", 6, 20), ("网速", "font_size_net", 5, 16),
                 ("磁盘", "font_size_disk", 5, 16)]

        for i, (label, key, mn, mx) in enumerate(fonts):
            r, c = divmod(i, 5)
            if c == 0:
                row = tk.Frame(font_grid, bg="#1e1e1e")
                row.pack(fill=tk.X, pady=1)
            tk.Label(row, text=label, font=("微软雅黑", 9), fg="#dddddd", bg="#1e1e1e",
                     width=4, anchor=tk.W).pack(side=tk.LEFT, padx=(2, 0))
            var = tk.IntVar(value=s.get(key, DEFAULT_SETTINGS.get(key, 9)))
            self._font_vars[key] = var
            tk.Spinbox(row, from_=mn, to=mx, textvariable=var, width=4,
                       font=("Consolas", 8), justify=tk.CENTER,
                       bg="#3a3a3a", fg="#ffffff", relief=tk.FLAT,
                       buttonbackground="#555555").pack(side=tk.LEFT, padx=(2, 6))

        # ---- 音效 ----
        sep2 = ttk.Separator(main, orient="horizontal")
        sep2.pack(fill=tk.X, pady=10)

        tk.Label(main, text="自定义音效 (WAV)", font=("微软雅黑", 11, "bold"),
                 fg="#88aacc", bg="#1e1e1e").pack(anchor=tk.W, pady=(0, 4))

        self._sound_vars = {}
        for label, key in [("完成音", "sound_done_file"),
                            ("操作音", "sound_action_file"),
                            ("错误音", "sound_error_file")]:
            frow = tk.Frame(main, bg="#1e1e1e")
            frow.pack(fill=tk.X, pady=1)
            tk.Label(frow, text=label, font=("微软雅黑", 9), fg="#dddddd",
                     bg="#1e1e1e", width=5, anchor=tk.W).pack(side=tk.LEFT)
            var = tk.StringVar(value=s.get(key, ""))
            self._sound_vars[key] = var
            tk.Entry(frow, textvariable=var, font=("Consolas", 8),
                     bg="#3a3a3a", fg="#cccccc", relief=tk.FLAT).pack(
                         side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 4))
            tk.Button(frow, text="浏览",
                      command=lambda k=key, v=var: self._browse(k, v),
                      font=("微软雅黑", 8), bg="#3a3a5a", fg="#cccccc",
                      relief=tk.FLAT, padx=6, pady=1, cursor="hand2").pack(side=tk.RIGHT, padx=(0, 2))
            tk.Button(frow, text="试听",
                      command=lambda k=key.replace("sound_","").replace("_file",""): play_sound(k),
                      font=("微软雅黑", 8), bg="#5a3a3a", fg="#cccccc",
                      relief=tk.FLAT, padx=6, pady=1, cursor="hand2").pack(side=tk.RIGHT, padx=(0, 2))

        # ---- 开关 ----
        sep3 = ttk.Separator(main, orient="horizontal")
        sep3.pack(fill=tk.X, pady=10)

        self._sound_en = tk.BooleanVar(value=s.get("sound_enabled", True))
        tk.Checkbutton(main, text="启用提示音", variable=self._sound_en,
                       font=("微软雅黑", 10), fg="#dddddd", bg="#1e1e1e",
                       selectcolor="#2d2d2d", activebackground="#1e1e1e",
                       activeforeground="#ffffff").pack(anchor=tk.W, pady=2)

        self._auto_var = tk.BooleanVar(value=s.get("auto_start", False))
        tk.Checkbutton(main, text="开机自启（重启后生效）", variable=self._auto_var,
                       font=("微软雅黑", 10), fg="#dddddd", bg="#1e1e1e",
                       selectcolor="#2d2d2d", activebackground="#1e1e1e",
                       activeforeground="#ffffff").pack(anchor=tk.W, pady=2)

        # ---- 按钮 ----
        btnf = tk.Frame(self.win, bg="#1e1e1e", pady=10)
        btnf.pack(fill=tk.X)
        tk.Button(btnf, text="保存", command=self._save,
                  font=("微软雅黑", 10), bg="#2a5c2a", fg="#ffffff",
                  relief=tk.FLAT, padx=24, pady=4, cursor="hand2").pack(
                      side=tk.RIGHT, padx=(8, 20))
        tk.Button(btnf, text="取消", command=self.win.destroy,
                  font=("微软雅黑", 10), bg="#5a1a1a", fg="#cccccc",
                  relief=tk.FLAT, padx=24, pady=4, cursor="hand2").pack(side=tk.RIGHT)

        self._preview_canvases = []
        for w in style_frame.winfo_children():
            if isinstance(w, tk.Frame):
                for c in w.winfo_children():
                    if isinstance(c, tk.Canvas):
                        self._preview_canvases.append(c)

    def _update_preview(self):
        for c in self._preview_canvases:
            parent = c.master.master if c.master else None
            # 更新所有预览
            pass

    def _browse(self, key, var):
        p = filedialog.askopenfilename(title="选择 WAV 音效", filetypes=[("WAV 音频", "*.wav"), ("所有文件", "*.*")])
        if p:
            var.set(p)

    def _save(self):
        s = get_settings()
        s["style"] = self.style_var.get()
        for k, v in self._font_vars.items():
            s[k] = v.get()
        for k, v in self._sound_vars.items():
            s[k] = v.get().strip()
        s["sound_enabled"] = self._sound_en.get()
        s["auto_start"] = self._auto_var.get()
        save_settings(s)
        try:
            toggle_auto_start(s["auto_start"])
        except Exception:
            pass
        self.win.destroy()
        if self.callback:
            self.callback()


# ============================================================
# 悬浮球
# ============================================================
class FloatingBall:
    def __init__(self):
        if SINGLE_OK:
            self._inst = SingleInstance("floating_ball")
            if not self._inst.acquire():
                self._inst.bring_to_front()
                sys.exit(0)
            self._inst.cleanup_on_exit()
            self._inst.start_server(on_message=self._on_ipc)
        else:
            self._inst = None

        self.settings = get_settings()
        self.stats = SystemStats()
        self.token_tracker = TokenTracker() if TOKEN_OK else None
        self._running = True
        self._drag_start = None
        self._is_dragging = False
        self._snapped = False
        self._snap_edge = ""
        self._hidden_mode = False
        self._leave_timer = None
        self._tok_data = ""

        self.root = tk.Tk()
        self.root.title("系统监控")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", "#000000")

        self.sw = self.root.winfo_screenwidth()
        self.sh = self.root.winfo_screenheight()
        self.bs = self._ball_size()

        self.canvas = tk.Canvas(
            self.root, width=self.bs, height=self.bs,
            bg="#000000", highlightthickness=0, cursor="hand2")
        self.canvas.pack()

        self._draw_ball()
        self._bind_events()
        self._menu = self._build_menu()  # 预构建右键菜单
        # 后台线程刷新数据，不阻塞 UI
        self._latest_data = {}
        self._latest_tok = {}
        self._stats_thread_running = True
        self._stats_thread()
        self.root.geometry(f"+{self.sw-self.bs-20}+{self.sh-self.bs-60}")
        self.update_stats()

    def _ball_size(self):
        return SIZE_2 if self.settings.get("style", 1) == 2 else SIZE_1

    def _get_font(self, key, default=9):
        return ("Consolas", self.settings.get(key, default), "bold")

    # ---- 绘制 ----

    def _draw_ball(self, size=None, snapped=False):
        self.canvas.delete("all")
        if size is None:
            size = self._ball_size()
        cx = cy = size // 2
        s = self.settings
        style = s.get("style", 1)

        if snapped:
            r = size // 2 - 1
            self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r, fill="#1a1a2e", outline="#3a3a5e", width=1)
            self.canvas.create_text(cx, cy, text="CC", fill="#888888",
                                    font=("Consolas", 7, "bold"), anchor=tk.CENTER)
            return

        if style == 1:
            self._draw_style1(size, cx, cy, s)
        else:
            self._draw_style2(size, cx, cy, s)

    def _draw_style1(self, size, cx, cy, s):
        r = size // 2 - 2
        self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r, fill="#1a1a2e", outline="#3a3a5e", width=2)
        r2 = r - 10
        self.canvas.create_oval(cx-r2, cy-r2, cx+r2, cy+r2, fill="#16213e", outline="#2a3a5e", width=1)

        fs_cpu = self._get_font("font_size_cpu", 13)
        fs_mem = self._get_font("font_size_mem", 9)
        fs_gpu = self._get_font("font_size_gpu", 9)
        fs_net = self._get_font("font_size_net", 7)
        fs_disk = self._get_font("font_size_disk", 7)

        self._t("cpu", self.canvas.create_text(cx, cy-18, text="CPU:--%", fill="#4ade80",
                                                font=fs_cpu, anchor=tk.CENTER))
        self._t("mem", self.canvas.create_text(cx, cy+2, text="MEM:--%", fill="#60a5fa",
                                                font=fs_mem, anchor=tk.CENTER))
        self._t("gpu", self.canvas.create_text(cx, cy+18, text="GPU:--%", fill="#f472b6",
                                                font=fs_gpu, anchor=tk.CENTER))
        self._t("netu", self.canvas.create_text(6, 6, text="▲--K", fill="#fbbf24",
                                                 font=fs_net, anchor=tk.NW))
        self._t("netd", self.canvas.create_text(6, 20, text="▼--K", fill="#34d399",
                                                 font=fs_net, anchor=tk.NW))
        self._t("disk", self.canvas.create_text(size-4, 6, text="C:--%", fill="#a78bfa",
                                                 font=fs_disk, anchor=tk.NE))

    def _draw_style2(self, size, cx, cy, s):
        r = size // 2 - 2
        self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r, fill="#1a1a2e", outline="#3a3a5e", width=2)
        # 内框线
        self.canvas.create_rectangle(cx-60, cy-65, cx+60, cy+68, outline="#2a3a5e", width=1, fill="#16213e")

        fs_big = ("Consolas", 8, "bold")
        fs_sm = ("Consolas", 7)
        fs_tiny = ("Consolas", 6)

        # Token 行
        self._t("toki", self.canvas.create_text(cx-55, cy-58, text="IN:--", fill="#88cc88",
                                                 font=fs_big, anchor=tk.W))
        self._t("toko", self.canvas.create_text(cx+5, cy-58, text="OUT:--", fill="#88cc88",
                                                 font=fs_big, anchor=tk.W))
        self._t("tokc", self.canvas.create_text(cx-55, cy-47, text="COST:--", fill="#fbbf24",
                                                 font=fs_sm, anchor=tk.W))
        # 分隔线
        self.canvas.create_line(cx-55, cy-40, cx+55, cy-40, fill="#333333", width=1)

        # CPU MEM 同排
        self._t("cpu", self.canvas.create_text(cx-55, cy-30, text="CPU:--%", fill="#4ade80",
                                                font=fs_sm, anchor=tk.W))
        self._t("mem", self.canvas.create_text(cx+5, cy-30, text="MEM:--%", fill="#60a5fa",
                                                font=fs_sm, anchor=tk.W))
        # 网速 GPU 同排
        self._t("netu", self.canvas.create_text(cx-55, cy-16, text="▲--K", fill="#fbbf24",
                                                 font=fs_sm, anchor=tk.W))
        self._t("gpu", self.canvas.create_text(cx+5, cy-16, text="GPU:--%", fill="#f472b6",
                                                font=fs_sm, anchor=tk.W))
        # 网速下行
        self._t("netd", self.canvas.create_text(cx-55, cy-4, text="▼--K", fill="#34d399",
                                                 font=fs_sm, anchor=tk.W))
        self._t("diskc", self.canvas.create_text(cx+5, cy-4, text="C:--%", fill="#a78bfa",
                                                  font=fs_sm, anchor=tk.W))

        # 分隔线
        self.canvas.create_line(cx-55, cy+7, cx+55, cy+7, fill="#333333", width=1)

        # 底部：Token 趋势/磁盘汇总
        self._t("tokt", self.canvas.create_text(cx-55, cy+18, text="Total:--", fill="#88cc88",
                                                 font=("Consolas", 7, "bold"), anchor=tk.W))
        self._t("disc", self.canvas.create_text(cx-55, cy+32, text="DISK:--", fill="#a78bfa",
                                                 font=fs_tiny, anchor=tk.W))
        self._t("msg", self.canvas.create_text(cx-55, cy+44, text="--", fill="#666666",
                                                font=fs_tiny, anchor=tk.W))

    # ---- 工具 ----

    def _t(self, name, item):
        """存储文本项引用"""
        if not hasattr(self, "_items"):
            self._items = {}
        self._items[name] = item

    def _st(self, name, text, color):
        """更新文本"""
        try:
            item = self._items.get(name)
            if item:
                self.canvas.itemconfig(item, text=text, fill=color)
        except Exception:
            pass

    # ---- 事件 ----

    def _bind_events(self):
        self.canvas.bind("<Button-1>", self._on_btn1)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Button-3>", self._on_right)
        self.canvas.bind("<Enter>", self._on_enter)
        self.canvas.bind("<Leave>", self._on_leave)

    def _on_btn1(self, event):
        self._drag_start = (event.x_root, event.y_root)
        self._is_dragging = False

    def _on_drag(self, event):
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
        if self._is_dragging:
            self._is_dragging = False
            self._snap_check()
        else:
            self._on_click()
        self._drag_start = None

    def _on_click(self):
        if self._hidden_mode:
            return
        if SINGLE_OK:
            try:
                gi = SingleInstance("gui")
                if gi.is_running():
                    gi.bring_to_front()
                    return
            except Exception:
                pass
        gui_path = SCRIPT_DIR / "gui.py"
        if gui_path.exists():
            try:
                subprocess.Popen([sys.executable, str(gui_path)],
                                 creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            except Exception:
                pass

    def _on_ipc(self, msg):
        if msg == "show":
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            if self._hidden_mode:
                self._slide_out()

    def _build_menu(self):
        """预构建右键菜单（只创建一次）"""
        m = tk.Menu(self.root, tearoff=0, bg="#2d2d2d", fg="#dddddd",
                    activebackground="#4a6a8a", activeforeground="#ffffff",
                    font=("微软雅黑", 10))

        m.add_command(label="打开主窗口", command=self._on_click)
        m.add_command(label="设置", command=self._open_settings)

        m.add_separator()

        # 样式子菜单
        sm = tk.Menu(m, tearoff=0, bg="#2d2d2d", fg="#dddddd",
                      activebackground="#4a6a8a", activeforeground="#ffffff")
        sm.add_command(label="简约圆形", command=lambda: self._switch_style(1))
        sm.add_command(label="Token 面板", command=lambda: self._switch_style(2))
        m.add_cascade(label="切换样式", menu=sm)

        m.add_command(label="解除吸附", command=self._unsnap)

        m.add_separator()
        m.add_command(label="退出", command=self.on_exit)
        return m

    def _stats_thread(self):
        """后台线程采集数据，不阻塞主线程"""
        import threading
        def _worker():
            while self._stats_thread_running:
                try:
                    data = self.stats.get_all()
                    tok = {}
                    if self.token_tracker:
                        self.token_tracker.poll()
                        tok = self.token_tracker.get_stats()
                    self._latest_data = data
                    self._latest_tok = tok
                except Exception:
                    pass
                time.sleep(2)
        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    def _on_right(self, event):
        """右键点击：弹出预构建菜单（不阻塞）"""
        try:
            self._menu.entryconfig("解除吸附",
                                    state=tk.NORMAL if self._snapped else tk.DISABLED)
        except Exception:
            pass
        self._menu.post(event.x_root, event.y_root)

    def _open_settings(self):
        SettingsDialog(self.root, callback=self._on_settings_changed)

    def _on_settings_changed(self):
        old_bs = self.bs
        self.settings = get_settings()
        self.bs = self._ball_size()
        if self.bs != old_bs:
            self.root.geometry(f"{self.bs}x{self.bs}")
            self.canvas.configure(width=self.bs, height=self.bs)
        self._draw_ball()

    def _switch_style(self, style):
        s = get_settings()
        s["style"] = style
        save_settings(s)
        self._on_settings_changed()

    # ---- 吸附 ----

    def _snap_check(self):
        x, y = self.root.winfo_x(), self.root.winfo_y()
        cx, cy = x + self.bs//2, y + self.bs//2
        snap = self.settings.get("snap_distance", 40)
        dl, dr = cx, self.sw - cx
        dt, db = cy, self.sh - cy
        md = min(dl, dr, dt, db)
        if md > snap:
            if self._snapped:
                self._unsnap()
            return
        self._snapped = True
        if md == dl:
            self._snap_edge = "left"
            self.root.geometry(f"{TAB_SIZE}x{self.bs}+0+{y}")
        elif md == dr:
            self._snap_edge = "right"
            self.root.geometry(f"{TAB_SIZE}x{self.bs}+{self.sw-TAB_SIZE}+{y}")
        elif md == dt:
            self._snap_edge = "top"
            self.root.geometry(f"{self.bs}x{TAB_SIZE}+{x}+0")
        else:
            self._snap_edge = "bottom"
            self.root.geometry(f"{self.bs}x{TAB_SIZE}+{x}+{self.sh-TAB_SIZE}")
        self._hidden_mode = True
        self._draw_ball(TAB_SIZE, snapped=True)

    def _unsnap(self):
        self._snapped = False
        self._snap_edge = ""
        self._hidden_mode = False
        x, y = self.root.winfo_x(), self.root.winfo_y()
        self.root.geometry(f"{self.bs}x{self.bs}+{x}+{y}")
        self._draw_ball(self.bs)

    def _on_enter(self, event):
        if not self._snapped:
            return
        if self._leave_timer:
            self.root.after_cancel(self._leave_timer)
            self._leave_timer = None
        if self._hidden_mode:
            self._slide_out()

    def _on_leave(self, event):
        if not self._snapped:
            return
        if self._leave_timer:
            self.root.after_cancel(self._leave_timer)
        self._leave_timer = self.root.after(1500, self._slide_in)

    def _slide_out(self):
        if not self._snapped:
            return
        self._hidden_mode = False
        x, y = self.root.winfo_x(), self.root.winfo_y()
        e = self._snap_edge
        if e == "left":
            self.root.geometry(f"{self.bs}x{self.bs}+0+{y}")
        elif e == "right":
            self.root.geometry(f"{self.bs}x{self.bs}+{self.sw-self.bs}+{y}")
        elif e == "top":
            self.root.geometry(f"{self.bs}x{self.bs}+{x}+0")
        elif e == "bottom":
            self.root.geometry(f"{self.bs}x{self.bs}+{x}+{self.sh-self.bs}")
        self._draw_ball(self.bs)

    def _slide_in(self):
        if not self._snapped or self._hidden_mode:
            return
        try:
            wx, wy = self.root.winfo_pointerxy()
            rx, ry = self.root.winfo_x(), self.root.winfo_y()
            if rx <= wx <= rx+self.bs and ry <= wy <= ry+self.bs:
                return
        except Exception:
            pass
        self._hidden_mode = True
        x, y = self.root.winfo_x(), self.root.winfo_y()
        e = self._snap_edge
        if e == "left":
            self.root.geometry(f"{TAB_SIZE}x{self.bs}+0+{y}")
        elif e == "right":
            self.root.geometry(f"{TAB_SIZE}x{self.bs}+{self.sw-TAB_SIZE}+{y}")
        elif e == "top":
            self.root.geometry(f"{self.bs}x{TAB_SIZE}+{x}+0")
        elif e == "bottom":
            self.root.geometry(f"{self.bs}x{TAB_SIZE}+{x}+{self.sh-TAB_SIZE}")
        self._draw_ball(TAB_SIZE, snapped=True)

    # ---- 数据 ----

    def update_stats(self):
        """UI 更新（只读取缓存，不阻塞）"""
        if not self._running:
            return
        try:
            data = self._latest_data
            tok = self._latest_tok
            if not self._hidden_mode:
                if data:
                    if self.settings.get("style", 1) == 1:
                        self._render_style1(data)
                    else:
                        self._render_style2(data, tok)
        except Exception:
            pass
        self.root.after(UPDATE_MS, self.update_stats)

    def _render_style1(self, data):
        cpu = data.get("cpu", {}).get("percent", 0)
        mem = data.get("memory", {}).get("percent", 0)
        gpu = self._gpu_str(data.get("gpu"))
        net = data.get("network", {})
        up, dn = net.get("up_kbps", 0), net.get("down_kbps", 0)
        disks = data.get("disks", [])

        self._st("cpu", f"CPU:{cpu:.0f}%", _load_color(cpu))
        self._st("mem", f"MEM:{mem:.0f}%", _load_color(mem))
        self._st("gpu", gpu, _load_color(self._gpu_val(data.get("gpu"))))
        self._st("netu", f"▲{up:.0f}K" if up < 999 else f"▲{up/1024:.1f}M", "#fbbf24")
        self._st("netd", f"▼{dn:.0f}K" if dn < 999 else f"▼{dn/1024:.1f}M", "#34d399")
        parts = [f"{d['mount'][0]}:{d['percent']:.0f}%" for d in disks[:2]]
        self._st("disk", " ".join(parts) if parts else "--", "#a78bfa")

    def _render_style2(self, data, tok):
        cpu = data.get("cpu", {}).get("percent", 0)
        mem = data.get("memory", {}).get("percent", 0)
        gpu_data = data.get("gpu")
        gpu_str = self._gpu_str(gpu_data)
        gpu_v = self._gpu_val(gpu_data)
        net = data.get("network", {})
        up, dn = net.get("up_kbps", 0), net.get("down_kbps", 0)
        disks = data.get("disks", [])

        # Token
        inp = tok.get("input", 0)
        out = tok.get("output", 0)
        cost = tok.get("cost", 0)
        total = tok.get("total", 0)
        msgs = tok.get("messages", 0)
        self._st("toki", f"IN:{inp//1000}K" if inp >= 1000 else f"IN:{inp}", "#88cc88")
        self._st("toko", f"OUT:{out//1000}K" if out >= 1000 else f"OUT:{out}", "#88cc88")
        self._st("tokc", f"COST:${cost:.4f}" if cost else "COST:--", "#fbbf24")
        self._st("tokt", f"Total:{total//1000}K" if total >= 1000 else f"Total:{total}", "#88cc88")

        # 系统
        self._st("cpu", f"CPU:{cpu:.0f}%", _load_color(cpu))
        self._st("mem", f"MEM:{mem:.0f}%", _load_color(mem))
        self._st("gpu", gpu_str, _load_color(gpu_v))
        self._st("netu", f"▲{up:.0f}K" if up < 999 else f"▲{up/1024:.1f}M", "#fbbf24")
        self._st("netd", f"▼{dn:.0f}K" if dn < 999 else f"▼{dn/1024:.1f}M", "#34d399")

        # 磁盘
        c_disk = next((d for d in disks if d["mount"] == "C:\\"), None)
        e_disk = next((d for d in disks if d["mount"] == "E:\\"), None)
        disk_str = ""
        if c_disk:
            disk_str += f"C:{c_disk['percent']:.0f}%"
        if e_disk:
            disk_str += f" E:{e_disk['percent']:.0f}%"
        self._st("diskc", f"C:{c_disk['percent']:.0f}%" if c_disk else "C:--", "#a78bfa")
        self._st("disc", f"DISK: {disk_str}" if disk_str else "DISK:--", "#a78bfa")
        self._st("msg", f"msgs:{msgs}" if msgs else "", "#666666")

    def _gpu_str(self, gpu):
        if gpu and isinstance(gpu, list) and len(gpu) > 0:
            return f"GPU:{gpu[0].get('util',0):.0f}%"
        return "GPU:--"

    def _gpu_val(self, gpu):
        if gpu and isinstance(gpu, list) and len(gpu) > 0:
            return gpu[0].get("util", 0)
        return 0

    def on_exit(self):
        self._running = False
        self._stats_thread_running = False
        if self._inst:
            self._inst.stop()
        self.root.destroy()


def main():
    ball = FloatingBall()
    ball.root.mainloop()


if __name__ == "__main__":
    main()
