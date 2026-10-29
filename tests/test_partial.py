"""Partly visible pin on REAL frames (s1_data, git-ignored, local only): the pin shadow of a real frame is MOVED relative to the fixed lit
footprint (beam E and pin transmission T are separated; see Scene) until it is half cut off at the left/right rim, or its top is above / its
body is barely above the bottom of the footprint. Checks (a) where the pin is (axis column / top row estimated from the visible part),
(b) the suggested move has the right direction and size, (c) closed loop: applying the suggested move brings the pin into proper view.
Usage: python -I tests/test_partial.py"""
import sys
sys.dont_write_bytecode = True
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import numpy as np  # noqa: E402
import h5py  # noqa: E402
from scipy import ndimage as ndi  # noqa: E402
import balign  # noqa: E402,F401
from balign import measure as M  # noqa: E402
import align_config as cfg  # noqa: E402

D = ROOT / "s1_data/tomo_alignment/"
if not (D / "alignment_pin/alignment_pin_000044.h5").exists():
    print("SKIP: s1_data not available"); sys.exit(0)


def load(fn, i):
    with h5py.File(D / fn, "r") as f:
        return f["exchange/data"][i].astype(np.float32)


def empty_beam(img):
    """Pin removed: smooth polynomial over the pin region (+ matching noise), real data elsewhere."""
    bx = M.beam_footprint(img)["box"]
    r0, r1, c0, c1 = bx[2] + 3, bx[3] - 3, bx[0] + 25, bx[1] - 25
    sub = img[r0:r1, c0:c1]
    base = np.percentile(img, 5)
    thr = base + 0.4 * (np.median(sub) - base)
    pin = ndi.binary_dilation(ndi.gaussian_filter(sub, 2) < thr, iterations=12)
    yy, xx = np.mgrid[0:sub.shape[0], 0:sub.shape[1]]
    u, v = xx / sub.shape[1] * 2 - 1, yy / sub.shape[0] * 2 - 1
    A = np.stack([u ** i * v ** j for i in range(5) for j in range(5 - i)], -1)
    coef, *_ = np.linalg.lstsq(A[~pin][::7], sub[~pin][::7], rcond=None)
    fit = A @ coef
    out = img.copy()
    out[r0:r1, c0:c1] = np.where(pin, fit + np.random.default_rng(0).normal(0, np.sqrt(np.maximum(fit, 1)) * 0.6, fit.shape), sub)
    return out, base


class Scene:
    """Real pin frame = beam E x pin transmission T; render(dx, dy) moves only the pin (dx right, dy down, image px)."""
    def __init__(self, img):
        self.E, self.bg = empty_beam(img)
        lit = self.E - self.bg
        ok = lit > 0.25 * np.median(lit[lit > 0.5 * np.percentile(lit, 95)])
        self.T = np.ones_like(img)
        self.T[ok] = np.clip((img[ok] - self.bg) / lit[ok], 0, 1.3)
        rl = int(np.flatnonzero(ok.mean(axis=1) > 0.2)[-1]) - 25          # last well-lit row: below it the real pin continues, unseen
        row = self.T[rl]
        pin = np.flatnonzero(row < 0.5)
        if len(pin):                                                       # continue the cone below the footprint (widening at the cone rate)
            lo, hi = pin[0], pin[-1]
            c, w, lev = (lo + hi) / 2, hi - lo + 1, float(np.median(row[pin]))
            xs = np.arange(self.T.shape[1])
            for k, y in enumerate(range(rl + 1, self.T.shape[0]), 1):
                self.T[y] = np.where(np.abs(xs - c) <= (w + 2 * np.tan(np.radians(15.2)) * k) / 2, lev, 1.0)

    def render(self, dx=0, dy=0):
        T, dx, dy = self.T, int(round(dx)), int(round(dy))
        if dx:
            T2 = np.ones_like(T)
            if dx > 0: T2[:, dx:] = T[:, :-dx]
            else: T2[:, :dx] = T[:, -dx:]
            T = T2
        if dy:
            T2 = np.empty_like(T)
            if dy > 0: T2[dy:] = T[:-dy]; T2[:dy] = 1.0
            else: T2[:dy] = T[-dy:]; T2[dy:] = T[-1]
            T = T2
        return self.bg + (self.E - self.bg) * T


def hint_px(view):
    h = view.get("hint") or {}
    dx = h["x_mm"] * 1e3 / cfg.PIXEL_UM * cfg.IMAGE_COL_PER_X if "x_mm" in h else 0.0      # image px the pin must move right
    dy = h["y_mm"] * 1e3 / cfg.PIXEL_UM * cfg.IMAGE_ROW_PER_Y if "y_mm" in h else 0.0      # image px the pin must move down
    return dx, dy


