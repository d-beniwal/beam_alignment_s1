"""Stage 1: beam-footprint centre from a direct-beam tomo image (no sample). Read-only image analysis.

The core is saturated/structured, so the intensity peak is a poor beam position. Use the footprint instead:
column/row profiles -> positions where the (smoothed) profile crosses a fraction of its plateau level; centre = midpoint.
Several fractions are reported so the spread (soft edges) is visible.
"""
import sys
import numpy as np
from scipy import ndimage as ndi

FRACS = (0.1, 0.25, 0.5, 0.75)


def load_viewer_screenshot(path):
    """Crop the 1920x1200 image out of an ImageJ-viewer screenshot; paint over the yellow ROI overlay."""
    from PIL import Image
    rgb = np.asarray(Image.open(path).convert("RGB")).astype(float)
    g = rgb.mean(axis=2)
    r0 = 36  # image area starts below the title/info bar; 5 px left border
    img = g[r0:r0 + 1200, 5:5 + 1920]
    rgbc = rgb[r0:r0 + 1200, 5:5 + 1920]
    yellow = (rgbc[..., 0] > 150) & (rgbc[..., 1] > 150) & (rgbc[..., 2] < 100)
    yellow = ndi.binary_dilation(yellow, iterations=2)
    # replace overlay pixels by the nearest non-overlay pixel
    idx = ndi.distance_transform_edt(yellow, return_distances=False, return_indices=True)
    filled = img[tuple(idx)]
    return filled, yellow


def _edges(profile, frac):
    p = ndi.gaussian_filter1d(profile, 5)
    base = np.percentile(p, 5)
    top = np.percentile(p, 90)
    lvl = base + frac * (top - base)
    above = np.where(p > lvl)[0]
    return above[0], above[-1]


def beam_center(img, fracs=FRACS):
    """Return {frac: (cx, cy, width, height)} (pixels, column/row, 0-based pixel centres)."""
    # remove isolated hot pixels
    im = ndi.median_filter(img, size=3)
    out = {}
    for f in fracs:
        # the footprint box is found from the mean profiles over the rows/columns that hold the beam
        col = im.mean(axis=0)
        x0, x1 = _edges(col, f)
        row = im[:, x0:x1 + 1].mean(axis=1)
        y0, y1 = _edges(row, f)
        col = im[y0:y1 + 1].mean(axis=0)
        x0, x1 = _edges(col, f)
        out[f] = ((x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0)
    return out


def half_max_footprint(img):
    """Adopted beam centre (user decision 2026-10-27): midpoint of the half-maximum footprint.

    Returns dict with centre (cx, cy), box (x0, x1, y0, y1) and the smoothed profiles/levels used, for QA plots.
    """
    im = ndi.median_filter(img, size=3)
    x0, x1 = _edges(im.mean(axis=0), 0.5)
    y0, y1 = _edges(im[:, x0:x1 + 1].mean(axis=1), 0.5)
    colp = im[y0:y1 + 1].mean(axis=0)
    x0, x1 = _edges(colp, 0.5)
    rowp = im[:, x0:x1 + 1].mean(axis=1)
    out = {"box": (x0, x1, y0, y1), "cx": (x0 + x1) / 2, "cy": (y0 + y1) / 2}
    for key, prof in (("col", colp), ("row", rowp)):
        p = ndi.gaussian_filter1d(prof, 5)
        base, top = np.percentile(p, 5), np.percentile(p, 90)
        out[key] = {"raw": prof, "smooth": p, "base": base, "top": top, "half": base + 0.5 * (top - base)}
    return out


def threshold_centroid(img, frac=0.5):
    im = ndi.gaussian_filter(ndi.median_filter(img, size=3), 3)
    base = np.percentile(im, 5)
    top = np.percentile(im, 90)
    m = im > base + frac * (top - base)
    lab, n = ndi.label(m)
    big = lab == (1 + np.argmax(ndi.sum(m, lab, range(1, n + 1))))
    cy, cx = ndi.center_of_mass(big)
    return cx, cy


if __name__ == "__main__":
    img, ov = load_viewer_screenshot(sys.argv[1])
    print("image", img.shape, "overlay px", int(ov.sum()), "sat frac", float((img >= 250).mean()))
    for f, (cx, cy, w, h) in beam_center(img).items():
        print(f"frac {f:4.2f}: centre ({cx:7.1f}, {cy:7.1f})  size {w:5.0f} x {h:5.0f}")
    for f in (0.25, 0.5):
        print("mask centroid frac", f, "->", tuple(round(v, 1) for v in threshold_centroid(img, f)))
    print("frame centre (959.5, 599.5)")
