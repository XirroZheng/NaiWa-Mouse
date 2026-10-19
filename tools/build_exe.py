"""Package the mouse skin as a standalone Windows executable.

    python tools/build_exe.py              # single NaiWaMouse.exe in dist/
    python tools/build_exe.py --onedir      # folder build, starts up faster

The exe carries Python, Pillow, numpy, the assets and a default config.json.
Only config.json is also copied next to the exe so it stays user-editable.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
DIST = ROOT / "dist"
NAME = "NaiWaMouse"
VERSION = "1.0.0"

# not needed at runtime: the preview APNG only feeds preview.html,
# assets.json is build metadata
SKIP_ASSETS = {"laugh_preview.png"}

VERSION_RC = f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(1, 0, 0, 0),
    prodvers=(1, 0, 0, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('080404B0', [
        StringStruct('CompanyName', ''),
        StringStruct('FileDescription', 'NaiWa Mouse - desktop mouse skin'),
        StringStruct('FileVersion', '{VERSION}'),
        StringStruct('InternalName', '{NAME}'),
        StringStruct('OriginalFilename', '{NAME}.exe'),
        StringStruct('ProductName', 'NaiWa Mouse'),
        StringStruct('ProductVersion', '{VERSION}')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
"""


def make_icon() -> Path:
    """Use the shipped app.ico, or rebuild it from the idle pose."""
    shipped = ROOT / "assets" / "app.ico"
    if shipped.exists():
        return shipped
    out = BUILD / "icon.ico"
    out.parent.mkdir(parents=True, exist_ok=True)
    src = Image.open(ROOT / "assets" / "glimpse.png").convert("RGBA")
    canvas_size = 256
    box = int(canvas_size * 0.86)
    src.thumbnail((box, box), Image.LANCZOS)
    canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    canvas.paste(src, ((canvas_size - src.width) // 2, (canvas_size - src.height) // 2), src)
    canvas.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return out


def stage_assets() -> Path:
    """Copy the runtime assets into a clean folder so the exe stays small."""
    stage = BUILD / "stage" / "assets"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    copied = 0
    for item in sorted((ROOT / "assets").iterdir()):
        if not item.is_file():          # assets/poses/ are optional extras
            continue
        if item.name in SKIP_ASSETS or item.name.startswith("_"):
            continue
        if item.suffix.lower() not in {".png", ".json", ".ico"}:
            continue
        shutil.copy2(item, stage / item.name)
        copied += 1
    size = sum(f.stat().st_size for f in stage.iterdir())
    print(f"  staged {copied} assets  ({size / 1048576:.1f} MB)")
    return stage


def build(onefile: bool) -> Path:
    icon = make_icon()
    stage = stage_assets()

    version_file = BUILD / "version_info.txt"
    version_file.write_text(VERSION_RC, encoding="utf-8")

    sep = os.pathsep  # ';' on Windows
    # separate work dirs: onefile and onedir reuse cached Analysis output that is
    # not interchangeable, and sharing it makes the second build fail on a lock
    work = BUILD / ("pyi-onefile" if onefile else "pyi-onedir")
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--windowed",
        "--name", NAME,
        "--icon", str(icon),
        "--version-file", str(version_file),
        "--add-data", f"{stage}{sep}assets",
        "--add-data", f"{ROOT / 'config.json'}{sep}.",
        "--distpath", str(DIST),
        "--workpath", str(work),
        "--specpath", str(BUILD),
        # trim interpreter modules the skin never touches
        "--hidden-import", "naiwa.gui",
        "--exclude-module", "tkinter",
        "--exclude-module", "unittest",
        "--exclude-module", "pydoc",
        "--exclude-module", "lib2to3",
        "--log-level", "WARN",
    ]
    args += ["--onefile" if onefile else "--onedir"]
    args.append(str(ROOT / "app.py"))

    print("  running PyInstaller ...")
    # antivirus sometimes holds the freshly written files from the previous run,
    # which makes PyInstaller fail while clearing dist/ - retry a few times
    for attempt in range(3):
        result = subprocess.run(args, cwd=str(ROOT))
        if result.returncode == 0:
            break
        if attempt < 2:
            print("  retrying after a file lock ...")
            time.sleep(4.0)
        else:
            raise SystemExit(f"PyInstaller failed with exit code {result.returncode}")

    target = DIST / f"{NAME}.exe" if onefile else DIST / NAME / f"{NAME}.exe"
    # ship an editable config beside the exe
    shutil.copy2(ROOT / "config.json", target.parent / "config.json")
    return target


def main() -> int:
    onefile = "--onedir" not in sys.argv
    print(f"building {NAME}.exe ({'onefile' if onefile else 'onedir'})")
    exe = build(onefile)
    if not exe.exists():
        print("! build finished but the exe is missing")
        return 1
    print(f"\nok  {exe}  ({exe.stat().st_size / 1048576:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
