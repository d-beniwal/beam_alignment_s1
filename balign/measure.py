"""Image measurements: pin axis column (pinfit), beam-footprint centre (beam_center), sinusoid fit, overlay rendering."""
import numpy as np
from scipy import ndimage as ndi
from PIL import Image, ImageDraw
import pinfit
import align_config as cfg


def _cross(profile, sigma=5.0, frac=0.5):
    """Sub-pixel half-maximum edges (lo, hi) of a lit-area profile."""
    p = ndi.gaussian_filter1d(np.asarray(profile, float), sigma)
    base, top = np.percentile(p, 5), np.percentile(p, 90)
    lvl = base + frac * (top - base)
    idx = np.where(p > lvl)[0]
    if len(idx) < 2:
        return None
    i0, i1 = idx[0], idx[-1]
    lo = i0 - 1 + (lvl - p[i0 - 1]) / (p[i0] - p[i0 - 1]) if i0 > 0 else float(i0)
    hi = i1 + (p[i1] - lvl) / (p[i1] - p[i1 + 1]) if i1 < len(p) - 1 else float(i1)
    return lo, hi


def beam_footprint(img, pin=None, margin=15, pin_present=True, geom=None):
    """Half-maximum footprint of the lit area (centre = midpoint, user decision 2026-10-27) that IGNORES the pin shadow.

    The old estimate averaged whole rows/columns, so a pin sitting off-centre darkened one side and dragged the 'beam centre'
    by up to ~150 px. Here the column profile is taken only over rows ABOVE the pin top, the row profile only over columns
    OUTSIDE the pin. A coarse 90th-percentile pass (insensitive to a shadow covering < 90 % of a row/column) fixes the search window.
    `pin` = the PinFit (optional); `pin_present=False` (empty frame) allows plain means. With a pin present but its geometry unavailable the
    result stays on the coarse percentile pass (method 'p90-coarse', a few px less consistent with the half-max definition).
    Returns cx, cy, box (x0, x1, y0, y1), width, height, method."""
    f = 4
    H, W = img.shape
    h, w = H // f * f, W // f * f
    im4 = img[:h, :w].astype(np.float32).reshape(h // f, f, w // f, f).mean(axis=(1, 3))
    rr = _cross(np.percentile(im4, 90, axis=1), 1.5)
    if rr is None:
        return None
    m = int(0.1 * (rr[1] - rr[0]))
    cc = _cross(np.percentile(im4[int(rr[0]) + m:int(rr[1]) - m], 90, axis=0), 1.5)
    if cc is None:
        return None
    c0, c1 = cc[0] * f + (f - 1) / 2, cc[1] * f + (f - 1) / 2
    r0, r1 = rr[0] * f + (f - 1) / 2, rr[1] * f + (f - 1) / 2
    method = "p90-coarse"
    # refinement at full resolution, excluding the pin
    xl = xr = top = None
    if geom is not None:                                    # (x_left, x_right, top_row) of the pin's dark object, e.g. from its mask
        xl, xr, top = geom
    elif pin is not None and getattr(pin, "left_line", None) is not None and getattr(pin, "right_line", None) is not None \
            and np.isfinite(getattr(pin, "top_row", np.nan)):
        top = float(pin.top_row)
        ys = (top, r1)
        xl = min(pin.left_line[0] * y + pin.left_line[1] for y in ys)
        xr = max(pin.right_line[0] * y + pin.right_line[1] for y in ys)
    pad = 100
    xa, xb = max(0, int(c0) - pad), min(W, int(c1) + pad)
    ya, yb = max(0, int(r0) - pad), min(H, int(r1) + pad)
    out_c = out_r = None
    if top is not None and top - r0 > 60:                        # pin-free band above the pin top
        band = img[int(r0) + margin:int(top) - margin, xa:xb].astype(np.float32).mean(axis=0)
        e = _cross(band)
        if e:
            out_c = (e[0] + xa, e[1] + xa)
    elif top is None and not pin_present:
        e = _cross(img[int(r0) + int(m * f):int(r1) - int(m * f), xa:xb].astype(np.float32).mean(axis=0))
        if e:
            out_c = (e[0] + xa, e[1] + xa)
    cols = np.arange(int(c0) + margin, int(c1) - margin)
    if xl is not None:
        cols = cols[(cols < xl - 30) | (cols > xr + 30)]
    if (xl is not None or not pin_present) and len(cols) >= 80:
        e = _cross(img[ya:yb][:, cols].astype(np.float32).mean(axis=1))
        if e:
            out_r = (e[0] + ya, e[1] + ya)
    if out_c:
        c0, c1, method = out_c[0], out_c[1], "pin-excluded"
    if out_r:
        r0, r1 = out_r
    return {"cx": float((c0 + c1) / 2), "cy": float((r0 + r1) / 2), "box": [int(round(c0)), int(round(c1)), int(round(r0)), int(round(r1))],
            "width": float(c1 - c0), "height": float(r1 - r0), "method": method}


def _pin_geom(r, dbg):
    """(x_left, x_right, top_row) of the pin's dark object in full-image coordinates, from the pinfit mask (works for a partly visible pin)."""
    if dbg is None or "comp" not in dbg:
        return None
    comp, (ox, oy) = dbg["comp"], dbg["origin"]
    ys, xs = np.flatnonzero(comp.any(1)), np.flatnonzero(comp.any(0))
    if len(ys) == 0:
        return None
    return float(xs[0] + ox), float(xs[-1] + ox), float(ys[0] + oy)


def measure_frame(img, omega, prior=None, beam_prior=None):
    """Pin + beam measurement on one frame. Returns a JSON-able dict (never raises on a bad frame).

    `prior` = {"top_width": px, "half_angle_deg": deg} learned earlier in the run (optional); `beam_prior` = the lit footprint learned from clean frames. A frame is `usable` only if the pin's top
    corners and both flanks are real pin edges inside the lit footprint; if just one flank is trustworthy and a top-width prior exists,
    the axis is taken from that flank (`quality` = one_sided_left/right). Everything else is rejected with `reasons` (never guessed)."""
    coarse = beam_footprint(img)           # pin-independent lit footprint: tells pinfit where the real rims are
    prm = pinfit.Params(lit_box=tuple(coarse["box"])) if coarse else None
    r, dbg = pinfit.fit_pin(img, prm, return_debug=True)
    out = {"omega": float(omega), "status": r.status, "message": r.message, "confidence": str(r.confidence),
           "pin_col": None, "pin_col_raw": None, "usable": False, "quality": None, "reasons": [], "top_row": None, "top_width": None,
           "half_angle_deg": None, "full_view": bool(r.full_view), "notes": list(r.notes),
           "identity": "other" if r.cone_like is False else ("pin" if r.cone_like else "unknown"),
           "cone_top_width": None if not np.isfinite(r.cone_top_width) else float(r.cone_top_width),
           "n_dark_objects": int(r.n_candidates), "cone_slope": None if not np.isfinite(r.cone_slope) else float(r.cone_slope)}
    pin_obj = (r.status not in ("no_pin", "low_contrast", "error")) and np.isfinite(r.contrast) and r.contrast >= cfg.PIN_MIN_CONTRAST \
        and r.pin_area_px > 0.002 * (img.shape[0] * img.shape[1] * 0.2)
    out["pin_object"] = bool(pin_obj)
    b = beam_footprint(img, r if pin_obj else None, pin_present=bool(pin_obj), geom=_pin_geom(r, dbg) if pin_obj else None)
    if beam_prior and (b is None or b.get("method") != "pin-excluded"):   # the footprint is fixed during a run: reuse the one learned from clean frames
        b = dict(beam_prior, method="prior")
    out["beam"] = b if b else {"cx": float("nan"), "cy": float("nan"), "box": [0, 0, 0, 0], "width": 0.0, "height": 0.0, "method": "failed"}
    if r.status == "ok" and np.isfinite(r.axis_x_top) and pin_obj:
        out.update(pin_col_raw=float(r.axis_x_top), top_row=float(r.top_row), top_width=float(r.top_width),
                   half_angle_deg=float(r.half_angle_deg))
        v = _validate(r, out["beam"], prior, out)
        out.update(v)
        if v.get("identity"):
            out["identity"] = v["identity"]
    else:
        out["reasons"].append(r.status if r.status != "ok" else "no_axis")
    wp = (prior or {}).get("top_width")      # object width at its top vs the pin width learned in this run (works even if the edge fit failed)
    if pin_obj and wp and out["cone_top_width"] and abs(out["cone_top_width"] - wp) / wp > 2 * cfg.TOP_WIDTH_TOL:
        out["identity"] = "other"
        out["reasons"].append(f"object top width ~{out['cone_top_width']:.0f}px vs {wp:.0f}px learned for the pin")
    out["view"] = assess_view(out, r, dbg, prior)
    out["_fit"] = r
    return out


def _validate(r, beam, prior, out):
    """Decide whether the fit is a trustworthy pin silhouette (see measure_frame)."""
    reasons, bx0, bx1 = [], beam["box"][0], beam["box"][1]
    tl, tr = r.top_left, r.top_right
    nom = (prior or {}).get("half_angle_deg", cfg.NOMINAL_HALF_ANGLE_DEG)
    w_prior = (prior or {}).get("top_width")

    def side_ok(name, ang, line, corner, inferred):
        why = []
        if line is None or corner is None:
            return ["missing (clipped)"]
        if inferred:
            why.append("inferred (clipped)")
        if not np.isfinite(ang) or abs(ang - nom) > cfg.HALF_ANGLE_TOL_DEG:
            why.append(f"slope {ang:.1f}deg vs {nom:.1f}")
        if not (bx0 + cfg.CLIP_MARGIN_PX <= corner[0] <= bx1 - cfg.CLIP_MARGIN_PX):
            why.append("corner at lit-area edge (clipped)")
        return why
    wl = side_ok("L", r.half_angle_left_deg, r.left_line, tl, r.left_inferred)
    wr = side_ok("R", r.half_angle_right_deg, r.right_line, tr, r.right_inferred)
    if r.top_clipped:
        reasons.append("top touches lit-area edge (move pin down)")
    for side, frac in (("left", r.left_clip_rows_frac), ("right", r.right_clip_rows_frac)):   # a few clipped rows are fine (pinfit skips them)
        if frac > 0.6:
            reasons.append(f"pin runs off the {side} lit-area edge over {frac:.0%} of its length")
    if not wl and not wr and w_prior and r.top_width and abs(r.top_width - w_prior) / w_prior > cfg.TOP_WIDTH_TOL:
        return {"identity": "other", "reasons": [f"top width {r.top_width:.0f}px vs {w_prior:.0f}px learned for the pin: a different object"]}
    clip_involved = any("clipped" in x for x in wl + wr) or any("runs off" in x for x in reasons)
    if wl and wr and not clip_involved:     # neither flank has the pin's cone angle, and it is not just the rim cutting the pin
        return {"identity": "other", "reasons": reasons + [f"left flank: {'; '.join(wl)}", f"right flank: {'; '.join(wr)}"]}
    if not reasons and not wl and not wr:
        return {"pin_col": float(r.axis_x_top), "usable": True, "quality": "both_flanks", "identity": "pin"}
    if not reasons and bool(w_prior) and (not wl) != (not wr):
        good_left = not wl
        corner = tl if good_left else tr
        col = corner[0] + w_prior / 2 if good_left else corner[0] - w_prior / 2
        return {"pin_col": float(col), "usable": True, "quality": "one_sided_" + ("left" if good_left else "right"),
                "reasons": [f"{'right' if good_left else 'left'} flank rejected: " + "; ".join(wr if good_left else wl)]}
    return {"reasons": reasons + ([f"left flank: {'; '.join(wl)}"] if wl else []) + ([f"right flank: {'; '.join(wr)}"] if wr else [])}


def locate_partial(r, dbg, prior, nominal_half_angle=None):
    """Where is a partly visible pin, and how far must it move? Uses the dark object's per-row extents and the cone model with the width
    learned in this run:  width(y) = W + 2 t (y - y_top).  Rows that run into the lit-area rim only constrain their free edge, so
    c = r_edge - width/2 (left side cut) or l_edge + width/2 (right side cut); rows with both edges free give (l+r)/2 directly.
    If the top is cut off, y_top follows from the width of free rows. Returns None when it cannot be done."""
    if not prior or not prior.get("top_width") or dbg is None or "comp" not in dbg or r.box is None:
        return None
    comp, (ox, oy) = dbg["comp"], dbg["origin"]
    h, w = comp.shape
    gl, gr, gt = dbg.get("guards", (24, 24, 24))
    ys = np.flatnonzero(comp.any(1))
    if len(ys) < 40:
        return None
    first = comp.argmax(1)
    last = w - 1 - comp[:, ::-1].argmax(1)
    W = float(prior["top_width"])
    t = np.tan(np.radians(prior.get("half_angle_deg") or nominal_half_angle or cfg.NOMINAL_HALF_ANGLE_DEG))
    y0 = int(ys[0])
    top_clipped = y0 <= gt
    rows = ys[(ys >= (y0 + 12 if not top_clipped else gt + 12)) & (ys < min(int(ys[-1]) - 6, h - gt))]
    if len(rows) < 20:
        return None
    l, rr = first[rows].astype(float), last[rows].astype(float)
    lc, rc = l <= gl, rr >= w - 1 - gr
    free = ~lc & ~rc
    ytop = float(y0)
    if top_clipped:                                    # how far above the lit area the top is: from the widths of free rows
        if free.sum() < 10:
            return None
        ytop = float(np.median(rows[free] - ((rr - l + 1)[free] - W) / (2 * t)))
    wm = W + 2 * t * (rows - ytop)                     # model width per row
    c = np.where(free, (l + rr) / 2, np.where(lc & ~rc, rr - wm / 2, np.where(rc & ~lc, l + wm / 2, np.nan)))
    c = c[np.isfinite(c)]
    if len(c) < 10:
        return None                                    # every row cut on both sides: pin wider than the field
    return {"axis_col": float(np.median(c)) + ox, "top_row": ytop + oy, "top_clipped": bool(top_clipped),
            "cut_left": bool(lc.any()), "cut_right": bool(rc.any()), "rows_cut_frac": float((~free).mean())}


def assess_view(m, r, dbg=None, prior=None):
    """Is the pin in the field of view - and if not, which way to move it? The 'field of view' is the LIT footprint, not the sensor.
    state: in_view | partial | absent | other_object | no_beam. `hint` = which stage move would bring it in (x from image shift, y assumed sign)."""
    b = m["beam"]
    if b["width"] < 150 or b["height"] < 150:
        return {"state": "no_beam", "hint": None, "why": "no lit footprint found (beam off the detector / shutter closed?)"}
    if m["usable"]:
        return {"state": "in_view", "hint": None, "why": m["quality"]}
    if m.get("identity") == "other":
        n = m.get("n_dark_objects", 0)
        return {"state": "other_object", "hint": None,
                "why": "a dark object is in view but it is not cone-shaped like the pin (holder / other)" + (f"; {n} dark objects" if n > 1 else "")
                + ("; " + "; ".join(m["reasons"]) if m["reasons"] else "")}
    hint = {}
    if not m.get("pin_object"):
        return {"state": "absent", "hint": None, "why": f"no dark pin-sized object inside the lit area ({r.status}, contrast {r.contrast:.2f} < {cfg.PIN_MIN_CONTRAST})"
                if np.isfinite(r.contrast) else f"no dark pin-sized object inside the lit area ({r.status})"}
    loc = locate_partial(r, dbg, prior)
    if loc:                                                      # exact move from the cone model: put the pin axis on the beam centre
        by0, by1 = b["box"][2], b["box"][3]
        out_loc = dict(loc)
        if loc["cut_left"] or loc["cut_right"]:
            dx = b["cx"] - loc["axis_col"]                       # image px the pin must move right (+) / left (-)
            hint["x_mm"] = cfg.px_to_mm(dx / cfg.IMAGE_COL_PER_X)
            hint["x_image_dir"] = "right" if dx > 0 else "left"
        target_top = by0 + 0.2 * b["height"]
        if loc["top_clipped"] or loc["top_row"] > by0 + 0.55 * b["height"]:
            dy = target_top - loc["top_row"]                     # image px the pin must move down (+) / up (-)
            hint["y_mm"] = cfg.px_to_mm(dy / cfg.IMAGE_ROW_PER_Y)
        if hint:
            hint["from"] = "cone model"
            return {"state": "partial", "hint": hint, "locate": out_loc,
                    "why": "; ".join(m["reasons"]) or "pin partly outside the lit area"}
    if getattr(r, "move_pin_image_x", "none") in ("left", "right") and abs(r.shift_px) > 0:
        # pinfit's shift only clears the border (and is just a lower bound when the flank is lost): add a margin / a footprint-fraction step
        sgn = 1.0 if r.move_pin_image_x == "right" else -1.0
        d = sgn * (abs(float(r.shift_px)) + (0.15 * b["width"] if r.shift_is_lower_bound or m["pin_col_raw"] is None else cfg.CLIP_MARGIN_PX))
        hint["x_mm"] = cfg.px_to_mm(d / cfg.IMAGE_COL_PER_X)
        hint["x_image_dir"] = r.move_pin_image_x
    if r.top_clipped or getattr(r, "move_pin_image_y", "none") == "down":
        # top above the lit area: how far above is unknown, so step by 40 % of the footprint height (pinfit's own shift is only a lower bound)
        dy = max(abs(getattr(r, "shift_y_px", 0.0)), 0.4 * b["height"])
        hint["y_mm"] = cfg.px_to_mm(dy / cfg.IMAGE_ROW_PER_Y)      # moving down = row increases by dy; row = row0 + IMAGE_ROW_PER_Y*y_px
    if not hint and (m["pin_col_raw"] is not None):             # a pin is visible but shape checks failed
        return {"state": "partial", "hint": None, "why": "; ".join(m["reasons"]) or "unreliable edges"}
    return {"state": "partial", "hint": hint or None, "why": "; ".join(m["reasons"]) or r.message}


def fit_axis(omegas, cols, weights=None):
    """x(w) = c + a cos w + b sin w (optionally weighted). Returns dict with c, a, b, rms, residuals, rad, phase_deg (their rad*sin(w+st))."""
    om = np.radians(np.asarray(omegas, float))
    x = np.asarray(cols, float)
    if len(x) < 3:
        return {"ok": False, "reason": f"need >=3 valid angles, have {len(x)}"}
    A = np.c_[np.ones_like(om), np.cos(om), np.sin(om)]
    sw = np.sqrt(np.ones_like(x) if weights is None else np.asarray(weights, float))
    (c, a, b), *_ = np.linalg.lstsq(A * sw[:, None], x * sw, rcond=None)
    res = x - A @ [c, a, b]
    return {"ok": True, "c": float(c), "a": float(a), "b": float(b), "rms": float(np.sqrt(np.mean(res ** 2))),
            "residuals": [float(v) for v in res], "n": int(len(x)),
            "rad": float(np.hypot(a, b)), "phase_deg": float(np.degrees(np.arctan2(a, b)))}


def overlay_jpeg(img, m, path, scale=2):
    """Contrast-scaled frame with the detections drawn on it: lit box, beam centre, pin outline, pin axis column."""
    lo, hi = np.percentile(img, [1, 99.5])
    g = np.clip((img.astype(np.float32) - lo) / max(hi - lo, 1) * 255, 0, 255).astype(np.uint8)
    im = Image.fromarray(g).convert("RGB").resize((img.shape[1] // scale, img.shape[0] // scale))
    d = ImageDraw.Draw(im)
    s = 1.0 / scale
    bx0, bx1, by0, by1 = m["beam"]["box"]
    d.rectangle([bx0 * s, by0 * s, bx1 * s, by1 * s], outline=(80, 200, 120))
    d.line([m["beam"]["cx"] * s, 0, m["beam"]["cx"] * s, im.size[1]], fill=(80, 200, 120), width=1)
    r = m.get("_fit")
    if m["pin_col_raw"] is not None and r is not None:
        ytop, ybot = m["top_row"], by1
        if r.left_line is not None and r.right_line is not None:
            for ln in (r.left_line, r.right_line):   # x = a*y + b
                d.line([(ln[0] * ytop + ln[1]) * s, ytop * s, (ln[0] * ybot + ln[1]) * s, ybot * s], fill=(255, 200, 0), width=1)
        if r.top_left is not None and r.top_right is not None:
            d.line([r.top_left[0] * s, r.top_left[1] * s, r.top_right[0] * s, r.top_right[1] * s], fill=(255, 80, 80), width=2)
        col = m["pin_col"] if m["pin_col"] is not None else m["pin_col_raw"]
        d.line([col * s, ytop * s, col * s, ybot * s], fill=(255, 80, 80) if m["usable"] else (160, 160, 160), width=1)
    d.text((6, 4), f"omega {m['omega']:+.1f} deg  pin col {m['pin_col'] if m['pin_col'] is None else round(m['pin_col'], 1)}  "
                   f"beam cx {m['beam']['cx']:.1f}  [{m['status']}; {m['view']['state']}"
                   + (f"; {m['quality']}" if m["usable"] else "; NOT USED: " + "; ".join(m["reasons"])[:90]) + "]", fill=(255, 255, 255))
    im.save(path, quality=85)
