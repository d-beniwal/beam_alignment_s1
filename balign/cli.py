"""Command-line tools for the agent. Every command prints one JSON object (stdout) and appends events the GUI shows live.
The agent decides what to run next; nothing here decides or loops on its own, except the explicit `sweep`/`calibrate` helpers.
Backends: sim (default) or epics (real beamline, when the user says so; see session.get_backend)."""
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


_CTX = {"run": None, "cmd": None}   # set by main(): every result is also saved inside the run folder (outputs/)


def _out(obj):
    print(json.dumps(obj, indent=2, default=float))
    if _CTX["run"] is not None:
        _CTX["run"].save_output(_CTX["cmd"], obj)


# ---- primitives -----------------------------------------------------------------------------------------------------
def goto_omega(run, deg):
    if abs(deg) > cfg.MAX_ROT_DEG + 1e-9:
        raise ValueError(f"omega {deg:+.1f} deg refused: beam alignment never rotates beyond +-{cfg.MAX_ROT_DEG:g} deg")
    before = run.inst.get_omega()
    run.inst.move_omega(deg)
    run.save()
    run.log("omega", f"omega {before:+.2f} -> {deg:+.2f} deg", {"from": before, "to": deg})


def _update_prior(run, m):
    """Learn the pin's top width / half-angle (from frames where both flanks were trusted; used to rescue one-sided frames) and the lit
    footprint (from clean frames; used when the pin hides part of it)."""
    b = m["beam"]
    if m["view"]["state"] == "in_view" and b.get("method") == "pin-excluded":
        hb = run.state.setdefault("beam_hist", [])
        hb.append({k: b[k] for k in ("cx", "cy", "width", "height", "box")})
        del hb[:-20]
        if len(hb) >= 2:
            run.state["beam_prior"] = {k: ([int(np.median([e["box"][i] for e in hb])) for i in range(4)] if k == "box" else float(np.median([e[k] for e in hb])))
                                       for k in ("cx", "cy", "width", "height", "box")}
    if m.get("quality") != "both_flanks":
        return
    h = run.state.setdefault("pin_prior_hist", {"w": [], "ang": []})
    h["w"] = (h["w"] + [m["top_width"]])[-30:]
    h["ang"] = (h["ang"] + [m["half_angle_deg"]])[-30:]
    if len(h["w"]) >= 2:
        run.state["pin_prior"] = {"top_width": float(np.median(h["w"])), "half_angle_deg": float(np.median(h["ang"]))}


def do_measure(run, omega=None, tag="meas"):
    if omega is not None:
        goto_omega(run, omega)
    img = run.inst.acquire()
    m = M.measure_frame(img, run.inst.get_omega(), run.state.get("pin_prior"), run.state.get("beam_prior"))
    path, rel = run.next_frame_path(tag)
    M.overlay_jpeg(img, m, path)
    if cfg.SAVE_RAW:   # raw frame next to the overlay so any detection can be re-run / debugged offline
        np.savez_compressed(run.subdir("raw") / (path.stem + ".npz"), img=img, omega=run.inst.get_omega())
    _update_prior(run, m)
    d = _clean(m)
    if d["pin_col"] is not None:
        msg = f"omega {d['omega']:+.1f}: pin col {d['pin_col']:.2f}" + ("" if d["quality"] == "both_flanks" else f" ({d['quality']})")
    else:
        msg = f"omega {d['omega']:+.1f}: pin NOT usable [{d['view']['state']}] ({d['status']}; {'; '.join(d['reasons']) or d['message']})"
    run.log("measure", msg + f", beam cx {d['beam']['cx']:.1f}", d, rel)
    run.save()
    return d


def _beam_cx(ms):
    good = [m for m in ms if m["beam"]["width"] > 150]
    good = [m for m in good if m["beam"].get("method") == "pin-excluded"] or good   # prefer pin-excluded estimates
    v = [m["beam"]["cx"] for m in good]
    return float(np.median(v)) if v else float("nan")


