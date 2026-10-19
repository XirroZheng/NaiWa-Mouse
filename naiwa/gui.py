"""Desktop app shell: a small settings window plus a tray icon.

The skin itself is an invisible layered window driven by `SkinEngine`; this
module adds the visible parts - a settings window (drawn with GDI, no GUI
toolkit) and a notification-area icon. Both share the engine's message loop,
so there is no cross-thread state to worry about.

Closing the window hides it to the tray; the skin and the tray icon keep
running. Only "退出（恢复系统鼠标）" in the tray menu actually quits.
"""
from __future__ import annotations

import ctypes
import logging
from ctypes import byref, c_void_p, sizeof
from ctypes import wintypes as wt

from . import __version__
from .config import Config
from .engine import SkinEngine, MODES
from .skin import load_layer
from .ui import (
    APP_WINDOW_CLASS,
    DT_NOPREFIX, DT_SINGLELINE, DT_LEFT, DT_TOP,
    DoubleBuffer, Font, Painter, PAINTSTRUCT, RECT, Tray,
    FW_BOLD, FW_NORMAL,
    IDC_ARROW, IMAGE_ICON, LR_LOADFROMFILE,
    NIN_SELECT,
    WS_CAPTION, WS_MINIMIZEBOX, WS_OVERLAPPED, WS_SYSMENU,
    SW_HIDE, SW_RESTORE, SW_SHOW,
    SIZE_MINIMIZED,
    WM_CLOSE, WM_DESTROY, WM_ERASEBKGND, WM_LBUTTONDOWN,
    WM_MOUSEMOVE, WM_PAINT, WM_SHOW_WINDOW, WM_SIZE,
    hex_color, user32, kernel32,
)
from .win32 import SWP_NOMOVE, SWP_NOSIZE, WNDCLASSEXW, WNDPROC

user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int
user32.IsIconic.argtypes = [wt.HWND]
user32.IsIconic.restype = wt.BOOL

log = logging.getLogger("ui")

APP_NAME = "NaiWa Mouse"
CLASS_NAME = APP_WINDOW_CLASS
TRAY_MSG = 0x8000 + 1  # WM_APP + 1

# ---------------------------------------------------------------- palette
C_BG = hex_color("F7F6F2")
C_CARD = hex_color("FFFFFF")
C_CARD_IDLE = hex_color("F0EEE7")
C_CARD_HOVER = hex_color("FAF9F5")
C_BORDER_SEL = hex_color("5F9440")
C_BORDER_IDLE = hex_color("E2DFD5")
C_TITLE = hex_color("23221D")
C_TEXT = hex_color("4A4740")
C_MUTED = hex_color("8B877C")
C_DIVIDER = hex_color("E6E3D9")
C_ACCENT = hex_color("5F9440")
C_DOT_OFF = hex_color("BFBBB0")
C_PILL_BG = hex_color("EDF3E6")

# ---------------------------------------------------------------- layout (96dpi)
CLIENT_W, CLIENT_H = 470, 440
PAD = 26
CARD_W = CLIENT_W - PAD * 2
CARD_H = 84
CARD1_Y = 128
CARD2_Y = 224
DIV1_Y = 92
LABEL_Y = 106
DIV2_Y = CARD2_Y + CARD_H + 22
STATUS_Y = DIV2_Y + 16
FOOTER_Y = 386

# tray menu ids
ID_SHOW, ID_MINIMAL, ID_FULL, ID_QUIT = 1001, 1002, 1003, 1099

MODE_LABEL = {"minimal": "极简模式", "full": "完整模式"}


