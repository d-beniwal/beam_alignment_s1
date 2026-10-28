"""Command-line tools for the agent. Every command prints one JSON object (stdout) and appends events the GUI shows live.
The agent decides what to run next; nothing here decides or loops on its own, except the explicit `sweep`/`calibrate` helpers.
Backend is simulated only (see session.get_backend)."""
import argparse
import json
import sys
import numpy as np
from . import RUNS_DIR  # noqa: F401  (also puts scripts/ on sys.path)
import align_config as cfg
import axis_align
from .session import Run
from . import measure as M


def _clean(m):
    return {k: v for k, v in m.items() if not k.startswith("_")}


def _out(obj):
    print(json.dumps(obj, indent=2, default=float))


# ---- primitives -----------------------------------------------------------------------------------------------------
def goto_omega(run, deg):
    before = run.inst.get_omega()
    run.inst.move_omega(deg)
    run.save()
    run.log("omega", f"omega {before:+.2f} -> {deg:+.2f} deg", {"from": before, "to": deg})


def do_measure(run, omega=None, tag="meas"):
    if omega is not None:
        goto_omega(run, omega)
    img = run.inst.acquire()
    m = M.measure_frame(img, run.inst.get_omega())
    path, rel = run.next_frame_path(tag)
    M.overlay_jpeg(img, m, path)
    d = _clean(m)
    msg = (f"omega {d['omega']:+.1f}: pin col {d['pin_col']:.2f}" if d["pin_col"] is not None
           else f"omega {d['omega']:+.1f}: pin NOT measured ({d['status']}: {d['message']})")
    run.log("measure", msg + f", beam cx {d['beam']['cx']:.1f}", d, rel)
    run.save()
    return d


def do_sweep(run, angles, tag="sweep"):
    ms = [do_measure(run, a, tag) for a in angles]
    ok = [m for m in ms if m["pin_col"] is not None]
    fit = M.fit_axis([m["omega"] for m in ok], [m["pin_col"] for m in ok])
    beam_cx = float(np.median([m["beam"]["cx"] for m in ms]))
    res = {"tag": tag, "angles": list(angles), "n_valid": len(ok), "beam_cx": beam_cx, "fit": fit,
           "omegas": [m["omega"] for m in ok], "cols": [m["pin_col"] for m in ok]}
    if fit["ok"]:
        res["within_tol"] = {"a": abs(fit["a"]) < cfg.TOL_AB_PX, "b": abs(fit["b"]) < cfg.TOL_AB_PX,
                             "c_on_beam": abs(fit["c"] - beam_cx) < cfg.TOL_C_PX, "c_minus_beam_px": fit["c"] - beam_cx}
        run.state["last_fit"] = {"c": fit["c"], "a": fit["a"], "b": fit["b"], "rms": fit["rms"], "beam_cx": beam_cx,
                                 "stale": False}
        msg = (f"sweep fit: axis c={fit['c']:.2f}, a={fit['a']:+.2f}, b={fit['b']:+.2f} px, rms {fit['rms']:.2f}; "
               f"beam cx {beam_cx:.1f} (c-beam {fit['c'] - beam_cx:+.1f})")
    else:
        msg = f"sweep fit failed: {fit['reason']}"
    run.log("sweep_fit", msg, res)
    run.save()
    return res


def cal_get(run, motor):
    return run.state["calibration"].get(motor)


def do_propose(run):
    lf = run.state.get("last_fit")
    if not lf:
        return {"ok": False, "reason": "no sweep fit yet; run `sweep` first"}
    a, b, c, bcx = lf["a"], lf["b"], lf["c"], lf["beam_cx"]
    notes, mv = [], {}
    cx, cz, cb = cal_get(run, "x"), cal_get(run, "z"), cal_get(run, "aerox")
    # pin x: cancel a (image column at omega=0 changes by -a)
    if cx:
        mv["x"] = -a / cx["d_a_per_mm"]
    else:
        mv["x"] = cfg.px_to_mm(-a / cfg.IMAGE_COL_PER_X)
        notes.append("x sign ASSUMED (IMAGE_COL_PER_X), not calibrated")
    # pin z: cancel b
    if cz:
        mv["z"] = -b / cz["d_b_per_mm"]
    else:
        mv["z"] = -cfg.ROT_SIGN * cfg.px_to_mm(b)
        notes.append("z sign ASSUMED (ROT_SIGN), not calibrated")
    # base: bring the axis onto the beam centre. NOTE the pin moves above do not change c; the base move shifts c (and the pin with it).
    if cb:
        mv[cfg.BASE_MOTOR] = (bcx - c) / cb["d_c_per_mm"]
    elif cfg.BASE_COL_PER_AEROX is not None:
        mv[cfg.BASE_MOTOR] = (bcx - c) / (cfg.BASE_COL_PER_AEROX * 1e3 / cfg.PIXEL_UM)
    else:
        mv[cfg.BASE_MOTOR] = None
        notes.append(f"base motor '{cfg.BASE_MOTOR}' sign/size unknown: run `calibrate --motor {cfg.BASE_MOTOR}` first")
    res = {"ok": True, "from_fit": {"a": a, "b": b, "c": c, "beam_cx": bcx, "stale": lf.get("stale", False)},
           "proposed_moves_mm": mv, "notes": notes}
    if lf.get("stale"):
        res["notes"].append("fit is STALE (a motor moved since the sweep): re-sweep before trusting this")
    run.log("proposal", "proposed moves (not executed): " + ", ".join(f"{k} {v:+.4f} mm" if v is not None else f"{k} ?" for k, v in mv.items()), res)
    return res


