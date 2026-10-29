"""A run = one alignment session. EVERYTHING produced for it lives in runs/<id>/ (nothing else is written under runs/ except the CURRENT pointer):
  events.jsonl, state.json, live.jpg   - core record (CLI appends events; the GUI tails them)
  frames/   JPEGs shown in the GUI       outputs/  JSON printed by every CLI command (auto-saved, NNN_<cmd>.json)
  raw/      raw .npy frames              figures/  beam/analysis figures (+ json)
  logs/     process logs (live-feed, scripted agent, ...)      report/  make_report.py output
Use Run.subdir(name) / Run.save_output(...) rather than building paths by hand."""
import json
import time
from datetime import datetime
from pathlib import Path
from . import RUNS_DIR
from .sim import SimInstrument
import align_config as cfg


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
        cam = self.state["inst"].get("camera")
        cfg.set_camera(cam if cam in cfg.CAMERA_INFO else None)   # pixel size follows the run's camera

    # -- lifecycle ---------------------------------------------------------------------------------------------------
    @classmethod
    def create(cls, backend="sim", seed=0, truth=None, camera=None):
        # Build the backend first: a refused/failed backend must not leave a run directory behind.
        inst = get_backend(backend, None, seed, camera)
        if camera and camera not in cfg.CAMERA_INFO:
            raise ValueError(f"unknown camera '{camera}'; choose from {sorted(cfg.CAMERA_INFO)}")
        if camera:
            inst.s["camera"] = camera
        if truth:
            inst.s.update(truth)
        RUNS_DIR.mkdir(exist_ok=True)       # the only place this code creates directories: inside runs/
        base = datetime.now().strftime("%Y%m%d-%H%M%S")
        rid, n = base, 0
        while True:                         # atomic claim; two runs in the same second get -1, -2, ...
            d = RUNS_DIR / rid
            try:
                d.mkdir()
                break
            except FileExistsError:
                n += 1
                rid = f"{base}-{n}"
        (d / "frames").mkdir()
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

    def subdir(self, name):
        """runs/<id>/<name>/, created on demand. `name` must be a plain folder name (keeps everything inside the run)."""
        if name != Path(name).name or name in ("", ".", ".."):
            raise ValueError(f"bad run subfolder '{name}'")
        d = self.dir / name
        d.mkdir(exist_ok=True)
        return d

    def save_output(self, cmd, obj):
        """Auto-save a CLI command's JSON result as outputs/NNN_<cmd>.json (numbered in call order)."""
        d = self.subdir("outputs")
        n = sum(1 for _ in d.glob("*.json")) + 1
        path = d / f"{n:03d}_{cmd}.json"
        path.write_text(json.dumps(obj, indent=2, default=float))
        return path

    def next_frame_path(self, tag):
        self.state["n_frames"] += 1
        name = f"{self.state['n_frames']:03d}_{tag}.jpg"
        return self.dir / "frames" / name, f"frames/{name}"
