"""Single place for alignment constants. Everything else imports from here - never redefine them elsewhere."""

# Tomo detector pixel size (um/pixel). Confirmed by the user 2026-10-27 (1 um/px).
PIXEL_UM = 1.0

# Sign links - UNVERIFIED, to be confirmed with a small user-approved test move.
IMAGE_COL_PER_X = -1   # +samE.x moves the pin image LEFT, i.e. its column decreases (user, 2026-10-27)
ROT_SIGN = +1          # k: sign of the b (sin w) change per +samE.z move; wrong value is caught by axis_align.run()


def px_to_mm(px, pixel_um=None):
    return px * (PIXEL_UM if pixel_um is None else pixel_um) * 1e-3


def mm_to_px(mm, pixel_um=None):
    return mm * 1e3 / (PIXEL_UM if pixel_um is None else pixel_um)

# ---- run-time limits and unknowns for the agent-driven pipeline (balign) -------------------------------------------
MAX_STEP_PIN_MM = 0.5      # largest single samE.x/y/z move the CLI will accept
MAX_STEP_BASE_MM = 0.3     # largest single base (aerox) move the CLI will accept
BASE_MOTOR = "aerox"       # CANDIDATE base motor that moves the rotation axis (samE.aerox, 1ide1:m101) - not confirmed
BASE_COL_PER_AEROX = None  # sign/size of image-column change per +aerox mm: UNKNOWN, must be learned with `calibrate`
BEAM_FRAC = 0.5            # footprint level that defines the beam centre (half-maximum, user decision)
TOL_AB_PX = 1.0            # pin-on-axis tolerance for a, b (px)
TOL_C_PX = 2.0             # axis-on-beam-centre tolerance (px)
DEFAULT_SWEEP_DEG = (-90, -60, -30, 0, 30, 60, 90)

# ---- real-instrument wiring (NOT used by the simulator; the epics backend is gated, see balign/epics_backend.py) -----------------
# Tomo cameras of the 1-ID-E profile (midas-gui settings.py BUNDLED_PROFILES): PVA image PV = <prefix>Pva1:Image.
CAMERAS = {"gh1": "1idGH1:", "pg1": "1idPG1:", "pg5": "1idSP5:"}
CAMERA_PVA_SUFFIX = "Pva1:Image"
# Motor records (from mpe_bluesky s1ide_motors.py, see DOMAIN.md). Units must read back as mm (checked before any move).
MOTOR_PVS = {"omega": "1ide:m9", "x": "1ide1:m34", "y": "1ide1:m35", "z": "1ide1:m36", "aerox": "1ide1:m101"}
OMEGA_TOL_DEG = 0.05
MOVE_TIMEOUT_S = 60.0
