import sys
from pathlib import Path

_SCRIPT_DIR = str(Path(__file__).resolve().parent)

if __name__ == "__main__":
    if _SCRIPT_DIR in sys.path:
        sys.path.remove(_SCRIPT_DIR)
    from visa_gate.cli import main

    raise SystemExit(main())
