"""Thin ctypes layer over the few Win32 calls the skin needs.

Everything here is deliberately low level: a layered top-most window with
per-pixel alpha (UpdateLayeredWindow), a low-level mouse hook, and the cursor
replacement used to hide the system pointer.
"""
from __future__ import annotations

import ctypes
from ctypes import (
    POINTER,
    Structure,
    WINFUNCTYPE,
    byref,
    c_int,
    c_ssize_t,
    c_ubyte,
    c_uint,
    c_ulong,
    c_void_p,
)
from ctypes import wintypes as wt

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = c_ssize_t
WNDPROC = WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
HOOKPROC = WINFUNCTYPE(LRESULT, c_int, wt.WPARAM, wt.LPARAM)

# ---------------------------------------------------------------- constants
WS_POPUP = 0x80000000
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008
WS_EX_NOACTIVATE = 0x08000000
SW_SHOWNOACTIVATE = 4
HWND_TOPMOST = c_void_p(-1)
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010

WM_DESTROY = 0x0002
WM_TIMER = 0x0113
WM_HOTKEY = 0x0312

WH_MOUSE_LL = 14
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208

ULW_ALPHA = 0x02
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
DIB_RGB_COLORS = 0
BI_RGB = 0

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

SPI_SETCURSORS = 0x0057
SPIF_SENDCHANGE = 0x02

# System cursor ids replaced while the skin is active.
OCR_IDS = (
    32512,  # arrow
    32513,  # ibeam
    32514,  # wait
    32515,  # cross
    32516,  # up arrow
    32642,  # sizenwse
    32643,  # sizenesw
    32644,  # sizewe
    32645,  # sizens
    32646,  # sizeall
    32648,  # no
    32649,  # hand
    32650,  # appstarting
    32651,  # help
)

IDC_WAIT = 32514        # the "busy" hourglass / spinner
IDC_APPSTARTING = 32650  # arrow + spinner, shown while a process starts
BUSY_IDS = (IDC_WAIT, IDC_APPSTARTING)



# ----------------------------------------------------------------- structs
class WNDCLASSEXW(Structure):
    _fields_ = [
        ("cbSize", wt.UINT),
        ("style", wt.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", c_int),
        ("cbWndExtra", c_int),
        ("hInstance", wt.HINSTANCE),
        ("hIcon", wt.HICON),
        ("hCursor", wt.HANDLE),
        ("hbrBackground", wt.HBRUSH),
        ("lpszMenuName", wt.LPCWSTR),
        ("lpszClassName", wt.LPCWSTR),
        ("hIconSm", wt.HICON),
    ]


class BLENDFUNCTION(Structure):
    _fields_ = [
        ("BlendOp", c_ubyte),
        ("BlendFlags", c_ubyte),
        ("SourceConstantAlpha", c_ubyte),
        ("AlphaFormat", c_ubyte),
    ]


class BITMAPINFOHEADER(Structure):
    _fields_ = [
        ("biSize", wt.DWORD),
        ("biWidth", wt.LONG),
        ("biHeight", wt.LONG),
        ("biPlanes", wt.WORD),
        ("biBitCount", wt.WORD),
        ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD),
        ("biXPelsPerMeter", wt.LONG),
        ("biYPelsPerMeter", wt.LONG),
        ("biClrUsed", wt.DWORD),
        ("biClrImportant", wt.DWORD),
    ]


class RGBQUAD(Structure):
    _fields_ = [("rgbBlue", c_ubyte), ("rgbGreen", c_ubyte), ("rgbRed", c_ubyte), ("rgbReserved", c_ubyte)]


