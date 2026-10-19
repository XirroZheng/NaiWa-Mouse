"""Application bootstrap: paths, logging, single instance, CLI.

    python app.py                 # settings window + skin
    python app.py --headless      # skin only, no window
    python app.py --restore-cursor
"""
from __future__ import annotations

import argparse
import atexit
import ctypes
import logging
import logging.handlers
import sys
import tempfile
from pathlib import Path

from . import __version__

# Frozen by PyInstaller: code+assets unpack to a temp dir (sys._MEIPASS) that
# vanishes on exit, so anything the user may edit or that must survive a run
# (config.json, naiwa-mouse.log) has to live next to the executable instead.
FROZEN = bool(getattr(sys, "frozen", False))
if FROZEN:
    APP_DIR = Path(sys.executable).resolve().parent
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
else:
    # repo root = one level above this package
    APP_DIR = Path(__file__).resolve().parents[1]
    RESOURCE_DIR = APP_DIR

from .config import Config                    # noqa: E402
from .engine import SkinEngine                # noqa: E402
from .hook import restore_cursor_now          # noqa: E402
from .win32 import set_dpi_aware              # noqa: E402

MUTEX_NAME = "Local\\NaiWaMouse_SingleInstance"
LOG_PATH = APP_DIR / "naiwa-mouse.log"


def _single_instance() -> bool:
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW(None, False, MUTEX_NAME)
    return kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def _writable_log_path() -> Path:
    """Prefer a log beside the exe, fall back to %TEMP% when that is read-only."""
    for folder in (APP_DIR, Path(tempfile.gettempdir()) / "NaiWaMouse"):
        try:
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / "naiwa-mouse.log"
            with path.open("a", encoding="utf-8"):
                return path
        except OSError:
            continue
    return LOG_PATH


def _setup_logging(debug: bool) -> None:
    handlers: list[logging.Handler] = [
        logging.handlers.RotatingFileHandler(
            _writable_log_path(), maxBytes=1_000_000, backupCount=2, encoding="utf-8"
        )
    ]
    # under --windowed there is no console, so sys.stdout is None
    if debug and sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        handlers=handlers,
    )
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("skin").info(
        "NaiWa Mouse %s  app dir=%s resources=%s", __version__, APP_DIR, RESOURCE_DIR
    )


def _default_config() -> Path:
    """config.json next to the exe wins, otherwise the bundled copy."""
    beside = APP_DIR / "config.json"
    if beside.exists():
        return beside
    return RESOURCE_DIR / "config.json"


def _fatal(message: str) -> None:
    logging.exception(message)
    ctypes.windll.user32.MessageBoxW(None, message, "NaiWa Mouse", 0x10)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="NaiWa Mouse", description="Desktop mouse skin")
    parser.add_argument("--version", action="version", version=f"NaiWa Mouse {__version__}")
    parser.add_argument("--config", default=str(_default_config()))
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--no-hide-cursor", action="store_true",
                        help="keep the system pointer visible (skin follows beside it)")
    parser.add_argument("--seconds", type=float, default=0.0,
                        help="stop automatically after N seconds (useful for a quick demo)")
    parser.add_argument("--demo", action="store_true",
                        help="cycle idle / left / right automatically")
    parser.add_argument("--headless", action="store_true",
                        help="run the skin without opening the settings window")
    parser.add_argument("--mode", choices=("minimal", "full"), default=None,
                        help="override the appearance mode for this run")
    parser.add_argument("--restore-cursor", action="store_true",
                        help="restore the system cursors and exit (rescue after a hard kill)")
    args = parser.parse_args(argv)

    _setup_logging(args.debug)
    set_dpi_aware()  # before any DPI query / asset scaling / window creation

    if args.restore_cursor:
        # usable without Python installed: NaiWaMouse.exe --restore-cursor
        restore_cursor_now()
        logging.getLogger("skin").info("system cursors restored on request")
        if args.debug:
            print("system cursors restored")
        return 0

    if not _single_instance():
        logging.getLogger("skin").warning("another instance is already running")
        # raise the window of the running copy instead of doing nothing
        from .ui import APP_WINDOW_CLASS, WM_SHOW_WINDOW
        from .win32 import user32

        hwnd = user32.FindWindowW(APP_WINDOW_CLASS, None)
        if hwnd:
            user32.PostMessageW(hwnd, WM_SHOW_WINDOW, 0, 0)
        if args.debug:
            print("already running -> asked the existing window to show")
        return 0

    atexit.register(restore_cursor_now)

    try:
        cfg = Config.load(Path(args.config), assets_dir=RESOURCE_DIR / "assets")
        if args.no_hide_cursor:
            cfg.data["cursor"]["hide_system_cursor"] = False
        if args.mode:
            cfg.data["mode"] = args.mode

        # --demo / --seconds are scripted runs: no window, no tray
        if args.headless or args.demo or args.seconds > 0:
            engine = SkinEngine(cfg)
            engine.demo = args.demo
            if args.seconds > 0:
                import time as _time

                engine.auto_stop_at = _time.perf_counter() + args.seconds
            engine.run()
        else:
            from .gui import run_app
            from .win32 import get_dpi

            return run_app(cfg, get_dpi())
    except Exception as exc:  # surface the error even under pythonw
        _fatal(f"Failed to start NaiWa Mouse:\n\n{exc}")
        return 1
    finally:
        restore_cursor_now()
    return 0
