"""Allow `python -m naiwa` as an alternative to `python app.py`."""
from .app import main

if __name__ == "__main__":
    raise SystemExit(main())
