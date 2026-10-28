#!/usr/bin/env python
"""Entry point for the agent: python align.py <command> ...   (see balign/cli.py). Simulated backend only."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from balign.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
