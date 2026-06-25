#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
系统硬件监控
============
CPU、内存、GPU、磁盘、网速一站式采集。
"""

import psutil
import subprocess
import time
from datetime import datetime


class SystemStats:
    """系统硬件状态采集器"""

    def __init__(self):
        self._prev_net = psutil.net_io_counters()
        self._net_time = time.time()
        self._gpu_cache = None
        self._gpu_cache_time = 0

    def get_all(self):
        """获取所有硬件状态"""
        return {
            "cpu": self.get_cpu(),
            "memory": self.get_memory(),
            "gpu": self.get_gpu(),
            "disks": self.get_disks(),
            "network": self.get_network(),
            "time": datetime.now().strftime("%H:%M:%S"),
        }

    def get_cpu(self):
        """CPU 占用率"""
        return {
            "percent": psutil.cpu_percent(interval=0),
            "count": psutil.cpu_count(),
            "freq": psutil.cpu_freq().current if psutil.cpu_freq() else 0,
        }

    def get_memory(self):
        """内存占用"""
        mem = psutil.virtual_memory()
        return {
            "total": mem.total,
            "used": mem.used,
            "percent": mem.percent,
        }

    def get_gpu(self):
        """GPU 占用（nvidia-smi，缓存 3 秒）"""
        now = time.time()
        if self._gpu_cache and now - self._gpu_cache_time < 3:
            return self._gpu_cache

        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,name",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split("\n")
                gpus = []
                for line in lines:
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 4:
                        gpus.append({
                            "util": float(parts[0]),
                            "mem_used": float(parts[1]),
                            "mem_total": float(parts[2]),
                            "temp": float(parts[3]),
                            "name": parts[4] if len(parts) > 4 else "NVIDIA",
                        })
                self._gpu_cache = gpus
                self._gpu_cache_time = now
                return gpus
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
            pass

        self._gpu_cache = None
        return None

    def get_disks(self):
        """所有磁盘分区占用"""
        disks = []
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disks.append({
                    "mount": part.mountpoint,
                    "total": usage.total,
                    "used": usage.used,
                    "percent": usage.percent,
                })
            except (PermissionError, OSError):
                continue
        return disks

    def get_network(self):
        """网速（KB/s）"""
        now = time.time()
        current = psutil.net_io_counters()
        dt = now - self._net_time
        if dt > 0:
            up = (current.bytes_sent - self._prev_net.bytes_sent) / dt / 1024
            down = (current.bytes_recv - self._prev_net.bytes_recv) / dt / 1024
        else:
            up = down = 0
        self._prev_net = current
        self._net_time = now
        return {
            "up_kbps": max(0, up),
            "down_kbps": max(0, down),
            "total_up_mb": current.bytes_sent / 1024 / 1024,
            "total_down_mb": current.bytes_recv / 1024 / 1024,
        }


# 快速测试
if __name__ == "__main__":
    ss = SystemStats()
    import json
    print(json.dumps(ss.get_all(), indent=2, ensure_ascii=False, default=str))