def do_move(run, motor, mm, reason=""):
    lim = cfg.MAX_STEP_BASE_MM if motor == cfg.BASE_MOTOR else cfg.MAX_STEP_PIN_MM
    if motor not in ("x", "y", "z", cfg.BASE_MOTOR):
        return {"ok": False, "reason": f"unknown motor {motor}"}
    if abs(mm) > lim:
        run.log("warning", f"REFUSED move {motor} {mm:+.4f} mm: exceeds the {lim} mm per-step limit", {"motor": motor, "mm": mm})
        return {"ok": False, "reason": f"|{mm}| mm exceeds per-step limit {lim} mm; split the move"}
    before = dict(run.inst.positions())
    run.inst.move(motor, mm)
    after = dict(run.inst.positions())
    if run.state.get("last_fit"):
        run.state["last_fit"]["stale"] = True
    run.save()
    run.log("move", f"MOVE {motor} {mm:+.4f} mm ({reason or 'no reason given'}); {motor}: {before[motor]:+.4f} -> {after[motor]:+.4f}",
            {"motor": motor, "mm": mm, "reason": reason, "before": before, "after": after})
    return {"ok": True, "motor": motor, "mm": mm, "before": before, "after": after}


def do_calibrate(run, motor, mm, undo=True):
    """Small test move: re-fit before/after to learn how (a, b, c) respond per mm; stores the calibration."""
    run.log("note", f"calibrating {motor} with a {mm:+.4f} mm test move", {"agent": False})
    f0 = do_sweep(run, cfg.DEFAULT_SWEEP_DEG, "cal_before")["fit"]
    r = do_move(run, motor, mm, "calibration test move")
    if not r["ok"]:
        return r
    f1 = do_sweep(run, cfg.DEFAULT_SWEEP_DEG, "cal_after")["fit"]
    if not (f0["ok"] and f1["ok"]):
        return {"ok": False, "reason": "sweeps failed"}
    d = {k: (f1[k] - f0[k]) / mm for k in ("a", "b", "c")}
    cal = {"d_a_per_mm": d["a"], "d_b_per_mm": d["b"], "d_c_per_mm": d["c"], "test_mm": mm}
    expected = 1e3 / cfg.PIXEL_UM
    main = {"x": "d_a_per_mm", "z": "d_b_per_mm", cfg.BASE_MOTOR: "d_c_per_mm"}.get(motor)
    cal["px_per_mm"] = abs(cal[main]) if main else None
    cal["matches_pixel_size"] = (abs(abs(cal[main]) - expected) / expected < 0.15) if main else None
    run.state["calibration"][motor] = cal
    run.save()
    run.log("calibration", f"calibrated {motor}: d(a,b,c)/mm = ({d['a']:+.1f}, {d['b']:+.1f}, {d['c']:+.1f}) px/mm "
            f"(expected |.| = {expected:.0f} for the main term)", cal)
    if undo:
        do_move(run, motor, -mm, "undo calibration test move")
    return {"ok": True, "calibration": cal, "undone": undo}