class BITMAPINFO(Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", RGBQUAD * 1)]


class CURSORINFO(Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("flags", wt.DWORD),
        ("hCursor", wt.HANDLE),
        ("ptScreenPos", wt.POINT),
    ]


# ----------------------------------------------------------------- signatures
user32.RegisterClassExW.argtypes = [POINTER(WNDCLASSEXW)]
user32.RegisterClassExW.restype = wt.WORD

user32.CreateWindowExW.argtypes = [
    wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
    c_int, c_int, c_int, c_int,
    wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID,
]
user32.CreateWindowExW.restype = wt.HWND

user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.DefWindowProcW.restype = LRESULT

user32.UpdateLayeredWindow.argtypes = [
    wt.HWND, wt.HDC, POINTER(wt.POINT), POINTER(wt.SIZE),
    wt.HDC, POINTER(wt.POINT), wt.DWORD, POINTER(BLENDFUNCTION), wt.DWORD,
]
user32.UpdateLayeredWindow.restype = wt.BOOL

user32.SetWindowsHookExW.argtypes = [c_int, HOOKPROC, wt.HINSTANCE, wt.DWORD]
user32.SetWindowsHookExW.restype = wt.HHOOK

user32.CallNextHookEx.argtypes = [wt.HHOOK, c_int, wt.WPARAM, wt.LPARAM]
user32.CallNextHookEx.restype = LRESULT

user32.UnhookWindowsHookEx.argtypes = [wt.HHOOK]
user32.UnhookWindowsHookEx.restype = wt.BOOL

user32.GetMessageW.argtypes = [POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
user32.GetMessageW.restype = wt.BOOL

user32.TranslateMessage.argtypes = [POINTER(wt.MSG)]
user32.DispatchMessageW.argtypes = [POINTER(wt.MSG)]
user32.DispatchMessageW.restype = LRESULT

user32.PostQuitMessage.argtypes = [c_int]
user32.ShowWindow.argtypes = [wt.HWND, c_int]
user32.UpdateWindow.argtypes = [wt.HWND]

user32.SetTimer.argtypes = [wt.HWND, c_uint, c_uint, c_void_p]
user32.SetTimer.restype = c_ulong

user32.KillTimer.argtypes = [wt.HWND, c_uint]

user32.RegisterHotKey.argtypes = [wt.HWND, c_int, wt.UINT, wt.UINT]
user32.RegisterHotKey.restype = wt.BOOL

user32.GetCursorPos.argtypes = [POINTER(wt.POINT)]
user32.GetCursorPos.restype = wt.BOOL

user32.LoadCursorW.argtypes = [wt.HINSTANCE, c_void_p]
user32.LoadCursorW.restype = wt.HANDLE

user32.GetCursorInfo.argtypes = [POINTER(CURSORINFO)]
user32.GetCursorInfo.restype = wt.BOOL

user32.SetSystemCursor.argtypes = [wt.HANDLE, wt.DWORD]
user32.SetSystemCursor.restype = wt.BOOL

user32.SystemParametersInfoW.argtypes = [wt.UINT, wt.UINT, wt.LPVOID, wt.UINT]
user32.SystemParametersInfoW.restype = wt.BOOL

user32.CreateCursor.argtypes = [wt.HINSTANCE, c_int, c_int, c_int, c_int, wt.LPVOID, wt.LPVOID]
user32.CreateCursor.restype = wt.HANDLE

user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, c_int, c_int, c_int, c_int, wt.UINT]
user32.SetWindowPos.restype = wt.BOOL

user32.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]
user32.FindWindowW.restype = wt.HWND

user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.PostMessageW.restype = wt.BOOL

user32.GetDC.argtypes = [wt.HWND]
user32.GetDC.restype = wt.HDC
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]

gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.CreateDIBSection.argtypes = [
    wt.HDC, POINTER(BITMAPINFO), wt.UINT, POINTER(c_void_p), wt.HANDLE, wt.DWORD,
]
gdi32.CreateDIBSection.restype = wt.HBITMAP
gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi32.SelectObject.restype = wt.HGDIOBJ
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wt.HDC]

kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
kernel32.GetModuleHandleW.restype = wt.HMODULE


def set_dpi_aware() -> None:
    """Per-monitor v2 so cursor coordinates are real pixels."""
    try:
        user32.SetProcessDpiAwarenessContext(c_void_p(-4))
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def get_dpi() -> int:
    try:
        return int(user32.GetDpiForSystem())
    except Exception:
        try:
            hdc = user32.GetDC(None)
            dpi = int(gdi32.GetDeviceCaps(hdc, 88))  # LOGPIXELSX
            user32.ReleaseDC(None, hdc)
            return dpi or 96
        except Exception:
            return 96


def cursor_pos() -> tuple[int, int]:
    pt = wt.POINT()
    user32.GetCursorPos(byref(pt))
    return pt.x, pt.y


def load_system_cursor(cid: int) -> int:
    """Handle of a system cursor slot (stable even after SetSystemCursor)."""
    return int(user32.LoadCursorW(None, c_void_p(cid)) or 0)


def current_cursor() -> int:
    """Handle of the cursor the shell is drawing right now (0 if unknown)."""
    ci = CURSORINFO()
    ci.cbSize = ctypes.sizeof(ci)
    if not user32.GetCursorInfo(byref(ci)):
        return 0
    return int(ci.hCursor or 0)

