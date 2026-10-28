"""Image measurements: pin axis column (pinfit), beam-footprint centre (beam_center), sinusoid fit, overlay rendering."""
import numpy as np
from PIL import Image, ImageDraw
import pinfit
import beam_center as bc
import align_config as cfg


def measure_frame(img, omega):
    """Pin + beam measurement on one frame. Returns a JSON-able dict (never raises on a bad frame)."""
    r = pinfit.fit_pin(img)
    out = {"omega": float(omega), "status": r.status, "message": r.message, "confidence": str(r.confidence),
           "pin_col": None, "top_row": None, "top_width": None, "half_angle_deg": None, "full_view": bool(r.full_view),
           "notes": list(r.notes)}
    if r.status == "ok" and np.isfinite(r.axis_x_top):
        out.update(pin_col=float(r.axis_x_top), top_row=float(r.top_row), top_width=float(r.top_width),
                   half_angle_deg=float(r.half_angle_deg))
    h = bc.half_max_footprint(img.astype(np.float32))
    x0, x1, y0, y1 = (int(v) for v in h["box"])
    out["beam"] = {"cx": float(h["cx"]), "cy": float(h["cy"]), "box": [x0, x1, y0, y1], "width": x1 - x0, "height": y1 - y0}
    out["_fit"] = r
    return out


def fit_axis(omegas, cols):
    """x(w) = c + a cos w + b sin w. Returns dict with c, a, b, rms, residuals, rad, phase_deg (their rad*sin(w+st))."""
    om = np.radians(np.asarray(omegas, float))
    x = np.asarray(cols, float)
    if len(x) < 3:
        return {"ok": False, "reason": f"need >=3 valid angles, have {len(x)}"}
    A = np.c_[np.ones_like(om), np.cos(om), np.sin(om)]
    (c, a, b), *_ = np.linalg.lstsq(A, x, rcond=None)
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
    if m["pin_col"] is not None and r is not None:
        ytop, ybot = m["top_row"], by1
        if r.left_line is not None and r.right_line is not None:
            for ln in (r.left_line, r.right_line):   # x = a*y + b
                d.line([(ln[0] * ytop + ln[1]) * s, ytop * s, (ln[0] * ybot + ln[1]) * s, ybot * s], fill=(255, 200, 0), width=1)
        if r.top_left is not None and r.top_right is not None:
            d.line([r.top_left[0] * s, r.top_left[1] * s, r.top_right[0] * s, r.top_right[1] * s], fill=(255, 80, 80), width=2)
        d.line([m["pin_col"] * s, ytop * s, m["pin_col"] * s, ybot * s], fill=(255, 80, 80), width=1)
    d.text((6, 4), f"omega {m['omega']:+.1f} deg  pin col {m['pin_col'] if m['pin_col'] is None else round(m['pin_col'], 1)}  "
                   f"beam cx {m['beam']['cx']:.1f}  [{m['status']}]", fill=(255, 255, 255))
    im.save(path, quality=85)
