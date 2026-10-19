"""NaiWa Mouse launcher.

    python app.py               # settings window + skin
    python app.py --headless    # skin only
    python app.py --debug       # verbose console output

The implementation lives in the `naiwa` package; this file only exists so the
program can be started with a plain `python app.py` (and so PyInstaller has a
stable entry point).
"""
from __future__ import annotations

from naiwa.app import main

if __name__ == "__main__":
    raise SystemExit(main())
