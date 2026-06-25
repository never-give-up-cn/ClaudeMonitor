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

## 开发历程

### 缘起

用 Claude Code 写代码时，经常想知道它当前在做什么——是在思考、读文件、写代码，还是已经空闲了？虽然终端能看到输出，但如果人走开了，回来时就不知道进度。于是做了这个小工具，把 AI 助手的"内心活动"可视化。

### v0.1 — 控制台原型（2025-06-24）

最初的版本只有一个控制台脚本 `monitor.py`，每 1 秒轮询一次 `psutil` 检测 `claude.exe` 进程的 CPU 占用。那时只有 5 种状态：空闲、思考、读文件、写代码、错误。能跑，但很简陋。

### v0.2 — GUI 浮窗（2025-06-25）

觉得控制台不够直观，加上了 Tkinter 桌面浮窗 `gui.py`。每个状态用独立颜色标识，一眼就能看到 Claude 在干嘛。支持窗口置顶、串口状态指示。

### v0.3 — Arduino LED Matrix 显示（2025-06-25）

为了把状态带到物理世界，增加了串口通信功能。通过 `pyserial` 以 CSV 格式发送状态码到 Arduino Uno R4 WiFi，LED Matrix 显示对应图标。写 `arduino/claude_status/claude_status.ino` 固件时调了不少 PWM 输出的坑。

### v0.4 — 状态细化 + 文件监控（2025-06-25）

从 5 种状态逐步细化到 12 种：区分高强度思考(THINKING)和中度处理(PROCESSING)，把空闲等待(WAITING)单独提取，增加 DONE 过渡态和 ERROR 异常态。同时加入文件变化检测，通过 `os.scandir` 递归扫描桌面文件变更来触发 WRITING 状态。

### v0.5 — Token 用量追踪（2025-06-25）

用户想要看 API 消耗了多少 Token。翻 Claude Code 的本地会话文件（`~/.claude/projects/` 下的 JSONL），发现每个 assistant 消息都带有 `usage` 字段，包含 `input_tokens`、`output_tokens`、`cache_read_input_tokens`。写了 `token_tracker.py` 做增量解析，按模型单价实时估算费用。

### v0.6 — 对话日志 + 日志查看器（2025-06-26）

从会话文件中提取每一轮用户输入和 AI 返回，记录 Token 消耗到 `conversation_log.jsonl`。同时做了 Tkinter 表格查看器 `log_viewer.py`，支持日期/关键词搜索、分页浏览、双击详情、CSV/HTML 导出。

### v0.7 — Web 日志查看器（2025-06-26）

纯 Python 内置模块实现 —— 用 `http.server` 提供 REST API，单 HTML 页面 + Vanilla JS 搞定搜索、分页、弹窗详情。零外部依赖，轻量够用。

### v0.8 — 提示音系统（2025-06-26）

任务完成时响一声，需要操作时响两声。用 `winsound.Beep()` 直接驱动主板蜂鸣器，不依赖系统音效方案。可自定义 WAV 文件替代默认音效。

### v0.9 — 系统托盘 + 边缘吸附（2025-06-26）

加了 `pystray` 系统托盘图标，左键显示窗口，右键弹出菜单。悬浮球拖到屏幕边缘自动吸附，缩成小标签条，鼠标悬停滑出。设置面板支持字体大小、开机自启。

### v1.0 — 悬浮球双样式（2025-06-26）

样式 1：圆形简约，显示 CPU/内存/GPU/网速/磁盘。样式 2：Token 数据面板，实时展示 IN/OUT/COST + 硬件负载进度条。右侧菜单可一键切换。

### v1.1 — GUI 全面重设计（2025-06-26）

移除了原生白色标题栏，自定义深色标题栏。布局重构为 5 个区块：标题栏 → 状态环 → 硬件卡片 → Token 卡片 → 底部按钮。统一暗色科技配色（#18191C 基底，#56E3F5 主色），按钮 hover 效果，进度条辅助显示。

