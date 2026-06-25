#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
桌面悬浮球 v3
=============
圆形浮窗显示 CPU/内存/GPU/网速/磁盘。
支持：边缘吸附自动隐藏、设置面板、自定义音效、开机自启。
"""

import sys, os, json, subprocess, time, threading, webbrowser
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
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False

# ===== 路径 =====
SCRIPT_DIR = Path(__file__).parent
SETTINGS_FILE = SCRIPT_DIR / "ball_settings.json"

# ===== 默认配置 =====
DEFAULT_SETTINGS = {
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
BALL_SIZE = 140
TAB_SIZE = 16
UPDATE_MS = 1500

# ===== 辅助函数 =====

def _load_color(pct):
    if pct < 50: return "#4ade80"
    elif pct < 80: return "#fbbf24"
    return "#ef4444"

def get_settings():
    """加载设置"""
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
    """保存设置"""
    try:
        SETTINGS_FILE.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        messagebox.showerror("错误", f"保存设置失败:\n{e}")

def play_sound(sound_type="done"):
    """播放提示音（支持自定义 WAV 文件）"""
    if not HAS_WINSOUND:
        return
    settings = get_settings()
    if not settings.get("sound_enabled", True):
        return

    wav_key = f"sound_{sound_type}_file"
    wav = settings.get(wav_key, "")

    if wav and os.path.isfile(wav):
        try:
            winsound.PlaySound(wav, winsound.SND_FILENAME | winsound.SND_ASYNC)
            return
        except Exception:
            pass

    # 默认 Beep
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
    """设置开机自启（启动文件夹放 VBS 启动脚本）"""
    try:
        startup = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        startup.mkdir(parents=True, exist_ok=True)
        vbs_dest = startup / "ClaudeMonitor_Ball.vbs"

        if not enable:
            if vbs_dest.exists():
                vbs_dest.unlink()
            return True

        # 复制 VBS 启动脚本到启动文件夹
        vbs_src = SCRIPT_DIR / "start_ball.vbs"
        if not vbs_src.exists():
            return False

        content = vbs_src.read_text(encoding="utf-8")
        vbs_dest.write_text(content, encoding="utf-8")

        if vbs_dest.exists():
            return True
        return False
    except Exception as e:
        print(f"Auto-start error: {e}")
        return False


class SettingsDialog:
    """设置面板"""

    def __init__(self, parent, callback=None):
        self.parent = parent
        self.callback = callback
        self.settings = get_settings()

        self.win = tk.Toplevel(parent)
        self.win.title("悬浮球设置")
        self.win.geometry("500x560")
        self.win.resizable(False, False)
        self.win.configure(bg="#1e1e1e")
        self.win.transient(parent)
        self.win.grab_set()

        self._build_ui()
        self.win.wait_window()

    def _build_ui(self):
        s = self.settings
        win = self.win

        # 外框
        main = tk.Frame(win, bg="#1e1e1e", padx=20, pady=16)
        main.pack(fill=tk.BOTH, expand=True)

        row = 0

        # ---- 字体大小 ----
        tk.Label(main, text="字体大小", font=("微软雅黑", 12, "bold"),
                 fg="#88cc88", bg="#1e1e1e").grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))
        row += 1

        fonts = [
            ("CPU 占用", "font_size_cpu", 8, 24),
            ("内存占用", "font_size_mem", 6, 20),
            ("GPU 占用", "font_size_gpu", 6, 20),
            ("网速显示", "font_size_net", 5, 16),
            ("磁盘显示", "font_size_disk", 5, 16),
        ]

        self._font_vars = {}
        for label, key, min_v, max_v in fonts:
            tk.Label(main, text=label, font=("微软雅黑", 10),
                     fg="#dddddd", bg="#1e1e1e").grid(row=row, column=0, sticky=tk.W, pady=3)
            var = tk.IntVar(value=s.get(key, DEFAULT_SETTINGS.get(key, 9)))
            self._font_vars[key] = var
            spin = tk.Spinbox(main, from_=min_v, to=max_v, textvariable=var,
                              width=5, font=("Consolas", 9), justify=tk.CENTER,
                              bg="#3a3a3a", fg="#ffffff", relief=tk.FLAT,
                              buttonbackground="#555555")
            spin.grid(row=row, column=1, sticky=tk.W, padx=10)
            row += 1

        # ---- 分割线 ----
        ttk.Separator(main, orient="horizontal").grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=12)
        row += 1

        # ---- 自定义音效 ----
        tk.Label(main, text="自定义音效 (WAV 文件)", font=("微软雅黑", 12, "bold"),
                 fg="#88aacc", bg="#1e1e1e").grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))
        row += 1

        self._sound_vars = {}
        for label, key in [("任务完成音", "sound_done_file"),
                            ("操作提示音", "sound_action_file"),
                            ("错误提示音", "sound_error_file")]:
            f_row = tk.Frame(main, bg="#1e1e1e")
            f_row.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=2)
            tk.Label(f_row, text=label, font=("微软雅黑", 10),
                     fg="#dddddd", bg="#1e1e1e", width=10, anchor=tk.W).pack(side=tk.LEFT)
            var = tk.StringVar(value=s.get(key, ""))
            self._sound_vars[key] = var
            entry = tk.Entry(f_row, textvariable=var, font=("Consolas", 8),
                             bg="#3a3a3a", fg="#cccccc", relief=tk.FLAT)
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 4))
            tk.Button(f_row, text="浏览", command=lambda k=key, v=var: self._browse_sound(k, v),
                      font=("微软雅黑", 8), bg="#3a3a5a", fg="#cccccc",
                      relief=tk.FLAT, padx=8, pady=1, cursor="hand2").pack(side=tk.RIGHT)
            tk.Button(f_row, text="试听", command=lambda k=key.replace("sound_","").replace("_file",""): play_sound(k),
                      font=("微软雅黑", 8), bg="#5a3a3a", fg="#cccccc",
                      relief=tk.FLAT, padx=8, pady=1, cursor="hand2").pack(side=tk.RIGHT, padx=(0, 4))
            row += 1

        # ---- 分割线 ----
        ttk.Separator(main, orient="horizontal").grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=12)
        row += 1

        # ---- 开关 ----
        self._sound_enabled_var = tk.BooleanVar(value=s.get("sound_enabled", True))
        tk.Checkbutton(main, text="启用提示音", variable=self._sound_enabled_var,
                       font=("微软雅黑", 10), fg="#dddddd", bg="#1e1e1e",
                       selectcolor="#2d2d2d", activebackground="#1e1e1e",
                       activeforeground="#ffffff").grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=3)
        row += 1

        self._auto_start_var = tk.BooleanVar(value=s.get("auto_start", False))
        tk.Checkbutton(main, text="开机自动启动悬浮球", variable=self._auto_start_var,
                       font=("微软雅黑", 10), fg="#dddddd", bg="#1e1e1e",
                       selectcolor="#2d2d2d", activebackground="#1e1e1e",
                       activeforeground="#ffffff").grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=3)
        row += 1

        # ---- 按钮 ----
        btn_frame = tk.Frame(win, bg="#1e1e1e", pady=10)
        btn_frame.pack(fill=tk.X)
        tk.Button(btn_frame, text="保存", command=self._save,
                  font=("微软雅黑", 10), bg="#2a5c2a", fg="#ffffff",
                  relief=tk.FLAT, padx=24, pady=4, cursor="hand2").pack(side=tk.RIGHT, padx=(8, 20))
        tk.Button(btn_frame, text="取消", command=self.win.destroy,
                  font=("微软雅黑", 10), bg="#5a1a1a", fg="#cccccc",
                  relief=tk.FLAT, padx=24, pady=4, cursor="hand2").pack(side=tk.RIGHT)

    def _browse_sound(self, key, var):
        path = filedialog.askopenfilename(
            title="选择 WAV 音效文件",
            filetypes=[("WAV 音频", "*.wav"), ("所有文件", "*.*")]
        )
        if path:
            var.set(path)

    def _save(self):
        s = get_settings()
        for key, var in self._font_vars.items():
            s[key] = var.get()
        for key, var in self._sound_vars.items():
            s[key] = var.get().strip()
        s["sound_enabled"] = self._sound_enabled_var.get()
        s["auto_start"] = self._auto_start_var.get()
        save_settings(s)

        # 处理开机自启
        try:
            toggle_auto_start(s["auto_start"])
        except Exception:
            pass

        self.win.destroy()
        if self.callback:
            self.callback()


class FloatingBall:
    def __init__(self):
        # 单例
        if SINGLE_OK:
            self._instance = SingleInstance("floating_ball")
            if not self._instance.acquire():
                self._instance.bring_to_front()
                sys.exit(0)
            self._instance.cleanup_on_exit()
            self._instance.start_server(on_message=self._on_ipc)
        else:
            self._instance = None

        self.settings = get_settings()
        self.stats = SystemStats()
        self._running = True
        self._drag_start = None
        self._is_dragging = False
        self._snapped = False
        self._snap_edge = ""
        self._hidden_mode = False
        self._leave_timer = None

        self.root = tk.Tk()
        self.root.title("系统监控")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", "#000000")

        self.sw = self.root.winfo_screenwidth()
        self.sh = self.root.winfo_screenheight()
        self._default_x = self.sw - BALL_SIZE - 20
        self._default_y = self.sh - BALL_SIZE - 60

        self.canvas = tk.Canvas(
            self.root, width=BALL_SIZE, height=BALL_SIZE,
            bg="#000000", highlightthickness=0, cursor="hand2"
        )
        self.canvas.pack()

        self._draw_ball()
        self._bind_events()
        self.root.geometry(f"+{self._default_x}+{self._default_y}")
        self.update_stats()

    def _get_font(self, key, default=9):
        return ("Consolas", self.settings.get(key, default), "bold")

    def _draw_ball(self, size=BALL_SIZE, snapped=False):
        self.canvas.delete("all")
        cx = cy = size // 2

        if snapped:
            r = size // 2 - 1
            self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r, fill="#1a1a2e", outline="#3a3a5e", width=1)
            self.canvas.create_text(cx, cy, text="CC", fill="#888888",
                                    font=("Consolas", 7, "bold"), anchor=tk.CENTER)
            return

        r = size // 2 - 2
        self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r, fill="#1a1a2e", outline="#3a3a5e", width=2)
        r2 = r - 10
        self.canvas.create_oval(cx-r2, cy-r2, cx+r2, cy+r2, fill="#16213e", outline="#2a3a5e", width=1)

        s = self.settings
        self.cpu_t = self.canvas.create_text(cx, cy-20, text="CPU:--%", fill="#4ade80",
                                              font=self._get_font("font_size_cpu", 13), anchor=tk.CENTER)
        self.mem_t = self.canvas.create_text(cx, cy+1, text="MEM:--%", fill="#60a5fa",
                                              font=self._get_font("font_size_mem", 9), anchor=tk.CENTER)
        self.gpu_t = self.canvas.create_text(cx, cy+18, text="GPU:--%", fill="#f472b6",
                                              font=self._get_font("font_size_gpu", 9), anchor=tk.CENTER)
        self.net_up_t = self.canvas.create_text(6, 6, text="▲--K", fill="#fbbf24",
                                                 font=self._get_font("font_size_net", 7), anchor=tk.NW)
        self.net_dn_t = self.canvas.create_text(6, 20, text="▼--K", fill="#34d399",
                                                 font=self._get_font("font_size_net", 7), anchor=tk.NW)
        self.disk_t = self.canvas.create_text(size-4, 6, text="C:--%", fill="#a78bfa",
                                               font=self._get_font("font_size_disk", 7), anchor=tk.NE)

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
        # 尝试让已有 GUI 显示
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

    def _on_right(self, event):
        menu = tk.Menu(self.root, tearoff=0, bg="#2d2d2d", fg="#dddddd",
                       activebackground="#4a6a8a", activeforeground="#ffffff",
                       font=("微软雅黑", 10))
        menu.add_command(label="打开主窗口", command=self._on_click)
        menu.add_command(label="设置", command=self._open_settings)
        if self._snapped:
            menu.add_command(label="解除吸附", command=self._unsnap)
        menu.add_separator()
        menu.add_command(label="重新加载", command=lambda: self.update_stats())
        menu.add_separator()
        menu.add_command(label="退出", command=self.on_exit)
        menu.post(event.x_root, event.y_root)

    def _open_settings(self):
        SettingsDialog(self.root, callback=self._on_settings_changed)

    def _on_settings_changed(self):
        self.settings = get_settings()
        self._draw_ball()

    # ---- 边缘吸附 ----

    def _snap_check(self):
        x, y = self.root.winfo_x(), self.root.winfo_y()
        cx, cy = x + BALL_SIZE//2, y + BALL_SIZE//2
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
            self.root.geometry(f"{TAB_SIZE}x{BALL_SIZE}+0+{y}")
        elif md == dr:
            self._snap_edge = "right"
            self.root.geometry(f"{TAB_SIZE}x{BALL_SIZE}+{self.sw - TAB_SIZE}+{y}")
        elif md == dt:
            self._snap_edge = "top"
            self.root.geometry(f"{BALL_SIZE}x{TAB_SIZE}+{x}+0")
        else:
            self._snap_edge = "bottom"
            self.root.geometry(f"{BALL_SIZE}x{TAB_SIZE}+{x}+{self.sh - TAB_SIZE}")
        self._hidden_mode = True
        self._draw_ball(TAB_SIZE, snapped=True)

    def _unsnap(self):
        self._snapped = False
        self._snap_edge = ""
        self._hidden_mode = False
        x, y = self.root.winfo_x(), self.root.winfo_y()
        self.root.geometry(f"{BALL_SIZE}x{BALL_SIZE}+{x}+{y}")
        self._draw_ball(BALL_SIZE)

    def _on_enter(self, event):
        if not self._snapped or not self._hidden_mode:
            return
        if self._leave_timer:
            self.root.after_cancel(self._leave_timer)
            self._leave_timer = None
        self._slide_out()

    def _on_leave(self, event):
        if not self._snapped or not self._hidden_mode:
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
            self.root.geometry(f"{BALL_SIZE}x{BALL_SIZE}+0+{y}")
        elif e == "right":
            self.root.geometry(f"{BALL_SIZE}x{BALL_SIZE}+{self.sw - BALL_SIZE}+{y}")
        elif e == "top":
            self.root.geometry(f"{BALL_SIZE}x{BALL_SIZE}+{x}+0")
        elif e == "bottom":
            self.root.geometry(f"{BALL_SIZE}x{BALL_SIZE}+{x}+{self.sh - BALL_SIZE}")
        self._draw_ball(BALL_SIZE)

    def _slide_in(self):
        if not self._snapped or self._hidden_mode:
            return
        try:
            wx, wy = self.root.winfo_pointerxy()
            rx, ry = self.root.winfo_x(), self.root.winfo_y()
            if rx <= wx <= rx + BALL_SIZE and ry <= wy <= ry + BALL_SIZE:
                return
        except Exception:
            pass
        self._hidden_mode = True
        x, y = self.root.winfo_x(), self.root.winfo_y()
        e = self._snap_edge
        if e == "left":
            self.root.geometry(f"{TAB_SIZE}x{BALL_SIZE}+0+{y}")
        elif e == "right":
            self.root.geometry(f"{TAB_SIZE}x{BALL_SIZE}+{self.sw - TAB_SIZE}+{y}")
        elif e == "top":
            self.root.geometry(f"{BALL_SIZE}x{TAB_SIZE}+{x}+0")
        elif e == "bottom":
            self.root.geometry(f"{BALL_SIZE}x{TAB_SIZE}+{x}+{self.sh - TAB_SIZE}")
        self._draw_ball(TAB_SIZE, snapped=True)

    # ---- 数据 ----

    def update_stats(self):
        if not self._running:
            return
        try:
            data = self.stats.get_all()
            self._render(data)
        except Exception:
            pass
        self.root.after(UPDATE_MS, self.update_stats)

    def _render(self, data):
        if self._hidden_mode:
            return
        cpu = data.get("cpu", {}).get("percent", 0)
        mem = data.get("memory", {}).get("percent", 0)
        gpu = data.get("gpu")

        self._st(self.cpu_t, f"CPU:{cpu:.0f}%", _load_color(cpu))
        self._st(self.mem_t, f"MEM:{mem:.0f}%", _load_color(mem))
        if gpu and isinstance(gpu, list) and len(gpu) > 0:
            self._st(self.gpu_t, f"GPU:{gpu[0].get('util',0):.0f}%", _load_color(gpu[0].get('util',0)))
        else:
            self._st(self.gpu_t, "GPU:--", "#555555")

        net = data.get("network", {})
        up, dn = net.get("up_kbps", 0), net.get("down_kbps", 0)
        self._st(self.net_up_t, f"▲{up:.0f}K" if up < 999 else f"▲{up/1024:.1f}M", "#fbbf24")
        self._st(self.net_dn_t, f"▼{dn:.0f}K" if dn < 999 else f"▼{dn/1024:.1f}M", "#34d399")

        disks = data.get("disks", [])
        parts = [f"{d['mount'][0]}:{d['percent']:.0f}%" for d in disks[:2]]
        self._st(self.disk_t, " ".join(parts) if parts else "--", "#a78bfa")

    def _st(self, item, text, color):
        try:
            self.canvas.itemconfig(item, text=text, fill=color)
        except Exception:
            pass

    def on_exit(self):
        self._running = False
        if self._instance:
            self._instance.stop()
        self.root.destroy()


def main():
    ball = FloatingBall()
    ball.root.mainloop()


if __name__ == "__main__":
    main()
