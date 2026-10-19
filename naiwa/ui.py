"""Tiny Win32 UI toolkit: GDI painting helpers plus a tray icon.

The skin is a zero-dependency ctypes app, so the settings window is drawn
directly with GDI instead of pulling in Tk/Qt: it keeps the exe small and the
look consistent with the pointer itself. Everything here works on logical
pixel coordinates scaled by the system DPI.
"""
from __future__ import annotations

import ctypes
from ctypes import POINTER, Structure, byref, c_int, c_ssize_t, c_ubyte, c_uint, c_void_p
from ctypes import wintypes as wt

from .win32 import BLENDFUNCTION, AC_SRC_ALPHA, AC_SRC_OVER, gdi32, kernel32, user32

msimg32 = ctypes.WinDLL("msimg32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)

LRESULT = c_ssize_t

# ------------------------------------------------------------------ constants
DT_LEFT, DT_CENTER, DT_RIGHT = 0x0000, 0x0001, 0x0002
DT_VCENTER, DT_SINGLELINE, DT_TOP = 0x0004, 0x0020, 0x0000
DT_WORDBREAK, DT_CALCRECT = 0x0010, 0x0400
DT_END_ELLIPSIS = 0x8000
DT_NOPREFIX = 0x0800

PS_SOLID, PS_CLEARTYPE = 0, 5
DEFAULT_CHARSET, CLEARTYPE_QUALITY = 1, 5
FW_NORMAL, FW_SEMIBOLD, FW_BOLD = 400, 600, 700

WM_PAINT, WM_ERASEBKGND = 0x000F, 0x0014
WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0200, 0x0201, 0x0202
WM_CLOSE, WM_DESTROY, WM_COMMAND = 0x0010, 0x0002, 0x0111
WM_SIZE = 0x0005
SIZE_MINIMIZED = 1
WM_CONTEXTMENU = 0x007B
WM_APP = 0x8000

# app shell: window class + the message a second instance posts to raise it
APP_WINDOW_CLASS = "NaiWaMouseAppWindow"
WM_SHOW_WINDOW = WM_APP + 2


WS_OVERLAPPED, WS_CAPTION, WS_SYSMENU, WS_MINIMIZEBOX = 0x0, 0x00C00000, 0x00080000, 0x00020000
SW_HIDE, SW_SHOW, SW_MINIMIZE, SW_RESTORE = 0, 5, 6, 9

NIM_ADD, NIM_MODIFY, NIM_DELETE, NIM_SETVERSION = 0, 1, 2, 4
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO, NIF_SHOWTIP = 0x1, 0x2, 0x4, 0x10, 0x80
NIIF_INFO = 0x1
NOTIFYICON_VERSION_4 = 4
NIN_SELECT = 0x0400

MF_STRING, MF_SEPARATOR, MF_CHECKED, MF_GRAYED = 0x0, 0x800, 0x8, 0x1
MF_POPUP, MF_DEFAULT = 0x10, 0x1000
TPM_RIGHTBUTTON, TPM_RETURNCMD, TPM_LEFTALIGN, TPM_BOTTOMALIGN = 0x2, 0x100, 0x0, 0x20

LR_LOADFROMFILE, IMAGE_ICON = 0x10, 1
IDC_ARROW = 32512


def rgb(r: int, g: int, b: int) -> int:
    """COLORREF is 0x00BBGGRR."""
    return (b << 16) | (g << 8) | r


def hex_color(text: str) -> int:
    text = text.lstrip("#")
    return rgb(int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))


# -------------------------------------------------------------------- structs
class RECT(Structure):
    _fields_ = [("left", wt.LONG), ("top", wt.LONG), ("right", wt.LONG), ("bottom", wt.LONG)]

    def __init__(self, left=0, top=0, right=0, bottom=0):
        super().__init__(left, top, right, bottom)

    @property
    def w(self) -> int:
        return self.right - self.left

    @property
    def h(self) -> int:
        return self.bottom - self.top


class PAINTSTRUCT(Structure):
    _fields_ = [
        ("hdc", wt.HDC), ("fErase", wt.BOOL), ("rcPaint", RECT),
        ("fRestore", wt.BOOL), ("fIncUpdate", wt.BOOL), ("rgbReserved", c_ubyte * 32),
    ]


