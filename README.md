# Claude Code 工作状态监控器

监控 Claude Code 的工作状态，通过串口发送状态码到 Arduino LED Matrix 显示。
支持 **桌面窗口** 和 **控制台** 两种模式。

内置 **Token 用量追踪** 和 **对话日志记录**，实时跟踪 API 消耗。

## 工作流程

```
┌─────────────────┐    串口 (115200)    ┌──────────────────┐
│  PC端监控程序    │ ──────────────────→ │  Arduino         │
│  gui.py          │    "状态码,0\n"     │  LED Matrix 显示  │
│  monitor.py      │                     │  S0, S1, ... S11 │
└─────────────────┘                     └──────────────────┘
     ↑
     │ psutil 检测进程 + 会话文件解析
     │
┌────┴────────────┐
│  Claude Code    │
│  (工作状态变化)  │
└─────────────────┘
```

## 功能特性

### 🎯 12 种工作状态监控

| 码 | 英文 | 中文 | 说明 |
|----|------|------|------|
| 0 | IDLE | 空闲 | Claude 未运行 |
| 1 | LOADING | 启动 | 进程刚创建 |
| 2 | THINKING | 思考 | CPU 占用高，正在推理 |
| 3 | READING | 读文件 | 大量读取文件活动 |
| 4 | WRITING | 写代码 | 检测到文件修改 |
| 5 | SEARCHING | 搜索 | 搜索代码库 |
| 6 | BUILDING | 编译 | NPM/Git 等子进程运行中 |
| 7 | COMMAND | 命令 | 执行其他命令 |
| 8 | WAITING | 等待 | CPU 为零超过 15 秒 |
| 9 | PROCESSING | 处理中 | 中等 CPU 活动 |
| 10 | DONE | 完成 | 任务刚完成 |
| 11 | ERROR | 错误 | 异常状态 |

### 📊 Token 用量追踪

自动解析 Claude Code 会话文件，实时监控 API Token 消耗：

- **输入 Token** / **输出 Token** / **缓存读取** / **缓存创建**
- **多模型计价**：支持 deepseek-v4-flash、Claude Sonnet、Haiku
- **费用估算**：实时显示当前会话费用
- **零配置**：自动检测最新会话文件，增量解析

GUI 窗口底部显示 Token 统计面板，控制台每 60 秒打印详细日志。

### 📝 对话日志记录

自动记录每一轮用户输入和 API 返回数据：

- **用户输入**：提取实际文本输入，跳过 tool_result 等系统内容
- **Token 明细**：每条记录包含输入/输出/缓存 Token 和费用
- **增量写入**：`conversation_log.jsonl` 追加写入，性能无损

### 🔍 对话日志查看器

独立 GUI 窗口，通过主窗口 **「查看日志」** 按钮打开：

- **表格展示**：10 列（ID、时间、模型、用户输入、Token 明细、费用）
- **搜索条件**：
  - 📅 日期范围搜索
  - 🔍 关键词搜索（回车即搜）
- **分页浏览**：上/下页、首/末页、页码跳转、每页条数（20/50/100/200）
- **详情查看**：双击任意行弹出完整详情窗口
- **汇总统计**：顶部显示总轮数、Token 合计、总费用

### 🖥️ 桌面窗口版特点

- 半透明浮窗，实时显示中文状态
- 每个状态有独立颜色标识
- 显示 CPU 占用和进程信息
- 串口连接状态指示灯
- 支持窗口置顶
- Token 统计面板（深绿底色）
- 「查看日志」按钮一键打开日志浏览器

## 文件结构

```
ClaudeMonitor/
├── gui.py                  # 桌面窗口版 (Tkinter，推荐)
├── monitor.py              # 控制台版
├── start.bat               # 启动脚本
├── README.md               # 本文档
├── token_tracker.py        # Token 用量追踪模块
├── conversation_logger.py  # 对话日志记录模块
├── log_viewer.py           # 对话日志查看器 GUI
├── conversation_log.jsonl  # 对话日志数据（自动生成）
├── monitor.log             # 运行日志 (自动生成)
└── arduino/
    └── claude_status/
        └── claude_status.ino  # Arduino LED Matrix 固件
```

## 快速开始

### 1. Arduino 端

用 Arduino IDE 打开 `arduino/claude_status/claude_status.ino`，上传到 Arduino Uno R4 WiFi 开发板。

### 2. PC 端

双击 `start.bat` — 自动启动桌面窗口版。

### 启动方式

| 命令 | 效果 |
|------|------|
| `start.bat` | 桌面窗口版（默认） |
| `start.bat console` | 控制台版（显示日志） |

## 配置

编辑 `gui.py` 或 `monitor.py` 开头的 `CONFIG` 字典:

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| serial_port | "auto" | 串口名，"auto"=自动检测 |
| baud_rate | 115200 | 波特率 |
| check_interval | 0.5 (gui) / 1.0 (console) | 检测间隔(秒) |
| idle_timeout | 15 | 无 CPU 活动多少秒后标记为等待 |
| cpu_think_threshold | 8.0 | THINKING 状态的 CPU 阈值(%) |
| enable_token_tracking | True | 启用 Token 监控 |
| token_poll_interval | 2 (console) | Token 轮询间隔(检测次数) |

## 依赖

- Python 3.7+
- pyserial
- psutil
- tkinter (内置)
- 标准库（Token 追踪和日志记录无需额外安装）

首次运行 `start.bat` 会自动安装依赖。手动安装:
```bash
pip install pyserial psutil
```
