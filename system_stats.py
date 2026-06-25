#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
System hardware monitor: CPU, memory, GPU, disk, network.
"""

import psutil
import subprocess
import time
import os
import tempfile
from datetime import datetime


class SystemStats:
    """System hardware stats collector"""

    def __init__(self):
        self._prev_net = psutil.net_io_counters()
        self._net_time = time.time()
        self._gpu_cache = None
        self._gpu_cache_time = 0

    def get_all(self):
        return {
            "cpu": self.get_cpu(),
            "memory": self.get_memory(),
            "gpu": self.get_gpu(),
            "disks": self.get_disks(),
            "network": self.get_network(),
            "time": datetime.now().strftime("%H:%M:%S"),
        }

    def get_cpu(self):
        return {"percent": psutil.cpu_percent(interval=0), "count": psutil.cpu_count(),
                "freq": psutil.cpu_freq().current if psutil.cpu_freq() else 0}

    def get_memory(self):
        mem = psutil.virtual_memory()
        return {"total": mem.total, "used": mem.used, "percent": mem.percent}

    def get_gpu(self):
        """GPU: nvidia-smi -> PowerShell counters -> WMI fallback"""
        now = time.time()
        if self._gpu_cache and now - self._gpu_cache_time < 3:
            return self._gpu_cache

        gpu = self._gpu_nvidia_smi() or self._gpu_ps_counter() or self._gpu_wmi_fallback()
        self._gpu_cache = gpu
        self._gpu_cache_time = now
        return gpu

    def _gpu_nvidia_smi(self):
        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,name",
                 "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=2)
            if r.returncode == 0 and r.stdout.strip():
                gpus = []
                for line in r.stdout.strip().split("\n"):
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 4:
                        gpus.append({"util": float(parts[0]), "mem_used": float(parts[1]),
                                     "mem_total": float(parts[2]), "temp": float(parts[3]),
                                     "name": parts[4] if len(parts) > 4 else "NVIDIA"})
                return gpus
        except Exception:
            pass
        return None

    def _gpu_ps_counter(self):
        """GPU via PowerShell counters (write temp file to avoid -Command timeout)"""
        ps_script = (
            '$c = @(Get-Counter -Counter "\\GPU Engine(*)\\Utilization Percentage" -ErrorAction SilentlyContinue)\n'
            '$u = 0; $h = $false\n'
            'if ($c) { foreach ($s in $c[0].CounterSamples) { $v = $s.CookedValue; if ($v -gt 0) { $h = $true }; $u += $v } }\n'
            'if ($u -gt 0 -or $h) { Write-Output ("UTIL:" + [math]::Round($u, 1)) }\n'
            '$adapters = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue\n'
            'foreach ($a in $adapters) {\n'
            '  if ($a.Name -and $a.Name -notmatch "Oray|Indirect|Basic|Microsoft") {\n'
            '    Write-Output ("NAME:" + $a.Name) }\n'
            '}\n'
            '$r = "HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Class\\{4d36e968-e325-11ce-bfc1-08002be10318}"\n'
            'Get-ChildItem $r -ErrorAction SilentlyContinue | ForEach-Object {\n'
            '  $v = $_ | Get-ItemProperty -Name "HardwareInformation.qwMemorySize" -ErrorAction SilentlyContinue\n'
            '  if ($v -and $v."HardwareInformation.qwMemorySize") {\n'
            '    Write-Output ("MEM:" + [math]::Round($v."HardwareInformation.qwMemorySize" / 1GB, 1)) }\n'
            '}\n'
        )
        try:
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".ps1", delete=False, encoding="utf-8")
            tmp.write(ps_script); tmp.close()
            r = subprocess.run(
                ["powershell", "-NoProfile", "-File", tmp.name],
                capture_output=True, text=True, timeout=8,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0)
            os.unlink(tmp.name)
            out = r.stdout.strip()
            if out and ("UTIL:" in out or "NAME:" in out or "MEM:" in out):
                lines = out.split("\n")
                util = 0; name = "GPU"; mem_total = 0
                for ln in lines:
                    ln = ln.strip()
                    if ln.startswith("UTIL:"):
                        try: util = float(ln.split(":", 1)[1])
                        except: pass
                    elif ln.startswith("NAME:"):
                        name = ln.split(":", 1)[1][:50]
                    elif ln.startswith("MEM:"):
                        try: mem_total = float(ln.split(":", 1)[1])
                        except: pass
                return [{"util": util, "mem_used": 0, "mem_total": mem_total, "temp": 0, "name": name}]
        except Exception:
            pass
        return None

    def _gpu_wmi_fallback(self):
        """WMI GPU basic info (no utilization)"""
        try:
            r = subprocess.run(
                ["wmic", "path", "win32_videocontroller", "get", "name", "/format:csv"],
                capture_output=True, text=True, timeout=3)
            if r.returncode == 0 and r.stdout.strip():
                for line in r.stdout.strip().split("\n"):
                    parts = [p.strip() for p in line.split(",")]
                    for p in parts:
                        if p and p not in ("Name", "Node") and "Oray" not in p and "Basic" not in p and "Microsoft" not in p:
                            return [{"util": 0, "mem_used": 0, "mem_total": 0, "temp": 0, "name": p}]
        except Exception:
            pass
        return None

    def get_disks(self):
        disks = []
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disks.append({"mount": part.mountpoint, "total": usage.total,
                              "used": usage.used, "percent": usage.percent})
            except (PermissionError, OSError):
                continue
        return disks

    def get_network(self):
        now = time.time()
        current = psutil.net_io_counters()
        dt = now - self._net_time
        up = (current.bytes_sent - self._prev_net.bytes_sent) / dt / 1024 if dt > 0 else 0
        down = (current.bytes_recv - self._prev_net.bytes_recv) / dt / 1024 if dt > 0 else 0
        self._prev_net = current
        self._net_time = now
        return {"up_kbps": max(0, up), "down_kbps": max(0, down),
                "total_up_mb": current.bytes_sent / 1024 / 1024,
                "total_down_mb": current.bytes_recv / 1024 / 1024}


if __name__ == "__main__":
    import json
    ss = SystemStats()
    print(json.dumps(ss.get_all(), indent=2, ensure_ascii=False, default=str))
