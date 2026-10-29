"""Detection checks on simulated frames (no hardware): beam centre ignores the pin; pin validity / view state / hints.
Usage: python -I tests/test_detection.py"""
import sys
sys.dont_write_bytecode = True
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import balign  # noqa: E402,F401  (puts scripts/ on sys.path)
from balign.sim import SimInstrument  # noqa: E402
from balign import measure as M  # noqa: E402
import beam_center as bc  # noqa: E402

fails = []


def check(name, ok, info=""):
    print(("PASS " if ok else "FAIL ") + name, info)
    if not ok:
        fails.append(name)


def frame(**truth):
    inst = SimInstrument()
    inst.s.update(truth)
    return inst, inst.acquire()


# 1) beam centre must not follow the pin (old method did)
for a in (-132, 0, 100, -250):
    inst, img = frame(a=a, c=818.0)
    tx, ty = inst.true_beam_centre()
    m = M.measure_frame(img, 0.0)
    old = bc.half_max_footprint(img.astype(float))["cx"]
    check(f"beam centre, pin offset a={a}", abs(m["beam"]["cx"] - tx) < 2.0 and abs(m["beam"]["cy"] - ty) < 2.0,
          f"new {m['beam']['cx']:.1f} (err {m['beam']['cx'] - tx:+.1f}) old {old:.1f} (err {old - tx:+.1f}) truth {tx:.1f}")

# 2) good frames at all angles, incl. +-90 with the half-transparent flank: usable and accurate
_i, _img = frame(a=-132.0, b=-10.0, c=818.0)
_m0 = M.measure_frame(_img, 0.0)
prior = {"top_width": _m0["top_width"], "half_angle_deg": _m0["half_angle_deg"]}     # as learned from the omega=0 frame
check("without prior the wedge frame is rejected, not guessed", not M.measure_frame(frame(omega=-90.0, a=-132.0, b=-10.0, c=818.0)[1], -90)["usable"])
for w in (-90, -60, -30, 0, 30, 60, 90):
    inst, img = frame(omega=float(w), a=-132.0, b=-10.0, c=818.0)
    m = M.measure_frame(img, w, prior)
    truth = inst.true_pin_col()
    check(f"usable at omega={w}", m["usable"] and abs(m["pin_col"] - truth) < 1.5,
          f"{m['quality']} col {m['pin_col']} truth {truth:.1f} {m['reasons']}")

# 3) states
inst, img = frame(a=-900.0, c=818.0)
check("pin outside lit area -> absent", M.measure_frame(img, 0)["view"]["state"] == "absent")
inst, img = frame(a=300.0, top_row_shift=-400.0)
v = M.measure_frame(img, 0)["view"]
check("pin top above lit area -> partial + y hint", v["state"] == "partial" and v["hint"] and "y_mm" in v["hint"] and v["hint"]["y_mm"] < 0, str(v))
inst, img = frame(a=-132.0)
check("normal frame -> in_view", M.measure_frame(img, 0)["view"]["state"] == "in_view")
print("ALL OK" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
