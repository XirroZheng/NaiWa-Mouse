"""Configuration loading with sane defaults."""
from __future__ import annotations

import copy
import json
from pathlib import Path

DEFAULTS: dict = {
    "mode": "full",
    "modes": {
        # every state collapses to this one pose
        "minimal": {"asset": "default.png", "height": 22, "anchor": "center", "press_offset": 0},
        # full mode enlarges every pose except idle
        "full": {"others_scale": 1.2},
    },
    "states": {
        "idle":  {"asset": "glimpse.png",   "height": 22, "anchor": "center", "press_offset": 0},
        "left":  {"asset": "left_hand.png", "height": 22, "anchor": "bottom", "press_offset": 1},
        "right": {"asset": "thinking.png",  "height": 22, "anchor": "bottom", "press_offset": 0},
        "wait":  {"sheet": "laugh_sheet.png", "scale": 1.1, "anchor": "center", "press_offset": 0},
    },
    "timing": {
        "fps": 60,
        "idle_after_left_ms": 90,
        "idle_after_right_ms": 320,
    },
    "cursor": {
        "hide_system_cursor": True,
        "hotspot_dot": False,
    },
    "hotkeys": {
        "quit": "Ctrl+Alt+Q",
        "toggle_cursor": "Ctrl+Alt+H",
        "toggle_skin": "Ctrl+Alt+S",
    },
    "auto_dpi_scale": True,
}


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


class Config:
    def __init__(self, data: dict, base_dir: Path, assets_dir: Path | None = None,
                 path: Path | None = None):
        self.data = data
        self.base_dir = base_dir
        self.path = path
        # assets may be unpacked elsewhere than config.json (PyInstaller onefile)
        self.assets_dir = assets_dir or (base_dir / "assets")

    @classmethod
    def load(cls, path: Path, assets_dir: Path | None = None) -> "Config":
        data = {}
        if path.exists():
            try:
                data = json.loads(path.read_text("utf-8"))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"config.json is not valid JSON: {exc}")
        return cls(_merge(DEFAULTS, data), path.parent, assets_dir, path)

    @property
    def mode(self) -> str:
        mode = str(self.data.get("mode", "full")).strip().lower()
        return mode if mode in ("minimal", "full") else "full"

    def save_mode(self, mode: str) -> bool:
        """Remember the mode across launches; silently no-op if read-only."""
        self.data["mode"] = mode
        if not self.path:
            return False
        try:
            self.path.write_text(
                json.dumps(self.data, indent=2, ensure_ascii=False) + "\n", "utf-8"
            )
            return True
        except OSError:
            return False

    def state(self, name: str) -> dict:
        return self.data["states"].get(name) or self.data["states"]["idle"]

    def asset_path(self, name: str) -> Path:
        return self.assets_dir / name

    def __getitem__(self, key: str):
        return self.data[key]
