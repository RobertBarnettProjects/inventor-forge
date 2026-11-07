"""Driving Inventor's own dialogs (for features that have no API, like Stress Analysis).

Inventor's Stress Analysis environment is only reachable through its commands and their Win32
dialogs. Commands are started through the API (with the faces pre-selected through the API); the
dialogs they open are then filled in and confirmed with window messages, the same as a person typing
into the fields and clicking the buttons. While this runs Inventor's window must not be used by
anyone else.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import win32api
import win32con
import win32gui
import win32process

from .com import InventorError


def _dpi_aware() -> bool:
    """Work in physical pixels, like Inventor (otherwise Windows scales our coordinates on high-DPI
    screens and clicks / pixel reads land in the wrong place)."""
    import ctypes
    try:
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):   # per-monitor v2
            return True
    except Exception:
        pass
    try:
        return ctypes.windll.user32.IsProcessDPIAware() != 0 or bool(ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0)
    except Exception:
        return False


DPI_AWARE = _dpi_aware()


@dataclass
class Ctrl:
    hwnd: int
    cls: str
    text: str
    cid: int
    visible: bool
    enabled: bool


def _info(h: int) -> Ctrl:
    return Ctrl(h, win32gui.GetClassName(h), win32gui.GetWindowText(h), win32gui.GetDlgCtrlID(h),
                bool(win32gui.IsWindowVisible(h)), bool(win32gui.IsWindowEnabled(h)))


def process_windows(pid: int) -> list[int]:
    out: list[int] = []

    def cb(h, _):
        if win32gui.IsWindowVisible(h) and win32process.GetWindowThreadProcessId(h)[1] == pid:
            out.append(h)
        return True
    win32gui.EnumWindows(cb, None)
    return out


def wait_window(pid: int, title: str | tuple[str, ...], timeout: float = 30.0, cls: str = "#32770") -> int:
    titles = (title,) if isinstance(title, str) else title
    t0 = time.time()
    while time.time() - t0 < timeout:
        for h in process_windows(pid):
            try:
                if win32gui.GetClassName(h) == cls and any(t.lower() in win32gui.GetWindowText(h).lower() for t in titles):
                    return h
            except Exception:
                continue
        time.sleep(0.15)
    raise InventorError(f"Inventor dialog {titles} did not appear within {timeout:.0f} s")


def wait_gone(h: int, timeout: float = 30.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if not win32gui.IsWindow(h) or not win32gui.IsWindowVisible(h):
            return True
        time.sleep(0.15)
    return False


def controls(h: int) -> list[Ctrl]:
    out: list[int] = []
    win32gui.EnumChildWindows(h, lambda c, _: out.append(c) or True, None)
    res = []
    for c in out:
        try:
            res.append(_info(c))
        except Exception:
            continue
    return res


def find(h: int, cid: int | None = None, text: str | None = None, cls: str | None = None,
         visible: bool = True) -> Ctrl:
    for c in controls(h):
        if visible and not c.visible:
            continue
        if cid is not None and c.cid != cid:
            continue
        if cls is not None and c.cls != cls:
            continue
        if text is not None and c.text.replace("&", "").lower() != text.replace("&", "").lower():
            continue
        return c
    raise InventorError(f"control not found in dialog {win32gui.GetWindowText(h)!r}: id={cid} text={text!r} cls={cls}")


def find_all(h: int, cls: str | None = None, visible: bool = True) -> list[Ctrl]:
    return [c for c in controls(h) if (not visible or c.visible) and (cls is None or c.cls == cls)]


def click(c: Ctrl) -> None:
    """Press a button (PostMessage so a modal step it triggers doesn't block us)."""
    win32gui.PostMessage(c.hwnd, win32con.BM_CLICK, 0, 0)
    time.sleep(0.25)


def set_text(c: Ctrl, value: str) -> None:
    """Type into an edit box and tell the dialog it changed (EN_CHANGE), like a keyboard edit."""
    win32gui.SendMessage(c.hwnd, win32con.WM_SETTEXT, 0, str(value))
    parent = win32gui.GetParent(c.hwnd)
    win32gui.SendMessage(parent, win32con.WM_COMMAND, (win32con.EN_CHANGE << 16) | (c.cid & 0xFFFF), c.hwnd)
    # some Inventor value boxes evaluate on focus loss
    win32gui.SendMessage(parent, win32con.WM_COMMAND, (win32con.EN_KILLFOCUS << 16) | (c.cid & 0xFFFF), c.hwnd)
    time.sleep(0.1)


def get_text(c: Ctrl) -> str:
    return win32gui.GetWindowText(c.hwnd)


def is_checked(c: Ctrl) -> bool:
    return win32gui.SendMessage(c.hwnd, win32con.BM_GETCHECK, 0, 0) == win32con.BST_CHECKED


def set_check(c: Ctrl, on: bool = True) -> None:
    if is_checked(c) != on:
        win32gui.SendMessage(c.hwnd, win32con.BM_CLICK, 0, 0)
        time.sleep(0.15)


def combo_items(c: Ctrl) -> list[str]:
    n = win32gui.SendMessage(c.hwnd, win32con.CB_GETCOUNT, 0, 0)
    out = []
    for i in range(max(n, 0)):
        ln = win32gui.SendMessage(c.hwnd, win32con.CB_GETLBTEXTLEN, i, 0)
        buf = win32gui.PyMakeBuffer((ln + 1) * 2)
        win32gui.SendMessage(c.hwnd, win32con.CB_GETLBTEXT, i, buf)
        out.append(buf.tobytes().decode("utf-16-le", "ignore").rstrip("\x00"))
    return out


def combo_select(c: Ctrl, text: str) -> str:
    items_ = combo_items(c)
    pick = next((i for i, t in enumerate(items_) if t.lower() == text.lower()), None)
    if pick is None:
        pick = next((i for i, t in enumerate(items_) if text.lower() in t.lower()), None)
    if pick is None:
        raise InventorError(f"{text!r} not in list {items_}")
    win32gui.SendMessage(c.hwnd, win32con.CB_SETCURSEL, pick, 0)
    parent = win32gui.GetParent(c.hwnd)
    win32gui.SendMessage(parent, win32con.WM_COMMAND, (win32con.CBN_SELCHANGE << 16) | (c.cid & 0xFFFF), c.hwnd)
    time.sleep(0.15)
    return items_[pick]


def dump(h: int) -> str:
    lines = [f"{win32gui.GetWindowText(h)!r}"]
    for c in controls(h):
        if c.visible:
            lines.append(f"  [{c.cid}] {c.cls} {c.text!r}{'' if c.enabled else ' (disabled)'}")
    return "\n".join(lines)


def press_enter(h: int) -> None:
    win32api.PostMessage(h, win32con.WM_KEYDOWN, win32con.VK_RETURN, 0)
    win32api.PostMessage(h, win32con.WM_KEYUP, win32con.VK_RETURN, 0)
