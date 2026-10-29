"""Pin-vs-other-object checks on REAL frames from s1_data (git-ignored, local only) with synthetic extra objects painted in.
The real pin frame is alignment_pin / off-centre scan 46; the 'empty beam' is that frame with the pin inpainted away (data_white is all zeros).
Objects are placed INSIDE the lit footprint (an object outside it is invisible, as in reality). Skips if s1_data is absent.
Usage: python -I tests/test_identity.py"""
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

D = ROOT / "s1_data/tomo_alignment/"
f44, f46 = D / "alignment_pin/alignment_pin_000044.h5", D / "alignment_pin_off_center_0_180/alignment_pin_off_center_0_180_000046.h5"
if not f44.exists():
    print("SKIP: s1_data not available"); sys.exit(0)
with h5py.File(f44, "r") as f:
    pin44 = f["exchange/data"][0].astype(np.float32); dark = f["exchange/data_dark"][0].astype(np.float32)
with h5py.File(f46, "r") as f:
    pin46 = [f["exchange/data"][i].astype(np.float32) for i in (0, 25, 50, 75)]
H, W = pin44.shape
fails = []


def inpaint_pin(img):
    """Remove the dark pin: a smooth 2-D polynomial fitted to the lit pixels replaces the pin region (+ matching noise)."""
    bx = M.beam_footprint(img)["box"]
    r0, r1, c0, c1 = bx[2] + 3, bx[3] - 3, bx[0] + 25, bx[1] - 25
    sub = img[r0:r1, c0:c1]
    base = np.percentile(img, 5)
    thr = base + 0.4 * (np.median(sub) - base)
    pin = ndi.binary_dilation(ndi.gaussian_filter(sub, 2) < thr, iterations=12)
    yy, xx = np.mgrid[0:sub.shape[0], 0:sub.shape[1]]
    u, v = xx / sub.shape[1] * 2 - 1, yy / sub.shape[0] * 2 - 1
    A = np.stack([u ** i * v ** j for i in range(5) for j in range(5 - i)], -1)
    ok = ~pin
    coef, *_ = np.linalg.lstsq(A[ok][::7], sub[ok][::7], rcond=None)
    fit = A @ coef
    rng = np.random.default_rng(0)
    out = img.copy()
    filled = np.where(pin, fit + rng.normal(0, np.sqrt(np.maximum(fit, 1)) * 0.6), sub)
    out[r0:r1, c0:c1] = filled
    return out


def check(name, ok, info=""):
    print(("PASS " if ok else "FAIL ") + name, info)
    if not ok:
        fails.append(name)


def paint(img, mask, T=0.05):
    """Multiply the object's transmission T into `img` (soft edge)."""
    m = ndi.gaussian_filter(mask.astype(np.float32), 1.5)
    return dark + (img - dark) * (1 - (1 - T) * m)


rows, cols = np.mgrid[0:H, 0:W]


def rect(c0, c1, r0, r1): return (cols >= c0) & (cols <= c1) & (rows >= r0) & (rows <= r1)


def flared(cx, r0, r1, w_top, w_bot):
    half = (w_top + (w_bot - w_top) * np.clip((rows - r0) / max(r1 - r0, 1), 0, 1)) / 2
    return (np.abs(cols - cx) <= half) & (rows >= r0) & (rows <= r1)


def meas(img, prior=None, omega=0.0):
    return M.measure_frame(img, omega, prior)


# --- baseline: the real pin frames are identified as the pin and give the same column with and without extra objects
m0 = meas(pin44)
check("real pin frame -> in_view", m0["view"]["state"] == "in_view", f"col {m0['pin_col']:.1f} w {m0['top_width']:.0f}")
prior = {"top_width": m0["top_width"], "half_angle_deg": m0["half_angle_deg"]}
x0 = m0["pin_col"]

white = inpaint_pin(pin44)
bx0, bx1, by0, by1 = m0["beam"]["box"]
print(f"lit footprint cols {bx0}-{bx1}, rows {by0}-{by1}; pin col {x0:.0f}, top row {m0['top_row']:.0f}")
check("empty beam (pin inpainted) -> absent", meas(white)["view"]["state"] == "absent", meas(white)["view"]["state"])

# --- holder only (no pin): wide rectangle, vertical flanks, flat top
cxm = (bx0 + bx1) // 2
for name, mask in {"holder: plain rectangle": rect(cxm - 200, cxm + 200, by0 + 300, H),
                   "holder: rectangle + flared base": flared(cxm, by0 + 250, H, 330, 700),
                   "holder: narrow post (wire-like)": rect(cxm - 30, cxm + 30, by0 + 100, H),
                   "holder: wide block, short": rect(cxm - 300, cxm + 300, by0 + 500, H)}.items():
    for lab, pr in (("no prior", None), ("with prior", prior)):
        v = meas(paint(white, mask), pr)["view"]
        check(f"{name} [{lab}] -> not in_view", v["state"] in ("other_object", "absent"), v["state"])
    check(f"{name} -> other_object (with prior)", meas(paint(white, mask), prior)["view"]["state"] == "other_object", meas(paint(white, mask), prior)["view"]["state"])

# --- pin PLUS a bigger separate dark object: the pin must still be picked (multi-blob selection)
pl, pr_ = int(x0) - 270, int(x0) + 270          # columns the pin can reach at the bottom of the footprint
for name, mask in {"big block left of it": rect(bx0 + 25, max(bx0 + 150, pl - 40), by0 + 60, by1 - 20),
                   "big block right of it": rect(pr_ + 40, bx1 - 25, by0 + 60, by1 - 20),
                   "blocks both sides + wire": rect(bx0 + 25, pl - 40, by0 + 100, by1 - 20) | rect(pr_ + 40, bx1 - 25, by0 + 100, by1 - 20)}.items():
    m = meas(paint(pin44, mask), prior)
    check(f"pin + {name}: pin picked", m["usable"] and abs(m["pin_col"] - x0) < 1.5,
          f"{m['view']['state']} col {m['pin_col']} (clean {x0:.1f}) n_obj {m['n_dark_objects']} {m['reasons']}")

# --- pin merged with a wider holder below it (the realistic pin-on-holder case)
top = m0["top_row"]
for name, mask in {"holder block under the pin (rows 1150+)": rect(int(x0) - 420, int(x0) + 420, 1150, H),
                   "holder block under the pin (rows 1300+)": rect(int(x0) - 600, int(x0) + 600, 1300, H)}.items():
    m = meas(paint(pin44, mask), prior)
    check(f"pin on {name}", m["view"]["state"] in ("in_view", "partial", "other_object") and (not m["usable"] or abs(m["pin_col"] - x0) < 2.0),
          f"{m['view']['state']} usable={m['usable']} col {m['pin_col']} q={m['quality']} {m['reasons'][:2]}")

# --- real scan frames keep working with a prior (regression on 46)
for i, img in enumerate(pin46):
    m = meas(img, prior)
    check(f"real scan-46 frame {i} usable", m["usable"], f"{m['quality']} {m['reasons']}")
print("ALL OK" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
