# Stage-1 alignment playbook (for the agent: Claude Code, Codex, ...)

Goal: put the **pin on the rotation axis** (a, b → 0) and the **rotation axis on the beam centre** (c → beam centre).
Assumes the beam is already on the tomo detector (no slits / edge / flux, no wedge). Everything the user must see goes through the
CLI, which logs to `runs/<id>/events.jsonl`; the GUI (`python -I gui.py`, http://localhost:8765) follows it live.
**You make every decision; the tools never move or loop on their own** (except the explicit `sweep` and `calibrate` helpers).

**One folder per run:** everything for a run goes in `runs/<id>/` — the CLI auto-saves each command's JSON to `outputs/`, frames to `frames/`, raw
frames to `raw/`, figures to `figures/`, logs to `logs/`, reports to `report/`. Never write files to `runs/` itself, `/tmp`, or the repo root; redirect
any process log to `runs/<id>/logs/<name>.log` (get `<id>` from `new-run`).

## Safety (absolute)
- Use `--backend sim`. A real `epics` backend exists (`balign/epics_backend.py`) but is gated (needs `BALIGN_ENABLE_HARDWARE=1` + `--camera`) and must only be enabled by the user after review; never set that variable yourself. Never run
  anything that touches EPICS / the beamline. If asked to "start the alignment" on the real instrument, say it is not enabled yet.
- Per-step move limits are enforced (`MAX_STEP_PIN_MM`, `MAX_STEP_BASE_MM` in `scripts/align_config.py`); never try to bypass them — split moves.
- Pixel size (`PIXEL_UM`) and sign constants live **only** in `scripts/align_config.py`. Never hard-code them.
- Narrate with `note` before each decision (what you saw, what you will do, why). The user watches the GUI, not your terminal.

## Commands (`python -I align.py <cmd>`; each prints JSON)
| cmd | what it does |
|---|---|
| `new-run [--backend sim] [--truth JSON]` | start a run (the GUI switches to it) |
| `status` | positions, last fit, calibrations |
| `goto-omega DEG` / `measure [--omega DEG]` | rotate / acquire + pin + beam measurement (overlay image to the GUI) |
| `sweep [--angles ...]` | measure at several omegas (default −90…90 step 30) and fit `x(ω)=c+a·cosω+b·sinω`; reports tolerances |
| `step-pm THETA [--apply] [--base]` | **fast step**: measure 0, ±THETA (one monotonic rotation) → a, b, c; `--apply` moves z (b), x (a, THETA ≥ 30) and with `--base` aerox (c → beam centre) |
| `fast-align [--no-verify]` | the whole quick routine: `step-pm 30 --apply`, `step-pm 90 --apply --base`, then a verify `step-pm 90` (≈ 3 short rotations, ~1–2 min on hardware) |
| `find-pin [--max-steps N] [--no-y]` | pin out of view/partly visible: follows the hint or searches x (then y) outward in footprint-sized steps within `SEARCH_RADIUS_*`; returns to the start if not found. **Moves stages** |
| `estimate-pm THETA` | measure at 0, ±THETA; b = (x₊−x₋)/(2 sin θ); a only for θ ≥ 30 |
| `calibrate --motor M --mm D` | small test move (then undone): learns d(a,b,c)/mm, checks it against the pixel size |
| `propose` | moves that would cancel a, b and bring c onto the beam centre (**does not move**) |
| `move MOTOR MM --reason "…"` | the only command that moves a stage (motors: x, y, z, aerox) |
| `live-feed [--interval 1]` | (separate process) keeps `live.jpg` fresh for the GUI's live panel; read-only |
| `note "…"` / `finish --status ok\|failed --summary "…"` | narration / close the run |

## Model (what the numbers mean)
Pin column vs rotation angle: `x(ω) = c + a·cos ω + b·sin ω` (px). `c` = rotation-axis column (fixed by the base; **samE.x/y/z do not change it**),
`a` = pin offset along image-x at ω=0 (cancelled by **samE.x**), `b` = pin offset along the beam (cancelled by **samE.z**). The base motor
(`aerox`, confirmed, −1 px per µm-pixel direction) moves `c` (and the pin with it). Tolerances: |a|,|b| < `TOL_AB_PX`, |c − beam centre| < `TOL_C_PX`.
Beam centre = midpoint of the half-maximum footprint (median over the sweep frames).

## Detection (what `measure` tells you)
Every measurement has `view.state`: **in_view** (usable), **partial** (pin seen but cut off / edges unreliable; `view.hint` = the x/y move that centres it, `view.locate` = estimated axis column and top row from the visible part),
**absent** (no dark pin-sized object inside the lit footprint), **other_object** (a dark object is in view but it is not cone-shaped like the pin — e.g. the holder; treated like absent by `find-pin`), **no_beam** (no lit footprint). The *field of view is the lit footprint*, not the sensor.
`pin_col` is only set for **usable** frames (`quality`: `both_flanks`, or `one_sided_left/right` when one flank was the grey bevel wedge at large |ω| and the other
flank + the learned top width were used). Rejected frames carry `reasons`; never use their `pin_col_raw`. The beam centre ignores the pin shadow.
The pin's top width is learned from the first both-flank frames (so measure ω=0 first, or let `step-pm` do it). Raw frames are in `runs/<id>/raw/*.npz`.

## Procedure (fast; no calibration — signs/scales are confirmed constants)
1. `new-run --camera <name>` (sets the pixel size); `note` the plan. `measure --omega 0`. If `view.state != in_view` → `find-pin`; if it fails, `finish --status failed` and report.
2. `fast-align`. It stops with a reason + `suggest` if the pin is not usable at ±θ (e.g. runs into the lit-area edge → try `step-pm 60 --apply --base`, or `find-pin` first).
   Equivalent manual form: `step-pm 30 --apply` → `step-pm 90 --apply --base` → `step-pm 90` (verify). If |b| fails to shrink after a z move it refuses to move again (sign suspect).
3. Done when the verify step reports `converged` (|a|,|b| < `TOL_AB_PX`, |c − beam| < `TOL_C_PX`). If not, repeat `step-pm 90 --apply --base` once more; then `finish`.
4. `finish --status ok --summary "<final a, b, c−beam>"`. On any stop condition, `finish --status failed` with the reason and what you would try next.
`sweep`/`calibrate`/`propose`/`move` remain for diagnosis (e.g. a suspected sign problem); `calibrate` is **not** part of the normal run. Narrate with `note` before each decision.

## Reference run
`python -I tests/scripted_agent.py` is a scripted agent following exactly this procedure on the simulator (~10 s); `python -I tests/test_detection.py` (sim) `python -I tests/test_identity.py` (real frames in `s1_data/` + painted-in objects) and `python -I tests/test_partial.py` (real frames, pin moved half out of view, closed loop) check the detection logic; useful to see the expected event flow.
