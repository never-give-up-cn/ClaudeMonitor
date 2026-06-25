#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对话日志记录器
==============
从 Claude Code 会话文件中提取每一轮的用户输入和返回数据（Token 用量、费用），
写入结构化日志文件，供日志查看器查询。
"""

import json
import os
import time
import threading
from pathlib import Path
from datetime import datetime, timedelta

# Claude Code 项目会话目录
CLAUDE_PROJECT_DIR = Path.home() / ".claude" / "projects"

# 日志文件
DEFAULT_LOG_FILE = Path(__file__).parent / "conversation_log.jsonl"

# Token 单价参考
MODEL_RATES = {
    "deepseek-v4-flash": {"input": 0.00015, "output": 0.0006, "cache_read": 0.000015, "cache_create": 0.00018},
    "claude-sonnet-4-20250514": {"input": 0.003, "output": 0.015, "cache_read": 0.0003, "cache_create": 0.00375},
    "claude-haiku-3-5-20241022": {"input": 0.0008, "output": 0.004, "cache_read": 0.00008, "cache_create": 0.001},
}

DEFAULT_RATES = {"input": 0.003, "output": 0.015, "cache_read": 0.0003, "cache_create": 0.00375}


def calculate_cost(usage, model=""):
    """根据 usage 和模型计算费用"""
    rates = MODEL_RATES.get(model, DEFAULT_RATES)
    return (
        usage.get("input_tokens", 0) / 1000 * rates["input"]
        + usage.get("output_tokens", 0) / 1000 * rates["output"]
        + usage.get("cache_read_input_tokens", 0) / 1000 * rates["cache_read"]
        + usage.get("cache_creation_input_tokens", 0) / 1000 * rates["cache_create"]
    )




def get_latest_session_file():
    """找到最新的会话 JSONL 文件"""
    if not CLAUDE_PROJECT_DIR.exists():
        return None
    try:
        candidates = []
        for d in CLAUDE_PROJECT_DIR.iterdir():
            if d.is_dir():
                for f in d.glob("*.jsonl"):
                    candidates.append(f)
        if not candidates:
            return None
        return max(candidates, key=lambda f: f.stat().st_mtime)
    except (PermissionError, OSError):
        return None


class ConversationLogger:
    """对话日志记录器

    从会话文件中提取用户→助手的每一轮对话，记录 Token 用量和费用。
    支持增量解析和日志查询。
    """

    def __init__(self, log_file=None):
        self.log_file = Path(log_file or DEFAULT_LOG_FILE)
        self._lock = threading.Lock()
        self._running = True
        self._last_file = None
        self._last_pos = 0
        self._last_turn_id = 0
        self._pending_user = None   # 缓存当前用户输入
        self._pending_output = {"text": "", "thinking": ""}  # 缓存 assistant 输出
        self._pending_usage = None  # 缓存当前 turn 的 usage 数据
        self._pending_model = ""    # 缓存当前 turn 的模型名

        # 初始化时读取已有日志的最大 ID
        self._load_last_id()

    def _load_last_id(self):
        """读取已有日志的最大 ID"""
        try:
            if self.log_file.exists():
                with open(self.log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                data = json.loads(line)
                                tid = data.get("id", 0)
                                if tid > self._last_turn_id:
                                    self._last_turn_id = tid
                            except json.JSONDecodeError:
                                continue
        except (FileNotFoundError, PermissionError):
            pass

    def poll(self):
        """轮询最新会话文件，提取新对话并记录"""
        if not self._running:
            return

        latest = get_latest_session_file()
        if not latest:
            return

        if latest != self._last_file:
            self._flush_pending()
            self._last_file = latest
            self._last_pos = 0
            self._pending_user = None
            self._pending_output = {"text": "", "thinking": ""}
            self._pending_usage = None

        self._parse_file(latest)

    def _parse_file(self, filepath):
        """增量解析会话文件，提取用户→助手配对"""
        try:
            size = filepath.stat().st_size
            if size <= self._last_pos:
                return

            with open(filepath, "r", encoding="utf-8") as f:
                f.seek(self._last_pos)
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        self._process_line(data)
                    except json.JSONDecodeError:
                        continue

            self._last_pos = size
        except (FileNotFoundError, PermissionError, OSError):
            pass

    def _process_line(self, data):
        """处理一行会话数据"""
        tp = data.get("type")
        msg = data.get("message", {})

        if tp == "user":
            # 有实际文本 → 新的一轮开始，先保存上一轮
            user_text = self._extract_user_text(msg)
            if user_text:
                self._flush_pending()
                self._pending_user = {
                    "timestamp": data.get("timestamp", ""),
                    "user_input": user_text,
                }
                self._pending_output = {"text": "", "thinking": ""}
                self._pending_usage = None
                self._pending_model = ""
            # 无文本（tool_result 反馈）→ 跳过

        elif tp == "assistant":
            # 累积输出内容
            self._accumulate_output(msg)

            usage = msg.get("usage", {})
            if usage and usage.get("input_tokens") and self._pending_user:
                if not self._pending_usage:
                    self._pending_usage = usage
                    self._pending_model = msg.get("model", "unknown")

    def _extract_user_text(self, msg):
        """提取用户实际输入文本，跳过 tool_result 等非用户内容"""
        content = msg.get("content", "")
        if isinstance(content, str):
            text = content.strip()
            return text[:1000] if text else ""
        if isinstance(content, list):
            texts = []
            for block in content:
                if block.get("type") == "text":
                    t = block.get("text", "").strip()
                    if t:
                        texts.append(t)
            combined = " ".join(texts)
            return combined[:1000] if combined else ""
        return ""

    def _accumulate_output(self, msg):
        """累积 assistant 输出的文本和思考内容"""
        content = msg.get("content", [])
        if not isinstance(content, list):
            return
        for block in content:
            ct = block.get("type", "")
            if ct == "text":
                txt = block.get("text", "")
                if txt:
                    self._pending_output["text"] += txt
            elif ct == "thinking":
                txt = block.get("thinking", "")
                if txt:
                    self._pending_output["thinking"] += txt

    def _flush_pending(self):
        """将上一轮的待写入记录保存到日志"""
        if not self._pending_user or not self._pending_usage:
            return

        usage = self._pending_usage
        model = self._pending_model or "unknown"
        ts = self._pending_user["timestamp"]
        cost = calculate_cost(usage, model)

        # 截断输出文本（最多 5000 字符）
        output_text = self._pending_output.get("text", "").strip()
        output_thinking = self._pending_output.get("thinking", "").strip()
        if len(output_text) > 5000:
            output_text = output_text[:5000] + "\n\n[... 已截断 ...]"
        if len(output_thinking) > 3000:
            output_thinking = output_thinking[:3000] + "\n\n[... 已截断 ...]"

        self._last_turn_id += 1
        record = {
            "id": self._last_turn_id,
            "timestamp": self._normalize_ts(ts),
            "user_input": self._pending_user["user_input"][:1000],
            "assistant_output": output_text,
            "assistant_thinking": output_thinking,
            "model": model,
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "cache_read_tokens": usage.get("cache_read_input_tokens", 0),
            "cache_create_tokens": usage.get("cache_creation_input_tokens", 0),
            "total_tokens": (usage.get("input_tokens", 0)
                             + usage.get("output_tokens", 0)
                             + usage.get("cache_read_input_tokens", 0)
                             + usage.get("cache_creation_input_tokens", 0)),
            "cost": round(cost, 6),
            "session_id": "",  # 从消息中提取 sessionId 稍复杂，不影响主要功能
        }
        self._write_record(record)

        # 清空待写入状态
        self._pending_user = None
        self._pending_output = {"text": "", "thinking": ""}
        self._pending_usage = None
        self._pending_model = ""

    def _normalize_ts(self, ts_str):
        """标准化时间戳格式"""
        if not ts_str:
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            # ISO 格式: 2026-06-25T14:51:51.297Z
            if "T" in ts_str:
                ts_str = ts_str.replace("Z", "").split(".")[0]
                return ts_str.replace("T", " ")
            return ts_str[:19]
        except Exception:
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _write_record(self, record):
        """写入一条日志记录"""
        try:
            with self._lock:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass

    # ============================================================
    # 查询接口
    # ============================================================

    def query(self, date_from="", date_to="", keyword="", page=1, page_size=50):
        """查询日志记录，支持按日期和关键词搜索，分页返回"""
        results = []
        total = 0

        if not self.log_file.exists():
            return [], 0, 0

        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if not self._match(record, date_from, date_to, keyword):
                        continue

                    total += 1
                    results.append(record)
        except (FileNotFoundError, PermissionError):
            return [], 0, 0

        # 按 ID 降序排列（最新的在前）
        results.sort(key=lambda r: r.get("id", 0), reverse=True)

        # 分页
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))
        start = (page - 1) * page_size
        end = start + page_size
        page_data = results[start:end]

        return page_data, total, total_pages

    def _match(self, record, date_from, date_to, keyword):
        """检查记录是否匹配搜索条件"""
        ts = record.get("timestamp", "")

        # 日期范围过滤
        if date_from and ts < date_from:
            return False
        if date_to:
            # date_to 是当天结束时间
            date_to_end = date_to + " 23:59:59" if len(date_to) <= 10 else date_to
            if ts > date_to_end:
                return False

        # 关键词搜索
        if keyword:
            kw = keyword.lower()
            user_input = (record.get("user_input") or "").lower()
            assistant_out = (record.get("assistant_output") or "").lower()
            assistant_think = (record.get("assistant_thinking") or "").lower()
            model = (record.get("model") or "").lower()
            rid = str(record.get("id", ""))
            if (kw not in user_input and kw not in assistant_out
                    and kw not in assistant_think and kw not in model
                    and kw not in rid):
                return False

        return True

    def get_summary(self):
        """获取当前日志的汇总统计"""
        total_turns = 0
        total_input = 0
        total_output = 0
        total_cost = 0.0

        if not self.log_file.exists():
            return {"turns": 0, "input_tokens": 0, "output_tokens": 0, "cost": 0.0}

        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        total_turns += 1
                        total_input += record.get("input_tokens", 0)
                        total_output += record.get("output_tokens", 0)
                        total_cost += record.get("cost", 0.0)
                    except json.JSONDecodeError:
                        continue
        except (FileNotFoundError, PermissionError):
            pass

        return {
            "turns": total_turns,
            "input_tokens": total_input,
            "output_tokens": total_output,
            "cost": round(total_cost, 4),
        }

    def flush(self):
        """手动刷新待写入的记录（会话结束或停止前调用）"""
        self._flush_pending()

    def stop(self):
        self.flush()
        self._running = False


# ============================================================
# 独立测试
# ============================================================
if __name__ == "__main__":
    logger = ConversationLogger()
    print("对话日志测试")
    print("=" * 50)

    # 测试轮询
    print("\n[轮询最新会话...]")
    logger.poll()
    summary = logger.get_summary()
    print(f"已记录: {summary['turns']} 轮对话")
    print(f"输入 Tokens: {summary['input_tokens']:,}")
    print(f"输出 Tokens: {summary['output_tokens']:,}")
    print(f"总费用: ${summary['cost']:.4f}")

    # 测试查询
    print("\n[查询最新 3 条记录:]")
    records, total, pages = logger.query(page=1, page_size=3)
    for r in records:
        inp = r.get("input_tokens", 0)
        out = r.get("output_tokens", 0)
        cost = r.get("cost", 0)
        inp_text = (r.get("user_input") or "")[:60]
        print(f"  #{r['id']} [{r['timestamp']}] IN:{inp} OUT:{out} ${cost:.4f} | {inp_text}")

    print(f"\n总计: {total} 条, 共 {pages} 页")
    print(f"日志文件: {logger.log_file}")
