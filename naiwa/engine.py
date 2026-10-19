"""The engine: message loop, pointer tracking and pose state machine."""
from __future__ import annotations

import ctypes
import logging
import time
from collections.abc import Callable

from .config import Config
from .hook import MouseHook, SystemCursor
from .skin import Layer, load_flipbook, load_layer
from .win32 import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_NOREPEAT,
    MOD_SHIFT,
    MOD_WIN,
    WM_DESTROY,
    WM_HOTKEY,
    WM_LBUTTONDOWN,
    WM_LBUTTONUP,
    WM_RBUTTONDOWN,
    WM_RBUTTONUP,
    WM_TIMER,
    WNDPROC,
    cursor_pos,
    gdi32,
    kernel32,
    get_dpi,
    set_dpi_aware,
    user32,
)
from .window import LayeredWindow
from ctypes import byref
from ctypes import wintypes as wt

log = logging.getLogger("skin")

TIMER_ID = 1
HK_QUIT, HK_CURSOR, HK_SKIN = 1, 2, 3
MODES = ("minimal", "full")

_VK_EXTRA = {
    "space": 0x20, "tab": 0x09, "esc": 0x1B, "enter": 0x0D,
    "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23,
    "pause": 0x13, "printscreen": 0x2C,
}


def parse_hotkey(text: str) -> tuple[int, int]:
    mods, vk = 0, 0
    for part in str(text).lower().split("+"):
        part = part.strip()
        if part in ("ctrl", "control"):
            mods |= MOD_CONTROL
        elif part == "alt":
            mods |= MOD_ALT
        elif part == "shift":
            mods |= MOD_SHIFT
        elif part in ("win", "meta"):
            mods |= MOD_WIN
        elif len(part) == 1:
            vk = ord(part.upper())
        elif part in _VK_EXTRA:
            vk = _VK_EXTRA[part]
    return mods | MOD_NOREPEAT, vk