class GUID(Structure):
    _fields_ = [
        ("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD),
        ("Data4", c_ubyte * 8),
    ]


class NOTIFYICONDATAW(Structure):
    _fields_ = [
        ("cbSize", wt.DWORD), ("hWnd", wt.HWND), ("uID", wt.UINT), ("uFlags", wt.UINT),
        ("uCallbackMessage", wt.UINT), ("hIcon", wt.HICON), ("szTip", wt.WCHAR * 128),
        ("dwState", wt.DWORD), ("dwStateMask", wt.DWORD), ("szInfo", wt.WCHAR * 256),
        ("uVersion", wt.UINT), ("szInfoTitle", wt.WCHAR * 64), ("dwInfoFlags", wt.DWORD),
        ("guidItem", GUID), ("hBalloonIcon", wt.HICON),
    ]


# ----------------------------------------------------------------- signatures
user32.BeginPaint.argtypes = [wt.HWND, POINTER(PAINTSTRUCT)]
user32.BeginPaint.restype = wt.HDC
user32.EndPaint.argtypes = [wt.HWND, POINTER(PAINTSTRUCT)]
user32.GetClientRect.argtypes = [wt.HWND, POINTER(RECT)]
user32.InvalidateRect.argtypes = [wt.HWND, POINTER(RECT), wt.BOOL]
user32.GetDC.argtypes = [wt.HWND]
user32.GetDC.restype = wt.HDC
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
user32.LoadImageW.argtypes = [wt.HINSTANCE, wt.LPCWSTR, wt.UINT, c_int, c_int, wt.UINT]
user32.LoadImageW.restype = wt.HANDLE
user32.DestroyIcon.argtypes = [wt.HICON]
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.AdjustWindowRectEx.argtypes = [POINTER(RECT), wt.DWORD, wt.BOOL, wt.DWORD]
shell32.Shell_NotifyIconW.argtypes = [wt.DWORD, POINTER(NOTIFYICONDATAW)]
shell32.Shell_NotifyIconW.restype = wt.BOOL
user32.CreatePopupMenu.restype = wt.HMENU
user32.AppendMenuW.argtypes = [wt.HMENU, wt.UINT, c_ssize_t, wt.LPCWSTR]
user32.TrackPopupMenu.argtypes = [
    wt.HMENU, wt.UINT, c_int, c_int, c_int, wt.HWND, c_void_p,
]
user32.TrackPopupMenu.restype = c_int
user32.DestroyMenu.argtypes = [wt.HMENU]
user32.RegisterWindowMessageW.argtypes = [wt.LPCWSTR]
user32.RegisterWindowMessageW.restype = wt.UINT
user32.LoadCursorW.argtypes = [wt.HINSTANCE, c_void_p]
user32.LoadCursorW.restype = wt.HANDLE

gdi32.CreateFontW.argtypes = [
    c_int, c_int, c_int, c_int, c_int, wt.DWORD, wt.DWORD, wt.DWORD,
    wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.LPCWSTR,
]
gdi32.CreateFontW.restype = wt.HANDLE
gdi32.CreateSolidBrush.argtypes = [wt.DWORD]
gdi32.CreateSolidBrush.restype = wt.HANDLE
gdi32.CreatePen.argtypes = [c_int, c_int, wt.DWORD]
gdi32.CreatePen.restype = wt.HANDLE
gdi32.GetStockObject.argtypes = [c_int]
gdi32.GetStockObject.restype = wt.HANDLE
gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi32.SelectObject.restype = wt.HGDIOBJ
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
gdi32.SetBkMode.argtypes = [wt.HDC, c_int]
gdi32.SetTextColor.argtypes = [wt.HDC, wt.DWORD]
gdi32.SetBkColor.argtypes = [wt.HDC, wt.DWORD]
gdi32.GetTextExtentPoint32W.argtypes = [wt.HDC, wt.LPCWSTR, c_int, POINTER(wt.SIZE)]
gdi32.RoundRect.argtypes = [wt.HDC, c_int, c_int, c_int, c_int, c_int, c_int]
gdi32.Ellipse.argtypes = [wt.HDC, c_int, c_int, c_int, c_int]
gdi32.Rectangle.argtypes = [wt.HDC, c_int, c_int, c_int, c_int]
gdi32.MoveToEx.argtypes = [wt.HDC, c_int, c_int, c_void_p]
gdi32.LineTo.argtypes = [wt.HDC, c_int, c_int]
gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.CreateCompatibleBitmap.argtypes = [wt.HDC, c_int, c_int]
gdi32.CreateCompatibleBitmap.restype = wt.HBITMAP
gdi32.BitBlt.argtypes = [wt.HDC, c_int, c_int, c_int, c_int, wt.HDC, c_int, c_int, wt.DWORD]
gdi32.DeleteDC.argtypes = [wt.HDC]

user32.FillRect.argtypes = [wt.HDC, POINTER(RECT), wt.HBRUSH]
user32.FillRect.restype = c_int
user32.DrawTextW.argtypes = [wt.HDC, wt.LPCWSTR, c_int, POINTER(RECT), wt.UINT]
user32.DrawTextW.restype = c_int

msimg32.AlphaBlend.argtypes = [
    wt.HDC, c_int, c_int, c_int, c_int, wt.HDC, c_int, c_int, c_int, c_int, BLENDFUNCTION,
]
msimg32.AlphaBlend.restype = wt.BOOL

TRANSPARENT = 1


class Font:
    """A GDI font handle, deleted on close()."""

    def __init__(self, pt: float, dpi: int, weight: int = FW_NORMAL, face: str = "Microsoft YaHei UI"):
        height = -round(pt * dpi / 72)
        self.handle = gdi32.CreateFontW(
            height, 0, 0, 0, weight, 0, 0, 0,
            DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, face,
        )

    def close(self) -> None:
        if self.handle:
            gdi32.DeleteObject(self.handle)
            self.handle = None


class Painter:
    """Draws on a device context using DPI-scaled logical pixels."""

    def __init__(self, hdc: int, dpi: int):
        self.hdc = hdc
        self.dpi = dpi
        self.s = dpi / 96.0

    # ------------------------------------------------------------- geometry
    def px(self, value: float) -> int:
        return round(value * self.s)

    def rect(self, x: float, y: float, w: float, h: float) -> tuple[int, int, int, int]:
        return self.px(x), self.px(y), self.px(x) + self.px(w), self.px(y) + self.px(h)

    # -------------------------------------------------------------- drawing
    def _brush(self, color: int):
        return gdi32.CreateSolidBrush(color)

    def _pen(self, color: int, width: int = 1):
        return gdi32.CreatePen(PS_SOLID, max(1, self.px(width)), color)

    def fill(self, box, color: int) -> None:
        x0, y0, x1, y1 = box
        brush = self._brush(color)
        rect = RECT(x0, y0, x1, y1)
        user32.FillRect(self.hdc, byref(rect), brush)
        gdi32.DeleteObject(brush)

    def round_rect(self, box, radius: float, fill: int | None = None,
                   border: int | None = None, width: float = 1) -> None:
        x0, y0, x1, y1 = box
        if fill is not None:
            brush = self._brush(fill)
        else:
            brush = gdi32.GetStockObject(5)  # NULL_BRUSH
        pen = self._pen(border, width) if border is not None else gdi32.GetStockObject(8)  # NULL_PEN
        ob, op = gdi32.SelectObject(self.hdc, brush), gdi32.SelectObject(self.hdc, pen)
        r = self.px(radius)
        gdi32.RoundRect(self.hdc, x0, y0, x1, y1, r * 2, r * 2)
        gdi32.SelectObject(self.hdc, ob)
        gdi32.SelectObject(self.hdc, op)
        if fill is not None:
            gdi32.DeleteObject(brush)
        if border is not None:
            gdi32.DeleteObject(pen)

    def circle(self, cx: float, cy: float, r: float, fill: int | None = None,
               border: int | None = None, width: float = 1) -> None:
        x, y, rr = self.px(cx), self.px(cy), self.px(r)
        brush = self._brush(fill) if fill is not None else gdi32.GetStockObject(5)
        pen = self._pen(border, width) if border is not None else gdi32.GetStockObject(8)
        ob, op = gdi32.SelectObject(self.hdc, brush), gdi32.SelectObject(self.hdc, pen)
        gdi32.Ellipse(self.hdc, x - rr, y - rr, x + rr, y + rr)
        gdi32.SelectObject(self.hdc, ob)
        gdi32.SelectObject(self.hdc, op)
        if fill is not None:
            gdi32.DeleteObject(brush)
        if border is not None:
            gdi32.DeleteObject(pen)

    def line(self, x0: float, y0: float, x1: float, y1: float, color: int, width: float = 1) -> None:
        pen = self._pen(color, width)
        op = gdi32.SelectObject(self.hdc, pen)
        gdi32.MoveToEx(self.hdc, self.px(x0), self.px(y0), None)
        gdi32.LineTo(self.hdc, self.px(x1), self.px(y1))
        gdi32.SelectObject(self.hdc, op)
        gdi32.DeleteObject(pen)

    # ----------------------------------------------------------------- text
    def text(self, text: str, box, font: Font, color: int,
             flags: int = DT_LEFT | DT_TOP | DT_SINGLELINE | DT_NOPREFIX) -> int:
        gdi32.SelectObject(self.hdc, font.handle)
        gdi32.SetBkMode(self.hdc, TRANSPARENT)
        gdi32.SetTextColor(self.hdc, color)
        rect = RECT(*box)
        return user32.DrawTextW(self.hdc, text, len(text), byref(rect), flags)

    def text_width(self, text: str, font: Font) -> int:
        gdi32.SelectObject(self.hdc, font.handle)
        size = wt.SIZE()
        gdi32.GetTextExtentPoint32W(self.hdc, text, len(text), byref(size))
        return size.cx

    def text_height(self, text: str, font: Font, width: float) -> int:
        gdi32.SelectObject(self.hdc, font.handle)
        rect = RECT(0, 0, self.px(width), 0)
        user32.DrawTextW(self.hdc, text, len(text), byref(rect), DT_CALCRECT | DT_WORDBREAK | DT_NOPREFIX)
        return rect.bottom

    # ---------------------------------------------------------------- image
    def image(self, surface, x: float, y: float, w: float, h: float) -> None:
        """Alpha-blend a premultiplied Surface into the box (top-left anchored)."""
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        msimg32.AlphaBlend(
            self.hdc, self.px(x), self.px(y), self.px(w), self.px(h),
            surface.hdc, 0, 0, surface.w, surface.h, blend,
        )


class DoubleBuffer:
    """Off-screen bitmap for flicker-free painting."""

    def __init__(self):
        self.hdc = 0
        self.hbmp = 0
        self._old = 0
        self.size = (0, 0)

    def begin(self, hdc: int, w: int, h: int) -> int:
        if self.hdc and self.size == (w, h):
            return self.hdc
        self.release()
        self.hdc = gdi32.CreateCompatibleDC(hdc)
        self.hbmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
        self._old = gdi32.SelectObject(self.hdc, self.hbmp)
        self.size = (w, h)
        return self.hdc

    def end(self, hdc: int) -> None:
        if self.hdc:
            gdi32.BitBlt(hdc, 0, 0, self.size[0], self.size[1], self.hdc, 0, 0, 0x00CC0020)

    def release(self) -> None:
        if self.hdc:
            gdi32.SelectObject(self.hdc, self._old)
            gdi32.DeleteObject(self.hbmp)
            gdi32.DeleteDC(self.hdc)
            self.hdc = self.hbmp = 0
            self.size = (0, 0)


class Tray:
    """Notification-area icon with a right-click menu (all Chinese labels)."""

    def __init__(self, hwnd: int, hicon: int, callback_msg: int, tip: str = "NaiWa Mouse"):
        self.hwnd = hwnd
        self.hicon = hicon
        self.callback = callback_msg
        self.tip = tip
        self._data = NOTIFYICONDATAW()
        self._data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        self._data.hWnd = hwnd
        self._data.uID = 1
        self._data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_SHOWTIP
        self._data.uCallbackMessage = callback_msg
        self._data.hIcon = hicon
        self._data.szTip = tip
        self.visible = False

    def add(self) -> bool:
        ok = bool(shell32.Shell_NotifyIconW(NIM_ADD, byref(self._data)))
        if ok:
            self.visible = True
            self._data.uVersion = NOTIFYICON_VERSION_4
            shell32.Shell_NotifyIconW(NIM_SETVERSION, byref(self._data))
        return ok

    def remove(self) -> None:
        if self.visible:
            shell32.Shell_NotifyIconW(NIM_DELETE, byref(self._data))
            self.visible = False

    def notify(self, title: str, text: str) -> None:
        data = NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        data.hWnd = self.hwnd
        data.uID = 1
        data.uFlags = NIF_INFO
        data.szInfoTitle = title
        data.szInfo = text
        data.dwInfoFlags = NIIF_INFO
        shell32.Shell_NotifyIconW(NIM_MODIFY, byref(data))

    def menu(self, items: list[tuple[int, str, bool, bool]]) -> int:
        """items: (id, label, checked, enabled). Returns the chosen id or 0."""
        menu = user32.CreatePopupMenu()
        for item_id, label, checked, enabled in items:
            if item_id == 0:
                user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
                continue
            flags = MF_STRING
            if checked:
                flags |= MF_CHECKED
            if not enabled:
                flags |= MF_GRAYED
            user32.AppendMenuW(menu, flags, item_id, label)

        pt = wt.POINT()
        user32.GetCursorPos(byref(pt))
        user32.SetForegroundWindow(self.hwnd)
        cmd = user32.TrackPopupMenu(
            menu, TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_BOTTOMALIGN,
            pt.x, pt.y, 0, self.hwnd, None,
        )
        user32.DestroyMenu(menu)
        return int(cmd)