def do_sweep(run, angles, tag="sweep"):
    ms = [do_measure(run, a, tag) for a in angles]
    ok = [m for m in ms if m["pin_col"] is not None]
    fit = M.fit_axis([m["omega"] for m in ok], [m["pin_col"] for m in ok])
    beam_cx = _beam_cx(ms)
    res = {"tag": tag, "angles": list(angles), "n_valid": len(ok), "beam_cx": beam_cx, "fit": fit,
           "omegas": [m["omega"] for m in ok], "cols": [m["pin_col"] for m in ok],
           "rejected": {f"{m['omega']:+.0f}": m["reasons"] for m in ms if m["pin_col"] is None}}
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


def _moves_from_abc(run, a, b, c, bcx):
    """Moves (mm) that cancel a, b and bring c onto the beam centre. Uses run calibrations if present, else the confirmed constants.
    Entries are None when the needed quantity is unknown (nan)."""
    notes, mv = [], {}
    cx, cz, cb = cal_get(run, "x"), cal_get(run, "z"), cal_get(run, "aerox")
    # pin x: cancel a (image column at omega=0 changes by -a)
    if not np.isfinite(a):
        mv["x"] = None
    elif cx:
        mv["x"] = -a / cx["d_a_per_mm"]
    else:
        mv["x"] = cfg.px_to_mm(-a / cfg.IMAGE_COL_PER_X)
        notes.append("x sign from IMAGE_COL_PER_X (user-confirmed), not calibrated in this run")
    # pin z: cancel b
    if not np.isfinite(b):
        mv["z"] = None
    elif cz:
        mv["z"] = -b / cz["d_b_per_mm"]
    else:
        mv["z"] = -cfg.ROT_SIGN * cfg.px_to_mm(b)
        notes.append("z sign from ROT_SIGN (user-confirmed), not calibrated in this run")
    # base: bring the axis onto the beam centre. NOTE the pin moves above do not change c; the base move shifts c (and the pin with it).
    if not (np.isfinite(c) and np.isfinite(bcx)):
        mv[cfg.BASE_MOTOR] = None
    elif cb:
        mv[cfg.BASE_MOTOR] = (bcx - c) / cb["d_c_per_mm"]
    elif cfg.BASE_COL_PER_AEROX is not None:
        mv[cfg.BASE_MOTOR] = (bcx - c) / (cfg.BASE_COL_PER_AEROX * 1e3 / cfg.PIXEL_UM)
    else:
        mv[cfg.BASE_MOTOR] = None
        notes.append(f"base motor '{cfg.BASE_MOTOR}' sign/size unknown: run `calibrate --motor {cfg.BASE_MOTOR}` first")
    return mv, notes


def do_propose(run):
    lf = run.state.get("last_fit")
    if not lf:
        return {"ok": False, "reason": "no sweep fit yet; run `sweep` first"}
    a, b, c, bcx = lf["a"], lf["b"], lf["c"], lf["beam_cx"]
    mv, notes = _moves_from_abc(run, a, b, c, bcx)
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


def move_split(run, motor, mm, reason=""):
    """do_move, but a move above the per-step limit is split into equal chunks (every chunk still goes through the limit check)."""
    lim = cfg.MAX_STEP_BASE_MM if motor == cfg.BASE_MOTOR else cfg.MAX_STEP_PIN_MM
    n = max(1, int(np.ceil(abs(mm) / lim)))
    for _ in range(n):
        r = do_move(run, motor, mm / n, reason + (f" (1/{n})" if n > 1 else ""))
        if not r["ok"]:
            return r
    return {"ok": True, "motor": motor, "mm": mm}


MIN_MOVE_MM = 0.0005