class SkinEngine:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.state = "idle"
        self.left_down = False
        self.right_down = False
        self.pending_idle_at: float | None = None
        self.visible = True
        self._needs_flush = True
        self._last_top = 0.0
        self.auto_stop_at: float | None = None
        self.demo = False
        self._demo_at = 0.0
        self._demo_i = 0
        self.busy = False
        self._busy_at = 0.0
        self._frame_i = 0
        self._frame_at = 0.0
        self._cursor = SystemCursor()
        self.cursor_hidden = False
        self._hotkeys: dict[int, Callable[[], None]] = {}

        self.win = LayeredWindow(self._wndproc)

        dpi = get_dpi() if cfg["auto_dpi_scale"] else 96
        self.scale = dpi / 96.0
        log.info("dpi=%s scale=%.2f", dpi, self.scale)

        self.mode = cfg.mode
        self._built: dict[str, dict[str, Layer]] = {}
        self.layers: dict[str, Layer] = self._build_layers(self.mode)
        self._built[self.mode] = self.layers
        if "idle" not in self.layers:
            raise RuntimeError("config must define an 'idle' state")

        self.hook = MouseHook(self._on_mouse)

    # -------------------------------------------------------------- modes
    def _layer_specs(self, mode: str) -> dict[str, dict]:
        """Resolve per-state layer specs for one mode.

        minimal: every state collapses onto the plain disc pointer.
        full:    the configured poses, every non-idle one scaled up by
                 `modes.full.others_scale`.
        """
        states = {name: dict(spec) for name, spec in self.cfg["states"].items()}
        if mode == "minimal":
            mini = dict(self.cfg["modes"]["minimal"])
            return {name: dict(mini) for name in states}

        factor = float(self.cfg["modes"]["full"].get("others_scale", 1.0))
        if factor != 1.0:
            for name, spec in states.items():
                if name == "idle":
                    continue
                if spec.get("height") is not None:
                    spec["height"] = float(spec["height"]) * factor
                else:
                    spec["scale"] = float(spec.get("scale", 1.0)) * factor
        return states

    def _build_layers(self, mode: str) -> dict[str, Layer]:
        specs = self._layer_specs(mode)
        idle_h = float(self.cfg["states"]["idle"]["height"])
        cache: dict[str, Layer] = {}
        layers: dict[str, Layer] = {}
        for name, spec in specs.items():
            key = repr(sorted(spec.items()))
            if key in cache:  # identical specs share one layer (all of minimal)
                layers[name] = cache[key]
                continue
            height = spec.get("height")
            if height is None:
                height = idle_h * float(spec.get("scale", 1.0))
            px = max(16, round(float(height) * self.scale))
            offset = round(float(spec.get("press_offset", 0)) * self.scale)
            anchor = spec.get("anchor", "bottom")
            sheet = spec.get("sheet")
            if sheet:
                layer = load_flipbook(self.cfg.asset_path(sheet), px, anchor, offset)
            else:
                path = self.cfg.asset_path(spec["asset"])
                if not path.exists():
                    raise FileNotFoundError(f"missing asset: {path}")
                layer = load_layer(path, px, anchor, offset)
            cache[key] = layer
            layers[name] = layer
            extra = f" {len(layer.frames)}f/{layer.frame_ms}ms" if layer.animated else ""
            log.info("loaded %-6s %dx%d%s [%s]", name, layer.width, layer.height, extra, mode)
        return layers

    def set_mode(self, mode: str) -> str:
        """Swap the pose set at runtime. Call on the message-loop thread."""
        mode = mode if mode in MODES else "full"
        if mode == self.mode:
            return mode
        # layers stay cached (a few KB each): freeing them here would leave the
        # cache pointing at closed GDI surfaces, so switching back would fail
        if mode not in self._built:
            self._built[mode] = self._build_layers(mode)
        self.layers = self._built[mode]
        self.mode = mode

        self.state = self._compose()
        layer = self.layers[self.state]
        if layer.animated:
            self._frame_i = 0
            layer.show_frame(0)
            self._frame_at = time.perf_counter() + layer.frame_ms / 1000.0
        self.win.set_surface(layer.surface)
        self._needs_flush = True
        if self.visible:
            self._flush()
        log.info("mode -> %s", mode)
        return mode

    def _close_layers(self) -> None:
        seen: set[int] = set()
        for layers in self._built.values():
            for layer in layers.values():
                if id(layer.surface) in seen:
                    continue
                seen.add(id(layer.surface))
                try:
                    layer.surface.close()
                except Exception:
                    log.debug("surface close failed", exc_info=True)

    # ------------------------------------------------------------- window
    def _wndproc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_TIMER:
                self.tick()
                return 0
            if msg == WM_HOTKEY:
                action = self._hotkeys.get(int(wparam))
                if action:
                    action()
                return 0
            if msg == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
        except Exception:
            log.exception("window procedure failed")
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    # ------------------------------------------------------------- states
    def _compose(self) -> str:
        if self.right_down:
            return "right"
        if self.left_down:
            return "left"
        if self.busy:
            return "wait"
        return "idle"

    def _set_state(self, name: str) -> None:
        if name not in self.layers:
            name = "idle"
        if name == self.state:
            return
        self.state = name
        layer = self.layers[name]
        if layer.animated:
            self._frame_i = 0
            layer.show_frame(0)
            self._frame_at = time.perf_counter() + layer.frame_ms / 1000.0
        self.win.set_surface(layer.surface)
        self._needs_flush = True
        self._flush()

    def _schedule_idle(self, ms: float) -> None:
        if self.left_down or self.right_down:
            return
        self.pending_idle_at = time.perf_counter() + max(0, ms) / 1000.0

    # ------------------------------------------------------------- input
    def _on_mouse(self, msg: int) -> None:
        if not self.visible or self.demo:
            return
        log.debug("mouse msg=0x%04x", msg)
        if msg == WM_LBUTTONDOWN:
            self.left_down = True
            self.pending_idle_at = None
            self._set_state(self._compose())
        elif msg == WM_LBUTTONUP:
            self.left_down = False
            self._schedule_idle(float(self.cfg["timing"]["idle_after_left_ms"]))
        elif msg == WM_RBUTTONDOWN:
            self.right_down = True
            self.pending_idle_at = None
            self._set_state(self._compose())
        elif msg == WM_RBUTTONUP:
            self.right_down = False
            self._schedule_idle(float(self.cfg["timing"]["idle_after_right_ms"]))

    # ------------------------------------------------------------- drawing
    def _flush(self) -> None:
        if not self.visible:
            return
        layer = self.layers[self.state]
        cx, cy = cursor_pos()
        x, y = layer.origin(cx, cy)
        self.win.set_surface(layer.surface)
        self.win.move(x, y)
        if not self.win.flush():
            log.debug("UpdateLayeredWindow failed: %s", ctypes.get_last_error())
        self._needs_flush = False

    def tick(self) -> None:
        if not self.visible:
            return
        now = time.perf_counter()
        if self.auto_stop_at is not None and now >= self.auto_stop_at:
            self.quit()
            return
        if self.demo:
            if now >= self._demo_at:
                seq = ("idle", "left", "right", "wait")
                self._demo_i = (self._demo_i + 1) % len(seq)
                self._set_state(seq[self._demo_i])
                self._demo_at = now + 1.8
        if self.pending_idle_at is not None and now >= self.pending_idle_at:
            self.pending_idle_at = None
            self._set_state(self._compose())
            return

        # Watch for the shell switching to its busy cursor (the spinner). This
        # is what "waiting" means here: not idle, but a program is working.
        if not self.demo and not (self.left_down or self.right_down) and now - self._busy_at > 0.08:
            self._busy_at = now
            busy = self._cursor.system_busy()
            if busy != self.busy:
                self.busy = busy
                log.debug("busy=%s", busy)
                self._set_state(self._compose())

        layer = self.layers[self.state]
        if layer.animated and now >= self._frame_at:
            self._frame_i = (self._frame_i + 1) % len(layer.frames)
            layer.show_frame(self._frame_i)
            self._frame_at = now + layer.frame_ms / 1000.0
            self._needs_flush = True

        cx, cy = cursor_pos()
        x, y = layer.origin(cx, cy)
        if self.win.move(x, y) or self._needs_flush:
            self.win.flush()
            self._needs_flush = False

        if now - self._last_top > 2.0:
            self._last_top = now
            self.win.raise_top()
            if self.cursor_hidden:
                # some apps re-set their own cursor; nudge ours back
                self._cursor.hide()

    # ------------------------------------------------------------- hotkeys
    def _register_hotkeys(self) -> None:
        specs = self.cfg["hotkeys"]
        table = {
            HK_QUIT: ("quit", self.quit),
            HK_CURSOR: ("toggle_cursor", self.toggle_cursor),
            HK_SKIN: ("toggle_skin", self.toggle_skin),
        }
        for hk_id, (key, fn) in table.items():
            text = specs.get(key)
            if not text:
                continue
            mods, vk = parse_hotkey(text)
            if not vk:
                log.warning("hotkey %r could not be parsed", text)
                continue
            if user32.RegisterHotKey(self.win.hwnd, hk_id, mods, vk):
                self._hotkeys[hk_id] = fn
                log.info("hotkey %s -> %s", text, key)
            else:
                log.warning("hotkey %s is already taken", text)

    def toggle_cursor(self) -> None:
        if self.cursor_hidden:
            self._cursor.restore()
            self.cursor_hidden = False
            log.info("system cursor shown")
        else:
            self._cursor.hide()
            self.cursor_hidden = True
            log.info("system cursor hidden")

    def toggle_skin(self) -> None:
        self.visible = not self.visible
        if self.visible:
            self.win.show()
            if self.cfg["cursor"]["hide_system_cursor"]:
                self._cursor.hide()
                self.cursor_hidden = True
            self._needs_flush = True
            self._flush()
        else:
            self.win.hide()
            if self._cursor.hidden:
                self._cursor.restore()
                self.cursor_hidden = False
        log.info("skin %s", "shown" if self.visible else "hidden")

    def quit(self) -> None:
        log.info("quit requested")
        user32.PostQuitMessage(0)

    # -------------------------------------------------------------- run
    def prepare(self) -> None:
        """Arm everything and show the skin; the caller owns the message loop."""
        set_dpi_aware()
        self.hook.install()
        self._register_hotkeys()

        if self.cfg["cursor"]["hide_system_cursor"]:
            self._cursor.hide()
            self.cursor_hidden = True

        layer = self.layers[self.state]
        self.win.set_surface(layer.surface)
        self._flush()
        self.win.show()
        self.win.raise_top()

        fps = max(10, min(120, int(self.cfg["timing"]["fps"])))
        user32.SetTimer(self.win.hwnd, TIMER_ID, max(8, round(1000 / fps)), None)
        log.info("running at %d fps", fps)

    def run(self) -> None:
        self.prepare()
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
            self.shutdown()

    def shutdown(self) -> None:
        log.info("shutting down")
        try:
            user32.KillTimer(self.win.hwnd, TIMER_ID)
        except Exception:
            pass
        try:
            self.hook.uninstall()
        except Exception:
            pass
        if self.cursor_hidden or self._cursor.hidden:
            self._cursor.restore()
            self.cursor_hidden = False
        try:
            self.win.close()
        except Exception:
            pass
        self._close_layers()
