"""Simulated instrument: renders tomo frames (beam + dark trapezoid pin) like the real 1490x1940 uint16 frames, with a hidden
ground truth (axis column c, pin offsets a, b) that the motors change. No hardware, no EPICS."""
import numpy as np
from scipy.special import erf, expit
import align_config as cfg

H, W = 1490, 1940
BEAM_BOX = (457, 1488, 347, 1157)   # x0, x1, y0, y1 of the lit area (from real frames)
BG, PLATEAU, PIN_T = 5400.0, 12000.0, 0.045
TOP_ROW, TOP_W, HALF_ANGLE = 477.0, 151.5, 15.0


class SimInstrument:
    """State is a plain dict so it can be persisted between CLI calls."""
    name = "sim"

    def __init__(self, state=None, seed=0):
        self.s = state or {
            "omega": 0.0, "c": 818.0, "a": -132.0, "b": -10.0,
            "pos": {"x": 0.0, "y": 0.0, "z": 0.0, "aerox": 0.0},
            # hidden truth the agent must discover (can be flipped to test the sign guards)
            "true_col_per_x": -1.0, "true_k_z": +1.0, "true_col_per_aerox": +1.0,
            "noise": 1.0, "timing_lag_deg": 0.0, "seed": seed, "n_acq": 0,
        }

    # -- state -------------------------------------------------------------------------------------------------------
    def get_state(self): return self.s
    def get_omega(self): return self.s["omega"]
    def positions(self): return {"omega": self.s["omega"], **self.s["pos"]}

    def move_omega(self, deg):
        self.s["omega"] = float(deg)

    def move(self, motor, mm):
        s = self.s
        px = cfg.mm_to_px(mm)
        if motor == "x":   s["a"] += s["true_col_per_x"] * px
        elif motor == "z": s["b"] += s["true_k_z"] * px
        elif motor == "aerox": s["c"] += s["true_col_per_aerox"] * px
        elif motor == "y": pass
        else: raise ValueError(f"unknown motor {motor}")
        s["pos"][motor] += mm

    # -- truth (for tests only) --------------------------------------------------------------------------------------
    def true_pin_col(self, omega=None):
        w = np.radians(self.s["omega"] if omega is None else omega)
        return self.s["c"] + self.s["a"] * np.cos(w) + self.s["b"] * np.sin(w)

    def true_beam_centre(self):
        return ((BEAM_BOX[0] + BEAM_BOX[1]) / 2, (BEAM_BOX[2] + BEAM_BOX[3]) / 2)

    # -- imaging -----------------------------------------------------------------------------------------------------
    def acquire(self):
        s = self.s
        rng = np.random.default_rng(s["seed"] + s["n_acq"])
        s["n_acq"] += 1
        x0, x1, y0, y1 = BEAM_BOX
        cols = np.arange(W)[None, :]
        rows = np.arange(H)[:, None]
        edge = 22.0
        bx = 0.5 * (erf((cols - x0) / edge) - erf((cols - x1) / edge))
        by = 0.5 * (erf((rows - y0) / edge) - erf((rows - y1) / edge))
        mod = 1 + 0.12 * np.sin(cols / 140.0 + 1.0) * np.cos(rows / 190.0) + 0.25 * np.exp(-(((cols - 900) / 230.0) ** 2 + ((rows - 700) / 260.0) ** 2))
        beam = PLATEAU * bx * by * mod
        xc = self.true_pin_col(s["omega"] + s["timing_lag_deg"])
        half = TOP_W / 2 + np.clip(rows - TOP_ROW, 0, None) * np.tan(np.radians(HALF_ANGLE))
        inside = expit((half - np.abs(cols - xc)) / 1.2) * expit((rows - TOP_ROW) / 1.2)
        img = BG + beam * (1 - (1 - PIN_T) * inside)
        img = img + rng.normal(0, s["noise"] * np.sqrt(np.maximum(img, 1)) * 0.6)
        return np.clip(img, 0, 65535).astype(np.uint16)
