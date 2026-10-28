"""A run = one alignment session: runs/<id>/{events.jsonl, state.json, frames/}. Every CLI call appends events; the GUI tails them."""
import json
import time
from datetime import datetime
from pathlib import Path
from . import RUNS_DIR
from .sim import SimInstrument


def get_backend(name, state=None, seed=0, camera=None):
    if name == "sim":
        return SimInstrument(state, seed)
    if name == "epics":   # gated inside: needs BALIGN_ENABLE_HARDWARE=1 + explicit camera; never used in development sessions
        from .epics_backend import EpicsInstrument
        return EpicsInstrument(state, camera=camera or (state or {}).get("camera"))
    raise NotImplementedError(
        f"unknown backend '{name}'. Use --backend sim (the 'epics' backend is gated, see balign/epics_backend.py).")


class Run:
    def __init__(self, path: Path):
        self.dir = Path(path)
        self.events_path = self.dir / "events.jsonl"
        self.state_path = self.dir / "state.json"
        self.state = json.loads(self.state_path.read_text())
        self.inst = get_backend(self.state["backend"], self.state["inst"])

    # -- lifecycle ---------------------------------------------------------------------------------------------------
    @classmethod
    def create(cls, backend="sim", seed=0, truth=None, camera=None):
        RUNS_DIR.mkdir(exist_ok=True)
        rid = datetime.now().strftime("%Y%m%d-%H%M%S")
        d = RUNS_DIR / rid
        (d / "frames").mkdir(parents=True)
        inst = get_backend(backend, None, seed, camera)
        if truth:
            inst.s.update(truth)
        (d / "state.json").write_text(json.dumps({"backend": backend, "inst": inst.get_state(), "calibration": {},
                                                  "last_fit": None, "n_frames": 0, "status": "running"}))
        (RUNS_DIR / "CURRENT").write_text(rid)
        run = cls(d)
        run.log("run_started", f"Run {rid} started (backend: {backend})", {"backend": backend})
        return run

    @classmethod
    def current(cls, run_id=None):
        rid = run_id or (RUNS_DIR / "CURRENT").read_text().strip()
        return cls(RUNS_DIR / rid)

    def save(self):
        self.state["inst"] = self.inst.get_state()
        self.state_path.write_text(json.dumps(self.state))

    # -- events ------------------------------------------------------------------------------------------------------
    def n_events(self):
        return sum(1 for _ in open(self.events_path)) if self.events_path.exists() else 0

    def log(self, kind, msg, data=None, image=None):
        ev = {"i": self.n_events(), "t": datetime.now().isoformat(timespec="milliseconds"), "kind": kind, "msg": msg,
              "data": data or {}, "image": image}
        with open(self.events_path, "a") as f:
            f.write(json.dumps(ev) + "\n")
        return ev

    def next_frame_path(self, tag):
        self.state["n_frames"] += 1
        name = f"{self.state['n_frames']:03d}_{tag}.jpg"
        return self.dir / "frames" / name, f"frames/{name}"