def do_live_feed(run, interval, seconds):
    """Write runs/<id>/live.jpg every `interval` s (read-only frame grab + beam centre / last axis lines). Run it in its own terminal/process."""
    import time
    from PIL import Image, ImageDraw
    t_end = time.time() + seconds if seconds else None
    n = 0
    while t_end is None or time.time() < t_end:
        r = Run.current(run.dir.name)                       # re-read state: omega, last fit
        inst = r.inst
        img = inst.grab_latest() if hasattr(inst, "grab_latest") else inst.acquire()
        lo, hi = np.percentile(img, [1, 99.5])
        g = np.clip((img.astype(np.float32) - lo) / max(hi - lo, 1) * 255, 0, 255).astype(np.uint8)
        im = Image.fromarray(g).convert("RGB").resize((img.shape[1] // 3, img.shape[0] // 3))
        d = ImageDraw.Draw(im)
        lf = r.state.get("last_fit")
        if lf:
            for x, col in ((lf["beam_cx"], (80, 200, 120)), (lf["c"], (110, 164, 255))):
                d.line([x / 3, 0, x / 3, im.size[1]], fill=col, width=1)
        d.text((6, 4), f"LIVE  omega {inst.get_omega():+.1f}  (green: beam centre, blue: fitted axis c)", fill=(255, 255, 255))
        tmp = r.dir / "live.tmp.jpg"
        im.save(tmp, quality=75)
        tmp.replace(r.dir / "live.jpg")
        n += 1
        time.sleep(interval)
    return {"ok": True, "frames": n}


# ---- argparse -------------------------------------------------------------------------------------------------------
def main(argv=None):
    p = argparse.ArgumentParser(prog="align.py", description=__doc__)
    p.add_argument("--run", help="run id (default: current)")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("new-run"); s.add_argument("--backend", default="sim"); s.add_argument("--camera"); s.add_argument("--seed", type=int, default=0)
    s.add_argument("--truth", help="JSON dict overriding hidden sim truth, e.g. '{\"a\":-50,\"true_k_z\":-1}'")
    sub.add_parser("status")
    s = sub.add_parser("goto-omega"); s.add_argument("deg", type=float)
    s = sub.add_parser("measure"); s.add_argument("--omega", type=float)
    s = sub.add_parser("sweep"); s.add_argument("--angles", type=float, nargs="+", default=list(cfg.DEFAULT_SWEEP_DEG))
    s = sub.add_parser("estimate-pm"); s.add_argument("theta", type=float)
    sub.add_parser("propose")
    s = sub.add_parser("move"); s.add_argument("motor"); s.add_argument("mm", type=float); s.add_argument("--reason", default="")
    s = sub.add_parser("calibrate"); s.add_argument("--motor", required=True); s.add_argument("--mm", type=float, required=True)
    s.add_argument("--no-undo", action="store_true")
    s = sub.add_parser("live-feed"); s.add_argument("--interval", type=float, default=1.0); s.add_argument("--seconds", type=float, default=0)
    s = sub.add_parser("note"); s.add_argument("text")
    s = sub.add_parser("finish"); s.add_argument("--status", default="ok"); s.add_argument("--summary", default="")
    a = p.parse_args(argv)

    if a.cmd == "new-run":
        run = Run.create(a.backend, a.seed, json.loads(a.truth) if a.truth else None, a.camera)
        return _out({"run": run.dir.name, "dir": str(run.dir), "pixel_um": cfg.PIXEL_UM})
    run = Run.current(a.run)
    if a.cmd == "status":
        return _out({"run": run.dir.name, "positions": run.inst.positions(), "last_fit": run.state["last_fit"],
                     "calibration": run.state["calibration"], "status": run.state["status"], "events": run.n_events(),
                     "pixel_um": cfg.PIXEL_UM})
    if a.cmd == "goto-omega":
        goto_omega(run, a.deg); return _out({"omega": a.deg})
    if a.cmd == "measure":
        return _out(do_measure(run, a.omega))
    if a.cmd == "sweep":
        return _out(do_sweep(run, a.angles))
    if a.cmd == "estimate-pm":
        t = a.theta
        x0 = do_measure(run, 0, "pm0")["pin_col"]; xm = do_measure(run, -t, "pm_neg")["pin_col"]; xp = do_measure(run, t, "pm_pos")["pin_col"]
        if None in (x0, xm, xp):
            return _out({"ok": False, "reason": "pin not measured in one of the frames"})
        aa, bb = axis_align.estimate_ab(x0, xp, xm, t)
        res = {"ok": True, "theta": t, "x0": x0, "x_plus": xp, "x_minus": xm, "a": None if np.isnan(aa) else aa, "b": bb,
               "note": f"a only reliable for theta >= {axis_align.A_MIN_DEG}"}
        run.log("estimate", f"+-{t} deg: b={bb:+.2f} px" + ("" if np.isnan(aa) else f", a={aa:+.2f} px"), res)
        return _out(res)
    if a.cmd == "propose":
        return _out(do_propose(run))
    if a.cmd == "move":
        return _out(do_move(run, a.motor, a.mm, a.reason))
    if a.cmd == "calibrate":
        return _out(do_calibrate(run, a.motor, a.mm, not a.no_undo))
    if a.cmd == "live-feed":
        return _out(do_live_feed(run, a.interval, a.seconds))
    if a.cmd == "note":
        run.log("note", a.text, {"agent": True}); return _out({"ok": True})
    if a.cmd == "finish":
        run.state["status"] = a.status; run.save()
        run.log("run_finished", f"Run finished: {a.status}. {a.summary}", {"status": a.status, "summary": a.summary})
        return _out({"ok": True})


if __name__ == "__main__":
    main()