def do_step_pm(run, theta, apply=False, base=False, force=False):
    """One fast correction step: measure -theta, 0, +theta (monotonic rotation, nearest end first) -> a, b, c -> optionally move.
    b = (x+ - x-)/(2 sin t) -> z.  a = (x0 - mean)/(1 - cos t) (t >= 30) -> x.  c = x0 - a (= mean at 90) -> aerox if `base`."""
    cur = run.inst.get_omega()
    near, far = (-theta, theta) if abs(cur + theta) <= abs(cur - theta) else (theta, -theta)
    # no pin-shape prior yet: measure omega=0 first (full view there), so that a flank lost to the grey bevel wedge at large |omega|
    # can be rescued from the other flank
    order = [0, near, far] if not run.state.get("pin_prior") else [near, 0, far]
    ms = {w: do_measure(run, w, f"pm{theta:g}") for w in order}
    bad = {f"{w:+.0f}": ms[w]["reasons"] or [ms[w]["view"]["state"]] for w in order if ms[w]["pin_col"] is None}
    if bad:
        states = {ms[w]["view"]["state"] for w in order if ms[w]["pin_col"] is None}
        return {"ok": False, "reason": f"pin not usable at {sorted(bad)}", "details": bad, "states": sorted(states),
                "suggest": ("pin absent / another object in view: run `find-pin`" if states & {"absent", "no_beam", "other_object"} else
                            f"try a smaller theta (e.g. {max(10, theta // 2):g}); the pin runs into the lit-area edge at +-{theta:g}")}
    x0, xp, xm = ms[0]["pin_col"], ms[theta]["pin_col"], ms[-theta]["pin_col"]
    a, b = axis_align.estimate_ab(x0, xp, xm, theta)
    c = x0 - a if np.isfinite(a) else float("nan")
    bcx = _beam_cx(list(ms.values()))
    mv, notes = _moves_from_abc(run, a, b, c, bcx)
    res = {"ok": True, "theta": theta, "x0": x0, "x_plus": xp, "x_minus": xm, "a": None if np.isnan(a) else a, "b": b,
           "c": None if np.isnan(c) else c, "beam_cx": bcx, "c_minus_beam_px": None if np.isnan(c) else c - bcx,
           "proposed_moves_mm": mv, "applied": {}, "notes": notes}
    prev = run.state.get("pm_prev")
    if apply and prev and prev.get("z_applied") and abs(b) > max(5.0, 0.5 * abs(prev["b"])) and not force:
        res.update(sign_suspect=True, ok=False, reason=f"|b| did not shrink after the last z move ({prev['b']:+.1f} -> {b:+.1f} px): "
                   "wrong sign or a backlash/timing problem. Nothing moved; re-check, or pass --force")
        run.log("warning", res["reason"], res)
        return res
    if apply:
        for motor in ("z", "x") + ((cfg.BASE_MOTOR,) if base else ()):
            d = mv.get(motor)
            if d is None or abs(d) < MIN_MOVE_MM:
                continue
            r = move_split(run, motor, d, f"step +-{theta:g}: cancel " + {"z": "b", "x": "a", cfg.BASE_MOTOR: "c-beam"}[motor])
            if not r["ok"]:
                res.update(ok=False, reason=r["reason"]); break
            res["applied"][motor] = d
    run.state["pm_prev"] = {"b": b, "z_applied": "z" in res["applied"]}
    ok_ab = abs(b) < cfg.TOL_AB_PX and (np.isnan(a) or abs(a) < cfg.TOL_AB_PX)
    res["converged"] = bool(ok_ab and np.isfinite(c) and abs(c - bcx) < cfg.TOL_C_PX)
    run.state["last_fit"] = {"c": None if np.isnan(c) else c, "a": None if np.isnan(a) else a, "b": b, "rms": 0.0, "beam_cx": bcx,
                             "stale": bool(res["applied"])} if np.isfinite(c) else run.state.get("last_fit")
    run.log("pm_step", f"step +-{theta:g}: a={res['a'] if res['a'] is None else round(res['a'], 2)}, b={b:+.2f}, "
            f"c-beam={res['c_minus_beam_px'] if res['c_minus_beam_px'] is None else round(res['c_minus_beam_px'], 2)} px; "
            f"applied {', '.join(f'{k} {v:+.4f} mm' for k, v in res['applied'].items()) or 'nothing'}", res)
    run.save()
    return res


