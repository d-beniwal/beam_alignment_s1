"""REAL instrument backend (EPICS). *** DISABLED BY DEFAULT and never exercised from this project's development sessions. ***

It only constructs when ALL of these hold: environment BALIGN_ENABLE_HARDWARE=1, an explicit camera name from align_config.CAMERAS,
and pvapy + pyepics importable. Nothing here is run by tests. Safety layers: motor units must read back as mm, per-move soft-limit
check against .LLM/.HLM, per-step limits are enforced upstream in cli.do_move, readback verification after every move, no writes
to camera/IOC PVs (acquisition is read-only: it only reads frames from the existing PVA stream).

Camera must already be acquiring continuously (the IOC is NOT touched); after each motion we discard frames until `settle_frames`
new unique ids have arrived so the returned frame is taken after the stage stopped."""
import os
import time
import numpy as np
import align_config as cfg


class EpicsInstrument:
    name = "epics"

    def __init__(self, state=None, camera=None, settle_frames=2):
        if os.environ.get("BALIGN_ENABLE_HARDWARE") != "1":
            raise PermissionError("hardware backend disabled: set BALIGN_ENABLE_HARDWARE=1 only after the user has reviewed and approved this backend")
        if camera not in cfg.CAMERAS:
            raise ValueError(f"camera must be one of {sorted(cfg.CAMERAS)}")
        import epics                      # pyepics
        import pvapy as pva
        from pvapy.utility.adImageUtility import AdImageUtility
        self._epics, self._pva, self._util = epics, pva, AdImageUtility
        self.s = state or {"camera": camera, "n_acq": 0}
        self.s["camera"] = camera
        self.camera_pv = cfg.CAMERAS[camera] + cfg.CAMERA_PVA_SUFFIX
        self._chan = pva.Channel(self.camera_pv)
        self._req = "field(value,dimension,uniqueId,attribute,codec,uncompressedSize)"
        self.settle_frames = settle_frames
        self._motors = {k: epics.Motor(v) for k, v in cfg.MOTOR_PVS.items()}
        for k, m in self._motors.items():             # fail early if any PV is unreachable
            if m.get("RBV") is None:
                raise ConnectionError(f"motor {k} ({cfg.MOTOR_PVS[k]}) not reachable")

    def get_state(self): return self.s
    def get_omega(self): return float(self._motors["omega"].get("RBV"))
    def positions(self): return {k: float(m.get("RBV")) for k, m in self._motors.items()}

    def _check_done(self, motor, target, tol):
        m = self._motors[motor]
        t0 = time.time()
        while time.time() - t0 < cfg.MOVE_TIMEOUT_S:
            if m.get("DMOV") == 1:
                break
            time.sleep(0.05)
        rbv = float(m.get("RBV"))
        if abs(rbv - target) > tol:
            raise RuntimeError(f"{motor} readback {rbv} != target {target} (tol {tol})")

    def move_omega(self, deg):
        m = self._motors["omega"]
        m.move(float(deg), wait=True, ignore_limits=False, timeout=cfg.MOVE_TIMEOUT_S)
        self._check_done("omega", float(deg), cfg.OMEGA_TOL_DEG)

    def move(self, motor, mm):
        if motor not in ("x", "y", "z", "aerox"):
            raise ValueError(motor)
        m = self._motors[motor]
        egu = str(m.get("EGU") or "").strip().lower()
        if egu not in ("mm",):
            raise RuntimeError(f"{motor} units are '{egu}', expected mm - refusing to move")
        target = float(m.get("RBV")) + mm
        lo, hi = float(m.get("LLM") or 0), float(m.get("HLM") or 0)
        if hi > lo and not (lo <= target <= hi):
            raise RuntimeError(f"{motor} target {target} outside soft limits [{lo},{hi}]")
        m.move(target, wait=True, ignore_limits=False, timeout=cfg.MOVE_TIMEOUT_S)
        self._check_done(motor, target, max(0.002, abs(mm) * 0.05))

    # -- read-only imaging ------------------------------------------------------------------------------------------------
    def _grab(self):
        pv = self._chan.get(self._req)
        uid, img, *_ = self._util.reshapeNtNdArray(pv)
        return int(uid), img

    def acquire(self):
        uid0, _ = self._grab()
        t0 = time.time()
        while True:
            uid, img = self._grab()
            if uid >= uid0 + self.settle_frames and img is not None:
                break
            if time.time() - t0 > 30:
                raise TimeoutError("no new frames on " + self.camera_pv + " (is the camera acquiring?)")
            time.sleep(0.1)
        self.s["n_acq"] += 1
        return np.asarray(img)

    def grab_latest(self):
        """For the live view: one frame, no waiting."""
        return np.asarray(self._grab()[1])