### v1.2 — 桌面悬浮球 v3（2025-06-26）

`floating_ball.py` 全面升级：大圆角磨砂玻璃容器、AMD GPU 检测（通过 Windows 性能计数器）、显存从注册表读取（正确识别 12GB VRAM）、后台线程采集数据不阻塞 UI。

## 踩坑记录

一路上踩了不少坑，记下来供参考：

### 1. Python 2/3 混装导致 f-string 崩溃

系统同时装了 Python 2.7（Anaconda）和 Python 3.13（Microsoft Store），`python` 指向 2.7，f-string 全部报 `SyntaxError`。`start.bat` 最初只用 `where python3` 检测，但 Windows 下 `python3` 不一定存在。修复：先用 `py -3` launcher，再 `python3`，最后 `python` + 版本检查。

### 2. 子进程枚举竞态

遍历 Claude Code 子进程时获取 `c.name()`，如果进程刚好在那一瞬间退出，`psutil` 会抛 `NoSuchProcess` 导致整个监控器崩溃。修复：每个子进程单独 `try/except`。

### 3. PowerShell 超时 + 弹窗

GPU 检测用 `subprocess.run(["powershell", "-Command", ps_cmd])`，`-Command` 模式下 `Get-Counter` 会莫名超时（最长 8 秒），而且每次调用都会闪一个 PowerShell 窗口。修复：改写成临时 `.ps1` 文件用 `-File` 模式执行，加 `CREATE_NO_WINDOW` 标志。

### 4. 悬浮球右键无反应

菜单在每次右键时重新创建，加上 GPU 检测在主线程同步执行，导致界面卡死。修复：菜单预构建一次缓存，GPU 数据采集移到后台线程。

### 5. 悬浮窗启动崩溃

`menu.add_command()` 返回 `None`，传进 `menu.index(None)` 抛 Tcl 异常，整个窗口起不来。修复：直接用 `menu.entryconfig("标签名")` 按标签查找。

### 6. 悬浮球吸附后不会自动隐藏

`_on_leave` 的条件是 `if not self._snapped or not self._hidden_mode: return`，展开时 `_hidden_mode=False`，条件为真直接返回，不启动隐藏定时器。修复：去掉 `_hidden_mode` 检查，吸附状态下鼠标离开一律启动隐藏。

### 7. 8 位颜色码导致 Tkinter 崩溃

Tkinter Canvas 不支持 `#ffffff18` 等带透明度的 8 位十六进制颜色，直接报错无法启动。修复：全部改用 6 位纯色。

### 8. 文件编码被 PowerShell 写坏

用 PowerShell 的 `Set-Content` 写入 Python 文件，默认 ANSI 编码把中文全部变成乱码。`SyntaxError: invalid character '℃'` 排查了半天。修复：全程用 Python 读写文件，或者 PowerShell 加 `-Encoding utf8`。

### 9. AMD GPU 检测不到

默认只写 `nvidia-smi` 检测，用户是 AMD RX 6750 XT，一直显示 `GPU:--`。修复：加 Windows 性能计数器 (`GPU Engine`) 和注册表读取 (`HardwareInformation.qwMemorySize`) 双重回退。

### 10. 显存大小读错

`Win32_VideoController.AdapterRAM` 返回 4GB，实际是 12GB。WMI 对现代显卡的显存报告不准。修复：从注册表 `HKLM\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\*\HardwareInformation.qwMemorySize` 读取。

### 11. overrideredirect 后无法最小化

自定义标题栏用 `overrideredirect(True)` 移除了原生标题栏，但也失去了 `Alt+Tab` 和任务栏行为。修复：手动实现最小化按钮 `root.iconify()`，托盘功能通过 `pystray` 实现。

### 12. 按钮一多就溢出

底部 7 个按钮总宽超过窗口宽度，`padx=20` 时部分按钮被裁剪消失。反复调整窗口宽度 520→560→640，最终用 `padx=10` + 9px 字体才稳定。

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