def do_fast_align(run, verify=True, steps=None):
    """The quick routine: +-30 (z, x) -> +-90 (z, x, aerox) -> verify. ~3 short rotations instead of calibration + many sweeps."""
    out = {"ok": True, "steps": []}
    for th in (steps or cfg.FAST_STEPS_DEG):
        r = do_step_pm(run, th, apply=True, base=th >= 60)
        out["steps"].append({k: r.get(k) for k in ("theta", "a", "b", "c_minus_beam_px", "applied", "ok", "reason", "suggest", "states")})
        if not r["ok"]:
            out.update(ok=False, reason=f"step +-{th:g} failed: {r.get('reason')}", suggest=r.get("suggest"))
            return out
    if verify:
        r = do_step_pm(run, (steps or cfg.FAST_STEPS_DEG)[-1], apply=False)
        out["verify"] = {k: r.get(k) for k in ("theta", "a", "b", "c_minus_beam_px", "converged", "ok", "reason")}
        out["converged"] = bool(r.get("converged"))
    return out


def _pin_value(m):
    """(column, weight, kind) of the pin axis in a measurement, or None. Fully usable frames count 1; a partly visible pin whose axis was
    located from the visible part (cone model) counts 0.3 - it extends the angle range but is less accurate (~5 px)."""
    if m["pin_col"] is not None:
        return m["pin_col"], 1.0, "usable"
    loc = m["view"].get("locate")
    if m["view"]["state"] == "partial" and loc and loc["rows_cut_frac"] < 0.85:
        return float(loc["axis_col"]), 0.3, "located"
    return None


def _probe_side(run, sgn, step, jump_first):
    """Probe one side; if the pin cannot be measured even at the first step, retry with half the step, then a quarter (15 -> 7.5 -> 3.75 deg).
    Returns (points, limit_deg, usable_limit_deg, step_used)."""
    for k, s in enumerate((step, step / 2, step / 4)):
        pts, lim, limu = _probe_steps(run, sgn, s, jump_first and k == 0)
        if lim > 0:
            return pts, lim, limu, s
    return [], 0.0, 0.0, step / 4


def _probe_steps(run, sgn, step, jump_first):
    """Rotate away from 0 on one side until the pin can no longer be measured (the user's 'where does it go out of the field of view').
    With jump_first (the previous pass reached the limit on both sides) try the +-MAX_ROT_DEG end point straight away.
    Returns (points[(omega, col, weight, kind)], limit_deg = last angle with any measurement, usable_limit_deg)."""
    pts, lim, limu = [], 0.0, 0.0
    top = cfg.MAX_ROT_DEG
    if jump_first:
        m = do_measure(run, sgn * top, "adapt")
        v = _pin_value(m)
        if v and v[2] == "usable":
            return [(m["omega"], v[0], v[1], v[2])], top, top
    th = step
    while th <= top + 1e-9:
        m = do_measure(run, sgn * th, "adapt")
        v = _pin_value(m)
        if v is None:
            break
        pts.append((m["omega"], v[0], v[1], v[2]))
        lim = th
        if v[2] == "usable":
            limu = th
        th += step
    return pts, lim, limu


def _apply_moves(run, mv, why):
    out = {}
    for motor in ("z", "x", cfg.BASE_MOTOR):
        d = mv.get(motor)
        if d is None or abs(d) < MIN_MOVE_MM:
            continue
        r = move_split(run, motor, d, why)
        if not r["ok"]:
            return out, r
        out[motor] = d
    return out, {"ok": True}


