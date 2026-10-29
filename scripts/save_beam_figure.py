"""Beam-footprint centre + FWHM figure from a raw frame (.npy). Usage: python -I scripts/save_beam_figure.py FRAME.npy NAME [--run ID]
Writes runs/<id>/figures/NAME.png and NAME.json (inside the run folder). Top axis = column profile (+ full width at half max), right axis = row profile.
Method = beam_center.half_max_footprint (half-maximum footprint midpoint, user decision 2026-10-27)."""
import sys, json
sys.dont_write_bytecode = True
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import beam_center as bc
import align_config as cfg

img = np.load(sys.argv[1]).astype(np.float32)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from balign.session import Run
_a = sys.argv[1:]
_run = Run.current(_a[_a.index("--run") + 1] if "--run" in _a else None)
prefix = str(_run.subdir("figures") / Path(sys.argv[2]).name)
h = bc.half_max_footprint(img)
x0, x1, y0, y1 = (int(v) for v in h["box"])
cx, cy = h["cx"], h["cy"]
H, W = img.shape
fw, fh = x1 - x0, y1 - y0
col, row = h["col"], h["row"]

def step_edges(img, box):
    """Footprint edges = steepest rise / fall of the profile averaged over the central 60 % of the half-max box (independent of the dome shape)."""
    from scipy import ndimage as ndi
    im = ndi.median_filter(img, size=3)
    bx0, bx1, by0, by1 = box
    mx, my = int(0.2 * (bx1 - bx0)), int(0.2 * (by1 - by0))
    out = []
    for prof, a, b in ((im[by0 + my:by1 - my].mean(axis=0), bx0, bx1), (im[:, bx0 + mx:bx1 - mx].mean(axis=1), by0, by1)):
        g = np.gradient(ndi.gaussian_filter1d(prof, 3)); w = int(0.15 * (b - a))
        out.append((a - w + int(np.argmax(g[a - w:a + w])), b - w + int(np.argmin(g[b - w:b + w]))))
    return out

(sx0, sx1), (sy0, sy1) = step_edges(img, (x0, x1, y0, y1))
scx, scy = (sx0 + sx1) / 2, (sy0 + sy1) / 2

lo, hi = np.percentile(img, [1, 99.8])
fig = plt.figure(figsize=(11, 9.4))
gs = fig.add_gridspec(2, 2, width_ratios=[4, 1.1], height_ratios=[1.1, 4], hspace=0.04, wspace=0.04)
ax = fig.add_subplot(gs[1, 0]); axt = fig.add_subplot(gs[0, 0], sharex=ax); axr = fig.add_subplot(gs[1, 1], sharey=ax)
ax.imshow(img, cmap="gray", vmin=lo, vmax=hi, origin="upper", aspect="equal", interpolation="nearest")
ax.add_patch(plt.Rectangle((x0, y0), fw, fh, fill=False, ec="#3fd07f", lw=1.2))
ax.axvline(cx, color="#3fd07f", lw=0.9); ax.axhline(cy, color="#3fd07f", lw=0.9)
ax.plot([cx], [cy], "+", color="#ff5050", ms=18, mew=2)
ax.add_patch(plt.Rectangle((sx0, sy0), sx1 - sx0, sy1 - sy0, fill=False, ec="#ffb000", lw=1.2, ls="--"))
ax.plot([scx], [scy], "x", color="#ffb000", ms=14, mew=2)
ax.axvline((W - 1) / 2, color="#4aa3ff", ls=":", lw=1); ax.axhline((H - 1) / 2, color="#4aa3ff", ls=":", lw=1)
ax.set_xlim(0, W - 1); ax.set_ylim(H - 1, 0)
ax.set_xlabel("column (px)"); ax.set_ylabel("row (px)")
ax.text(0.01, 0.01, f"half-max centre (red +): ({cx:.1f}, {cy:.1f})   steep-edge centre (orange x): ({scx:.1f}, {scy:.1f})  |  dotted = frame ctr ({(W-1)/2:.1f}, {(H-1)/2:.1f})",
        transform=ax.transAxes, color="w", fontsize=6.5, va="bottom", bbox=dict(fc="k", alpha=0.6, lw=0))

