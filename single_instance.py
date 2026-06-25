#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单例锁 + 进程间通信
====================
防止重复启动相同窗口，支持已运行实例切换到前台。

用法:
    from single_instance import SingleInstance

    inst = SingleInstance("floating_ball")
    if inst.is_running():
        inst.bring_to_front()  # 切换到前台
        sys.exit(0)

    # 正常启动...
    inst.cleanup_on_exit()
"""

import os
import sys
import json
import socket
import atexit
import threading
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None

LOCK_DIR = Path.home() / ".claude_monitor"
LOCALHOST = "127.0.0.1"

# 每个实例的端口
INSTANCE_PORTS = {
    "floating_ball": 18585,
    "gui": 18586,
    "monitor": 18587,
    "web_viewer": 18588,
}


class SingleInstance:
    """单例锁 + IPC 通信"""

    def __init__(self, name, port=None):
        """
        name: 实例名称 (floating_ball/gui/monitor/web_viewer)
        port: 通信端口，默认从 INSTANCE_PORTS 获取
        """
        self.name = name
        self.port = port or INSTANCE_PORTS.get(name, 18590)
        self.lock_file = LOCK_DIR / f"{name}.lock"
        self._server = None
        self._cleanup_done = False

        LOCK_DIR.mkdir(parents=True, exist_ok=True)

    def is_running(self):
        """检测是否已有实例在运行"""
        if not self.lock_file.exists():
            return False

        try:
            pid = int(self.lock_file.read_text().strip())
            if psutil and psutil.pid_exists(pid):
                # 验证进程名是否匹配
                try:
                    proc = psutil.Process(pid)
                    pname = proc.name() or ""
                    if "python" not in pname.lower() and "py" != pname.lower():
                        # 进程名不匹配，可能是 stale lock
                        self.lock_file.unlink(missing_ok=True)
                        return False
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    self.lock_file.unlink(missing_ok=True)
                    return False
                return True
        except (ValueError, OSError):
            pass

        # Stale lock
        self.lock_file.unlink(missing_ok=True)
        return False

    def acquire(self):
        """获取锁（写入 PID），返回是否成功获取"""
        if self.is_running():
            return False
        self._write_lock()
        return True

    def _write_lock(self):
        """写入 PID 锁文件"""
        self.lock_file.write_text(str(os.getpid()))
        self._cleanup_done = False

    def _remove_lock(self):
        """删除锁文件"""
        if self._cleanup_done:
            return
        self._cleanup_done = True
        try:
            if self.lock_file.exists():
                pid = int(self.lock_file.read_text().strip())
                if pid == os.getpid():
                    self.lock_file.unlink(missing_ok=True)
        except (ValueError, OSError):
            pass

    def cleanup_on_exit(self):
        """注册退出清理"""
        atexit.register(self._remove_lock)

    # ---- IPC: 发送/接收消息 ----

    def start_server(self, on_message=None):
        """启动 TCP 服务端，接收其他实例的消息

        on_message: 回调函数，收到消息时调用
        """
        if self._server:
            return

        def _server_thread():
            try:
                srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                srv.bind((LOCALHOST, self.port))
                srv.listen(1)
                srv.settimeout(1)
                self._server = srv

                while True:
                    try:
                        conn, _ = srv.accept()
                        data = conn.recv(4096).decode("utf-8")
                        conn.close()
                        if data and on_message:
                            on_message(data)
                    except socket.timeout:
                        continue
                    except Exception:
                        break
            except OSError:
                pass  # 端口被占用（其他实例在运行）

        t = threading.Thread(target=_server_thread, daemon=True)
        t.start()

    def send_message(self, message):
        """发送消息到正在运行的实例（如果存在）"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            s.connect((LOCALHOST, self.port))
            s.send(message.encode("utf-8"))
            s.close()
            return True
        except (ConnectionRefusedError, OSError, socket.timeout):
            return False

    def bring_to_front(self):
        """发送 'show' 消息让已有实例显示窗口"""
        return self.send_message("show")

    def stop(self):
        """停止服务端"""
        self._remove_lock()
        if self._server:
            try:
                self._server.close()
            except Exception:
                pass
            self._server = None