def do_adaptive_align(run, step=15.0, max_passes=6):
    """Adaptive alignment (user procedure, 2026-10-30). omega -> 0; pin axis to the beam centre (x); then per pass: rotate + until the pin
    can no longer be measured (note how far its axis moved), rotate - likewise, fit x(w) = c + a cos w + b sin w to every measurement,
    correct (z <- b, x <- a, aerox <- c-beam), repeat. If a pass reaches +-90 on both sides, later passes just use 0, +90, -90.
    Never beyond +-MAX_ROT_DEG. Done when |a|,|b| < TOL_AB_PX and |c - beam| < TOL_C_PX."""
    out = {"ok": False, "passes": []}
    if abs(run.inst.get_omega()) > 1e-6:
        goto_omega(run, 0)
    m = do_measure(run, 0, "adapt0")
    for _ in range(8):                                      # get the pin properly into view first
        v = m["view"]
        if v["state"] == "in_view":
            break
        if v["state"] in ("absent", "other_object", "no_beam"):
            r = do_find_pin(run)
            if not r.get("found"):
                out["reason"] = f"pin not found: {r.get('reason')}"; return out
        elif v.get("hint"):
            h = v["hint"]
            for motor, key in (("x", "x_mm"), ("y", "y_mm")):
                if abs(h.get(key, 0.0)) >= MIN_MOVE_MM:
                    r = move_split(run, motor, h[key], "adaptive: bring the partly visible pin into view")
                    if not r["ok"]:
                        out["reason"] = r["reason"]; return out
        else:
            out["reason"] = f"pin at omega=0 is {v['state']} without a usable hint ({v['why']})"; return out
        m = do_measure(run, 0, "adapt0")
    if m["view"]["state"] != "in_view":
        out["reason"] = "could not bring the pin fully into view at omega=0"; return out
    bcx = (run.state.get("beam_prior") or {}).get("cx", m["beam"]["cx"])
    dx = bcx - m["pin_col"]                                 # centre the pin axis at omega=0 (moves a only)
    if abs(cfg.px_to_mm(dx)) >= MIN_MOVE_MM:
        r = move_split(run, "x", cfg.px_to_mm(dx / cfg.IMAGE_COL_PER_X), "adaptive: centre the pin axis in the field of view at omega=0")
        if not r["ok"]:
            out["reason"] = r["reason"]; return out
    m = do_measure(run, 0, "adapt0")                        # confirms the centring (and teaches the pin width prior)
    if m["pin_col"] is None:
        out["reason"] = f"pin lost after centring ({m['view']['state']})"; return out
    jump, prev, x0 = False, None, m["pin_col"]
    for k in range(max_passes):
        pts = [(0.0, x0, 1.0, "usable")]
        pos, lim_p, limu_p, st_p = _probe_side(run, +1, step, jump)
        neg, lim_n, limu_n, st_n = _probe_side(run, -1, step, jump)
        pts += pos + neg
        fit = M.fit_axis([p[0] for p in pts], [p[1] for p in pts], [p[2] for p in pts])
        small = False
        if not fit["ok"] and len(pts) >= 2:      # pin only measurable over a few degrees: b from the farthest point (a-term ~ a*theta^2/2 is negligible), z only
            om_, col_ = max(pts[1:], key=lambda p: abs(p[0]))[:2]
            fit = {"ok": True, "a": 0.0, "b": (col_ - x0) / np.sin(np.radians(om_)), "c": float("nan"), "rms": float("nan")}
            small = True
        bcx = (run.state.get("beam_prior") or {}).get("cx", bcx)
        rec = {"pass": k + 1, "limit_plus_deg": lim_p, "limit_minus_deg": lim_n, "usable_limit_plus_deg": limu_p,
               "usable_limit_minus_deg": limu_n, "step_plus_deg": st_p, "step_minus_deg": st_n, "n_points": len(pts),
               "n_located": sum(p[3] == "located" for p in pts), "small_angle_b_only": small}
        if not fit["ok"]:
            rec["reason"] = fit["reason"]; out["passes"].append(rec)
            out["reason"] = f"pass {k + 1}: only {len(pts)} measurable angle(s): the pin leaves the view within {step:g} deg; run `find-pin`/centre it first"
            return out
        a, b, c = fit["a"], fit["b"], fit["c"]
        max_ang = max(abs(p[0]) for p in pts)
        nn = lambda v: None if v != v else v        # NaN -> None (valid JSON)
        rec.update(a=nn(a), b=b, c=nn(c), rms=nn(fit["rms"]), beam_cx=bcx, c_minus_beam_px=nn(c - bcx), max_angle_deg=max_ang)
        ok_ab = abs(a) < cfg.TOL_AB_PX and abs(b) < cfg.TOL_AB_PX
        rec["converged"] = bool(not small and ok_ab and max_ang >= 30 and abs(c - bcx) < cfg.TOL_C_PX)
        if not small:
            run.state["last_fit"] = {"c": c, "a": a, "b": b, "rms": fit["rms"], "beam_cx": bcx, "stale": False}
        # after a correction the residual should be about (1 - fraction applied) of the old value; flag only if it is clearly larger than that
        if prev and prev["applied_z"] and abs(b) > max(5.0, 0.5 * abs(prev["b"])) or \
                prev and prev["applied_x"] and abs(a) > max(5.0, abs(prev["a"]) * (1 - prev["frac_a"]) + 0.5 * abs(prev["a"]) * prev["frac_a"]):
            rec["reason"] = "a or b did not shrink after the last correction (sign / backlash problem)"
            out["passes"].append(rec); out.update(reason=rec["reason"], sign_suspect=True)
            run.log("warning", rec["reason"], rec); run.save(); return out
        if rec["converged"]:
            out["passes"].append(rec); out["ok"] = True
            run.log("adaptive_pass", f"pass {k + 1}: converged (a={a:+.2f}, b={b:+.2f}, c-beam={c - bcx:+.2f} px, range +{lim_p:g}/-{lim_n:g} deg)", rec)
            break
        frac_a = 1.0 if max_ang >= 30 else max(0.25, max_ang / 30)          # small angles determine a poorly: apply only part of it
        mv, _ = _moves_from_abc(run, a * frac_a, b, c, bcx)
        if max_ang < 30 or small:
            mv[cfg.BASE_MOTOR] = None                                      # c needs a: wait for a larger range
        if small:
            mv["x"] = None
        applied, r = _apply_moves(run, mv, f"adaptive pass {k + 1}")
        rec.update(applied=applied, a_fraction=frac_a)
        out["passes"].append(rec)
        run.log("adaptive_pass", f"pass {k + 1}: range +{lim_p:g}/-{lim_n:g} deg ({len(pts)} pts){' [small-angle: b only]' if small else ''}, a={a:+.2f}, b={b:+.2f}, c-beam={c - bcx:+.1f} px; "
                f"applied {', '.join(f'{m_} {v:+.4f} mm' for m_, v in applied.items()) or 'nothing'}", rec)
        if not r["ok"]:
            out["reason"] = r["reason"]; run.save(); return out
        prev = {"a": a, "b": b, "applied_z": "z" in applied, "applied_x": "x" in applied, "frac_a": frac_a}
        jump = lim_p >= cfg.MAX_ROT_DEG and lim_n >= cfg.MAX_ROT_DEG
        goto_omega(run, 0)
        x0 = None
        m = do_measure(run, 0, "adapt0")
        if m["pin_col"] is None:
            out["reason"] = f"pin lost at omega=0 after the correction ({m['view']['state']})"; run.save(); return out
        x0 = m["pin_col"]
    else:
        out["reason"] = f"not converged after {max_passes} passes"
    out["final"] = out["passes"][-1] if out["passes"] else None
    run.save()
    return out


