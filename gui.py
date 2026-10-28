#!/usr/bin/env python
"""Start the alignment GUI: python -I gui.py [--port 8765]. Read-only viewer of runs/*/events.jsonl."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import balign  # noqa: E402,F401
from balign.gui import serve  # noqa: E402

if __name__ == "__main__":
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8765
    serve(port)