class SkinApp:
    def __init__(self, cfg: Config, dpi: int):
        self.cfg = cfg
        self.dpi = dpi or 96
        self.s = self.dpi / 96.0
        self.hover = -1
        self.cards: list[tuple[int, int, int, int]] = []
        self.buf = DoubleBuffer()
        self._hid_notice = False

        self.engine = SkinEngine(cfg)
        self.mode = self.engine.mode

        self._init_fonts()
        self._init_images()

        self.hinst = kernel32.GetModuleHandleW(None)
        self.hicon = self._load_icon(32)
        # registered *before* CreateWindowEx: WM_CREATE/WM_PAINT arrive inside it
        self._taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")
        self.hwnd = self._create_window()
        self.tray = Tray(self.hwnd, self.hicon or 0, TRAY_MSG, APP_NAME)
        log.info("tray icon %s (icon=%s)", "added" if self.tray.add() else "FAILED", self.hicon)

        log.info("window ready, mode=%s", self.mode)

    # ------------------------------------------------------------- resources
    def _init_fonts(self) -> None:
        self.f_title = Font(15, self.dpi, FW_BOLD)
        self.f_card = Font(10.5, self.dpi, FW_BOLD)
        self.f_body = Font(8.8, self.dpi, FW_NORMAL)
        self.f_label = Font(9, self.dpi, FW_BOLD)
        self.f_small = Font(8.6, self.dpi, FW_NORMAL)

    def _init_images(self) -> None:
        self.pic = {}
        for key, asset in (("minimal", "default.png"), ("full", "glimpse.png")):
            path = self.cfg.asset_path(asset)
            self.pic[key] = load_layer(path, round(40 * self.s), "center", 0).surface
        self.header = load_layer(
            self.cfg.asset_path("glimpse.png"), round(42 * self.s), "center", 0
        ).surface

    def _load_icon(self, size: int) -> int:
        path = self.cfg.asset_path("app.ico")
        if not path.exists():
            return 0
        return int(user32.LoadImageW(None, str(path), IMAGE_ICON, size, size, LR_LOADFROMFILE) or 0)

    # ---------------------------------------------------------------- window
    def _create_window(self) -> int:
        self._proc = WNDPROC(self._wndproc)
        wc = WNDCLASSEXW()
        wc.cbSize = sizeof(WNDCLASSEXW)
        wc.style = 0
        wc.lpfnWndProc = self._proc
        wc.hInstance = self.hinst
        wc.hIcon = self.hicon or 0
        wc.hCursor = user32.LoadCursorW(None, c_void_p(IDC_ARROW))
        wc.hbrBackground = 0
        wc.lpszClassName = CLASS_NAME
        wc.hIconSm = self.hicon or 0
        if not user32.RegisterClassExW(byref(wc)):
            if ctypes.get_last_error() != 1410:  # already registered
                raise ctypes.WinError(ctypes.get_last_error())

        style = WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX
        rect = RECT(0, 0, round(CLIENT_W * self.s), round(CLIENT_H * self.s))
        user32.AdjustWindowRectEx(byref(rect), style, False, 0)
        w = rect.w
        h = rect.h
        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)
        x = max(0, (screen_w - w) // 2 - round(60 * self.s))
        y = max(0, (screen_h - h) // 2 - round(40 * self.s))

        hwnd = user32.CreateWindowExW(
            0, CLASS_NAME, APP_NAME, style, x, y, w, h, None, None, self.hinst, None
        )
        if not hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        return hwnd

    def show_window(self) -> None:
        user32.ShowWindow(self.hwnd, SW_RESTORE if user32.IsIconic(self.hwnd) else SW_SHOW)
        user32.SetForegroundWindow(self.hwnd)
        # A process started in the background is not allowed to take the
        # foreground; bouncing through topmost raises the window anyway.
        user32.SetWindowPos(self.hwnd, c_void_p(-1), 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
        user32.SetWindowPos(self.hwnd, c_void_p(-2), 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
        user32.InvalidateRect(self.hwnd, None, False)

    def _hide_to_tray(self) -> None:
        user32.ShowWindow(self.hwnd, SW_HIDE)
        if not self._hid_notice:
            self.tray.notify(APP_NAME, "已最小化到托盘，右键托盘图标可退出并恢复鼠标。")
            self._hid_notice = True
        log.info("window hidden to tray")

    # ------------------------------------------------------------- wndproc
    def _wndproc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_PAINT:
                self._paint(hwnd)
                return 0
            if msg == WM_ERASEBKGND:
                return 1
            if msg == WM_MOUSEMOVE:
                self._on_move(self._mouse_xy(lparam))
                return 0
            if msg == WM_LBUTTONDOWN:
                self._on_click(self._mouse_xy(lparam))
                return 0
            if msg == WM_SIZE and wparam == SIZE_MINIMIZED:
                # the taskbar button is meaningless here: the app lives in the tray
                self._hide_to_tray()
                return 0
            if msg == WM_CLOSE:
                self._hide_to_tray()
                return 0
            if msg == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
            if msg == WM_SHOW_WINDOW:  # second launch asked us to come forward
                self.show_window()
                return 0
            if msg == TRAY_MSG:
                self._on_tray(lparam)
                return 0
            if msg == self._taskbar_created:
                self.tray.add()
                return 0
        except Exception:
            log.exception("window procedure failed")
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    @staticmethod
    def _mouse_xy(lparam) -> tuple[int, int]:
        x = ctypes.c_short(lparam & 0xFFFF).value
        y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
        return x, y

    def _card_at(self, x: int, y: int) -> int:
        for index, (x0, y0, x1, y1) in enumerate(self.cards):
            if x0 <= x < x1 and y0 <= y < y1:
                return index
        return -1

    def _on_move(self, pos: tuple[int, int]) -> None:
        index = self._card_at(*pos)
        if index != self.hover:
            self.hover = index
            user32.InvalidateRect(self.hwnd, None, False)

    def _on_click(self, pos: tuple[int, int]) -> None:
        index = self._card_at(*pos)
        if index == 0:
            self.set_mode("minimal")
        elif index == 1:
            self.set_mode("full")

    def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            return
        self.mode = self.engine.set_mode(mode)
        self.cfg.save_mode(self.mode)
        log.info("mode set to %s", self.mode)
        user32.InvalidateRect(self.hwnd, None, False)

    # ----------------------------------------------------------------- tray
    def _on_tray(self, lparam) -> None:
        event = lparam & 0xFFFF
        if event == 0x0205 or event == NIN_SELECT:  # WM_RBUTTONUP / left click
            if event == NIN_SELECT:
                self.show_window()
            else:
                self._tray_menu()
        elif event == 0x007B:  # WM_CONTEXTMENU
            self._tray_menu()

    def _tray_menu(self) -> None:
        cmd = self.tray.menu([
            (ID_SHOW, "打开主界面", False, True),
            (0, "", False, True),
            (ID_MINIMAL, "极简模式", self.mode == "minimal", True),
            (ID_FULL, "完整模式", self.mode == "full", True),
            (0, "", False, True),
            (ID_QUIT, "退出（恢复系统鼠标）", False, True),
        ])
        if cmd == ID_SHOW:
            self.show_window()
        elif cmd == ID_MINIMAL:
            self.set_mode("minimal")
        elif cmd == ID_FULL:
            self.set_mode("full")
        elif cmd == ID_QUIT:
            self.quit()

    def quit(self) -> None:
        log.info("quit from tray/menu")
        self.engine.quit()

    # ---------------------------------------------------------------- paint
    def _paint(self, hwnd) -> None:
        ps = PAINTSTRUCT()
        hdc = user32.BeginPaint(hwnd, byref(ps))
        if not hdc:
            return
        rc = RECT()
        user32.GetClientRect(hwnd, byref(rc))
        mem = self.buf.begin(hdc, rc.w, rc.h)
        painter = Painter(mem, self.dpi)
        self._draw(painter, rc.w, rc.h)
        self.buf.end(hdc)
        user32.EndPaint(hwnd, byref(ps))

    def _draw(self, p: Painter, w_px: int, h_px: int) -> None:
        p.fill((0, 0, w_px, h_px), C_BG)

        # header -------------------------------------------------------
        p.image(self.header, PAD, 20, self.header.w / p.s, self.header.h / p.s)
        p.text(APP_NAME, p.rect(PAD + 56, 24, 220, 26), self.f_title, C_TITLE)
        p.text(f"桌面鼠标皮肤 v{__version__}", p.rect(PAD + 57, 52, 240, 18), self.f_small, C_MUTED)

        pill = p.rect(CLIENT_W - PAD - 74, 32, 74, 26)
        p.round_rect(pill, 13, C_PILL_BG)
        p.circle(CLIENT_W - PAD - 74 + 16, 45, 3.5, C_ACCENT)
        p.text("运行中", p.rect(CLIENT_W - PAD - 74 + 26, 37, 44, 16), self.f_small, C_ACCENT)

        p.line(PAD, DIV1_Y, CLIENT_W - PAD, DIV1_Y, C_DIVIDER)
        p.text("外观模式", p.rect(PAD, LABEL_Y, 200, 16), self.f_label, C_MUTED)

        # cards --------------------------------------------------------
        self.cards = []
        for index, (y, key, title, desc) in enumerate((
            (CARD1_Y, "minimal", "极简模式", "所有状态都用同一枚黄绿黑圆盘"),
            (CARD2_Y, "full", "完整模式", "平时探头张望，按键时举手、托腮"),
        )):
            selected = self.mode == key
            box = p.rect(PAD, y, CARD_W, CARD_H)
            self.cards.append(box)
            if selected:
                p.round_rect(box, 10, C_CARD, C_BORDER_SEL, 1.4)
            else:
                fill = C_CARD_HOVER if self.hover == index else C_CARD_IDLE
                p.round_rect(box, 10, fill, C_BORDER_IDLE, 1)

            cx, cy = PAD + 24, y + 30
            if selected:
                p.circle(cx, cy, 7.5, None, C_ACCENT, 1.6)
                p.circle(cx, cy, 3.5, C_ACCENT)
            else:
                p.circle(cx, cy, 7.5, None, C_DOT_OFF, 1.4)

            p.text(title, p.rect(PAD + 46, y + 17, 200, 20), self.f_card,
                   C_TITLE if selected else C_TEXT)
            p.text(desc, p.rect(PAD + 47, y + 45, 250, 18), self.f_body, C_MUTED)

            surface = self.pic[key]
            pw = surface.w / p.s
            ph = surface.h / p.s
            p.image(surface, CLIENT_W - PAD - 16 - pw, y + (CARD_H - ph) / 2, pw, ph)

        # status -------------------------------------------------------
        p.line(PAD, DIV2_Y, CLIENT_W - PAD, DIV2_Y, C_DIVIDER)
        p.circle(PAD + 4, STATUS_Y + 8, 3.5, C_ACCENT)
        status = f"当前：{MODE_LABEL.get(self.mode, self.mode)}　·　系统指针已由皮肤接管"
        p.text(status, p.rect(PAD + 14, STATUS_Y, CARD_W - 14, 18), self.f_small, C_TEXT)

        # footer -------------------------------------------------------
        p.text("关闭窗口会最小化到托盘，皮肤继续生效",
               p.rect(PAD, FOOTER_Y, CARD_W, 16), self.f_small, C_MUTED)
        p.text("右键托盘图标 → 退出，即恢复系统鼠标",
               p.rect(PAD, FOOTER_Y + 20, CARD_W, 16), self.f_small, C_MUTED)

    # ----------------------------------------------------------------- run
    def run(self) -> int:
        try:
            self.engine.prepare()
        except Exception:
            self.tray.remove()
            self.engine.shutdown()
            raise
        self.show_window()
        msg = wt.MSG()
        try:
            while True:
                ret = user32.GetMessageW(byref(msg), None, 0, 0)
                if ret == 0:
                    break
                if ret == -1:
                    raise ctypes.WinError(ctypes.get_last_error())
                user32.TranslateMessage(byref(msg))
                user32.DispatchMessageW(byref(msg))
        finally:
            log.info("window loop ended")
            self.tray.remove()
            self.engine.shutdown()
            self.buf.release()
            for font in (self.f_title, self.f_card, self.f_body, self.f_label, self.f_small):
                font.close()
            if self.hwnd:
                user32.DestroyWindow(self.hwnd)
                self.hwnd = 0
        return 0


def run_app(cfg: Config, dpi: int) -> int:
    app = SkinApp(cfg, dpi)
    return app.run()
