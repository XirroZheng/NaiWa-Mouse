"""Global low-level mouse hook and system cursor helpers."""
from __future__ import annotations

import ctypes
import logging

from .win32 import (
    BUSY_IDS,
    HOOKPROC,
    OCR_IDS,
    SPIF_SENDCHANGE,
    SPI_SETCURSORS,
    WH_MOUSE_LL,
    current_cursor,
    kernel32,
    load_system_cursor,
    user32,
)

log = logging.getLogger("skin")


class MouseHook:
    """Watches button presses system-wide.

    The callback runs on the thread that installed the hook (our message loop)
    and must return fast -- it only records state, drawing happens on the timer.
    """

    def __init__(self, callback):
        self._callback = callback
        self._proc = HOOKPROC(self._handle)
        self._hook = None

    def _handle(self, n_code, w_param, l_param):
        if n_code >= 0:
            try:
                self._callback(int(w_param))
            except Exception:  # never let an exception escape into Win32
                log.exception("mouse hook callback failed")
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    def install(self) -> None:
        hmod = kernel32.GetModuleHandleW(None)
        self._hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc, hmod, 0)
        if not self._hook:
            raise ctypes.WinError(ctypes.get_last_error())

    def uninstall(self) -> None:
        if self._hook:
            user32.UnhookWindowsHookEx(self._hook)
            self._hook = None


class SystemCursor:
    """Swap every system cursor for a transparent one, and restore later."""

    def __init__(self):
        self._hidden = False
        self._and = ctypes.create_string_buffer(b"\xff")
        self._xor = ctypes.create_string_buffer(b"\x00")
        # Recorded before replacement: SetSystemCursor swaps the *image* behind
        # each system cursor slot but keeps its handle, so these handles stay
        # valid and let us tell which cursor the shell is showing right now.
        self._busy = {load_system_cursor(cid) for cid in BUSY_IDS} - {0}

    @property
    def hidden(self) -> bool:
        return self._hidden

    def system_busy(self) -> bool:
        """True while the shell is drawing the wait / app-starting cursor."""
        return current_cursor() in self._busy

    def hide(self) -> None:
        hinst = kernel32.GetModuleHandleW(None)
        for cid in OCR_IDS:
            handle = user32.CreateCursor(hinst, 0, 0, 1, 1, self._and, self._xor)
            if handle:
                # SetSystemCursor destroys the handle it is given
                user32.SetSystemCursor(handle, cid)
        self._hidden = True

    def restore(self) -> None:
        user32.SystemParametersInfoW(SPI_SETCURSORS, 0, None, SPIF_SENDCHANGE)
        self._hidden = False


def restore_cursor_now() -> None:
    """Hard reset, safe to call even if the app never started."""
    user32.SystemParametersInfoW(SPI_SETCURSORS, 0, None, SPIF_SENDCHANGE)
