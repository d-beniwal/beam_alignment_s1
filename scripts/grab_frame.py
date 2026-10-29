"""Read-only: save one raw frame (PVA stream) as .npy inside the current run folder: runs/<id>/raw/<name>.npy.
Usage: python -I scripts/grab_frame.py CAMERA [NAME] [--run ID]   (NAME defaults to a timestamp)"""
import sys
sys.dont_write_bytecode = True
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent)); sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import balign  # noqa: F401  (sets up paths)
from balign.epics_backend import EpicsInstrument

from datetime import datetime
from balign.session import Run
args = [x for x in sys.argv[1:]]
rid = args.pop(args.index("--run") + 1) if "--run" in args else None
if rid: args.remove("--run")
camera, name = args[0], (args[1] if len(args) > 1 else datetime.now().strftime("%H%M%S"))
run = Run.current(rid)
inst = EpicsInstrument(camera=camera)
img = inst.grab_latest()
np.save(run.subdir("raw") / (Path(name).stem + ".npy"), img)
print(img.shape, img.dtype, int(img.min()), int(np.percentile(img, 50)), int(img.max()))
