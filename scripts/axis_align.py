"""Stage 1 axis alignment loop (DRY-RUN ONLY: motion and acquisition are injected callables; nothing here touches hardware).

Geometry (user, 2026-10-27): the rotation axis is fixed by the base and does NOT move with samE.x/y/z; those move the pin
(sample) relative to the axis. Pin point at rotating-frame offset (a, b) from the axis, axis at image column c:
     x(w) = c + a cos w + b sin w          (pixels)
  =>  x(+t) - x(-t) = 2 b sin t            (a and c cancel)      -> b  (cancelled by z)
      x(+t) + x(-t) = 2 (c + a cos t),  x(0) = c + a  ->  a = (x(0) - s)/(1 - cos t)  (reliable only at large t) -> cancelled by x
After a, b -> 0 the pin sits on the axis and x(w) = c is constant; c is then moved onto the beam centre by the BASE motors
(not yet identified - base_move_mm() only reports the needed shift, it never moves anything).

Procedure: omega=0; (optional) x so the pin marker is at the beam centre; for theta in ANGLES_DEG: measure -theta/+theta,
z move from b; after the loop an x move from a (taken at the largest angle); report c and the base shift.
Constants (pixel size, signs) live in align_config.py.
"""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))  # python -I drops the script dir
import align_config as cfg  # noqa: E402

ANGLES_DEG = (1, 5, 10, 30, 60, 90)
A_MIN_DEG = 30        # smallest angle whose 'a' estimate is trusted
TOL_PX = 1.0


def estimate_ab(x0, x_plus, x_minus, theta_deg):
    t = np.deg2rad(theta_deg)
    b = (x_plus - x_minus) / (2 * np.sin(t))
    s = 0.5 * (x_plus + x_minus)
    a = (x0 - s) / (1 - np.cos(t)) if theta_deg >= A_MIN_DEG else np.nan
    return a, b


def base_move_mm(c_px, beam_cx_px):
    """Shift of the rotation axis needed to bring it onto the beam centre, in image columns -> mm. Motor/sign TBD (base stage)."""
    return cfg.px_to_mm(beam_cx_px - c_px)


def run(measure_x, move_x_mm, move_z_mm, goto_omega, beam_cx_px, angles=ANGLES_DEG, centre_first=True, log=print):
    """measure_x(): pin column at the current omega (px). move_x_mm/move_z_mm(d): relative pin moves. goto_omega(deg)."""
    goto_omega(0)
    x0 = measure_x()
    if centre_first:
        dx = cfg.px_to_mm((beam_cx_px - x0) / cfg.IMAGE_COL_PER_X)
        log(f"step 1: pin marker at col {x0:.1f} -> beam centre {beam_cx_px}: x move {dx:+.4f} mm")
        move_x_mm(dx)
    hist, prev_abs_b, a_last = [], None, np.nan
    for th in angles:
        goto_omega(-th); xm = measure_x()
        goto_omega(+th); xp = measure_x()
        goto_omega(0); x0 = measure_x()
        a, b = estimate_ab(x0, xp, xm, th)
        if prev_abs_b is not None and abs(b) > 1.5 * prev_abs_b + TOL_PX:
            log(f"STOP: |b| grew {prev_abs_b:.1f} -> {abs(b):.1f} px after the last z move; ROT_SIGN is probably wrong")
            return {"status": "sign_suspect", "hist": hist}
        dz = -cfg.ROT_SIGN * cfg.px_to_mm(b)
        log(f"theta=+-{th:>2}: x(0)={x0:8.2f} x(+)={xp:8.2f} x(-)={xm:8.2f} -> b={b:7.2f} px, a={a:7.2f} px => z move {dz:+.4f} mm")
        hist.append((th, a, b, dz))
        prev_abs_b = abs(b)
        if np.isfinite(a):
            a_last = a
        if abs(b) >= TOL_PX:
            move_z_mm(dz)
    out = {"status": "ok", "hist": hist}
    if np.isfinite(a_last) and abs(a_last) >= TOL_PX:
        dx = cfg.px_to_mm(a_last / cfg.IMAGE_COL_PER_X * -1)   # image column must change by -a
        log(f"pin offset a={a_last:.2f} px => x move {dx:+.4f} mm (puts the pin on the rotation axis)")
        move_x_mm(dx)
        out["x_move_mm"] = dx
    goto_omega(0)
    out["c_px"] = c_est = measure_x()
    out["base_move_mm"] = base_move_mm(c_est, beam_cx_px)
    log(f"pin now on axis: c={c_est:.2f} px; BASE shift to beam centre {beam_cx_px}: {out['base_move_mm']:+.4f} mm (base motor TBD, not moved)")
    return out


class SimPin:
    """Synthetic pin: x(w)=c+a cos w+b sin w. z changes b by k*dz; x changes a by IMAGE_COL_PER_X*dx (true signs adjustable)."""
    def __init__(self, c=818., a=-132., b=40., k_true=+1, xsign_true=cfg.IMAGE_COL_PER_X, noise=0.0, seed=0):
        self.c, self.a, self.b, self.k, self.xs, self.noise, self.w = c, a, b, k_true, xsign_true, noise, 0.0
        self.rng = np.random.default_rng(seed)
    def goto(self, deg): self.w = np.deg2rad(deg)
    def measure(self):
        return self.c + self.a * np.cos(self.w) + self.b * np.sin(self.w) + self.rng.normal(0, self.noise)
    def move_z(self, dz_mm): self.b += self.k * cfg.mm_to_px(dz_mm)
    def move_x(self, dx_mm): self.a += self.xs * cfg.mm_to_px(dx_mm)


if __name__ == "__main__":
    for kt, noise in ((+1, 0.0), (+1, 0.3), (-1, 0.0)):
        sim = SimPin(k_true=kt, noise=noise)
        print(f"--- simulated pin: true k={kt:+d}, noise={noise} px (ROT_SIGN assumed {cfg.ROT_SIGN:+d}), c=818, a=-132, b=40")
        res = run(sim.measure, sim.move_x, sim.move_z, sim.goto, beam_cx_px=959.5)
        print(f"status={res['status']}; true remaining a={sim.a:.2f} b={sim.b:.2f} px")
