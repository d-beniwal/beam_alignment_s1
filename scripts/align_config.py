"""Single place for alignment constants. Everything else imports from here - never redefine them elsewhere."""

# Tomo detectors (user, 2026-10-28): hutch + pixel size (um/px). `PIXEL_UM` is the ACTIVE camera's value; call set_camera(name) to switch
# (balign.session.Run does this from the run's stored camera). With no camera chosen (sim default) it stays at DEFAULT_PIXEL_UM.
# gh1: the user said "69 micron" - taken as 0.69 um/px (high-res table); matches the ~0.69 inferred from the 2026-10-28 live calibration moves.
CAMERA_INFO = {
    "retiga2": {"hutch": "B", "pixel_um": 1.0},
    "pg5":     {"hutch": "C", "pixel_um": 1.17},
    "gh1":     {"hutch": "E", "pixel_um": 0.69, "note": "high-res table"},
    "pg1":     {"hutch": "E", "pixel_um": 1.17, "note": "close to back wall"},
}
DEFAULT_PIXEL_UM = 1.0
PIXEL_UM = DEFAULT_PIXEL_UM
CAMERA = None


def set_camera(name):
    """Select the active tomo camera: sets PIXEL_UM (module attribute - always read it as cfg.PIXEL_UM, never `from ... import`)."""
    global PIXEL_UM, CAMERA
    if name is None:
        CAMERA, PIXEL_UM = None, DEFAULT_PIXEL_UM
        return PIXEL_UM
    if name not in CAMERA_INFO:
        raise ValueError(f"unknown camera '{name}'; choose from {sorted(CAMERA_INFO)}")
    CAMERA, PIXEL_UM = name, CAMERA_INFO[name]["pixel_um"]
    return PIXEL_UM

# Sign links. Both confirmed by the user 2026-10-28 (not yet verified by a hardware test move; `calibrate` still measures them at run time).
IMAGE_COL_PER_X = -1   # +samE.x moves the pin image LEFT, i.e. its column decreases (user, confirmed 2026-10-28)
# k: sign of the b (sin w) change per +samE.z move. Derived from: stage is left-handed (+omega = clockwise seen from the top), x = left looking
# downstream, y up, z downstream. Clockwise = rotation by -omega about +y, so x' = x cos w - z sin w, col = c - x' => a = -x_p, b = +z_p => k = +1.
# (A counter-clockwise +omega would give k = -1.) A wrong value is caught by axis_align.run() / `calibrate`.
ROT_SIGN = +1


def px_to_mm(px, pixel_um=None):
    return px * (PIXEL_UM if pixel_um is None else pixel_um) * 1e-3


def mm_to_px(mm, pixel_um=None):
    return mm * 1e3 / (PIXEL_UM if pixel_um is None else pixel_um)

# ---- run-time limits and unknowns for the agent-driven pipeline (balign) -------------------------------------------
MAX_STEP_PIN_MM = 0.5      # largest single samE.x/y/z move the CLI will accept
MAX_STEP_BASE_MM = 0.3     # largest single base (aerox) move the CLI will accept
BASE_MOTOR = "aerox"       # base motor that moves the rotation axis (samE.aerox, 1ide1:m101) - confirmed by the user 2026-10-28; sign still learned by `calibrate`
BASE_COL_PER_AEROX = -1    # +samE.aerox moves the axis image column DOWN (c decreases). Hardware-measured 2026-10-28: d_c/d_aerox = -1431 px/mm on gh1 (0.69 um/px).
IMAGE_ROW_PER_Y = -1       # +samE.y moves the pin UP in real space and in the image (row decreases). Confirmed by the user 2026-10-28 (hardware test). Used by `find-pin`.
# ---- pin shape priors / validity (learned per run where possible) -----------------------------------------------------------
NOMINAL_HALF_ANGLE_DEG = 15.2   # cone half-angle of the alignment pin (files 44/46 fits + 2026-10-28 frames)
HALF_ANGLE_TOL_DEG = 3.0        # a side line whose slope is further than this from nominal is not the pin flank (e.g. the grey bevel wedge at +-90)
PIN_MIN_CONTRAST = 0.5          # (beam - pin)/beam inside the dark object; below this the 'object' is just beam structure -> pin ABSENT (real empty frame: 0.07)
TOP_WIDTH_TOL = 0.30            # a both-flank candidate whose top width differs from the width learned in this run by more than this is another object
CLIP_MARGIN_PX = 30             # pin corners / flanks must be this far inside the lit footprint to be trusted
# ---- fast workflow ---------------------------------------------------------------------------------------------------------
FAST_STEPS_DEG = (30, 90)       # `fast-align`: first coarse (+-30), then fine (+-90)
SAVE_RAW = True                 # keep every acquired frame (runs/<id>/raw/*.npz) so detection can be debugged/re-run offline
# ---- pin search (`find-pin`) -----------------------------------------------------------------------------------------------
SEARCH_RADIUS_X_MM = 3.0        # farthest the search will move the pin horizontally from where it started
SEARCH_RADIUS_Y_MM = 2.0
SEARCH_STEP_FRAC = 0.5          # search step = this fraction of the lit-footprint size (so consecutive views overlap)
BEAM_FRAC = 0.5            # footprint level that defines the beam centre (half-maximum, user decision)
TOL_AB_PX = 1.0            # pin-on-axis tolerance for a, b (px)
TOL_C_PX = 2.0             # axis-on-beam-centre tolerance (px)
DEFAULT_SWEEP_DEG = (-90, -60, -30, 0, 30, 60, 90)

# ---- real-instrument wiring (used by the epics backend only, see balign/epics_backend.py) -----------------
# Tomo cameras of the 1-ID-E profile (midas-gui settings.py BUNDLED_PROFILES): PVA image PV = <prefix>Pva1:Image.
# retiga2 (B hutch) has no PV prefix recorded yet -> the epics backend refuses it until one is added here.
CAMERAS = {"gh1": "1idGH1:", "pg1": "1idPG1:", "pg5": "1idSP5:"}
CAMERA_PVA_SUFFIX = "Pva1:Image"
# Motor records (from mpe_bluesky s1ide_motors.py, see DOMAIN.md). Units must read back as mm (checked before any move).
MOTOR_PVS = {"omega": "1ide:m9", "x": "1ide1:m34", "y": "1ide1:m35", "z": "1ide1:m36", "aerox": "1ide1:m101"}
OMEGA_TOL_DEG = 0.05
MAX_ROT_DEG = 90.0          # beam alignment never rotates beyond +-90 deg (goto_omega refuses)
MOVE_TIMEOUT_S = 60.0