fails = []


def check(name, ok, info=""):
    print(("PASS " if ok else "FAIL ") + name, info)
    if not ok:
        fails.append(name)


def pick_bases():
    """Frames whose pin lies fully inside the footprint (no part of its shadow already lost to the rim), so moving the shadow is a fair test."""
    out = []
    for fn in ("alignment_pin/alignment_pin_000044.h5", "alignment_pin_off_center_0_180/alignment_pin_off_center_0_180_000046.h5",
               "alignment_pin_off_center_n90_p90/alignment_pin_off_center_n90_p90_000047.h5"):
        got = 0
        for idx in range(0, 100, 3):
            try:
                m = M.measure_frame(load(fn, idx), 0.0)
            except Exception:
                break
            if m["usable"] and abs(m["pin_col"] - m["beam"]["cx"]) < 60 and m["quality"] == "both_flanks":
                out.append((fn, idx)); got += 1
                if got == 2:
                    break
    return out


BASES = pick_bases()
print("bases:", [(f.split("/")[-1][14:-3], i) for f, i in BASES])
for fn, idx in BASES:
    tag = f"{fn.split('/')[-1][14:-3]}[{idx}]"
    base = load(fn, idx)
    m0 = M.measure_frame(base, 0.0)
    if not m0["usable"]:
        print("SKIP base", tag, m0["reasons"]); continue
    prior = {"top_width": m0["top_width"], "half_angle_deg": m0["half_angle_deg"]}
    bp = {k: m0["beam"][k] for k in ("cx", "cy", "width", "height", "box")}
    sc = Scene(base)
    bl, br, bt, bb = m0["beam"]["box"]
    x0, top0, cxb = m0["pin_col"], m0["top_row"], m0["beam"]["cx"]
    print(f"--- {tag}: footprint cols {bl}-{br} rows {bt}-{bb}, pin col {x0:.0f}, top row {top0:.0f}")
    cases = []
    for off in (60, 0, -60):                       # pin axis relative to the left / right footprint rim (0 = half visible)
        cases.append((f"half cut LEFT (axis at rim{off:+d})", (bl + off) - x0, 0))
        cases.append((f"half cut RIGHT (axis at rim{-off:+d})", (br - off) - x0, 0))
    for up in (60, 200, 350):
        cases.append((f"top {up}px above the footprint", 0, -(top0 - bt) - up))
    cases.append(("cut LEFT and top above", (bl + 0) - x0, -(top0 - bt) - 150))
    cases.append(("cut RIGHT and top above", (br - 0) - x0, -(top0 - bt) - 150))
    for name, dx, dy in cases:
        # (a)+(b): first look, with the prior learned from the clean frame
        m = M.measure_frame(sc.render(dx, dy), 0.0, prior, bp)
        v = m["view"]
        ex, ey = dx, dy
        hx, hy = hint_px(v)
        want_x = cxb - (x0 + dx) if (bl + 90 > x0 + dx or br - 90 < x0 + dx) else 0.0          # centre it when cut at a rim
        combined = dx != 0 and dy != 0
        okdir = (np.sign(hx) == np.sign(want_x) or abs(want_x) < 30) and (combined or abs(hx - want_x) < 70 or abs(want_x) < 30)   # combined: closed loop decides
        loc = v.get("locate")
        axis_err = None if not loc else loc["axis_col"] - (x0 + dx)
        # (c): closed loop, up to 3 moves
        cur_dx, cur_dy, steps, mm = dx, dy, 0, m
        while mm["view"]["state"] != "in_view" and steps < 3:
            hx2, hy2 = hint_px(mm["view"])
            if hx2 == 0 and hy2 == 0:
                break
            cur_dx += hx2; cur_dy += hy2; steps += 1
            mm = M.measure_frame(sc.render(cur_dx, cur_dy), 0.0, prior, bp)
        good = mm["usable"] and abs(mm["pin_col"] - (x0 + cur_dx)) < 3.0
        check(f"{name}", v["state"] == "partial" and okdir and good,
              f"first={v['state']} hint=({hx:+.0f},{hy:+.0f}) want_x={want_x:+.0f} axis_err={'-' if axis_err is None else f'{axis_err:+.0f}'} -> {steps} move(s) -> {mm['view']['state']} col_err={'-' if not mm['usable'] else f'{mm['pin_col'] - (x0 + cur_dx):+.1f}'}")
print("ALL OK" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)
