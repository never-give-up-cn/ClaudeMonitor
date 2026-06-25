#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web 版日志查看器
================
基于 Python 内置 http.server，无需额外依赖。
在浏览器中查看 Claude Code 对话日志，支持搜索和分页。

用法:
    python web_viewer.py
    或从 GUI 点击 "Web 日志" 按钮
"""

import json
import webbrowser
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path

try:
    from conversation_logger import ConversationLogger
except ImportError:
    ConversationLogger = None

HOST = "127.0.0.1"
PORT = 5858

logger = None  # 全局引用


class LogAPIHandler(BaseHTTPRequestHandler):
    """HTTP API: 提供日志数据查询"""

    def log_message(self, format, *args):
        pass  # 禁止输出请求日志

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self._serve_html()
        elif path == "/api/logs":
            self._serve_logs(parsed)
        elif path == "/api/summary":
            self._serve_summary()
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404")

    def _serve_html(self):
        """返回主页面 HTML"""
        html = self._get_html()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _serve_logs(self, parsed):
        """返回日志 JSON 数据"""
        params = parse_qs(parsed.query)
        page = int(params.get("page", [1])[0])
        page_size = int(params.get("page_size", [50])[0])
        date_from = params.get("date_from", [""])[0]
        date_to = params.get("date_to", [""])[0]
        keyword = params.get("keyword", [""])[0]

        if logger:
            try:
                records, total, total_pages = logger.query(
                    date_from=date_from, date_to=date_to,
                    keyword=keyword, page=page, page_size=page_size
                )
                # 序列化时处理特殊字符
                data = json.dumps({
                    "records": records,
                    "total": total,
                    "total_pages": total_pages,
                    "page": page,
                }, ensure_ascii=False, default=str)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data.encode("utf-8"))
                return
            except Exception as e:
                pass

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps({"records": [], "total": 0, "total_pages": 0}).encode("utf-8"))

    def _serve_summary(self):
        """返回汇总数据"""
        if logger:
            try:
                summary = logger.get_summary()
                data = json.dumps(summary, ensure_ascii=False, default=str)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data.encode("utf-8"))
                return
            except Exception:
                pass
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"{}")

    def _get_html(self):
        """生成 Web UI HTML"""
        return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Claude Code 对话日志</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', system-ui, sans-serif; background: #1a1a1a; color: #ddd; min-height: 100vh; }
.header { background: #252525; padding: 16px 24px; border-bottom: 1px solid #333; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; }
.header h1 { font-size: 18px; color: #88cc88; }
.summary { font-size: 13px; color: #88cc88; }
.search-bar { background: #252525; padding: 12px 24px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; border-bottom: 1px solid #333; }
.search-bar label { font-size: 13px; color: #aaa; }
.search-bar input { background: #3a3a3a; border: 1px solid #555; color: #fff; padding: 6px 10px; border-radius: 4px; font-size: 13px; outline: none; }
.search-bar input:focus { border-color: #4a9eff; }
.search-bar button { background: #2a5c2a; color: #fff; border: none; padding: 6px 16px; border-radius: 4px; cursor: pointer; font-size: 13px; }
.search-bar button:hover { background: #3a7a3a; }
.search-bar .btn-reset { background: #5a5a5a; }
.search-bar .btn-reset:hover { background: #7a7a7a; }
.table-wrap { padding: 12px 24px; overflow-x: auto; flex: 1; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { background: #333; color: #fff; padding: 8px 10px; text-align: left; white-space: nowrap; cursor: pointer; position: sticky; top: 0; z-index: 1; }
th:hover { background: #444; }
td { padding: 7px 10px; border-bottom: 1px solid #2a2a2a; max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
tr:hover td { background: #2a3a2a; }
.pagination { padding: 12px 24px; display: flex; align-items: center; justify-content: center; gap: 6px; flex-wrap: wrap; border-top: 1px solid #333; }
.pagination button { background: #3a3a3a; color: #ccc; border: none; padding: 5px 12px; border-radius: 3px; cursor: pointer; font-size: 13px; }
.pagination button:disabled { opacity: 0.4; cursor: default; }
.pagination button:hover:not(:disabled) { background: #555; }
.pagination span { color: #aaa; font-size: 13px; }
.pagination input { background: #3a3a3a; border: 1px solid #555; color: #fff; width: 50px; padding: 4px 8px; border-radius: 3px; text-align: center; font-size: 13px; }
.loading { text-align: center; padding: 40px; color: #666; font-size: 16px; }
.modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 999; }
.modal-content { background: #252525; margin: 5% auto; padding: 20px; width: 80%; max-width: 750px; max-height: 80vh; border-radius: 8px; overflow-y: auto; }
.modal-content h2 { color: #88cc88; margin-bottom: 12px; font-size: 16px; }
.modal-content .field { margin-bottom: 8px; }
.modal-content .field-label { color: #88aacc; font-size: 12px; font-weight: bold; }
.modal-content .field-value { color: #ddd; font-size: 13px; white-space: pre-wrap; word-break: break-all; background: #1e1e1e; padding: 8px; border-radius: 4px; margin-top: 2px; max-height: 200px; overflow-y: auto; }
.modal-close { float: right; background: #5a1a1a; color: #ccc; border: none; padding: 5px 16px; border-radius: 4px; cursor: pointer; }
.modal-close:hover { background: #7a2a2a; }
</style>
</head>
<body>
<div class="header">
    <h1>📋 Claude Code 对话日志</h1>
    <div class="summary" id="summary">加载中...</div>
    <button onclick="location.reload()" style="background:#3a3a5a;color:#ccc;border:none;padding:5px 14px;border-radius:4px;cursor:pointer;">🔄 刷新</button>
</div>
<div class="search-bar">
    <label>日期从:</label>
    <input type="date" id="dateFrom">
    <label>到:</label>
    <input type="date" id="dateTo">
    <label>搜索:</label>
    <input type="text" id="keyword" placeholder="搜索用户输入 / AI 返回..." style="width:220px;">
    <button onclick="search()">🔍 搜索</button>
    <button class="btn-reset" onclick="resetSearch()">↺ 重置</button>
</div>
<div class="table-wrap">
    <table>
        <thead><tr>
            <th>ID</th>
            <th>时间</th>
            <th>模型</th>
            <th>用户输入</th>
            <th>AI 返回</th>
            <th>输入T</th>
            <th>输出T</th>
            <th>合计T</th>
            <th>费用</th>
        </tr></thead>
        <tbody id="logBody"></tbody>
    </table>
    <div class="loading" id="loading">加载中...</div>
</div>
<div class="pagination" id="pagination"></div>
<div class="modal" id="modal" onclick="if(event.target==this)closeModal()">
    <div class="modal-content">
        <button class="modal-close" onclick="closeModal()">关闭</button>
        <h2 id="modalTitle">详情</h2>
        <div id="modalBody"></div>
    </div>
</div>
<script>
let currentPage = 1, totalPages = 1, pageSize = 50;
function loadSummary() {
    fetch('/api/summary').then(r=>r.json()).then(d=>{
        document.getElementById('summary').textContent =
            '总计 ' + (d.turns||0) + ' 轮  Token: ' + ((d.input_tokens||0)/1000).toFixed(1) + 'K↑ ' +
            ((d.output_tokens||0)/1000).toFixed(1) + 'K↓  费用: $' + (d.cost||0).toFixed(4);
    }).catch(()=>{});
}
function search() {
    currentPage = 1;
    loadPage();
}
function resetSearch() {
    document.getElementById('dateFrom').value = '';
    document.getElementById('dateTo').value = '';
    document.getElementById('keyword').value = '';
    currentPage = 1;
    loadPage();
}
function loadPage() {
    const df = document.getElementById('dateFrom').value;
    const dt = document.getElementById('dateTo').value;
    const kw = encodeURIComponent(document.getElementById('keyword').value);
    const url = '/api/logs?page=' + currentPage + '&page_size=' + pageSize +
        '&date_from=' + df + '&date_to=' + dt + '&keyword=' + kw;
    document.getElementById('loading').style.display = 'block';
    fetch(url).then(r=>r.json()).then(d=>{
        document.getElementById('loading').style.display = 'none';
        totalPages = d.total_pages || 1;
        renderTable(d.records || []);
        renderPagination(d.total || 0, d.page || 1);
    }).catch(()=>{
        document.getElementById('loading').textContent = '加载失败';
    });
}
function renderTable(records) {
    const tbody = document.getElementById('logBody');
    tbody.innerHTML = '';
    if (!records.length) {
        tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:#666;padding:30px;">暂无数据</td></tr>';
        return;
    }
    for (const r of records) {
        const inp = (r.user_input || '').slice(0, 80);
        const out = (r.assistant_output || '').slice(0, 80);
        const model = (r.model || '').replace('deepseek-v4-flash','ds-v4').replace('claude-sonnet-4-20250514','sonnet').slice(0, 15);
        const tr = document.createElement('tr');
        tr.style.cursor = 'pointer';
        tr.ondblclick = () => showDetail(r);
        tr.innerHTML = '<td>' + (r.id||'') + '</td><td>' + (r.timestamp||'').slice(5,16) +
            '</td><td>' + model + '</td><td title="' + escAttr(inp) + '">' + esc(inp) +
            '</td><td title="' + escAttr(out) + '">' + esc(out) +
            '</td><td>' + (r.input_tokens||0) + '</td><td>' + (r.output_tokens||0) +
            '</td><td>' + (r.total_tokens||0) + '</td><td>$' + (r.cost||0).toFixed(6) + '</td>';
        tbody.appendChild(tr);
    }
}
function renderPagination(total, page) {
    const p = document.getElementById('pagination');
    if (!total) { p.innerHTML = '<span>0 条记录</span>'; return; }
    const start = (page-1)*pageSize+1, end = Math.min(page*pageSize, total);
    let html = '<button onclick="goPage(1)"' + (page<=1?' disabled':'') + '>|&lt;</button>';
    html += '<button onclick="goPage('+(page-1)+')"' + (page<=1?' disabled':'') + '>&lt;</button>';
    html += '<span> 第 ' + page + ' / ' + totalPages + ' 页 </span>';
    html += '<button onclick="goPage('+(page+1)+')"' + (page>=totalPages?' disabled':'') + '>&gt;</button>';
    html += '<button onclick="goPage('+totalPages+')"' + (page>=totalPages?' disabled':'') + '>&gt;|</button>';
    html += '<span style="margin-left:16px;">共 ' + total + ' 条 (' + start + '-' + end + ')</span>';
    p.innerHTML = html;
}
function goPage(p) { if(p>=1&&p<=totalPages){currentPage=p;loadPage();} }
function showDetail(r) {
    document.getElementById('modalTitle').textContent = '详情 #' + (r.id||'');
    const body = document.getElementById('modalBody');
    body.innerHTML = '';
    const fields = [
        ['时间', r.timestamp],
        ['模型', r.model],
        ['用户输入', r.user_input],
        ['AI 返回', r.assistant_output],
        ['思考过程', r.assistant_thinking],
        ['输入 Token', r.input_tokens], ['输出 Token', r.output_tokens],
        ['缓存读', r.cache_read_tokens], ['缓存创建', r.cache_create_tokens],
        ['合计 Token', r.total_tokens], ['费用', '$' + (r.cost||0).toFixed(6)],
    ];
    for (const [label, val] of fields) {
        if (!val) continue;
        const div = document.createElement('div');
        div.className = 'field';
        div.innerHTML = '<div class="field-label">' + label + '</div><div class="field-value">' + esc(String(val)) + '</div>';
        body.appendChild(div);
    }
    document.getElementById('modal').style.display = 'block';
}
function closeModal() { document.getElementById('modal').style.display = 'none'; }
function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function escAttr(s) { return esc(s).replace(/"/g,'&quot;'); }
document.getElementById('keyword').addEventListener('keyup', e => { if(e.key==='Enter') search(); });
loadSummary();
loadPage();
</script>
</body>
</html>"""


def start_server(logger_instance=None, host=HOST, port=PORT):
    """启动 Web 服务器"""
    global logger
    if logger_instance:
        logger = logger_instance
    elif ConversationLogger:
        logger = ConversationLogger()
        logger.poll()

    server = HTTPServer((host, port), LogAPIHandler)
    print(f"[Web 日志] http://{host}:{port}")
    webbrowser.open(f"http://{host}:{port}")
    server.serve_forever()


def start_web_viewer(logger_instance=None):
    """在后台线程启动 Web 查看器"""
    thread = threading.Thread(target=start_server, args=(logger_instance,), daemon=True)
    thread.start()


if __name__ == "__main__":
    print("启动 Claude Code Web 日志查看器...")
    print(f"访问地址: http://{HOST}:{PORT}")
    print("按 Ctrl+C 停止")
    start_server()
