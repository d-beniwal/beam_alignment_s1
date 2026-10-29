"""Robust segmentation and shape fit of the alignment pin on a tomo-camera image.

The pin is a dark (absorbing) upright truncated cone: a flat top surface and two
straight inclined sides.  `fit_pin(image)` returns a `PinFit` with

 1. the top surface: corners, width, midpoint, flatness (rms / max deviation of
    the top boundary from its best-fit line, tilt of that line);
 2. the pin axis: bisector of the two fitted sides, anchored at the midpoint of
    the top surface (also the plain vertical line through that midpoint);
 3. view completeness: is the whole pin (top corners + both sides down to the
    bottom of the lit area) inside the field, and the signed horizontal shift
    the pin needs in the *image* to be fully in view (+ = pin moves right).

Design for robustness against contrast / brightness / noise changes:
 - everything is expressed in *ratios to a fitted beam model*, so absolute
   counts and gradients do not matter; optional dark/white frames are used if
   valid (non-zero);
 - the pin/beam threshold is the 50 % level between the measured beam and pin
   levels (not a fixed number); a contrast-to-noise check reports failure
   instead of returning garbage;
 - edges are located per row/column to sub-pixel precision and lines are fitted
   robustly (Theil-Sen start, soft-L1 refine, MAD inlier re-fit);
 - rows/columns touching the lit-area (or detector) border are excluded from
   the fits and counted as clipped.

Only numpy + scipy are required.  Image coordinates: x = column, y = row (down),
pixel centres at integers.  Nothing here talks to hardware.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict

import numpy as np
from scipy import ndimage as ndi
from scipy.optimize import least_squares
from scipy.stats import theilslopes


# --------------------------------------------------------------------------- #
# parameters / result containers
# --------------------------------------------------------------------------- #
@dataclass
class Params:
    hot_median: int = 3             # median size to kill hot/dead pixels
    smooth_sigma: float = 2.0       # px, Gaussian before thresholding
    fp_level: float = 0.35          # lit-area threshold: lo + fp_level*(hi-lo)
    box_frac: float = 0.03          # row/col bright fraction (rel. to max) to be inside lit area
    edge_guard_px: int = 24         # rows within this of a lit-area rim count as clipped (rim blur / model error)
    min_edge_sharp: float = 0.4     # drop rows whose edge gradient is < this fraction of the median
    box_inset: int = 6              # px, shrink lit-area box (blurry rim) when not at detector border
    beam_poly_deg: int = 3          # polynomial degree of the beam model
    min_contrast: float = 0.10      # min (beam - pin) in beam-normalised units
    min_cnr: float = 5.0            # min contrast / noise of the smoothed ratio
    min_area_frac: float = 0.002    # min pin area as a fraction of lit-area box
    top_tol_px: float = 1.5         # min tolerance of the top plateau about its line
    edge_start_px: int = 12         # rows skipped below the top (corner rounding)
    min_edge_rows: int = 30         # min unclipped rows to trust a side fit
    margin_px: int = 15             # required free margin around the pin in view
    margin_frac: float = 0.10       # ... or this fraction of the top width, if larger
    flat_rms_px: float = 1.0        # top surface "flat" if rms <= this ...
    flat_tilt_deg: float = 1.0      # ... and |tilt| <= this
    corner_probe_px: int = 45       # far end of the window probed beyond a plateau end (corners round off over ~25 px)
    corner_min_slope: float = 0.75  # min |dy/dx| of the boundary beyond a real corner (side steepness)
    expected_top_width_px: float | None = None  # prior used only to size a clipped-corner shift
    expected_half_angle_deg: float = 15.2  # cone half-angle of the pin; used to tell the pin from other dark objects (holder, ...)
    cone_slope_tol: float = 0.15    # |dwidth/drow - expected| / expected allowed for a 'cone-like' object (real pin frames: 0.53-0.54 vs 0.544 expected)
    cone_rms_tol: float = 0.06      # rms of width(row) about its line, relative to the mean width
    cone_min_rows: int = 60         # fewer usable rows -> shape unknown (not judged)


@dataclass
class PinFit:
    status: str = "not_run"          # ok | low_contrast | no_pin | sides_unavailable | error
    message: str = ""
    # image / lit-area geometry (full-image pixel coords, inclusive, after inset)
    box: tuple | None = None         # (x0, x1, y0, y1)
    box_at_detector_edge: dict = field(default_factory=dict)  # which sides are the detector border
    # detection quality
    pin_level: float = np.nan        # beam-normalised transmission inside pin (0..1)
    contrast: float = np.nan         # beam - pin (normalised)
    cnr: float = np.nan              # contrast / noise
    pin_area_px: int = 0
    # top surface
    top_found: bool = False
    top_row: float = np.nan          # y of top line at its midpoint
    top_left: tuple | None = None    # (x, y) corner (side-line / top-line intersection)
    top_right: tuple | None = None
    top_width: float = np.nan
    top_flat_width: float = np.nan   # width of the measured flat plateau
    top_plateau_mid: float = np.nan
    top_left_bevel_px: float = 0.0   # virtual-top width not on the flat plateau (chamfered tip)
    top_right_bevel_px: float = 0.0
    top_mid: tuple | None = None     # midpoint of the two corners = axis anchor
    top_plateau_x: tuple | None = None   # measured plateau extent (xa, xb)
    top_flat: bool = False
    top_tilt_deg: float = np.nan     # tilt of the top line from horizontal
    top_rms_px: float = np.nan       # roughness of top boundary about its line
    top_maxdev_px: float = np.nan
    top_left_visible: bool = False
    top_right_visible: bool = False
    top_clipped: bool = False        # top touches the lit-area/detector top
    # sides
    left_line: tuple | None = None   # x = a*y + b
    right_line: tuple | None = None
    left_rms_px: float = np.nan
    right_rms_px: float = np.nan
    left_rows: int = 0
    right_rows: int = 0
    left_inferred: bool = False      # side mirrored from the other one
    right_inferred: bool = False
    half_angle_left_deg: float = np.nan
    half_angle_right_deg: float = np.nan
    half_angle_deg: float = np.nan   # cone half angle (mean of both)
    asymmetry_deg: float = np.nan    # right - left
    apex: tuple | None = None
    # axis
    axis_tilt_deg: float = np.nan    # cone axis vs image vertical (+: leans to +x going down)
    axis_x_top: float = np.nan       # x of vertical axis through top-surface midpoint
    axis_x_at_row: dict = field(default_factory=dict)  # cone axis x at a few rows
    # view completeness
    full_view: bool = False
    view_score: float = 0.0          # 1 = fully in view, 0 = nothing usable
    clipped_left: bool = False       # pin runs off the left lit/detector border
    clipped_right: bool = False
    left_clip_rows_frac: float = 0.0
    right_clip_rows_frac: float = 0.0
    need_move_right_px: float = 0.0  # pin must move +x (right) by this to clear the left border
    need_move_left_px: float = 0.0
    shift_px: float = 0.0            # signed image shift to bring pin fully in view (+ = right)
    shift_is_lower_bound: bool = False
    field_too_small: bool = False    # pin wider than the usable field
    move_pin_image_x: str = "none"   # right | left | none | unknown
    move_pin_image_y: str = "none"   # down | none
    cone_slope: float = np.nan       # d(width)/d(row) of the chosen dark object (cone: 2*tan(half angle))
    cone_rel_rms: float = np.nan
    cone_top_width: float = np.nan   # width of the chosen object extrapolated to its top row (px)
    cone_like: bool | None = None    # True: width grows linearly like the pin cone; False: some other object; None: too few rows to judge
    n_candidates: int = 0            # dark objects of pin-like size considered
    shift_y_px: float = 0.0
    confidence: str = "high"
    notes: list = field(default_factory=list)

    def to_dict(self):
        return json.loads(json.dumps(asdict(self), default=_jsonable))

    def summary(self):
        f = lambda v, n=1: "nan" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:.{n}f}"
        t = f"[{self.status}] full_view={self.full_view} score={self.view_score:.2f} move_x={self.move_pin_image_x}({f(self.shift_px)}px"
        t += ",>=)" if self.shift_is_lower_bound else ")"
        if self.top_found:
            t += (f" | top width={f(self.top_width)} mid=({f(self.top_mid[0] if self.top_mid else None)},"
                  f"{f(self.top_mid[1] if self.top_mid else None)}) flat={self.top_flat} rms={f(self.top_rms_px,2)}"
                  f" tilt={f(self.top_tilt_deg,2)}deg")
        t += f" | half-angle={f(self.half_angle_deg,2)} axis_tilt={f(self.axis_tilt_deg,2)}deg axis_x={f(self.axis_x_top)}"
        return t


def _jsonable(o):
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _otsu(vals, nbins=128):
    vals = vals[np.isfinite(vals)]
    hist, edges = np.histogram(vals, bins=nbins)
    c = 0.5 * (edges[:-1] + edges[1:])
    w0 = np.cumsum(hist).astype(float)
    w1 = w0[-1] - w0
    s = np.cumsum(hist * c)
    m0 = s / np.maximum(w0, 1)
    m1 = (s[-1] - s) / np.maximum(w1, 1)
    return c[np.argmax(w0 * w1 * (m0 - m1) ** 2)]


def _as_2d_ref(a):
    if a is None:
        return None
    a = np.asarray(a, float)
    if a.ndim == 3:
        a = np.median(a, axis=0)
    return a


def _span_from_steps(profile, min_rel=0.3):
    """Lit span [i0, i1] of a 1-D brightness profile from its two strongest opposite steps.
    A side with no strong step is treated as running off the detector (edge = array border).
    Step based, so a smooth beam gradient / vignetting does not matter."""
    n = len(profile)
    pr = ndi.gaussian_filter1d(profile.astype(float), 3)
    d = np.gradient(pr)
    span = max(np.percentile(pr, 92) - np.percentile(pr, 5), 1e-9)
    half = n // 2
    i0 = int(np.argmax(d[:half]))
    i1 = half + int(np.argmin(d[half:]))
    k = 10
    up = pr[min(i0 + k, n - 1)] - pr[max(i0 - k, 0)]
    dn = pr[max(i1 - k, 0)] - pr[min(i1 + k, n - 1)]
    lo = i0 if up > min_rel * span else 0
    hi = i1 if dn > min_rel * span else n - 1
    return int(lo), int(hi)


def _footprint_steps(sm, p: Params):
    """EXPERIMENTAL (regressed under noise/blur/crop in tests, not used): lit-area box from step profiles."""
    H, W = sm.shape
    sub = sm[::4]
    c0, c1 = _span_from_steps(np.percentile(sub, 75, axis=0))
    r0, r1 = _span_from_steps(np.percentile(sm[:, c0:c1 + 1][:, ::4], 75, axis=1))
    c0, c1 = _span_from_steps(np.percentile(sm[r0:r1 + 1:4, :], 75, axis=0))
    if c1 - c0 < 20 or r1 - r0 < 20:
        return None
    return int(r0), int(r1), int(c0), int(c1)


def _footprint(sm, p: Params):
    """Bounding box (y0, y1, x0, x1) of the lit area, from bright-fraction projections."""
    sub = sm[::4, ::4]
    lo, hi = np.percentile(sub, [2, 98])
    if not np.isfinite(hi - lo) or hi - lo <= 1e-9:
        return None
    bright = sm > lo + p.fp_level * (hi - lo)
    bright = ndi.binary_opening(bright, iterations=3)
    if not bright.any():
        return None
    colf = bright.mean(0)
    c = np.flatnonzero(colf >= p.box_frac * colf.max())
    c0, c1 = c[0], c[-1]
    rowf = bright[:, c0:c1 + 1].mean(1)
    r = np.flatnonzero(rowf >= p.box_frac * rowf.max())
    r0, r1 = r[0], r[-1]
    colf = bright[r0:r1 + 1].mean(0)
    c = np.flatnonzero(colf >= p.box_frac * colf.max())
    return int(r0), int(r1), int(c[0]), int(c[-1])


def _outside_bg(sm, x0, x1, y0, y1):
    """Dark/scatter level estimated from the region outside the lit area (0 if there is none)."""
    m = np.ones(sm.shape, bool)
    m[max(y0 - 20, 0):y1 + 21, max(x0 - 20, 0):x1 + 21] = False
    if m.sum() < 0.02 * sm.size:
        return 0.0
    bg = float(np.median(sm[m][::7]))
    # a dark/scatter level cannot exceed the darkest in-beam object (the pin): otherwise do not subtract
    pin_floor = float(np.percentile(sm[y0:y1 + 1:2, x0:x1 + 1:2], 5))
    return bg if 0 <= bg <= pin_floor else 0.0


def _poly_design(x, y, deg):
    cols = [(x ** i) * (y ** j) for i in range(deg + 1) for j in range(deg + 1 - i)]
    return np.stack(cols, -1)


def _beam_model(sub, deg):
    """Smooth multiplicative beam model: robust polynomial fit to the *bright* pixels."""
    h, w = sub.shape
    ds = max(1, min(h, w) // 120)
    yy, xx = np.mgrid[0:h:ds, 0:w:ds]
    X = (xx - w / 2) / w
    Y = (yy - h / 2) / h
    v = sub[::ds, ::ds]
    A = _poly_design(X.ravel(), Y.ravel(), deg)
    mask = (v > _otsu(v.ravel())).ravel()
    coef = None
    for _ in range(5):
        if mask.sum() < A.shape[1] * 3:
            break
        coef, *_ = np.linalg.lstsq(A[mask], v.ravel()[mask], rcond=None)
        model = A @ coef
        mask = v.ravel() > 0.75 * np.maximum(model, 1e-9)
    if coef is None:
        return np.full_like(sub, np.median(sub))
    Xf = (np.arange(w) - w / 2) / w
    Yf = (np.arange(h) - h / 2) / h
    XX, YY = np.meshgrid(Xf, Yf)
    full = (_poly_design(XX.ravel(), YY.ravel(), deg) @ coef).reshape(h, w)
    return np.maximum(full, 0.05 * full.max())


def _robust_line(y, x, f_scale=0.7):
    """x = a*y + b, outlier-resistant.  Returns a, b, rms(inliers), n_inliers."""
    y = np.asarray(y, float)
    x = np.asarray(x, float)
    if len(y) > 400:
        k = int(np.ceil(len(y) / 400))
        ys, xs = y[::k], x[::k]
    else:
        ys, xs = y, x
    a0, b0 = theilslopes(xs, ys)[:2]
    res = least_squares(lambda q: q[0] * y + q[1] - x, [a0, b0], loss="soft_l1", f_scale=f_scale)
    a, b = res.x
    r = a * y + b - x
    mad = 1.4826 * np.median(np.abs(r - np.median(r)))
    inl = np.abs(r) < max(2.5 * mad, 1.0)
    if inl.sum() >= 5:
        a, b = np.polyfit(y[inl], x[inl], 1)
        r = a * y + b - x
    rms = float(np.sqrt(np.mean(r[inl] ** 2))) if inl.any() else float("nan")
    return float(a), float(b), rms, int(inl.sum())



def _local_cross(rv, i, side, w, contrast, win=8, ref=(4, 14)):
    """Sub-pixel edge using a *local* 50 % level (beam sampled just outside the edge, pin just inside).
    Immune to residual beam-model error near rims.  Returns (x, sharpness) or None.
    sharpness = transition amplitude per pixel relative to the local step (1 = ideal step)."""
    if side == "L":
        blo, bhi, plo, phi = i - ref[1], i - ref[0], i + ref[0] + 2, i + ref[1] + 2
    else:
        blo, bhi, plo, phi = i + ref[0], i + ref[1], i - ref[1] - 2, i - ref[0] - 2
    if min(blo, plo) < 0 or max(bhi, phi) > w - 1:
        return None
    b = np.median(rv[blo:bhi + 1])
    q = np.median(rv[plo:phi + 1])
    if b - q < 0.3 * contrast:
        return None
    lv = 0.5 * (b + q)
    a0, a1 = max(0, i - win), min(w - 1, i + win)
    seg = rv[a0:a1 + 1] - lv
    if side == "L":
        k = np.flatnonzero((seg[:-1] > 0) & (seg[1:] <= 0))
        ref_pos = i - 0.5
    else:
        k = np.flatnonzero((seg[:-1] <= 0) & (seg[1:] > 0))
        ref_pos = i + 0.5
    if k.size == 0:
        return None
    k = k[np.argmin(np.abs(a0 + k + 0.5 - ref_pos))]
    d = seg[k] - seg[k + 1]
    if d == 0:
        return None
    return float(a0 + k + seg[k] / d), float(abs(d) / (b - q))


def _longest_run(mask_row):
    idx = np.flatnonzero(mask_row)
    if idx.size == 0:
        return None
    br = np.flatnonzero(np.diff(idx) > 1)
    starts = np.r_[idx[0], idx[br + 1]]
    ends = np.r_[idx[br], idx[-1]]
    k = np.argmax(ends - starts)
    return int(starts[k]), int(ends[k])


# --------------------------------------------------------------------------- #
# main entry point
# --------------------------------------------------------------------------- #
def _cone_stats(comp, p: Params):
    """Is this dark object cone-like? Width per row (rim-touching rows skipped) vs row: linear with slope ~ 2*tan(half angle)
    and small scatter. Returns (slope, rel_rms, like) with like=None when there are too few rows to judge."""
    h, w = comp.shape
    ys = np.flatnonzero(comp.any(1))
    if len(ys) == 0:
        return np.nan, np.nan, None, np.nan
    xs0, xs1 = [], []
    rows = []
    for y in ys[p.edge_start_px:]:
        r = comp[y]
        if r[0] or r[-1]:
            continue
        idx = np.flatnonzero(r)
        rows.append(y); xs0.append(idx[0]); xs1.append(idx[-1])
    if len(rows) < p.cone_min_rows:
        return np.nan, np.nan, None, np.nan
    rows = np.asarray(rows, float)
    wid = np.asarray(xs1, float) - np.asarray(xs0, float) + 1
    step = max(1, len(rows) // 200)
    slope, icpt, *_ = theilslopes(wid[::step], rows[::step])
    rms = float(np.sqrt(np.mean((wid - (icpt + slope * rows)) ** 2)))
    rel = rms / max(float(wid.mean()), 1.0)
    exp = 2.0 * np.tan(np.radians(p.expected_half_angle_deg))
    like = bool(abs(slope - exp) / exp <= p.cone_slope_tol and rel <= p.cone_rms_tol and slope > 0)
    return float(slope), float(rel), like, float(icpt + slope * ys[0])


def fit_pin(image, params: Params | None = None, dark=None, white=None, return_debug=False):
    p = params or Params()
    out = PinFit()
    dbg = {}
    try:
        _fit(np.asarray(image), p, dark, white, out, dbg)
    except Exception as e:  # never raise into an alignment loop
        out.status = "error"
        out.message = f"{type(e).__name__}: {e}"
    return (out, dbg) if return_debug else out


def _fit(image, p: Params, dark, white, out: PinFit, dbg):
    a = image.astype(float)
    H, W = a.shape
    dark = _as_2d_ref(dark)
    white = _as_2d_ref(white)
    use_dark = dark is not None and dark.shape == a.shape and np.any(dark)
    if use_dark:
        a = a - dark
    if p.hot_median and p.hot_median > 1:
        a = ndi.median_filter(a, size=p.hot_median)
    sm = ndi.gaussian_filter(a, p.smooth_sigma)

    # ---- lit area ---------------------------------------------------------
    if white is not None and white.shape == a.shape and np.any(white) and np.ptp(white) > 0:
        fp_img = ndi.gaussian_filter(ndi.median_filter(white - (dark if use_dark else 0), size=3), p.smooth_sigma)
    else:
        fp_img = sm
    fp = _footprint(fp_img, p)
    if fp is None:
        out.status, out.message = "no_pin", "no lit area found (flat image?)"
        return
    r0, r1, c0, c1 = fp
    at = {"left": c0 <= 2, "right": c1 >= W - 3, "top": r0 <= 2, "bottom": r1 >= H - 3}
    ins = p.box_inset
    x0 = c0 if at["left"] else c0 + ins
    x1 = c1 if at["right"] else c1 - ins
    y0 = r0 if at["top"] else r0 + ins
    y1 = r1 if at["bottom"] else r1 - ins
    out.box, out.box_at_detector_edge = (x0, x1, y0, y1), at
    sub = sm[y0:y1 + 1, x0:x1 + 1]
    h, w = sub.shape
    if h < 60 or w < 60:
        out.status, out.message = "no_pin", "lit area too small"
        return

    # ---- beam-normalised ratio image ---------------------------------------
    if white is not None and white.shape == a.shape and np.any(white):
        wd = ndi.gaussian_filter(white - (dark if use_dark else 0), p.smooth_sigma)[y0:y1 + 1, x0:x1 + 1]
        norm = sub / np.maximum(wd, 0.02 * np.abs(wd).max())
        out.notes.append("flat-fielded with dark/white")
    else:
        bg = 0.0 if use_dark else _outside_bg(sm, x0, x1, y0, y1)
        norm = sub - bg
        if bg:
            out.notes.append(f"subtracted outside-area background {bg:.0f}")
    model = _beam_model(norm, p.beam_poly_deg)
    rat = norm / model
    t0 = _otsu(rat[::2, ::2].ravel())
    beam_px, pin_px = rat > t0, rat <= t0
    if beam_px.sum() < 100 or pin_px.sum() < 100:
        out.status, out.message = "no_pin", "no dark object inside lit area"
        return
    mb, mp = float(np.median(rat[beam_px])), float(np.median(rat[pin_px]))
    noise = 1.4826 * float(np.median(np.abs(rat[beam_px] - mb)))
    level = 0.5 * (mb + mp)
    out.pin_level = mp / mb
    out.contrast = (mb - mp) / mb
    out.cnr = (mb - mp) / max(noise, 1e-9)
    rat = rat / mb
    level /= mb
    if out.contrast < p.min_contrast or out.cnr < p.min_cnr:
        out.status = "low_contrast"
        out.message = f"contrast {out.contrast:.2f}, CNR {out.cnr:.1f} below limits"
        return

    # ---- segmentation -------------------------------------------------------
    dark_mask = ndi.binary_opening(rat < level, iterations=1)
    lab, n = ndi.label(dark_mask)
    if n == 0:
        out.status, out.message = "no_pin", "no dark component"
        return
    areas = ndi.sum(dark_mask, lab, range(1, n + 1))
    k = 1 + int(np.argmax(areas))
    cands = [i + 1 for i in range(n) if areas[i] >= p.min_area_frac * h * w]
    out.n_candidates = len(cands)
    if len(cands) > 1:     # several pin-sized dark objects (holder, wire, debris ...): take the cone-like one, not the biggest
        scored = []
        for i in cands:
            sl, rel, like, _tw = _cone_stats(lab == i, p)
            if like:
                scored.append((abs(sl - 2.0 * np.tan(np.radians(p.expected_half_angle_deg))), -areas[i - 1], i))
        if scored:
            k = min(scored)[2]
            if k != 1 + int(np.argmax(areas)):
                out.notes.append(f"{len(cands)} dark objects: chose the cone-like one (not the largest)")
    comp = lab == k
    out.pin_area_px = int(areas[k - 1])
    out.cone_slope, out.cone_rel_rms, out.cone_like, out.cone_top_width = _cone_stats(comp, p)
    dbg.update(rat=rat, comp=comp, level=level, origin=(x0, y0))
    if out.pin_area_px < p.min_area_frac * h * w:
        out.status, out.message = "no_pin", f"largest dark object only {out.pin_area_px} px"
        _mass_direction(out, rat < level, w, x0)
        return

    ys_all = np.flatnonzero(comp.any(1))
    xs_all = np.flatnonzero(comp.any(0))
    ytop_i, ybot_i = int(ys_all[0]), int(ys_all[-1])

    # ---- per-row edges (sub-pixel) -----------------------------------------
    contrast_norm = out.contrast  # (beam - pin) in beam-normalised units
    gl = 2 if at["left"] else p.edge_guard_px     # no rim blur at a detector border
    gr = 2 if at["right"] else p.edge_guard_px
    rows, Lx, Rx, Lc, Rc, gL, gR = [], [], [], [], [], [], []
    for y in range(ytop_i, ybot_i + 1):
        run = _longest_run(comp[y])
        if run is None:
            continue
        l, r = run
        lc, rc = l <= gl, r >= w - 1 - gr
        sl = sr = 0.0
        if l > 0:
            va, vb = rat[y, l - 1], rat[y, l]
            xl = l - 1 + (va - level) / (va - vb) if va > vb else l
            sl = max(va - vb, 0.0)
        else:
            xl = 0.0
        if r < w - 1:
            va, vb = rat[y, r], rat[y, r + 1]
            xr = r + (level - va) / (vb - va) if vb > va else r
            sr = max(vb - va, 0.0)
        else:
            xr = float(w - 1)
        # refine with a local 50 % level (handles residual beam-model error / gradients near rims)
        cl = None if lc else _local_cross(rat[y], l, "L", w, contrast_norm)
        cr = None if rc else _local_cross(rat[y], r, "R", w, contrast_norm)
        if cl:
            xl, sl = cl
        if cr:
            xr, sr = cr
        rows.append(y); Lx.append(xl); Rx.append(xr); Lc.append(lc); Rc.append(rc); gL.append(sl); gR.append(sr)
    rows = np.array(rows); Lx = np.array(Lx); Rx = np.array(Rx); Lc = np.array(Lc); Rc = np.array(Rc)
    gL = np.array(gL); gR = np.array(gR)

    # ---- top boundary / plateau --------------------------------------------
    T = np.full(len(xs_all), np.nan)
    for j, x in enumerate(xs_all):
        col = np.flatnonzero(comp[:, x])
        y = col[0]
        if y > 0:
            va, vb = rat[y - 1, x], rat[y, x]
            T[j] = y - 1 + (va - level) / (va - vb) if va > vb else y
        else:
            T[j] = 0.0
    out.top_clipped = bool(np.nanmin(T) <= (1.0 if at['top'] else p.edge_guard_px))
    plateau = None
    if not out.top_clipped:
        y0p = np.nanpercentile(T, 3)
        cand = T <= y0p + 3.0
        runs, start = [], None
        for j, c in enumerate(cand):
            if c and start is None:
                start = j
            if (not c or j == len(cand) - 1) and start is not None:
                runs.append((start, j if c and j == len(cand) - 1 else j - 1))
                start = None
        if runs:
            ia, ib = max(runs, key=lambda t: t[1] - t[0])
            if ib - ia >= 4:
                tr = max(1, int(0.1 * (ib - ia + 1)))
                xi, Ti = xs_all[ia + tr:ib - tr + 1], T[ia + tr:ib - tr + 1]
                if len(xi) >= 3:
                    sl, ic = theilslopes(Ti, xi)[:2]
                    res = Ti - (sl * xi + ic)
                    tol = max(p.top_tol_px, 4 * 1.4826 * np.median(np.abs(res - np.median(res))))
                    ja, jb = ia, ib
                    while ja > 0 and abs(T[ja - 1] - (sl * xs_all[ja - 1] + ic)) <= tol:
                        ja -= 1
                    while jb < len(T) - 1 and abs(T[jb + 1] - (sl * xs_all[jb + 1] + ic)) <= tol:
                        jb += 1
                    tr = max(1, int(0.1 * (jb - ja + 1)))
                    xi, Ti = xs_all[ja + tr:jb - tr + 1], T[ja + tr:jb - tr + 1]
                    sl, ic = theilslopes(Ti, xi)[:2]
                    res = Ti - (sl * xi + ic)
                    plateau = dict(ja=int(ja), jb=int(jb), xa=float(xs_all[ja]), xb=float(xs_all[jb]), slope=float(sl), icpt=float(ic),
                                   rms=float(np.sqrt(np.mean(res ** 2))), maxdev=float(np.abs(res).max()))
    if plateau is None:
        out.notes.append("no flat top found (pointed, noisy, or clipped at top)")

    # ---- side lines ----------------------------------------------------------
    skip = (plateau['icpt'] + plateau['slope'] * 0.5 * (plateau['xa'] + plateau['xb'])) + p.edge_start_px \
        if plateau else ytop_i + p.edge_start_px
    use = rows >= skip
    left_line = right_line = None
    selL, selR = use & ~Lc, use & ~Rc
    if selL.sum() >= p.min_edge_rows:
        selL &= gL >= p.min_edge_sharp * np.median(gL[selL])
    if selR.sum() >= p.min_edge_rows:
        selR &= gR >= p.min_edge_sharp * np.median(gR[selR])
    if selL.sum() >= p.min_edge_rows:
        aL, bL, rmsL, nL = _robust_line(rows[selL], Lx[selL])
        left_line, out.left_rms_px, out.left_rows = (aL, bL), rmsL, nL
    if selR.sum() >= p.min_edge_rows:
        aR, bR, rmsR, nR = _robust_line(rows[selR], Rx[selR])
        right_line, out.right_rms_px, out.right_rows = (aR, bR), rmsR, nR
    out.left_clip_rows_frac = float(Lc[use].mean()) if use.any() else 0.0
    out.right_clip_rows_frac = float(Rc[use].mean()) if use.any() else 0.0
    out.clipped_left = bool(Lc.any() and out.left_clip_rows_frac > 0.0)
    out.clipped_right = bool(Rc.any() and out.right_clip_rows_frac > 0.0)

    # ---- geometry in full-image coordinates ------------------------------------
    def to_full_line(line):  # x = a*y + b in box coords -> full coords
        a_, b_ = line
        return a_, b_ + x0 - a_ * y0

    fl = to_full_line(left_line) if left_line else None
    fr = to_full_line(right_line) if right_line else None
    top_line = None
    if plateau:
        top_line = (plateau['slope'], plateau['icpt'] + y0 - plateau['slope'] * x0)  # y = m*x + c (full)
        out.top_found = True
        out.top_plateau_x = (plateau['xa'] + x0, plateau['xb'] + x0)
        out.top_flat_width = float(plateau['xb'] - plateau['xa'])
        out.top_tilt_deg = float(np.degrees(np.arctan(plateau['slope'])))
        out.top_rms_px, out.top_maxdev_px = plateau['rms'], plateau['maxdev']
        out.top_flat = bool(plateau['rms'] <= p.flat_rms_px and abs(out.top_tilt_deg) <= p.flat_tilt_deg
                            and plateau['xb'] - plateau['xa'] >= 8)
    if fl:
        out.left_line = fl
        out.half_angle_left_deg = float(-np.degrees(np.arctan(fl[0])))
    if fr:
        out.right_line = fr
        out.half_angle_right_deg = float(np.degrees(np.arctan(fr[0])))
    if fl and fr:
        out.half_angle_deg = 0.5 * (out.half_angle_left_deg + out.half_angle_right_deg)
        out.asymmetry_deg = out.half_angle_right_deg - out.half_angle_left_deg
        out.axis_tilt_deg = 0.5 * out.asymmetry_deg
        if abs(fr[0] - fl[0]) > 1e-9:
            ya = (fl[1] - fr[1]) / (fr[0] - fl[0])
            out.apex = (float(fl[0] * ya + fl[1]), float(ya))

    def corner(line_x):
        """Virtual top corner = side line meets the (extended) top line.  Robust to a bevelled top."""
        a_, b_ = line_x
        m, c = top_line
        x = (a_ * c + b_) / (1 - a_ * m)
        return (float(x), float(m * x + c))

    if top_line and fl and fr:
        cl, cr = corner(fl), corner(fr)
        out.top_left, out.top_right = cl, cr
        out.top_width = float(cr[0] - cl[0])
        out.top_mid = (0.5 * (cl[0] + cr[0]), 0.5 * (cl[1] + cr[1]))
        out.top_row = out.top_mid[1]
        out.axis_x_top = out.top_mid[0]
        tn = np.tan(np.radians(out.axis_tilt_deg))
        out.axis_x_at_row = {int(r): float(out.top_mid[0] + tn * (r - out.top_mid[1])) for r in (y0, (y0 + y1) // 2, y1)}
        # bevel = part of the virtual top width that is NOT on the flat plateau (pin tip can be chamfered)
        out.top_left_bevel_px = float(max(0.0, out.top_plateau_x[0] - cl[0]))
        out.top_right_bevel_px = float(max(0.0, cr[0] - out.top_plateau_x[1]))
        out.top_plateau_mid = float(0.5 * (out.top_plateau_x[0] + out.top_plateau_x[1]))
    elif top_line:
        m, c = top_line
        if fr:
            out.top_right = corner(fr)
        if fl:
            out.top_left = corner(fl)
        out.top_row = float(m * 0.5 * (out.top_plateau_x[0] + out.top_plateau_x[1]) + c)
        out.top_plateau_mid = float(0.5 * (out.top_plateau_x[0] + out.top_plateau_x[1]))
    if out.top_left and fl:
        out.top_left_visible = bool(out.top_left[0] > x0 + gl)
    if out.top_right and fr:
        out.top_right_visible = bool(out.top_right[0] < x1 - gr)
    if plateau is not None and (out.top_left_bevel_px > 12 or out.top_right_bevel_px > 12):
        out.notes.append(f"bevelled top: flat plateau is {out.top_flat_width:.0f}px of a {out.top_width:.0f}px virtual top "
                         f"(bevel L {out.top_left_bevel_px:.0f}px, R {out.top_right_bevel_px:.0f}px)")

    # ---- completeness / direction -------------------------------------------------
    bx0, bx1, by0, by1 = x0, x1, y0, y1
    mtop = out.top_width if np.isfinite(out.top_width) else (p.expected_top_width_px or 0.0)
    marg = max(p.margin_px, p.margin_frac * (mtop or 0.0))
    y_b = min(by1, y0 + ybot_i)   # pin continues to the bottom of the lit area, or ends earlier
    y_t = out.top_row if np.isfinite(out.top_row) else float(y0 + ytop_i)
    notes = out.notes
    if out.top_clipped:
        out.move_pin_image_y, out.shift_y_px = "down", float(marg)
        notes.append("top of pin is outside the lit area / detector")
    needR = needL = 0.0
    lb = False
    if fl and fr:
        # horizontal extent of the pin between its top row and the bottom of the view
        xmin = min(fl[0] * y_t + fl[1], fl[0] * y_b + fl[1])
        xmax = max(fr[0] * y_t + fr[1], fr[0] * y_b + fr[1])
        needR = max(0.0, (bx0 + marg) - xmin)
        needL = max(0.0, xmax - (bx1 - marg))
        out.view_score = float(np.clip(1 - (needR + needL) / max(xmax - xmin, 1.0), 0, 1))
        if out.top_clipped:
            out.view_score = min(out.view_score, 0.5)
    else:
        # a side is not measurable: direction is known, magnitude only a lower bound
        lb = True
        left_gone = fl is None and out.clipped_left
        right_gone = fr is None and out.clipped_right
        if left_gone and not right_gone:
            needR = marg
            if p.expected_top_width_px and out.top_right:
                needR = max(marg, p.expected_top_width_px - (out.top_right[0] - bx0) + marg)
            notes.append("left side of the pin is outside the view; shift is a lower bound")
        elif right_gone and not left_gone:
            needL = marg
            if p.expected_top_width_px and out.top_left:
                needL = max(marg, p.expected_top_width_px - (bx1 - out.top_left[0]) + marg)
            notes.append("right side of the pin is outside the view; shift is a lower bound")
        elif left_gone and right_gone:
            out.field_too_small = True
        else:
            _mass_direction(out, comp, w, x0)
            needR = max(0.0, out.shift_px)
            needL = max(0.0, -out.shift_px)
            notes.append("side edges could not be fitted (blurry/too few rows); direction from dark-mass position")
        out.view_score = float(np.clip(0.5 - 0.1 * (needR + needL) / max(w, 1), 0, 0.5))
    out.need_move_right_px, out.need_move_left_px = float(needR), float(needL)
    if needR > 0 and needL > 0:
        out.field_too_small = True
    if out.field_too_small:
        xs_cols = np.flatnonzero(comp.any(0))
        out.shift_px = float(0.5 * (bx0 + bx1) - (x0 + 0.5 * (xs_cols[0] + xs_cols[-1])))
        out.move_pin_image_x = "right" if out.shift_px > 0 else "left"
        out.confidence = "low"
        notes.append("pin wider than usable field in this view")
    elif needR > 0:
        out.shift_px, out.move_pin_image_x = float(needR), "right"
    elif needL > 0:
        out.shift_px, out.move_pin_image_x = -float(needL), "left"
    out.shift_is_lower_bound = bool(lb and (needR > 0 or needL > 0) and not out.field_too_small)
    out.full_view = bool(out.top_found and fl is not None and fr is not None and not out.top_clipped
                         and needR == 0 and needL == 0)
    if out.full_view:
        out.view_score = 1.0
    if fl and fr:
        out.status = "ok"
    else:
        out.status = "sides_unavailable"
        out.confidence = "medium" if (needR > 0 or needL > 0) else "low"
    dbg.update(rows=rows + y0, Lx=Lx + x0, Rx=Rx + x0, Lc=Lc, Rc=Rc, T=T + y0, xs_T=xs_all + x0)


def _mass_direction(out: PinFit, dark_mask, w, x0):
    """Fallback when the shape cannot be fitted: move the pin toward the side where less of it is."""
    cols = np.flatnonzero(dark_mask.any(0)) if dark_mask.any() else np.array([])
    if cols.size == 0:
        out.move_pin_image_x = "unknown"
        out.confidence = "low"
        return
    cx = cols.mean()
    out.move_pin_image_x = "right" if cx < w / 2 else "left"
    out.shift_px = float((w / 2 - cx) * (1 if out.move_pin_image_x == "right" else 1))
    out.shift_is_lower_bound = True
    out.confidence = "low"


def stage_x_hint(res: PinFit, image_x_to_stage_sign=None, pixel_size_um=None):  # default pixel size: align_config.PIXEL_UM
    """Convert the image shift into a stage move.  The motor sign / pixel size are NOT known yet
    (see DOMAIN.md to-confirm list), so by default only the image-space direction is returned."""
    d = {"move_pin_in_image": res.move_pin_image_x, "image_dx_px": res.shift_px,
         "lower_bound": res.shift_is_lower_bound}
    if pixel_size_um is None:
        import align_config
        pixel_size_um = align_config.PIXEL_UM
    if image_x_to_stage_sign is not None:
        d["stage_dx_mm"] = float(image_x_to_stage_sign * res.shift_px * pixel_size_um * 1e-3)
    else:
        d["stage_dx_mm"] = None
        d["note"] = "stage sign / pixel size not configured"
    return d


# --------------------------------------------------------------------------- #
# QA overlay (matplotlib is optional)
# --------------------------------------------------------------------------- #
def overlay(image, res: PinFit, path=None, ax=None, title=None):
    import matplotlib
    if ax is None:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    own = ax is None
    if own:
        fig, ax = plt.subplots(figsize=(7, 6))
    a = np.asarray(image, float)
    lo, hi = np.percentile(a, [1, 99.5])
    ax.imshow(a, cmap="gray", vmin=lo, vmax=hi)
    if res.box:
        x0, x1, y0, y1 = res.box
        ax.add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, ec="c", lw=0.8, ls="--"))
    H = a.shape[0]
    yy = np.array([res.top_row if np.isfinite(res.top_row) else 0, res.box[3] if res.box else H - 1])
    if res.left_line:
        ax.plot(res.left_line[0] * yy + res.left_line[1], yy, "r-" if not res.left_inferred else "r:", lw=1)
    if res.right_line:
        ax.plot(res.right_line[0] * yy + res.right_line[1], yy, "r-" if not res.right_inferred else "r:", lw=1)
    if res.top_left:
        ax.plot(*res.top_left, "yo", ms=5)
    if res.top_right:
        ax.plot(*res.top_right, "yo", ms=5)
    if res.top_plateau_x and np.isfinite(res.top_row):
        ax.plot(res.top_plateau_x, [res.top_row] * 2, "-", c="lime", lw=2)
    if res.top_mid:
        ym = np.array([res.top_mid[1], yy[1]])
        ax.plot(res.top_mid[0] + np.tan(np.radians(res.axis_tilt_deg)) * (ym - res.top_mid[1]), ym, "m--", lw=1)
        ax.plot(*res.top_mid, "m+", ms=12)
    ax.set_title(title or res.summary()[:110], fontsize=7)
    if own and path:
        fig.savefig(path, dpi=70)
        plt.close(fig)
    return ax


if __name__ == "__main__":
    import argparse
    import h5py
    ap = argparse.ArgumentParser(description="Fit the alignment pin in a tomo image (HDF5 exchange/data).")
    ap.add_argument("file")
    ap.add_argument("--frame", type=int, default=0)
    ap.add_argument("--png", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    with h5py.File(a.file, "r") as f:
        img = f["exchange/data"][a.frame]
        dk = f["exchange/data_dark"][()] if "exchange/data_dark" in f else None
        wh = f["exchange/data_white"][()] if "exchange/data_white" in f else None
    r = fit_pin(img, dark=dk, white=wh)
    print(json.dumps(r.to_dict(), indent=1) if a.json else r.summary())
    if a.png:
        overlay(img, r, a.png)
