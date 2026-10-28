"""balign: agent-driven stage-1 beam alignment (rotation axis onto the beam). Simulated backend only until the user enables hardware."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_scripts = str(ROOT / "scripts")
if _scripts not in sys.path:     # reuse pinfit / beam_center / axis_align / align_config without moving them
    sys.path.insert(0, _scripts)
RUNS_DIR = ROOT / "runs"
