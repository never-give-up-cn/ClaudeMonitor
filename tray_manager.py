#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
System tray manager with single-click support on Windows.
Left-click shows window, right-click shows menu.
"""

import threading

HAS_TRAY = False
TRAY_ICON = None
WM_LBUTTONUP = 0x202
WM_RBUTTONUP = 0x205

try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False


def _create_icon():
    try:
        img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([2, 2, 13, 13], fill=(74, 158, 255, 255))
        draw.ellipse([5, 5, 10, 10], fill=(255, 255, 255, 200))
        return img
    except Exception:
        return None


def setup_tray(gui, on_show=None, on_quit=None):
    """Setup system tray icon. Left-click shows window, right-click opens menu."""
    global TRAY_ICON
    if not HAS_TRAY:
        return False

    try:
        icon_img = _create_icon()
        if not icon_img:
            return False

        menu = (
            pystray.MenuItem("显示窗口", lambda: on_show() if on_show else None, default=True),
            pystray.MenuItem("查看日志", lambda: gui.open_log_viewer()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", lambda: on_quit() if on_quit else None),
        )

        TRAY_ICON = pystray.Icon("claude_monitor", icon_img, "Claude Code 监控", menu)

        # Patch: left-click shows window, right-click shows menu
        if hasattr(TRAY_ICON, '_on_notify'):
            original = TRAY_ICON._on_notify

            def patched(wparam, lparam):
                if lparam == WM_LBUTTONUP:
                    if on_show:
                        on_show()
                    return
                original(wparam, lparam)

            TRAY_ICON._on_notify = patched

        def run_tray():
            try:
                TRAY_ICON.run()
            except Exception:
                pass

        threading.Thread(target=run_tray, daemon=True).start()
        return True
    except Exception:
        return False


def remove_tray():
    global TRAY_ICON
    if TRAY_ICON:
        try:
            TRAY_ICON.stop()
        except Exception:
            pass
        TRAY_ICON = None


def notify_tray(title, message, duration=3):
    global TRAY_ICON
    if TRAY_ICON and hasattr(TRAY_ICON, "notify"):
        try:
            TRAY_ICON.notify(message, title)
        except Exception:
            pass
