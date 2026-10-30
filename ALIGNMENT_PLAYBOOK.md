# Stage-1 alignment playbook (for the agent: Claude Code, Codex, ...)

Goal: put the **pin on the rotation axis** (a, b → 0) and the **rotation axis on the beam centre** (c → beam centre).
Assumes the beam is already on the tomo detector (no slits / edge / flux, no wedge). Everything the user must see goes through the
CLI, which logs to `runs/<id>/events.jsonl`; the GUI (`python -I gui.py`, http://localhost:8765) follows it live.
**You make every decision; the tools never move or loop on their own** (except the explicit `sweep` and `calibrate` helpers).

**One folder per run:** everything for a run goes in `runs/<id>/` — the CLI auto-saves each command's JSON to `outputs/`, frames to `frames/`, raw
frames to `raw/`, figures to `figures/`, logs to `logs/`, reports to `report/`. Never write files to `runs/` itself, `/tmp`, or the repo root; redirect
any process log to `runs/<id>/logs/<name>.log` (get `<id>` from `new-run`).

## Standard beamline run
Trigger: the user says they are at the beamline and want the alignment started, e.g. *"start the beam alignment at beamline. You can access hardware."* That sentence authorises
connecting to the hardware and moving samE.x / y / z / aerox and rotating samE.ry within ±90° — **do not ask for confirmation**; only the equipment limits below apply. Then, in order:
1. **Camera.** Use the one the user named (gh1, pg1, pg5; hutch E/E/C). If none was named, use `DEFAULT_CAMERA` (`scripts/align_config.py`, gh1) and say so in your first note. The camera is assumed to be acquiring already.
2. **GUI.** If http://localhost:8765 does not answer, start it in the background: `nohup python -I gui.py > /dev/null 2>&1 &` (never write its log into `runs/`). Tell the user the URL.
3. **Run.** `python -I align.py new-run --backend epics --camera <camera>`, `note` the plan, then `python -I align.py adaptive-align`.
4. **If it stops (`ok: false`)**: read `reason`, `note` what happened, and try the matching remedy **once** — pin absent / other object / partly in view → `find-pin` then `adaptive-align` again; sign suspect or not
   converged → run `adaptive-align` once more. If it fails again, `finish --status failed --summary "<reason>"` and stop; tell the user what you saw and what you would try.
5. **Finish.** `finish --status ok --summary "<final a, b, c−beam in px and the motor positions>"` and report the same numbers to the user.
6. Everything for the run stays in `runs/<id>/` (the CLI does that; raw frames included). Don't write elsewhere.
Variations the user may add in words (e.g. "first move the pin 1 mm down", "only ±30°", "align on pg1") are applied on top of this; use the building blocks in *Commands* for them.
If the user does **not** say they are at the beamline, use the simulator (`new-run` without `--backend`).

## Hardware and safety
- Default backend is `sim`. When the user says they are on the real beamline and want to align on hardware, start with `new-run --backend epics --camera <gh1|pg1|pg5|...>`
  (the camera sets the pixel size; ask once only if the user has not said which) and run the alignment — no extra confirmation, no environment switch. Never connect to hardware
  unless the user says so.
- Equipment protection stays on (no prompts): per-step move limits (`MAX_STEP_PIN_MM`, `MAX_STEP_BASE_MM`; moves are split), motor soft limits, mm-units check, readback check, rotation within ±`MAX_ROT_DEG` (90°). Never try to bypass them.
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
| `adaptive-align [--step 15] [--max-passes 6]` | **the standard run**: ω→0, pin axis to the beam centre, then per pass rotate + until the pin can no longer be measured, rotate − likewise, fit c, a, b to all those points, correct z (b), x (a), aerox (c−beam), repeat; if a pass reaches ±90° on both sides later passes use only 0, +90, −90. Never beyond ±90°. Handles a pin that starts partly visible or absent (`find-pin`) |
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

## Procedure (no calibration — signs/scales are confirmed constants)
1. `new-run` (`--backend epics --camera <name>` on the real beamline, when the user says so; sim otherwise); `note` the plan.
2. `adaptive-align`. It does, by itself: ω→0 · bring the pin into view (`find-pin` / hint moves) · centre the pin axis on the beam centre (x) · pass 1: rotate +15° steps until the pin cannot
   be measured (if not even at 15°: retry with 7.5°, then 3.75°), then − likewise (a half-visible pin is located from its visible part and counts with weight 0.3) · fit x(ω)=c+a·cosω+b·sinω to every measurement · correct (z←b; x←a, only a fraction
   if the range is < 30°; aerox←c−beam only if the range ≥ 30°) · repeat. Done when |a|,|b| < `TOL_AB_PX` and |c−beam| < `TOL_C_PX`. It stops with a reason if a/b fail to shrink after a correction
   (sign suspect; the check allows for only part of a having been applied), if the pin leaves the view within the smallest step (3.75°), or after `--max-passes`. When the pin is measurable over only a few degrees the pass corrects z from b alone (small-angle mode) and the next pass has a larger range.
3. Result JSON: `passes` (limits ±, n points, a, b, c−beam, applied moves). If `ok` is false read `reason`, narrate it, `finish --status failed`. Otherwise `finish --status ok --summary "<final a, b, c−beam>"`.
Manual / diagnostic building blocks: `step-pm`, `fast-align` (fixed ±30 then ±90, assumes the pin is measurable there), `sweep`, `calibrate`, `propose`, `move`. `calibrate` is not part of a normal run.
Narrate with `note` before each decision.

## Reference run
`python -I tests/scripted_agent.py` is a scripted agent following exactly this procedure on the simulator (~10 s); `python -I tests/test_detection.py` (sim) `python -I tests/test_identity.py` (real frames in `s1_data/` + painted-in objects) and `python -I tests/test_partial.py` (real frames, pin moved half out of view, closed loop) check the detection logic; useful to see the expected event flow.