def _spiral(nx, ny):
    """Integer offsets (i, j), |i|<=nx, |j|<=ny (start cell excluded): row j=0 first, then j=+-1, ..."""
    pts = [(i, j) for i in range(-nx, nx + 1) for j in range(-ny, ny + 1) if (i, j) != (0, 0)]
    return sorted(pts, key=lambda p: (abs(p[1]), abs(p[0]), p))   # whole x line first (the pin is a long vertical object), then y rows


def do_find_pin(run, max_steps=60, use_y=True):
    """Bring the pin into the lit footprint. Follows hints when the pin is partly visible; if it is absent, searches x (and y)
    outward from the start in footprint-sized steps within SEARCH_RADIUS_*; returns to the start position if nothing is found."""
    start = dict(run.inst.positions())
    pos = {"x": 0.0, "y": 0.0}                       # offsets from the start (mm), tracked here
    log = []

    def goto(tx, ty, why):
        for motor, tgt in (("x", tx), ("y", ty)):
            d = tgt - pos[motor]
            if abs(d) >= MIN_MOVE_MM:
                r = move_split(run, motor, d, why)
                if not r["ok"]:
                    return r
                pos[motor] = tgt
        return {"ok": True}

    m = do_measure(run, None, "find")
    steps, cells, k = 0, None, 0
    while True:
        v = m["view"]
        log.append({"state": v["state"], "x": pos["x"], "y": pos["y"]})
        if v["state"] == "in_view":
            run.log("find_pin", f"pin in view at offset x {pos['x']:+.3f}, y {pos['y']:+.3f} mm", {"offset_mm": dict(pos)})
            return {"ok": True, "found": True, "offset_mm": dict(pos), "steps": steps, "positions": run.inst.positions()}
        if v["state"] == "no_beam":
            goto(0.0, 0.0, "find-pin: return to start"); return {"ok": False, "found": False, "reason": v["why"], "steps": steps}
        if steps >= max_steps:
            break
        steps += 1
        h = v.get("hint")
        if v["state"] == "partial" and h:
            tx = float(np.clip(pos["x"] + h.get("x_mm", 0.0), -cfg.SEARCH_RADIUS_X_MM, cfg.SEARCH_RADIUS_X_MM))
            ty = float(np.clip(pos["y"] + (h.get("y_mm", 0.0) if use_y else 0.0), -cfg.SEARCH_RADIUS_Y_MM, cfg.SEARCH_RADIUS_Y_MM))
            run.log("note", f"find-pin: pin partly visible ({v['why']}); moving x {tx - pos['x']:+.3f}, y {ty - pos['y']:+.3f} mm to bring it in", {"agent": False})
            if abs(tx - pos["x"]) < MIN_MOVE_MM and abs(ty - pos["y"]) < MIN_MOVE_MM:
                break                                   # hint cannot be followed any further
        else:                                           # absent or no usable hint: search outward
            if cells is None:
                b = m["beam"]
                sx = min(cfg.SEARCH_STEP_FRAC * b["width"] * cfg.PIXEL_UM * 1e-3, cfg.MAX_STEP_PIN_MM)
                sy = min(cfg.SEARCH_STEP_FRAC * b["height"] * cfg.PIXEL_UM * 1e-3, cfg.MAX_STEP_PIN_MM)
                cells = [(i * sx, j * sy) for i, j in _spiral(int(cfg.SEARCH_RADIUS_X_MM / sx), int(cfg.SEARCH_RADIUS_Y_MM / sy) if use_y else 0)]
            if k >= len(cells):
                break
            tx, ty = cells[k]; k += 1
            run.log("note", f"find-pin: no pin in view; searching at offset x {tx:+.3f}, y {ty:+.3f} mm", {"agent": False})
        r = goto(tx, ty, "find-pin")
        if not r["ok"]:
            return {"ok": False, "found": False, "reason": r["reason"], "steps": steps}
        m = do_measure(run, None, "find")
    goto(0.0, 0.0, "find-pin: nothing found, back to start")
    run.log("find_pin", "pin NOT found within the search limits; returned to the start position", {"steps": steps})
    return {"ok": False, "found": False, "reason": "pin not found within the search radius / step budget; returned to start", "steps": steps,
            "searched": len(log)}


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
    s = sub.add_parser("step-pm"); s.add_argument("theta", type=float); s.add_argument("--apply", action="store_true", help="also move z, x (and aerox with --base)")
    s.add_argument("--base", action="store_true", help="include the aerox move (axis -> beam centre); sensible for theta >= 60"); s.add_argument("--force", action="store_true")
    s = sub.add_parser("fast-align"); s.add_argument("--no-verify", action="store_true")
    s = sub.add_parser("adaptive-align"); s.add_argument("--step", type=float, default=15.0); s.add_argument("--max-passes", type=int, default=6)
    s = sub.add_parser("find-pin"); s.add_argument("--max-steps", type=int, default=60); s.add_argument("--no-y", action="store_true")
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
        _CTX.update(run=run, cmd=a.cmd)
        return _out({"run": run.dir.name, "dir": str(run.dir), "pixel_um": cfg.PIXEL_UM})
    run = Run.current(a.run)
    _CTX.update(run=run, cmd=a.cmd)
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
    if a.cmd == "step-pm":
        return _out(do_step_pm(run, a.theta, a.apply, a.base, a.force))
    if a.cmd == "adaptive-align":
        return _out(do_adaptive_align(run, a.step, a.max_passes))
    if a.cmd == "fast-align":
        return _out(do_fast_align(run, not a.no_verify))
    if a.cmd == "find-pin":
        return _out(do_find_pin(run, a.max_steps, not a.no_y))
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
