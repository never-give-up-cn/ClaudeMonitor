#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude Code 工作状态监控器
================================
监控 Claude Code 的运行状态，通过串口发送状态码到 Arduino LED Matrix 显示。

状态编码 (0-11):
  0  = IDLE      空闲     — Claude 未运行
  1  = LOADING   启动     — Claude 进程刚创建
  2  = THINKING  思考     — CPU 占用高，正在推理/生成
  3  = READING   读文件   — 检测到文件读取活动
  4  = WRITING   写代码   — 检测到文件修改
  5  = SEARCHING 搜索     — 低 CPU + 文件扫描活动
  6  = BUILDING  编译     — NPM/Webpack/Git 等子进程运行中
  7  = COMMAND   命令     — 其他子进程在运行
  8  = WAITING   等待输入 — 进程驻留但 CPU 为 0 超过 30 秒
  9  = PROCESSING 处理中   — 中等 CPU 活动
  10 = DONE      完成     — 进程刚退出
  11 = ERROR     错误     — 异常状态
"""

import sys
import time
import os
import re
import json
import signal
import threading
import logging
from datetime import datetime, timedelta
from pathlib import Path

try:
    import psutil
except ImportError:
    print("错误: 需要 psutil 库。请运行: pip install psutil")
    sys.exit(1)

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("错误: 需要 pyserial 库。请运行: pip install pyserial")
    sys.exit(1)

# ============================================================
# 配置
# ============================================================
CONFIG = {
    "serial_port": "auto",           # 串口，auto=自动检测
    "baud_rate": 115200,             # 波特率（与 Arduino 一致）
    "check_interval": 1.0,           # 检测间隔（秒）
    "watch_dirs": [                  # 监控的目录（检测文件变化）
        str(Path.home() / "Desktop"),
    ],
    "idle_timeout": 15,              # 无 CPU 活动多少秒后标记为等待
    "startup_timeout": 15,           # 进程刚启动多少秒内标记为加载
    "done_display_time": 3,          # 进程退出后显示"完成"的秒数
    "log_file": "monitor.log",       # 日志文件
    "cpu_think_threshold": 8.0,      # THINKING 状态的 CPU 阈值(%)
    "cpu_low_threshold": 1.0,        # 低 CPU 阈值
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

# 状态码常量 (0-11)
(IDLE, LOADING, THINKING, READING, WRITING, SEARCHING,
 BUILDING, COMMAND, WAITING, PROCESSING, DONE, ERROR) = range(12)


# ============================================================
# 日志
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(CONFIG["log_file"], encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger("ClaudeMonitor")


# ============================================================
# 串口通信
# ============================================================
class SerialManager:
    def __init__(self, config):
        self.config = config
        self.port = None
        self.serial = None
        self._lock = threading.Lock()
        self._last_send = -1

    def find_arduino_port(self):
        """自动检测 Arduino 串口"""
        ports = serial.tools.list_ports.comports()
        # 优先匹配已知的 Arduino VID/PID
        arduino_vids = {0x2341, 0x2A03, 0x1A86, 0x10C4, 0x239A}
        for p in ports:
            if p.vid in arduino_vids:
                log.info(f"检测到 Arduino: {p.device} ({p.description})")
                return p.device
        # 其次看描述含 Arduino 的
        for p in ports:
            desc = (p.description or "").lower()
            if "arduino" in desc or "ch340" in desc or "cp210" in desc:
                log.info(f"检测到 Arduino: {p.device} ({p.description})")
                return p.device
        # 最后返回第一个可用串口
        if ports:
            log.warning(f"未检测到 Arduino，使用第一个串口: {ports[0].device}")
            return ports[0].device
        return None

    def connect(self):
        """连接串口"""
        port_name = self.config["serial_port"]
        if port_name == "auto":
            port_name = self.find_arduino_port()

        if not port_name:
            log.warning("未找到串口设备，串口功能禁用")
            return False

        try:
            self.port = port_name
            self.serial = serial.Serial(
                port=port_name,
                baudrate=self.config["baud_rate"],
                timeout=0.1
            )
            time.sleep(2)  # 等待 Arduino 复位
            log.info(f"串口已连接: {port_name} @ {self.config['baud_rate']}bps")
            return True
        except serial.SerialException as e:
            log.warning(f"串口连接失败: {port_name} - {e}")
            self.serial = None
            return False

    def send(self, status_code):
        """发送状态码到 Arduino（格式: status,0\\n）"""
        if status_code == self._last_send:
            return
        self._last_send = status_code

        with self._lock:
            if self.serial and self.serial.is_open:
                try:
                    data = f"{status_code},0\n"
                    self.serial.write(data.encode())
                    self.serial.flush()
                except serial.SerialException as e:
                    log.warning(f"串口写入失败: {e}")
                    self.serial = None

    def try_reconnect(self):
        """尝试重新连接串口"""
        if self.serial and self.serial.is_open:
            return True
        return self.connect()

    def close(self):
        """关闭串口"""
        with self._lock:
            if self.serial and self.serial.is_open:
                try:
                    self.serial.close()
                    log.info("串口已关闭")
                except:
                    pass
            self.serial = None


# ============================================================
# Claude Code 进程检测
# ============================================================
def find_claude_processes():
    """查找所有 Claude Code 相关进程"""
    claude_procs = []
    try:
        for proc in psutil.process_iter(["pid", "name", "cmdline", "create_time", "cpu_percent"]):
            try:
                name = (proc.info["name"] or "").lower()
                cmdline = " ".join(proc.info["cmdline"] or []).lower()

                is_claude = False
                # 直接匹配 claude.exe
                if "claude" in name and "code" in name:
                    is_claude = True
                elif name == "claude.exe":
                    is_claude = True
                # node.exe 运行的 Claude Code
                elif name in ("node.exe", "node") and ("claude" in cmdline or "anthropic" in cmdline):
                    is_claude = True
                # 模糊匹配（防止名称变化）
                elif "claude" in name and name.endswith(".exe"):
                    is_claude = True

                if is_claude:
                    claude_procs.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception as e:
        log.debug(f"进程检测异常: {e}")

    return claude_procs


def get_claude_subprocesses(parent_procs):
    """获取 Claude 的子进程（如 git, npm 等）"""
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
# 文件变化监控
# ============================================================
class FileChangeMonitor:
    def __init__(self, watch_dirs):
        self.watch_dirs = watch_dirs
        self._snapshot = {}  # path -> last_write_time
        self._changed = False
        self._lock = threading.Lock()
        self._exclude_dirs = {
            ".git", "node_modules", "__pycache__",
            ".next", ".claude", ".idea", ".vscode",
            "dist", "build", ".cache", "target",
        }
        self._max_depth = 4  # 最大递归深度

    def _should_ignore(self, path):
        parts = path.replace("\\", "/").split("/")
        return any(ex in parts for ex in self._exclude_dirs)

    def _scandir_recursive(self, root, depth=0):
        """使用 scandir 高效遍历目录, 限制深度"""
        if depth > self._max_depth or self._should_ignore(root):
            return
        try:
            with os.scandir(root) as it:
                for entry in it:
                    full = entry.path
                    if entry.is_dir(follow_symlinks=False):
                        yield from self._scandir_recursive(full, depth + 1)
                    elif entry.is_file(follow_symlinks=False):
                        if entry.name.endswith((".log", ".pyc", ".tmp")):
                            continue
                        try:
                            yield full, entry.stat().st_mtime
                        except OSError:
                            pass
        except PermissionError:
            pass

    def snapshot(self):
        """快照当前文件状态"""
        self._snapshot.clear()
        for d in self.watch_dirs:
            if os.path.isdir(d):
                for fp, mtime in self._scandir_recursive(d):
                    self._snapshot[fp] = mtime
        with self._lock:
            self._changed = False
        log.info(f"文件快照已建立: {len(self._snapshot)} 个文件")

    def check_changes(self):
        """检查文件变化（高效增量扫描）"""
        changed = False
        new_snapshot = {}

        for d in self.watch_dirs:
            if not os.path.isdir(d):
                continue
            for fp, mtime in self._scandir_recursive(d):
                new_snapshot[fp] = mtime
                prev = self._snapshot.get(fp)
                if prev is None or abs(mtime - prev) > 0.1:
                    changed = True

        # 检查删除的文件
        for fp in self._snapshot:
            if fp not in new_snapshot:
                changed = True
                break

        self._snapshot = new_snapshot
        with self._lock:
            self._changed = changed
        return changed

    @property
    def has_changes(self):
        with self._lock:
            return self._changed


# ============================================================
# 状态检测引擎
# ============================================================
class StateDetector:
    def __init__(self, config, file_monitor):
        self.config = config
        self.file_monitor = file_monitor
        self._cpu_prev = {}            # pid -> (user, system, timestamp)
        self._idle_since = None        # 空闲开始时间
        self._was_running = False      # 上一帧 Claude 是否运行
        self._done_counter = 0         # 完成状态显示计数
        self._processes = []
        self._file_check_counter = 0   # 文件检测计数器（每 N 次检测一次）
        self.last_cpu = 0.0            # 最近一次 CPU 检测值供外部使用

    def _calc_cpu(self, pid):
        """通过 cpu_times 差值计算进程 CPU 使用率，避免 cpu_percent 对新对象的 0 值问题"""
        try:
            now = time.time()
            p = psutil.Process(pid)
            ct = p.cpu_times()
            key = (ct.user, ct.system)

            if pid in self._cpu_prev:
                prev_user, prev_sys, prev_time = self._cpu_prev[pid]
                dt = now - prev_time
                if dt > 0:
                    cpu = ((ct.user - prev_user) + (ct.system - prev_sys)) / dt * 100.0
                    self._cpu_prev[pid] = (ct.user, ct.system, now)
                    return min(cpu, 100.0)

            self._cpu_prev[pid] = (ct.user, ct.system, now)
            return 0.0
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            self._cpu_prev.pop(pid, None)
            return 0.0

    def detect(self):
        """执行一次状态检测，返回状态码"""
        procs = find_claude_processes()
        self._processes = procs
        is_running = len(procs) > 0

        if not is_running:
            return self._handle_no_process()
        else:
            return self._handle_running(procs)

    def _handle_no_process(self):
        """处理 Claude 未运行的情况"""
        self._idle_since = None

        if self._was_running:
            self._was_running = False
            self._done_counter = self.config["done_display_time"]
            return DONE
        elif self._done_counter > 0:
            self._done_counter -= 1
            return DONE
        else:
            return IDLE

    def _handle_running(self, procs):
        """处理 Claude 在运行的情况"""
        self._was_running = True
        self._done_counter = 0

        main_proc = procs[0]
        pid = main_proc.info["pid"]

        try:
            p = psutil.Process(pid)
            uptime = time.time() - p.create_time()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return ERROR

        # 真实 CPU 使用率（通过 cpu_times 差值计算）
        cpu_percent = self._calc_cpu(pid)
        self.last_cpu = cpu_percent

        # 子进程
        children = get_claude_subprocesses(procs)

        # 文件变化检测（每 3 秒一次，减少 IO 开销）
        self._file_check_counter += 1
        file_changed = False
        if self._file_check_counter >= 3:
            file_changed = self.file_monitor.check_changes()
            self._file_check_counter = 0

        # --- 状态判断逻辑 ---

        # 1. 启动状态
        if uptime < self.config["startup_timeout"]:
            return LOADING

        # 2. 子进程运行中
        if children:
            child_str = " ".join((c.name() or "").lower() for c in children)
            if any(t in child_str for t in
                   ["npm", "node", "webpack", "tsc", "babel",
                    "vite", "rollup", "esbuild", "ng", "vue"]):
                return BUILDING
            elif any(t in child_str for t in ["git", "svn", "hg"]):
                return COMMAND
            else:
                return COMMAND

        # 3. 文件写入
        if file_changed:
            return WRITING

        # 4. CPU 高 → 思考
        if cpu_percent > self.config["cpu_think_threshold"]:
            self._idle_since = None
            try:
                io = p.io_counters()
                if io.read_bytes > io.write_bytes * 10:
                    return READING
            except (psutil.AccessDenied, AttributeError):
                pass
            return THINKING

        # 5. 低 CPU
        if cpu_percent < self.config["cpu_low_threshold"]:
            if self._idle_since is None:
                self._idle_since = time.time()
            idle_sec = time.time() - self._idle_since
            return WAITING if idle_sec > self.config["idle_timeout"] else PROCESSING
        else:
            self._idle_since = None
            return PROCESSING

    def get_current_processes(self):
        return self._processes


# ============================================================
# 终端 UI
# ============================================================
class ConsoleUI:
    def __init__(self):
        self._last_status = -1
        self._last_update = 0

    def clear_line(self):
        """清除当前行"""
        sys.stdout.write("\r\033[K")

    def render(self, status_code, detail=""):
        """渲染状态显示"""
        now = time.time()
        en, cn, icon = STATUS[status_code]
        time_str = datetime.now().strftime("%H:%M:%S")

        # 状态改变时输出详细日志
        if status_code != self._last_status:
            self._last_status = status_code
            self._last_update = now

            # 清空行并输出
            self.clear_line()
            log.info(f"状态变更 [{status_code:2d}] {icon} {en:10s} {cn}  {detail}")
        else:
            # 每 5 秒刷新一次当前状态的简短显示
            if now - self._last_update >= 5:
                self._last_update = now
                self.clear_line()
                sys.stdout.write(f"\r> {time_str} | 状态 [{status_code:2d}] {icon} {en} - {cn}")
                sys.stdout.flush()

    def render_serial_status(self, connected):
        """渲染串口连接状态"""
        if connected:
            log.info("[SERIAL] 串口已连接")
        else:
            log.warning("[SERIAL] 串口未连接（状态仅记录到日志）")

    def render_header(self):
        """显示标题"""
        print("=" * 60)
        print("  Claude Code 工作状态监控器")
        print(f"  启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  监控目录: {', '.join(CONFIG['watch_dirs'])}")
        print("=" * 60)
        print("  状态码  状态             说明")
        print("  " + "-" * 50)
        for i, (en, cn, icon) in enumerate(STATUS):
            print(f"  [{i:2d}]     {icon} {en:10s}  {cn}")
        print("=" * 60)
        print()

    def render_error(self, msg):
        self.clear_line()
        log.error(msg)


# ============================================================
# 主程序
# ============================================================
def main():
    print()
    ui = ConsoleUI()
    ui.render_header()

    # 初始化串口
    serial_mgr = SerialManager(CONFIG)
    serial_ok = serial_mgr.connect()
    ui.render_serial_status(serial_ok)

    # 初始化文件监控
    file_monitor = FileChangeMonitor(CONFIG["watch_dirs"])
    file_monitor.snapshot()

    # 初始化状态检测器
    detector = StateDetector(CONFIG, file_monitor)

    # 首次运行快照
    log.info("开始监控 Claude Code 状态...")
    print()

    # 主循环
    retry_serial_counter = 0
    last_status = -1

    try:
        while True:
            # --- 文件变化检测（每 tick 检查，用于 WRITE 状态）---
            file_monitor.check_changes()

            # --- 状态检测 ---
            status_code = detector.detect()
            procs = detector.get_current_processes()

            # --- 构建详细描述 ---
            detail_parts = []
            if procs:
                try:
                    p = procs[0]
                    pname = p.info["name"] or "?"
                    pid = p.info["pid"]
                    cpu = detector.last_cpu
                    cmd = " ".join(p.info["cmdline"] or [""])[:60]
                    detail_parts.append(f"{pname}({pid}) CPU:{cpu:.0f}%")
                except:
                    pass

            children = get_claude_subprocesses(procs)
            if children:
                child_names = list(set(c.name() for c in children if c.name()))
                detail_parts.append(f"子进程: {','.join(child_names[:3])}")

            detail = " | ".join(detail_parts)

            # --- 更新 UI ---
            ui.render(status_code, detail)

            # --- 发送到 Arduino ---
            if status_code != last_status:
                serial_mgr.send(status_code)
                last_status = status_code

            # --- 串口重连（每 30 秒重试）---
            if not serial_ok:
                retry_serial_counter += 1
                if retry_serial_counter >= 30:
                    serial_ok = serial_mgr.try_reconnect()
                    retry_serial_counter = 0
            else:
                # 检查串口是否还连着
                if serial_mgr.serial and not serial_mgr.serial.is_open:
                    serial_ok = False
                    log.warning("串口连接断开，将尝试重连...")

            # --- 等待 ---
            time.sleep(CONFIG["check_interval"])

    except KeyboardInterrupt:
        print()
        log.info("监控已停止")
    finally:
        serial_mgr.close()
        print()
        log.info(f"运行结束: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    # Windows 下处理 Ctrl+C 更优雅
    if sys.platform == "win32":
        signal.signal(signal.SIGBREAK, lambda *_: sys.exit(0))
    main()
