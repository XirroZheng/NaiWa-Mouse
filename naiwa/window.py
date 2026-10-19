"""Top-most per-pixel-alpha window used to draw the skin."""
from __future__ import annotations

import ctypes
import os
from ctypes import byref, c_void_p, sizeof

from .win32 import (
    AC_SRC_ALPHA,
    AC_SRC_OVER,
    BI_RGB,
    BITMAPINFO,
    BITMAPINFOHEADER,
    BLENDFUNCTION,
    DIB_RGB_COLORS,
    SW_SHOWNOACTIVATE,
    ULW_ALPHA,
    WS_EX_LAYERED,
    WS_EX_NOACTIVATE,
    WS_EX_TOOLWINDOW,
    WS_EX_TOPMOST,
    WS_EX_TRANSPARENT,
    WS_POPUP,
    WNDCLASSEXW,
    WNDPROC,
    gdi32,
    kernel32,
    user32,
)
from ctypes import wintypes as wt


class Surface:
    """A 32bpp top-down DIB holding premultiplied BGRA pixels."""

    def __init__(self, bgra: bytes, width: int, height: int):
        self.w = width
        self.h = height
        screen = user32.GetDC(None)
        try:
            self.hdc = gdi32.CreateCompatibleDC(screen)
            bmi = BITMAPINFO()
            bmi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER)
            bmi.bmiHeader.biWidth = width
            bmi.bmiHeader.biHeight = -height  # negative = top-down rows
            bmi.bmiHeader.biPlanes = 1
            bmi.bmiHeader.biBitCount = 32
            bmi.bmiHeader.biCompression = BI_RGB
            bits = c_void_p()
            self.hbmp = gdi32.CreateDIBSection(
                screen, byref(bmi), DIB_RGB_COLORS, byref(bits), None, 0
            )
            if not self.hbmp:
                raise ctypes.WinError(ctypes.get_last_error())
            self._bits = bits
            self._old = gdi32.SelectObject(self.hdc, self.hbmp)
            ctypes.memmove(bits, bgra, len(bgra))
        finally:
            user32.ReleaseDC(None, screen)

    def upload(self, bgra: bytes) -> None:
        """Rewrite the pixels in place -- used to advance animation frames.

        One DIB is reused for every frame of a flipbook, so a 176-frame
        animation costs a single GDI surface instead of 176.
        """
        ctypes.memmove(self._bits, bgra, min(len(bgra), self.w * self.h * 4))

    def close(self) -> None:
        if getattr(self, "hdc", None):
            gdi32.SelectObject(self.hdc, self._old)
            gdi32.DeleteObject(self.hbmp)
            gdi32.DeleteDC(self.hdc)
            self.hdc = None


class LayeredWindow:
    def __init__(self, wndproc):
        self._proc = WNDPROC(wndproc)
        self.hinst = kernel32.GetModuleHandleW(None)
        self._class = f"NaiWaMouseWnd_{os.getpid()}"
        self._surface: Surface | None = None
        self._pos: tuple[int, int] | None = None

        wc = WNDCLASSEXW()
        wc.cbSize = sizeof(WNDCLASSEXW)
        wc.style = 0
        wc.lpfnWndProc = self._proc
        wc.hInstance = self.hinst
        wc.lpszClassName = self._class
        if not user32.RegisterClassExW(byref(wc)):
            err = ctypes.get_last_error()
            if err not in (1410,):  # class already exists
                raise ctypes.WinError(err)

        ex_style = (
            WS_EX_LAYERED
            | WS_EX_TRANSPARENT   # click-through
            | WS_EX_TOOLWINDOW    # no taskbar button
            | WS_EX_TOPMOST
            | WS_EX_NOACTIVATE    # never steal focus
        )
        self.hwnd = user32.CreateWindowExW(
            ex_style, self._class, "", WS_POPUP,
            -32000, -32000, 1, 1, None, None, self.hinst, None,
        )
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())

    # ------------------------------------------------------------------ view
    def set_surface(self, surface: Surface) -> None:
        self._surface = surface

    def move(self, x: int, y: int) -> bool:
        """Return True when the position actually changed."""
        if self._pos == (x, y):
            return False
        self._pos = (x, y)
        return True

    def flush(self) -> bool:
        """Push the current surface at the current position to the screen."""
        if not self._surface or not self._pos:
            return False
        pt_dst = wt.POINT(self._pos[0], self._pos[1])
        size = wt.SIZE(self._surface.w, self._surface.h)
        pt_src = wt.POINT(0, 0)
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        ok = user32.UpdateLayeredWindow(
            self.hwnd, None, byref(pt_dst), byref(size),
            self._surface.hdc, byref(pt_src), 0, byref(blend), ULW_ALPHA,
        )
        return bool(ok)

    def show(self) -> None:
        user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)

    def hide(self) -> None:
        user32.ShowWindow(self.hwnd, 0)

    def raise_top(self) -> None:
        from .win32 import HWND_TOPMOST, SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOSIZE

        user32.SetWindowPos(
            self.hwnd, HWND_TOPMOST, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
        )

    def close(self) -> None:
        if self._surface:
            self._surface.close()
        if self.hwnd:
            user32.DestroyWindow(self.hwnd)
            self.hwnd = None
