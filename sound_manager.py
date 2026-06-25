#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
声音管理
========
Windows 提示音播放，任务完成和用户操作时发出不同音效。
纯 winsound 实现，无额外依赖。
"""

import sys
import threading
import time

try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False

# 声音类型
SOUND_DONE = "done"        # 任务完成
SOUND_ACTION = "action"    # 需要用户操作
SOUND_ERROR = "error"      # 错误
SOUND_NOTIFY = "notify"    # 普通通知

# 默认启用声音
ENABLED = True


def play(sound_type=SOUND_NOTIFY):
    """播放指定类型的提示音"""
    if not ENABLED or not HAS_WINSOUND:
        return

    try:
        if sound_type == SOUND_DONE:
            # 任务完成：两声短促提示
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
            threading.Thread(target=lambda: (time.sleep(0.15), winsound.MessageBeep(winsound.MB_OK)),
                             daemon=True).start()

        elif sound_type == SOUND_ACTION:
            # 需要用户操作：重复两声
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            threading.Thread(target=lambda: (time.sleep(0.2), winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)),
                             daemon=True).start()

        elif sound_type == SOUND_ERROR:
            # 错误：低沉长音
            winsound.MessageBeep(winsound.MB_ICONHAND)

        elif sound_type == SOUND_NOTIFY:
            # 普通通知：一声短促
            winsound.MessageBeep(winsound.MB_OK)

    except Exception:
        pass


if __name__ == "__main__":
    print("测试提示音...")
    play(SOUND_DONE)
    time.sleep(0.5)
    play(SOUND_ACTION)
    time.sleep(0.5)
    play(SOUND_NOTIFY)
