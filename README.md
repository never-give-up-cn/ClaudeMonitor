# Claude Code 工作状态监控器

监控 Claude Code 的工作状态，通过串口发送状态码到 Arduino LED Matrix 显示。

## 工作流程

```
┌─────────────────┐    串口 (115200)    ┌──────────────────┐
│  PC端监控程序    │ ──────────────────→ │  Arduino         │
│  monitor.py      │    "状态码,0\n"     │  LED Matrix 显示  │
│                  │                     │  S0, S1, ... S11 │
└─────────────────┘                     └──────────────────┘
     ↑
     │ psutil 检测进程 + 文件监控
     │
┌────┴────────────┐
│  Claude Code    │
│  (工作状态变化)  │
└─────────────────┘
```

## 状态码定义

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
| 8 | WAITING | 等待 | CPU 为零超过 30 秒 |
| 9 | PROCESSING | 处理中 | 中等 CPU，一般处理活动 |
| 10 | DONE | 完成 | 任务刚完成 |
| 11 | ERROR | 错误 | 异常状态 |

## 快速开始

### 1. Arduino 端

用 Arduino IDE 打开 `arduino/claude_status.ino`，上传到 Arduino Uno R4 WiFi 开发板。

### 2. PC 端

双击 `start.bat` 启动监控程序。

或手动运行:
```bash
python3 monitor.py
```

程序会自动检测 Arduino 串口并连接。

## 文件结构

```
ClaudeMonitor/
├── monitor.py              # 主监控程序 (Python 3)
├── start.bat               # 启动脚本 (Windows)
├── monitor.log             # 运行日志 (自动生成)
└── arduino/
    └── claude_status.ino   # Arduino LED Matrix 固件
```

## 配置

编辑 `monitor.py` 开头的 `CONFIG` 字典:

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| serial_port | "auto" | 串口名，"auto"=自动检测 |
| baud_rate | 115200 | 波特率 |
| check_interval | 1.0 | 检测间隔(秒) |
| idle_timeout | 30 | 无 CPU 活动多少秒后标记为等待 |
| cpu_think_threshold | 15.0 | THINKING 状态的 CPU 阈值(%) |

## 依赖

- Python 3.7+
- pyserial
- psutil

首次运行 `start.bat` 会自动安装依赖。手动安装:
```bash
pip install pyserial psutil
```
