#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Token 用量追踪器
=================
从 Claude Code 会话文件中实时解析 API token 消耗数据。
支持累积统计和费用估算。

依赖: 无 (仅使用标准库)
"""

import json
import os
import time
import threading
from pathlib import Path
from datetime import datetime

# Claude Code 项目会话目录
CLAUDE_PROJECT_DIR = Path.home() / ".claude" / "projects"

# 费用单价 ($/1K tokens) — 以 Claude Sonnet 为参考
# 实际费用根据使用的模型不同会有差异
COST_PER_1K = {
    "input": 0.003,         # 输入 token
    "output": 0.015,        # 输出 token
    "cache_read": 0.0003,   # 缓存读取
    "cache_create": 0.00375,  # 缓存创建
}

# 各模型单价参考 (仅用于显示，暂不自动切换)
MODEL_COST = {
    "claude-sonnet-4-20250514": {"input": 0.003, "output": 0.015, "cache_read": 0.0003, "cache_create": 0.00375},
    "claude-haiku-3-5-20241022": {"input": 0.0008, "output": 0.004, "cache_read": 0.00008, "cache_create": 0.001},
    "deepseek-v4-flash": {"input": 0.00015, "output": 0.0006, "cache_read": 0.000015, "cache_create": 0.00018},
}


def find_latest_project_dir():
    """找到最新的 Claude Code 项目会话目录"""
    if not CLAUDE_PROJECT_DIR.exists():
        return None
    try:
        dirs = [d for d in CLAUDE_PROJECT_DIR.iterdir() if d.is_dir()]
        if not dirs:
            return None
        # 取最近修改过的目录中的最新 jsonl 文件
        candidates = []
        for d in dirs:
            jsonl_files = list(d.glob("*.jsonl"))
            if jsonl_files:
                latest = max(jsonl_files, key=lambda f: f.stat().st_mtime)
                candidates.append((latest, latest.stat().st_mtime))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0].parent
    except (PermissionError, OSError):
        return None


def find_latest_session_file(project_dir=None):
    """找到最新的会话 JSONL 文件"""
    if project_dir is None:
        project_dir = find_latest_project_dir()
    if not project_dir:
        return None
    try:
        files = [f for f in project_dir.iterdir()
                 if f.suffix == ".jsonl" and f.is_file()]
        if not files:
            return None
        return max(files, key=lambda f: f.stat().st_mtime)
    except (PermissionError, OSError):
        return None


class TokenTracker:
    """Token 用量追踪器

    定期轮询最新的 Claude Code 会话文件，解析 assistant 消息中的 usage 字段，
    统计累积 token 消耗和估算费用。

    用法:
        tracker = TokenTracker()
        # 在主循环中定期调用
        tracker.poll()
        # 获取统计
        stats = tracker.get_stats()
        print(stats["summary"])
    """

    def __init__(self, cost_key="deepseek-v4-flash"):
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_read_tokens = 0
        self.cache_create_tokens = 0
        self.thinking_tokens = 0
        self.total_messages = 0
        self.current_model = "unknown"
        self.cost_key = cost_key

        self._last_file = None
        self._last_pos = 0
        self._lock = threading.Lock()
        self._running = True
        self._last_update = 0
        self._session_start = time.time()
        self._last_poll_error = None

    def _parse_file(self, filepath, start_pos=0):
        """增量解析会话文件，提取 token usage"""
        try:
            size = filepath.stat().st_size
            if size <= start_pos:
                return start_pos

            with open(filepath, "r", encoding="utf-8") as f:
                f.seek(start_pos)
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if data.get("type") == "assistant":
                            msg = data.get("message", {})
                            usage = msg.get("usage", {})
                            if usage:
                                self.input_tokens += usage.get("input_tokens", 0)
                                self.output_tokens += usage.get("output_tokens", 0)
                                self.cache_read_tokens += usage.get("cache_read_input_tokens", 0)
                                self.cache_create_tokens += usage.get("cache_creation_input_tokens", 0)
                                self.thinking_tokens += usage.get("thinking_tokens", 0)
                                self.total_messages += 1

                                # 记录模型
                                model = msg.get("model", "")
                                if model:
                                    self.current_model = model

                                self._last_update = time.time()
                    except json.JSONDecodeError:
                        continue

            return size
        except (FileNotFoundError, PermissionError, OSError) as e:
            self._last_poll_error = str(e)
            return start_pos

    def poll(self):
        """轮询最新会话文件，解析新数据。在主循环中定期调用。"""
        if not self._running:
            return

        latest = find_latest_session_file()
        if not latest:
            return

        # 如果文件变了，重置位置
        if latest != self._last_file:
            self._last_file = latest
            self._last_pos = 0

        with self._lock:
            self._last_pos = self._parse_file(latest, self._last_pos)

    def get_stats(self):
        """获取当前 token 统计和费用估算"""
        with self._lock:
            elapsed = time.time() - self._session_start
            hours = elapsed / 3600

            # 使用对应模型的单价
            rates = MODEL_COST.get(self.current_model, MODEL_COST.get(self.cost_key, COST_PER_1K))

            input_cost = self.input_tokens / 1000 * rates["input"]
            output_cost = self.output_tokens / 1000 * rates["output"]
            cache_read_cost = self.cache_read_tokens / 1000 * rates["cache_read"]
            cache_create_cost = self.cache_create_tokens / 1000 * rates["cache_create"]
            total_cost = input_cost + output_cost + cache_read_cost + cache_create_cost

            total_tokens = self.input_tokens + self.output_tokens + self.cache_read_tokens + self.cache_create_tokens

            return {
                "input": self.input_tokens,
                "output": self.output_tokens,
                "cache_read": self.cache_read_tokens,
                "cache_create": self.cache_create_tokens,
                "thinking": self.thinking_tokens,
                "total": total_tokens,
                "messages": self.total_messages,
                "model": self.current_model,
                "cost": total_cost,
                "cost_input": input_cost,
                "cost_output": output_cost,
                "cost_cache": cache_read_cost + cache_create_cost,
                "elapsed_hours": hours,
                "summary": self._format_summary(total_tokens, total_cost, hours),
            }

    def _format_summary(self, total_tokens, total_cost, hours):
        """格式化摘要文本"""
        inp_k = self.input_tokens / 1000
        out_k = self.output_tokens / 1000
        cache_k = (self.cache_read_tokens + self.cache_create_tokens) / 1000

        parts = []
        if inp_k > 0:
            parts.append(f"IN:{inp_k:.0f}K")
        if out_k > 0:
            parts.append(f"OUT:{out_k:.0f}K")
        if cache_k > 0:
            parts.append(f"Cache:{cache_k:.0f}K")

        token_str = "+".join(parts) if parts else "0"
        cost_str = f"${total_cost:.4f}" if total_cost > 0.0001 else "<$0.0001"

        summary = f"模型:{self.current_model or '?'}  Token:{token_str}  费用:{cost_str}  消息:{self.total_messages}  耗时:{hours:.1f}h"
        return summary

    def get_short_summary(self):
        """获取简短的单行摘要"""
        with self._lock:
            inp_k = self.input_tokens / 1000
            out_k = self.output_tokens / 1000
            total_k = (self.input_tokens + self.output_tokens) / 1000

            rates = MODEL_COST.get(self.current_model, MODEL_COST.get(self.cost_key, COST_PER_1K))
            cost = (self.input_tokens / 1000 * rates["input"]
                    + self.output_tokens / 1000 * rates["output"]
                    + self.cache_read_tokens / 1000 * rates["cache_read"]
                    + self.cache_create_tokens / 1000 * rates["cache_create"])

            return f"Token IN:{inp_k:.0f}K OUT:{out_k:.0f}K Total:{total_k:.0f}K  ${cost:.4f}"

    def reset(self):
        """重置计数器（新会话时使用）"""
        with self._lock:
            self.input_tokens = 0
            self.output_tokens = 0
            self.cache_read_tokens = 0
            self.cache_create_tokens = 0
            self.thinking_tokens = 0
            self.total_messages = 0
            self.current_model = "unknown"
            self._session_start = time.time()
            self._last_file = None
            self._last_pos = 0

    def stop(self):
        """停止追踪"""
        self._running = False


# ============================================================
# 独立测试
# ============================================================
if __name__ == "__main__":
    tracker = TokenTracker()
    print("Token 追踪器测试")
    print("=" * 50)
    print(f"监控目录: {CLAUDE_PROJECT_DIR}")
    print()

    latest = find_latest_session_file()
    if latest:
        print(f"最新会话: {latest.name}")
        print(f"文件大小: {latest.stat().st_size / 1024:.0f} KB")
    else:
        print("未找到会话文件")

    print()
    tracker.poll()
    stats = tracker.get_stats()
    print(stats["summary"])
