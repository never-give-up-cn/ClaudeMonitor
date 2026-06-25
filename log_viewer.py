#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对话日志查看器
=============
Tkinter 表格窗口，显示 Claude Code 对话日志，
支持按日期和关键词搜索、分页浏览。
"""

import sys
import json
from datetime import datetime
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import ttk, font
except ImportError:
    print("错误: 需要 tkinter")
    sys.exit(1)

# 尝试引入日志模块
try:
    from conversation_logger import ConversationLogger
except ImportError:
    ConversationLogger = None

# 字体配置
try:
    font.Font(family="微软雅黑", size=10).measure("测")
    FONT = ("微软雅黑", 10)
    FONT_BOLD = ("微软雅黑", 10, "bold")
    FONT_SMALL = ("微软雅黑", 9)
    FONT_TITLE = ("微软雅黑", 11, "bold")
except:
    FONT = ("TkDefaultFont", 10)
    FONT_BOLD = ("TkDefaultFont", 10, "bold")
    FONT_SMALL = ("TkDefaultFont", 9)
    FONT_TITLE = ("TkDefaultFont", 11, "bold")

FONT_EN = ("Consolas", 9)
FONT_EN_SM = ("Consolas", 8)


class LogViewer:
    """对话日志查看器窗口"""

    def __init__(self, parent=None, logger=None):
        self.logger = logger or (ConversationLogger() if ConversationLogger else None)

        # 创建窗口
        self.win = tk.Toplevel(parent) if parent else tk.Tk()
        self.win.title("Claude Code 对话日志")
        self.win.geometry("1100x600")
        self.win.minsize(900, 400)
        self.win.configure(bg="#1e1e1e")

        # 状态变量
        self.current_page = 1
        self.page_size = 50
        self.total_records = 0
        self.total_pages = 1
        self.all_data = []  # 缓存当前搜索的所有数据

        self._build_ui()
        self._load_data()

        # 如果不是 Toplevel，启动主循环
        if not parent:
            self.win.mainloop()

    def _build_ui(self):
        """构建界面"""
        win = self.win

        # ===== 搜索栏 =====
        search_frame = tk.Frame(win, bg="#252525", padx=14, pady=10)
        search_frame.pack(fill=tk.X)

        # 标题
        tk.Label(search_frame, text="对话日志",
                 font=FONT_TITLE, fg="#ffffff", bg="#252525").pack(side=tk.LEFT, padx=(0, 20))

        # 日期范围
        tk.Label(search_frame, text="日期从:", font=FONT_SMALL,
                 fg="#aaaaaa", bg="#252525").pack(side=tk.LEFT)
        self.date_from_entry = tk.Entry(search_frame, width=12, font=FONT_EN_SM,
                                        bg="#3a3a3a", fg="#ffffff", relief=tk.FLAT, insertbackground="#ffffff")
        self.date_from_entry.pack(side=tk.LEFT, padx=(2, 8))
        self.date_from_entry.insert(0, "")

        tk.Label(search_frame, text="到:", font=FONT_SMALL,
                 fg="#aaaaaa", bg="#252525").pack(side=tk.LEFT)
        self.date_to_entry = tk.Entry(search_frame, width=12, font=FONT_EN_SM,
                                      bg="#3a3a3a", fg="#ffffff", relief=tk.FLAT, insertbackground="#ffffff")
        self.date_to_entry.pack(side=tk.LEFT, padx=(2, 8))

        # 关键词搜索
        tk.Label(search_frame, text="搜索:", font=FONT_SMALL,
                 fg="#aaaaaa", bg="#252525").pack(side=tk.LEFT, padx=(10, 2))
        self.keyword_entry = tk.Entry(search_frame, width=20, font=FONT_EN_SM,
                                      bg="#3a3a3a", fg="#ffffff", relief=tk.FLAT, insertbackground="#ffffff")
        self.keyword_entry.pack(side=tk.LEFT, padx=(2, 8))
        self.keyword_entry.bind("<Return>", lambda e: self._search())

        # 搜索按钮
        self.search_btn = tk.Button(search_frame, text="搜索", command=self._search,
                                    font=FONT_SMALL, bg="#2a5c2a", fg="#ffffff",
                                    relief=tk.FLAT, padx=14, pady=2, cursor="hand2")
        self.search_btn.pack(side=tk.LEFT, padx=(4, 4))

        # 重置按钮
        self.reset_btn = tk.Button(search_frame, text="重置", command=self._reset,
                                   font=FONT_SMALL, bg="#5a5a5a", fg="#cccccc",
                                   relief=tk.FLAT, padx=14, pady=2, cursor="hand2")
        self.reset_btn.pack(side=tk.LEFT, padx=(4, 4))

        # 刷新按钮
        self.refresh_btn = tk.Button(search_frame, text="刷新", command=self._load_data,
                                     font=FONT_SMALL, bg="#3a3a5a", fg="#cccccc",
                                     relief=tk.FLAT, padx=14, pady=2, cursor="hand2")
        self.refresh_btn.pack(side=tk.LEFT, padx=(4, 4))

        # 汇总统计
        self.summary_label = tk.Label(search_frame, text="", font=FONT_SMALL,
                                      fg="#88cc88", bg="#252525")
        self.summary_label.pack(side=tk.RIGHT, padx=(10, 0))

        # ===== 分割线 =====
        sep = tk.Frame(win, height=1, bg="#333333")
        sep.pack(fill=tk.X)

        # ===== 表格 =====
        table_frame = tk.Frame(win, bg="#1e1e1e")
        table_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Treeview 样式
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview",
                        background="#2d2d2d",
                        foreground="#dddddd",
                        rowheight=26,
                        fieldbackground="#2d2d2d",
                        font=FONT_SMALL)
        style.configure("Treeview.Heading",
                        background="#3a3a3a",
                        foreground="#ffffff",
                        font=FONT_BOLD,
                        relief=tk.FLAT)
        style.map("Treeview",
                  background=[("selected", "#4a6a8a")],
                  foreground=[("selected", "#ffffff")])

        # 列定义
        columns = ("id", "timestamp", "model", "user_input", "assistant_output",
                   "input_tokens", "output_tokens", "total_tokens", "cost")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings",
                                 selectmode="browse")

        # 列头
        col_configs = [
            ("id", "ID", 36, tk.CENTER),
            ("timestamp", "时间", 140, tk.CENTER),
            ("model", "模型", 100, tk.CENTER),
            ("user_input", "用户输入", 260, tk.W),
            ("assistant_output", "AI 返回", 260, tk.W),
            ("input_tokens", "输入T", 65, tk.CENTER),
            ("output_tokens", "输出T", 65, tk.CENTER),
            ("total_tokens", "合计T", 70, tk.CENTER),
            ("cost", "费用$", 72, tk.CENTER),
        ]
        for col, text, width, anchor in col_configs:
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor=anchor, minwidth=50)

        # 滚动条
        v_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=v_scroll.set)
        h_scroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(xscrollcommand=h_scroll.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        # 双击查看详情
        self.tree.bind("<Double-1>", self._show_detail)

        # ===== 底部 =====
        bottom_frame = tk.Frame(win, bg="#1e1e1e", padx=14, pady=8)
        bottom_frame.pack(fill=tk.X)

        # 分页信息
        self.page_info_label = tk.Label(bottom_frame, text="",
                                        font=FONT_SMALL, fg="#aaaaaa", bg="#1e1e1e")
        self.page_info_label.pack(side=tk.LEFT)

        # 分页按钮
        self.first_btn = tk.Button(bottom_frame, text="|<", command=lambda: self._go_page(1),
                                   font=FONT_SMALL, bg="#3a3a3a", fg="#cccccc",
                                   relief=tk.FLAT, padx=8, pady=1, cursor="hand2")
        self.first_btn.pack(side=tk.RIGHT, padx=(2, 2))

        self.prev_btn = tk.Button(bottom_frame, text="<", command=self._prev_page,
                                  font=FONT_SMALL, bg="#3a3a3a", fg="#cccccc",
                                  relief=tk.FLAT, padx=10, pady=1, cursor="hand2")
        self.prev_btn.pack(side=tk.RIGHT, padx=(2, 2))

        self.page_entry = tk.Entry(bottom_frame, width=5, font=FONT_EN_SM,
                                   bg="#3a3a3a", fg="#ffffff", relief=tk.FLAT,
                                   insertbackground="#ffffff", justify=tk.CENTER)
        self.page_entry.pack(side=tk.RIGHT, padx=(2, 2))
        self.page_entry.bind("<Return>", lambda e: self._jump_page())

        self.page_total_label = tk.Label(bottom_frame, text="/ 1",
                                         font=FONT_SMALL, fg="#aaaaaa", bg="#1e1e1e")
        self.page_total_label.pack(side=tk.RIGHT, padx=(0, 4))

        self.next_btn = tk.Button(bottom_frame, text=">", command=self._next_page,
                                  font=FONT_SMALL, bg="#3a3a3a", fg="#cccccc",
                                  relief=tk.FLAT, padx=10, pady=1, cursor="hand2")
        self.next_btn.pack(side=tk.RIGHT, padx=(2, 2))

        self.last_btn = tk.Button(bottom_frame, text=">|", command=self._go_last_page,
                                  font=FONT_SMALL, bg="#3a3a3a", fg="#cccccc",
                                  relief=tk.FLAT, padx=8, pady=1, cursor="hand2")
        self.last_btn.pack(side=tk.RIGHT, padx=(2, 4))

        # 每页条数
        tk.Label(bottom_frame, text="每页:", font=FONT_SMALL,
                 fg="#888888", bg="#1e1e1e").pack(side=tk.RIGHT, padx=(10, 2))
        self.page_size_combo = ttk.Combobox(bottom_frame, values=["20", "50", "100", "200"],
                                             width=5, font=FONT_EN_SM, state="readonly")
        self.page_size_combo.set(str(self.page_size))
        self.page_size_combo.pack(side=tk.RIGHT, padx=(2, 0))
        self.page_size_combo.bind("<<ComboboxSelected>>", lambda e: self._change_page_size())

    def _load_data(self):
        """加载日志数据"""
        if not self.logger:
            self._show_empty("日志模块未初始化")
            return

        # 先轮询新数据
        self.logger.poll()

        # 搜索
        self._search()

    def _search(self):
        """执行搜索"""
        if not self.logger:
            return

        date_from = self.date_from_entry.get().strip()
        date_to = self.date_to_entry.get().strip()
        keyword = self.keyword_entry.get().strip()

        try:
            records, total, total_pages = self.logger.query(
                date_from=date_from,
                date_to=date_to,
                keyword=keyword,
                page=self.current_page,
                page_size=self.page_size,
            )
        except Exception:
            records, total, total_pages = [], 0, 1

        self.total_records = total
        self.total_pages = total_pages

        # 自动调整页码
        if self.current_page > self.total_pages:
            self.current_page = self.total_pages

        self._render_table(records)
        self._update_pagination()

        # 更新汇总
        summary = self.logger.get_summary()
        self.summary_label.config(
            text=f"总计 {summary['turns']} 轮  Token: {summary['input_tokens']:,}↑ {summary['output_tokens']:,}↓  费用: ${summary['cost']:.4f}"
        )

    def _reset(self):
        """重置搜索条件"""
        self.date_from_entry.delete(0, tk.END)
        self.date_to_entry.delete(0, tk.END)
        self.keyword_entry.delete(0, tk.END)
        self.current_page = 1
        self._search()

    def _render_table(self, records):
        """渲染表格数据"""
        # 清空
        for row in self.tree.get_children():
            self.tree.delete(row)

        if not records:
            self.tree.insert("", tk.END, values=(
                "--", "--", "--", "没有匹配的日志记录", "--", "--", "--", "--", "--"
            ))
            return

        for r in records:
            user_input = (r.get("user_input") or "")
            if len(user_input) > 50:
                user_input = user_input[:47] + "..."

            ai_output = (r.get("assistant_output") or "")
            if len(ai_output) > 50:
                ai_output = ai_output[:47] + "..."

            cost = r.get("cost", 0)

            self.tree.insert("", tk.END, values=(
                r.get("id", ""),
                r.get("timestamp", ""),
                self._short_model(r.get("model", "")),
                user_input,
                ai_output,
                self._fmt_num(r.get("input_tokens", 0)),
                self._fmt_num(r.get("output_tokens", 0)),
                self._fmt_num(r.get("total_tokens", 0)),
                f"{cost:.6f}" if isinstance(cost, (int, float)) else str(cost),
            ))

    def _short_model(self, model):
        """缩短模型名显示"""
        short = {
            "deepseek-v4-flash": "deepseek-v4",
            "claude-sonnet-4-20250514": "sonnet-4",
            "claude-haiku-3-5-20241022": "haiku-3.5",
        }
        return short.get(model, model[:20])

    def _fmt_num(self, n):
        """格式化数字"""
        if isinstance(n, int):
            return f"{n:,}"
        return str(n)

    def _update_pagination(self):
        """更新分页状态"""
        # 信息
        start = (self.current_page - 1) * self.page_size + 1 if self.total_records > 0 else 0
        end = min(self.current_page * self.page_size, self.total_records)
        self.page_info_label.config(
            text=f"共 {self.total_records} 条  |  第 {start}-{end} 条  |  {self.total_pages} 页"
        )

        # 页码输入
        self.page_entry.delete(0, tk.END)
        self.page_entry.insert(0, str(self.current_page))
        self.page_total_label.config(text=f"/ {self.total_pages}")

        # 按钮状态
        self.first_btn.config(state=tk.NORMAL if self.current_page > 1 else tk.DISABLED)
        self.prev_btn.config(state=tk.NORMAL if self.current_page > 1 else tk.DISABLED)
        self.next_btn.config(state=tk.NORMAL if self.current_page < self.total_pages else tk.DISABLED)
        self.last_btn.config(state=tk.NORMAL if self.current_page < self.total_pages else tk.DISABLED)

    def _prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self._search()

    def _next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self._search()

    def _go_page(self, page):
        self.current_page = page
        self._search()

    def _go_last_page(self):
        self.current_page = self.total_pages
        self._search()

    def _jump_page(self):
        try:
            page = int(self.page_entry.get())
            if 1 <= page <= self.total_pages:
                self.current_page = page
                self._search()
        except ValueError:
            pass

    def _change_page_size(self):
        try:
            self.page_size = int(self.page_size_combo.get())
            self.current_page = 1
            self._search()
        except ValueError:
            pass

    def _show_detail(self, event):
        """双击查看记录详情"""
        selected = self.tree.selection()
        if not selected:
            return

        values = self.tree.item(selected[0], "values")
        if not values or values[0] == "--":
            return

        record_id = int(values[0])

        # 弹出详情窗口
        detail = tk.Toplevel(self.win)
        detail.title(f"日志详情 #{record_id}")
        detail.geometry("680x560")
        detail.configure(bg="#1e1e1e")

        # 从日志文件读取完整记录
        record = self._get_full_record(record_id)
        if not record:
            record = {}

        frame = tk.Frame(detail, bg="#1e1e1e", padx=20, pady=16)
        frame.pack(fill=tk.BOTH, expand=True)

        # -- 基本信息 --
        info_frame = tk.Frame(frame, bg="#1e1e1e")
        info_frame.pack(fill=tk.X)

        fields = [
            ("ID", str(record.get("id", values[0]))),
            ("时间", record.get("timestamp", values[1])),
            ("模型", record.get("model", values[2])),
            ("输入 Token", self._fmt_num(record.get("input_tokens", values[4]))),
            ("输出 Token", self._fmt_num(record.get("output_tokens", values[5]))),
            ("费用 ($)", f"{record.get('cost', 0):.6f}" if isinstance(record.get('cost'), (int, float)) else values[8]),
        ]

        for label, val in fields:
            row = tk.Frame(info_frame, bg="#1e1e1e")
            row.pack(fill=tk.X, pady=1)
            tk.Label(row, text=label + ":", font=FONT_BOLD,
                     fg="#88aacc", bg="#1e1e1e", width=10, anchor=tk.W).pack(side=tk.LEFT)
            tk.Label(row, text=val, font=FONT_EN,
                     fg="#dddddd", bg="#1e1e1e", anchor=tk.W).pack(side=tk.LEFT)

        # -- Notebook: 用户输入 / AI 输出 / 思考过程 --
        sep = tk.Frame(frame, height=1, bg="#333333")
        sep.pack(fill=tk.X, pady=(10, 6))

        note = ttk.Notebook(frame)
        note.pack(fill=tk.BOTH, expand=True)

        style = ttk.Style()
        style.configure("TNotebook", background="#252525", borderwidth=0)
        style.configure("TNotebook.Tab", background="#3a3a3a", foreground="#cccccc",
                        padding=[10, 2], font=FONT_SMALL)
        style.map("TNotebook.Tab", background=[("selected", "#2a5a5a")],
                  foreground=[("selected", "#ffffff")])

        # 用户输入 Tab
        user_tab = self._make_text_tab(note, record.get("user_input", ""),
                                       "用户输入", "#1e2a1e")
        note.add(user_tab, text="  用户输入  ")

        # AI 输出 Tab
        ai_tab = self._make_text_tab(note, record.get("assistant_output", ""),
                                      "AI 返回", "#1e1e2a")
        note.add(ai_tab, text="  AI 返回  ")

        # 思考过程 Tab
        thinking_tab = self._make_text_tab(note, record.get("assistant_thinking", ""),
                                            "思考过程", "#2a1e1e")
        note.add(thinking_tab, text="  思考过程  ")

        # -- 关闭按钮 --
        btn_frame = tk.Frame(detail, bg="#1e1e1e", pady=10)
        btn_frame.pack(fill=tk.X)
        tk.Button(btn_frame, text="关闭", command=detail.destroy,
                  font=FONT_SMALL, bg="#5a1a1a", fg="#cccccc",
                  relief=tk.FLAT, padx=20, pady=2, cursor="hand2").pack()

    def _make_text_tab(self, parent, content, label, bg_color):
        """创建一个带滚动文本的 Tab 页"""
        tab = tk.Frame(parent, bg=bg_color, padx=8, pady=8)

        text_widget = tk.Text(tab, font=FONT_EN_SM, bg=bg_color, fg="#cccccc",
                              relief=tk.FLAT, wrap=tk.WORD, padx=8, pady=6)
        text_widget.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        scroll = ttk.Scrollbar(tab, orient=tk.VERTICAL, command=text_widget.yview)
        text_widget.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        display_text = content or "(无内容)"
        text_widget.insert("1.0", display_text)
        text_widget.config(state=tk.DISABLED)
        return tab

    def _get_full_record(self, record_id):
        """从日志文件中读取指定 ID 的完整记录"""
        if not self.logger or not self.logger.log_file.exists():
            return None

        try:
            with open(self.logger.log_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        if record.get("id") == record_id:
                            return record
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass
        return None

    def _show_empty(self, msg):
        """显示空状态"""
        for row in self.tree.get_children():
            self.tree.delete(row)
        self.tree.insert("", tk.END, values=("--", "--", "--", msg, "--", "--", "--", "--", "--", "--"))
        self.page_info_label.config(text="0 条记录")
        self.first_btn.config(state=tk.DISABLED)
        self.prev_btn.config(state=tk.DISABLED)
        self.next_btn.config(state=tk.DISABLED)
        self.last_btn.config(state=tk.DISABLED)

    def close(self):
        """关闭窗口"""
        self.win.destroy()


# ============================================================
# 独立启动
# ============================================================
if __name__ == "__main__":
    LogViewer()