xs, ys = np.arange(W), np.arange(H)
axt.plot(xs, col["raw"], color="#999", lw=0.6, label="mean over beam rows")
axt.plot(xs, col["smooth"], color="C0", lw=1.2, label="smoothed")
axt.axhline(col["half"], color="C3", ls="--", lw=0.9, label="half max")
axt.axvline(cx, color="#3fd07f", lw=1); axt.axvline(scx, color="#ffb000", lw=1, ls="--")
for e in (sx0, sx1): axt.axvline(e, color="#ffb000", lw=0.8, ls=":")
axt.annotate("", xy=(x0, col["half"]), xytext=(x1, col["half"]), arrowprops=dict(arrowstyle="<->", color="C3"))
axt.text(cx, col["half"] * 1.04, f"FWHM = {fw} px = {fw*cfg.PIXEL_UM:.0f} um (at PIXEL_UM={cfg.PIXEL_UM})", ha="center", va="bottom", color="C3", fontsize=9)
axt.set_ylabel("counts"); axt.xaxis.tick_top(); axt.xaxis.set_label_position("top"); axt.set_xlabel("column profile  (centre col %.1f)" % cx)
axt.legend(fontsize=7, loc="upper left", frameon=False)

axr.plot(row["raw"], ys, color="#999", lw=0.6); axr.plot(row["smooth"], ys, color="C0", lw=1.2)
axr.axvline(row["half"], color="C3", ls="--", lw=0.9); axr.axhline(cy, color="#3fd07f", lw=1); axr.axhline(scy, color="#ffb000", lw=1, ls="--")
for e in (sy0, sy1): axr.axhline(e, color="#ffb000", lw=0.8, ls=":")
axr.annotate("", xy=(row["half"], y0), xytext=(row["half"], y1), arrowprops=dict(arrowstyle="<->", color="C3"))
axr.text(row["half"] * 1.04, cy, f"FWHM = {fh} px\n= {fh*cfg.PIXEL_UM:.0f} um", color="C3", fontsize=9, va="center", rotation=-90)
axr.yaxis.tick_right(); axr.xaxis.tick_top(); axr.xaxis.set_label_position("top"); axr.set_xlabel("row profile\n(centre row %.1f)" % cy)
plt.setp(axr.get_yticklabels(), visible=False); plt.setp(axt.get_xticklabels(), visible=True)
fig.suptitle("gh1 direct beam: half-maximum footprint centre and full width", y=0.995, fontsize=11)
fig.savefig(prefix + ".png", dpi=130, bbox_inches="tight")

out = {"frame": sys.argv[1], "shape": [H, W], "cx": cx, "cy": cy, "box_x": [x0, x1], "box_y": [y0, y1], "fwhm_x_px": fw, "fwhm_y_px": fh,
       "pixel_um": cfg.PIXEL_UM,
       "step_edge": {"cx": scx, "cy": scy, "x": [sx0, sx1], "y": [sy0, sy1], "width_px": sx1 - sx0, "height_px": sy1 - sy0}, "frame_centre": [(W - 1) / 2, (H - 1) / 2], "cx_minus_frame_px": cx - (W - 1) / 2, "cy_minus_frame_px": cy - (H - 1) / 2,
       "col_half_level": float(col["half"]), "col_base": float(col["base"]), "col_top": float(col["top"]),
       "row_half_level": float(row["half"]), "row_base": float(row["base"]), "row_top": float(row["top"]),
       "saturated_frac": float((img >= 65535).mean())}
json.dump(out, open(prefix + ".json", "w"), indent=1)
print(json.dumps(out, indent=1))
