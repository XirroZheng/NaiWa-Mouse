"""Load pose PNGs / sprite sheets into premultiplied BGRA surfaces."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from .window import Surface


@dataclass
class Layer:
    surface: Surface
    width: int
    height: int
    bbox: tuple[int, int, int, int]  # visible box inside the surface
    anchor: str
    press_offset: int
    frames: list[bytes] = field(default_factory=list)  # one premultiplied frame each
    frame_ms: int = 0

    @property
    def animated(self) -> bool:
        return len(self.frames) > 1

    def origin(self, cx: int, cy: int) -> tuple[int, int]:
        """Top-left screen position that puts this pose at the pointer."""
        left, top, right, bottom = self.bbox
        x = round(cx - (left + right) / 2)
        if self.anchor == "top":
            y = round(cy - top)
        elif self.anchor == "center":
            y = round(cy - (top + bottom) / 2)
        else:  # bottom
            y = round(cy - bottom)
        return x, y + self.press_offset

    def show_frame(self, index: int) -> None:
        """Push frame `index` into the (shared) surface."""
        if self.frames:
            self.surface.upload(self.frames[index % len(self.frames)])


def _premultiply_bgra(img: Image.Image) -> bytes:
    arr = np.asarray(img, dtype=np.uint16)
    a = arr[..., 3:4]
    rgb = (arr[..., :3] * a) // 255
    bgra = np.concatenate([rgb[..., 2:3], rgb[..., 1:2], rgb[..., 0:1], a], axis=2)
    return np.ascontiguousarray(bgra.astype(np.uint8)).tobytes()


def load_layer(path: Path, height: int, anchor: str, press_offset: int) -> Layer:
    img = Image.open(path).convert("RGBA")
    box = img.getbbox()
    if box is None:
        raise ValueError(f"{path.name} is fully transparent")

    # scale so the *visible* part of the pose is `height` px tall
    visible_h = max(1, box[3] - box[1])
    scale = height / visible_h
    size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
    img = img.resize(size, Image.LANCZOS)
    box = img.getbbox() or (0, 0, size[0], size[1])

    surface = Surface(_premultiply_bgra(img), img.width, img.height)
    return Layer(
        surface=surface,
        width=img.width,
        height=img.height,
        bbox=box,
        anchor=anchor,
        press_offset=int(press_offset),
    )


def load_flipbook(path: Path, height: int, anchor: str, press_offset: int) -> Layer:
    """Load a sprite sheet + its JSON sidecar as one animated layer.

    All frames share a single DIB: switching frames is a memcpy, and the
    window keeps pointing at the same surface, so animating costs almost
    nothing compared to re-uploading a bitmap per frame.
    """
    meta = json.loads(path.with_suffix(".json").read_text("utf-8"))
    sheet = Image.open(path).convert("RGBA")
    fw, fh = int(meta["frame_w"]), int(meta["frame_h"])
    cols, count = int(meta["cols"]), int(meta["frames"])

    scale = height / fh
    tw = max(1, round(fw * scale))
    frames: list[bytes] = []
    for i in range(count):
        c, r = i % cols, i // cols
        tile = sheet.crop((c * fw, r * fh, (c + 1) * fw, (r + 1) * fh))
        if (tw, height) != (fw, fh):
            tile = tile.resize((tw, height), Image.LANCZOS)
        frames.append(_premultiply_bgra(tile))

    surface = Surface(frames[0], tw, height)
    # every frame was cropped to the same rectangle when the sheet was built,
    # so the anchor sits still while the character animates inside it
    return Layer(
        surface=surface,
        width=tw,
        height=height,
        bbox=(0, 0, tw, height),
        anchor=anchor,
        press_offset=int(press_offset),
        frames=frames,
        frame_ms=int(meta.get("duration_ms", 100)),
    )
