"""A stand-in 'agent' that follows ALIGNMENT_PLAYBOOK.md using only the CLI (as Claude/Codex would). Simulated backend.
Usage: python -I tests/scripted_agent.py [--truth JSON] [--pace SECONDS]
Used to prove the tool set is sufficient end-to-end and to exercise the GUI."""
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


def note(t): print("AGENT:", t); call("note", t)


call("new-run", *(["--truth", truth] if truth else []))
note("Starting stage-1 alignment: put the pin on the rotation axis (a,b->0), then the axis on the beam centre.")
m = call("measure", "--omega", 0)
assert m["pin_col"] is not None, "pin not found"
note(f"Pin visible at omega=0 (col {m['pin_col']:.1f}, beam cx {m['beam']['cx']:.1f}). Sweeping -90..90.")
sw = call("sweep")
note(f"First fit: a={sw['fit']['a']:+.1f}, b={sw['fit']['b']:+.1f}, c={sw['fit']['c']:.1f} px, rms {sw['fit']['rms']:.2f}. Signs are unverified, so calibrate x, z and aerox with small test moves.")
for motor in ("x", "z", "aerox"):
    cal = call("calibrate", "--motor", motor, "--mm", 0.02)
    c = cal["calibration"]
    note(f"{motor}: d(a,b,c)/mm = ({c['d_a_per_mm']:+.0f},{c['d_b_per_mm']:+.0f},{c['d_c_per_mm']:+.0f}) px/mm; pixel-size check {c['matches_pixel_size']}")
for it in range(3):
    sw = call("sweep")
    f, t = sw["fit"], sw["within_tol"]
    note(f"Iteration {it}: a={f['a']:+.2f} b={f['b']:+.2f} c-beam={t['c_minus_beam_px']:+.1f} px")
    if t["a"] and t["b"]:
        break
    p = call("propose")["proposed_moves_mm"]
    for motor in ("z", "x"):
        if abs(p[motor]) > 5e-4:
            call("move", motor, round(p[motor], 5), "--reason", f"cancel {'b' if motor == 'z' else 'a'} (pin onto rotation axis)")
sw = call("sweep")
if not (sw["within_tol"]["a"] and sw["within_tol"]["b"]):
    note("Pin is not on the axis after 3 iterations: stopping for the human."); call("finish", "--status", "failed"); raise SystemExit(1)
note("Pin is on the axis. Now moving the axis (base) onto the beam centre.")
p = call("propose")["proposed_moves_mm"]
d = p["aerox"]
call("move", "aerox", round(d, 5), "--reason", "axis column -> beam centre")
sw = call("sweep")
t = sw["within_tol"]
note(f"Final: a={sw['fit']['a']:+.2f} b={sw['fit']['b']:+.2f} c-beam={t['c_minus_beam_px']:+.2f} px")
ok = t["a"] and t["b"] and t["c_on_beam"]
call("finish", "--status", "ok" if ok else "failed", "--summary", f"c-beam {t['c_minus_beam_px']:+.2f} px, a {sw['fit']['a']:+.2f}, b {sw['fit']['b']:+.2f}")
print("RESULT", "OK" if ok else "FAILED", t)
