"""Read-only: save one raw gh1 frame (PVA stream) as .npy. Usage: python -I scripts/grab_frame.py OUT.npy"""
import sys
sys.dont_write_bytecode = True
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent)); sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import balign  # noqa: F401  (sets up paths)
from balign.epics_backend import EpicsInstrument

inst = EpicsInstrument(camera="gh1")
img = inst.grab_latest()
np.save(sys.argv[1], img)
print(img.shape, img.dtype, int(img.min()), int(np.percentile(img, 50)), int(img.max()))
