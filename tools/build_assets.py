"""Build transparent assets from the source JPGs / GIFs.

Source images live in the parent folder (../*.jpg, ../*.gif). They are studio
renders on a flat background (white for the poses, yellow for the pointer). We
key that background out, keeping only the region connected to the image border
so that bright areas inside the character (pale belly, eye highlights) survive.
The cut-out edge is feathered and un-premultiplied against the background
colour so no white/yellow halo is left behind.

Animated sources are unrolled into a sprite sheet (`<name>_sheet.png`) plus a
small JSON sidecar with the grid geometry, so the runtime can upload one frame
at a time into a single DIB.

Usage:
    python tools/build_assets.py            # rebuild every asset
    python tools/build_assets.py default    # rebuild one

Output: assets/<name>.png (RGBA), assets/<name>_sheet.(png|json).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT.parent
OUT = ROOT / "assets"

# name -> job spec
#   src    : source image
#   bg/tol : flat studio colour used to find the background
#   mode   : "cutout" = key the background out, keep the character only
#            "disc"   = keep the artwork but mask it to a circle, so the flat
#                       background survives as a coloured rim
#   rim    : for "disc", outer radius as a multiple of the inner motif radius
JOBS = {
    "default":    {"src": "default.jpg",    "bg": (247, 222, 60), "tol": 30,
                   "mode": "disc", "rim": 1.42},
    "glimpse":    {"src": "glimpse.jpg",    "bg": (255, 255, 255), "tol": 16, "mode": "cutout"},
    "left_hand":  {"src": "left_hand.jpg",  "bg": (255, 255, 255), "tol": 16, "mode": "cutout"},
    "right_hand": {"src": "right_hand.jpg", "bg": (255, 255, 255), "tol": 16, "mode": "cutout"},
    "thinking":   {"src": "thinking.jpg",   "bg": (255, 255, 255), "tol": 16, "mode": "cutout"},
    # extra poses the config can bind to any action (kept in assets/poses/)
    "amazing":    {"src": "amazing.jpg",    "bg": (255, 255, 255), "tol": 16, "mode": "cutout", "dir": "poses"},
    "big_love":   {"src": "big_love.jpg",   "bg": (255, 255, 255), "tol": 16, "mode": "cutout", "dir": "poses"},
    "handup":     {"src": "handup.jpg",     "bg": (255, 255, 255), "tol": 16, "mode": "cutout", "dir": "poses"},
    "hug":        {"src": "hug.jpg",        "bg": (255, 255, 255), "tol": 16, "mode": "cutout", "dir": "poses"},
    "right_hand": {"src": "right_hand.jpg", "bg": (255, 255, 255), "tol": 16, "mode": "cutout", "dir": "poses"},
    "sayyes":     {"src": "sayyes.jpg",     "bg": (255, 255, 255), "tol": 16, "mode": "cutout", "dir": "poses"},
}

# name -> animated job spec
#   master_h  : frame height kept in the sheet (the runtime scales down from it)
#   cols      : grid columns
#   blur      : edge feather radius, relative to the (small) frame size
#   preview_h : frame height of the APNG used by preview.html
FLIPBOOKS = {
    "laugh": {"src": "laugh.gif", "bg": (255, 255, 255), "tol": 18,
              "master_h": 160, "cols": 16, "blur": 1.0, "preview_h": 48},
}


def _runs(row: np.ndarray) -> list[tuple[int, int]]:
    """Return [start, end] inclusive runs of True in a 1-D bool array."""
    if not row.any():
        return []
    d = np.diff(np.concatenate(([0], row.astype(np.int8), [0])))
    starts = np.flatnonzero(d == 1)
    ends = np.flatnonzero(d == -1)
    return list(zip(starts.tolist(), (ends - 1).tolist()))


def _component_runs(mask: np.ndarray):
    """Group mask pixels into 4-connected components (run-length union-find).

    Returns (runs, find) where runs is [(y, x0, x1, id)] and find(id) is the
    component root. Operating on horizontal runs keeps this fast on 2k images.
    """
    h, w = mask.shape
    parent: list[int] = []
    runs: list[tuple[int, int, int, int]] = []  # y, x0, x1, id

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    prev: list[tuple[int, int, int]] = []
    for y in range(h):
        cur = []
        for s, e in _runs(mask[y]):
            idx = len(runs)
            runs.append((y, s, e, idx))
            parent.append(idx)
            cur.append((s, e, idx))
        for s, e, idx in cur:
            for ps, pe, pidx in prev:
                if ps > e:
                    break
                if pe >= s:
                    union(idx, pidx)
        prev = cur
    return runs, find


def border_connected(cand: np.ndarray) -> np.ndarray:
    """Mask of `cand` pixels 4-connected to the image border."""
    h, w = cand.shape
    runs, find = _component_runs(cand)
    roots = {find(idx) for y, s, e, idx in runs
             if y == 0 or y == h - 1 or s == 0 or e == w - 1}
    mask = np.zeros((h, w), dtype=bool)
    for y, s, e, idx in runs:
        if find(idx) in roots:
            mask[y, s:e + 1] = True
    return mask


def keep_largest(mask: np.ndarray) -> np.ndarray:
    """Drop every component except the biggest one (watermarks, speckle)."""
    runs, find = _component_runs(mask)
    area: dict[int, int] = {}
    for y, s, e, idx in runs:
        area[find(idx)] = area.get(find(idx), 0) + (e - s + 1)
    if not area:
        return mask
    best = max(area, key=area.get)
    out = np.zeros_like(mask)
    for y, s, e, idx in runs:
        if find(idx) == best:
            out[y, s:e + 1] = True
    return out


def _close(mask: np.ndarray, size: int) -> np.ndarray:
    """Morphological close, to swallow 1-2px JPEG speckle in the background."""
    img = Image.fromarray((mask * 255).astype(np.uint8), "L")
    img = img.filter(ImageFilter.MaxFilter(size)).filter(ImageFilter.MinFilter(size))
    return np.asarray(img) > 127


def _disc(arr: np.ndarray, fg_mask: np.ndarray, rim: float) -> Image.Image:
    """Mask the artwork to a circle that keeps some of the flat background.

    The pointer artwork is a black dot inside a green ring on a yellow field.
    Cutting the yellow away leaves a thin ring with no weight, so instead we
    keep the yellow and clip everything to a disc whose radius is `rim` times
    the green ring's radius -- giving concentric yellow / green / black bands.
    """
    h, w = fg_mask.shape
    ys, xs = np.nonzero(fg_mask)
    cx = (xs.min() + xs.max()) / 2.0
    cy = (ys.min() + ys.max()) / 2.0
    r_inner = max(xs.max() - xs.min(), ys.max() - ys.min()) / 2.0
    r_outer = r_inner * rim

    yy, xx = np.mgrid[0:h, 0:w]
    dist = np.hypot(xx - cx, yy - cy)
    # thin soft edge -- just enough to stay anti-aliased at pointer size
    band = max(4.0, r_outer * 0.035)
    alpha = np.clip((r_outer + band / 2.0 - dist) / band, 0.0, 1.0) * 255.0

    out = np.dstack([arr.astype(np.float32), alpha]).astype(np.uint8)
    img = Image.fromarray(out, "RGBA")

    half = r_outer + band / 2.0
    return img.crop((
        max(0, int(cx - half)), max(0, int(cy - half)),
        min(w, int(cx + half)), min(h, int(cy + half)),
    ))


def _foreground_mask(rgb: Image.Image, bg: tuple[int, int, int], tol: int,
                     speck: bool = True) -> np.ndarray:
    arr = np.asarray(rgb).astype(np.int16)
    dist = np.abs(arr - np.array(bg, dtype=np.int16)).max(axis=2)
    cand = _close(dist <= tol, 5)
    bg_mask = _close(border_connected(cand), 3)
    fg = ~bg_mask
    return keep_largest(fg) if speck else fg


def _key_rgba(rgb: Image.Image, bg: tuple[int, int, int], tol: int,
              blur: float = 3.0, speck: bool = True) -> tuple[Image.Image, np.ndarray]:
    """Key the flat background out and return (RGBA image, foreground mask)."""
    arr = np.asarray(rgb).astype(np.int16)
    bg_arr = np.array(bg, dtype=np.int16)
    fg_mask = _foreground_mask(rgb, bg, tol, speck)

    # grow the background ~1px to eat the anti-aliased fringe, then soften.
    # The blur radius is generous on purpose: these assets are downscaled a lot
    # at render time, and a 1px hard alpha edge turns into visible stairsteps.
    bg_img = Image.fromarray(((~fg_mask) * 255).astype(np.uint8), "L")
    bg_img = bg_img.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(blur))
    alpha = np.clip(255.0 - np.asarray(bg_img).astype(np.float32), 0.0, 255.0)

    # un-premultiply against the background colour -> kills the halo
    af = np.clip(alpha / 255.0, 0.0, 1.0)[..., None]
    fg = (arr.astype(np.float32) - (1.0 - af) * bg_arr.astype(np.float32)) / np.maximum(af, 0.06)
    fg = np.clip(fg, 0, 255)
    return Image.fromarray(np.dstack([fg, alpha]).astype(np.uint8), "RGBA"), fg_mask


def extract(path: Path, spec: dict) -> Image.Image:
    rgb = Image.open(path).convert("RGB")
    if spec.get("mode") == "disc":
        fg_mask = _foreground_mask(rgb, spec["bg"], spec["tol"])
        return _disc(np.asarray(rgb).astype(np.int16), fg_mask, float(spec.get("rim", 1.4)))

    img, _ = _key_rgba(rgb, spec["bg"], spec["tol"], float(spec.get("blur", 3.0)))
    bbox = img.getbbox()
    if bbox:
        pad = max(2, int(min(img.size) * 0.01))
        img = img.crop((
            max(0, bbox[0] - pad),
            max(0, bbox[1] - pad),
            min(img.width, bbox[2] + pad),
            min(img.height, bbox[3] + pad),
        ))
    return img


def build_flipbook(name: str, spec: dict) -> dict | None:
    """Unroll an animated GIF into a sprite sheet + JSON sidecar (+ APNG preview).

    Two passes: the first one only measures the union of the visible boxes so
    every frame is cropped to the same rectangle (otherwise the sprite would
    jitter as its own bounding box changed), the second one writes the sheet.
    """
    src = SRC / spec["src"]
    gif = Image.open(src)
    count = getattr(gif, "n_frames", 1)
    bg, tol = spec["bg"], spec["tol"]
    blur = float(spec.get("blur", 1.0))

    boxes: list[tuple[int, int, int, int]] = []
    for i in range(count):
        gif.seek(i)
        frame, _ = _key_rgba(gif.convert("RGB"), bg, tol, blur, speck=False)
        box = frame.getbbox()
        if box:
            boxes.append(box)
    if not boxes:
        print(f"! {name}: every frame came out empty")
        return None

    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes)
    y1 = max(b[3] for b in boxes)
    crop_w, crop_h = x1 - x0, y1 - y0

    master_h = int(spec.get("master_h", 160))
    frame_w = max(1, round(crop_w * master_h / crop_h))
    cols = int(spec.get("cols", 16))
    rows = math.ceil(count / cols)

    sheet = Image.new("RGBA", (frame_w * cols, master_h * rows), (0, 0, 0, 0))
    previews: list[Image.Image] = []
    preview_h = int(spec.get("preview_h", 0))
    duration = int(gif.info.get("duration") or 100)

    for i in range(count):
        gif.seek(i)
        frame, _ = _key_rgba(gif.convert("RGB"), bg, tol, blur, speck=False)
        tile = frame.crop((x0, y0, x1, y1)).resize((frame_w, master_h), Image.LANCZOS)
        sheet.paste(tile, ((i % cols) * frame_w, (i // cols) * master_h))
        if preview_h:
            previews.append(tile.resize((max(1, round(frame_w * preview_h / master_h)), preview_h),
                                        Image.LANCZOS))

    sheet_path = OUT / f"{name}_sheet.png"
    sheet.save(sheet_path)
    meta = {
        "file": f"assets/{name}_sheet.png",
        "frames": count,
        "frame_w": frame_w,
        "frame_h": master_h,
        "cols": cols,
        "rows": rows,
        "duration_ms": duration,
    }
    (OUT / f"{name}_sheet.json").write_text(json.dumps(meta, indent=2), "utf-8")

    if previews:
        previews[0].save(
            OUT / f"{name}_preview.png", save_all=True, append_images=previews[1:],
            duration=duration, loop=0, disposal=1,
        )
    print(f"  {name:<12} {count} frames -> {sheet.width}x{sheet.height}  "
          f"({frame_w}x{master_h}/frame, {duration}ms)")
    return meta


def main(argv: list[str]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    only = [a for a in argv if not a.startswith("-")]
    for unknown in [n for n in only if n not in JOBS and n not in FLIPBOOKS]:
        print(f"! unknown target {unknown}")
    meta = {}
    # build metadata lives in build/ (git-ignored); the runtime never reads it
    meta_path = ROOT / "build" / "assets.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    if meta_path.exists():
        meta = json.loads(meta_path.read_text("utf-8"))

    for name in (only or list(JOBS)):
        if name not in JOBS:
            continue
        spec = JOBS[name]
        src_path = SRC / spec["src"]
        if not src_path.exists():
            print(f"! missing source {src_path}")
            continue
        img = extract(src_path, spec)
        out_dir = OUT / spec.get("dir", "")
        out_dir.mkdir(parents=True, exist_ok=True)
        img.save(out_dir / f"{name}.png")
        rel = f"assets/{spec['dir']}/{name}.png" if spec.get("dir") else f"assets/{name}.png"
        meta[name] = {"file": rel, "w": img.width, "h": img.height}
        print(f"  {name:<12} {img.width}x{img.height}  <- {spec['src']}")

    for name in (only or list(FLIPBOOKS)):
        if name not in FLIPBOOKS:
            continue
        src_path = SRC / FLIPBOOKS[name]["src"]
        if not src_path.exists():
            print(f"! missing source {src_path}")
            continue
        info = build_flipbook(name, FLIPBOOKS[name])
        if info:
            meta[f"{name}_sheet"] = info

    meta_path.write_text(json.dumps(meta, indent=2), "utf-8")
    print(f"\ndone -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
