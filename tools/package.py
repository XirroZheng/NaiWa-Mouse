"""Bundle the built exe into ready-to-send zip archives.

    python tools/package.py

Produces, in dist/:
    NaiWaMouse-单文件版.zip   one exe + config + readme   (best for sharing)
    NaiWaMouse-文件夹版.zip   the onedir build + readme    (fastest startup)

Both unzip into a single `NaiWaMouse/` folder, so the recipient just extracts
and double-clicks - no Python, no installer, nothing written to the registry.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
EXTRA = ROOT / "packaging"
DOCS = ("使用说明.txt", "恢复光标.bat")
SKIP = {".log", ".tmp"}


def _zip(out: Path, entries: list[tuple[Path, str]]) -> Path:
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for src, arc in entries:
            if not src.is_file():
                raise FileNotFoundError(src)
            zf.write(src, arc)
    return out


def build_portable() -> Path:
    base = "NaiWaMouse"
    entries = [
        (DIST / "NaiWaMouse.exe", f"{base}/NaiWaMouse.exe"),
        (DIST / "config.json", f"{base}/config.json"),
    ]
    entries += [(EXTRA / name, f"{base}/{name}") for name in DOCS]
    return _zip(DIST / "NaiWaMouse-单文件版.zip", entries)


def build_folder() -> Path:
    src = DIST / "NaiWaMouse"
    if not (src / "NaiWaMouse.exe").exists():
        raise FileNotFoundError(f"onedir build missing: {src}")
    entries = [
        (p, f"NaiWaMouse/{p.relative_to(src).as_posix()}")
        for p in sorted(src.rglob("*"))
        if p.is_file() and p.suffix.lower() not in SKIP
    ]
    entries += [(EXTRA / name, f"NaiWaMouse/{name}") for name in DOCS]
    return _zip(DIST / "NaiWaMouse-文件夹版.zip", entries)


def main() -> int:
    for build in (build_portable, build_folder):
        out = build()
        with zipfile.ZipFile(out) as zf:
            count = len(zf.namelist())
        print(f"  {out.name:<28} {out.stat().st_size / 1048576:6.1f} MB   {count} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
