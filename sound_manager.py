#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
声音管理
========
Windows 提示音，使用 Beep() 产生纯音，无需系统音效支持。
"""

import threading
import time

try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False

# 声音类型
SOUND_DONE = "done"
SOUND_ACTION = "action"
SOUND_ERROR = "error"
SOUND_NOTIFY = "notify"

# 默认启用
ENABLED = True


def _beep(freq, duration):
    """播放指定频率和时长的声音"""
    if not HAS_WINSOUND or not ENABLED:
        return
    try:
        winsound.Beep(freq, duration)
    except Exception:
        pass


def play(sound_type=SOUND_NOTIFY):
    """播放提示音"""
    if not ENABLED or not HAS_WINSOUND:
        return

    try:
        if sound_type == SOUND_DONE:
            # 任务完成：两声轻快上升音 (880Hz + 1320Hz)
            threading.Thread(target=lambda: (
                _beep(880, 120),
                time.sleep(0.12),
                _beep(1320, 180),
            ), daemon=True).start()

        elif sound_type == SOUND_ACTION:
            # 需要操作：两声短促警告音 (660Hz 重复)
            threading.Thread(target=lambda: (
                _beep(660, 100),
                time.sleep(0.15),
                _beep(660, 100),
            ), daemon=True).start()

        elif sound_type == SOUND_ERROR:
            # 错误：低沉长音
            _beep(330, 400)

        elif sound_type == SOUND_NOTIFY:
            # 通知：一声短促
            _beep(880, 80)

    except Exception:
        pass


if __name__ == "__main__":
    ENABLED = True
    print("测试提示音...")
    for name in [SOUND_DONE, SOUND_ACTION, SOUND_NOTIFY, SOUND_ERROR]:
        print(f"  {name}...")
        play(name)
        time.sleep(0.6)
