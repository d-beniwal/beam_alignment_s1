"""A stand-in 'agent' that follows ALIGNMENT_PLAYBOOK.md using only the CLI (as Claude/Codex would). Simulated backend.
Usage: python -I tests/scripted_agent.py [--truth JSON] [--pace SECONDS]
Fast flow: measure -> (find-pin) -> fast-align (+-30, +-90, verify). Used to prove the tool set end-to-end and to exercise the GUI."""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
args = sys.argv[1:]
truth = args[args.index("--truth") + 1] if "--truth" in args else None
pace = float(args[args.index("--pace") + 1]) if "--pace" in args else 0.0


def call(*a):
    time.sleep(pace)
    r = subprocess.run([PY, "-I", str(ROOT / "align.py"), *map(str, a)], capture_output=True, text=True)
    if r.returncode:
        print(r.stderr); raise SystemExit("command failed: " + " ".join(map(str, a)))
    return json.loads(r.stdout)


LOG = None   # runs/<id>/logs/scripted_agent.log (transcript stays inside the run folder)


def note(t):
    print("AGENT:", t); call("note", t)
    if LOG:
        with open(LOG, "a") as f: f.write(t + "\n")


_r = call("new-run", *(["--truth", truth] if truth else []))
(Path(_r["dir"]) / "logs").mkdir(exist_ok=True)
LOG = Path(_r["dir"]) / "logs" / "scripted_agent.log"
note("Starting stage-1 alignment: put the pin on the rotation axis (a,b->0), then the axis on the beam centre. Signs/scales are confirmed constants, so no calibration.")
m = call("measure", "--omega", 0)
if m["view"]["state"] != "in_view":
    note(f"Pin not cleanly in view at omega=0 ({m['view']['state']}: {m['view']['why']}). Searching for it.")
    f = call("find-pin")
    if not f["found"]:
        note("Could not find the pin within the search limits: stopping for the human."); call("finish", "--status", "failed", "--summary", f["reason"]); raise SystemExit(1)
    note(f"Pin found after {f['steps']} steps at offset {f['offset_mm']}.")
else:
    note(f"Pin in view at omega=0 (col {m['pin_col']:.1f}, beam cx {m['beam']['cx']:.1f}).")
note("Adaptive routine: rotate until the pin leaves the view on each side, fit, correct (z, x, aerox), repeat.")
r = call("adaptive-align")
for p in r["passes"]:
    note(f"pass {p['pass']}: range +{p['limit_plus_deg']:g}/-{p['limit_minus_deg']:g} deg, a={p.get('a', 0):+.2f}, b={p.get('b', 0):+.2f}, c-beam={p.get('c_minus_beam_px', 0):+.2f} px, applied {p.get('applied')}")
if not r["ok"]:
    note("Adaptive align stopped: " + str(r.get("reason"))); call("finish", "--status", "failed", "--summary", str(r.get("reason"))); raise SystemExit(1)
v = r["passes"][-1]
r["converged"] = True
call("finish", "--status", "ok", "--summary", f"c-beam {v['c_minus_beam_px']:+.2f} px, a {v['a']:+.2f}, b {v['b']:+.2f}")
print("RESULT OK", {k_: round(v[k_], 3) for k_ in ("a", "b", "c_minus_beam_px")})
sys.exit(0)
