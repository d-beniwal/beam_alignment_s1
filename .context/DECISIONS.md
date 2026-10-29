# Decisions

Add new decisions at the top using:

## YYYY-MM-DD — Short title

What was decided and why.

## 2026-10-28 — Partly visible pin: locate it and compute the move (user request)

When the pin is half cut off (lit-footprint rim) or its top is above / body barely above the footprint, `measure.locate_partial` finds it from the dark object's per-row extents and the cone model
(width(y) = W + 2 t (y - y_top), W and t learned in the run): rows touching a rim give c = free_edge -/+ width/2, free rows give (l+r)/2, a cut-off top is found from the widths of free rows.
The hint is then exact: x move to put the pin axis on the beam centre, y move to put the top at 20 % of the footprint height (`view.hint` + `view.locate`). Without a learned width it falls back to
pinfit's (lower-bound) shift + 15 % of the footprint (converges in 1-2 moves in tests). Supporting fixes found on real frames: pinfit's search box is ~40 px wider than the real lit rim, so rows
touching the real rim were treated as unclipped and fed wrong flank fits (probably a cause of the earlier bad detections) -> `Params.lit_box`/`rim_guard_px` (rims from the robust footprint + 36 px);
beam footprint now also uses the dark-object mask (works with a partial pin) and a footprint learned from clean frames (`beam_prior`); clipped flanks are no longer taken as evidence of 'other object'.
Test (`tests/test_partial.py`, real frames, pin shadow moved relative to the fixed footprint): axis estimated within ~1-5 px when >= ~half visible (worse with a sliver left), suggested move within ~10-70 px
of the centring move, and applying it brings the pin to usable in_view with column error < 1.5 px in every case (half cut left/right at 3 depths, top 60/200/350 px above, combined cut + top above, 4 frames).
Not tested: pin bottom stub only (works as in_view), holder in the same frame as a partial pin, real (not emulated) moves.

## 2026-10-28 — Pin identity check + multi-blob selection (user request: holder / other objects in view)

`pinfit` now considers every dark object of pin-like size and picks the cone-like one (width vs row linear with slope ~2*tan(15.2 deg)=0.544, rel. scatter <6 %, slope tol 15 %), not the biggest; each
object's shape stats (`cone_slope`, `cone_rel_rms`, `cone_like`, `cone_top_width`, `n_candidates`) are exposed. Tolerances set from real pin frames (files 44/46/47: slope 0.531-0.543, scatter <1.1 %, top width 144-152 px).
`measure` adds `identity` and a new view state `other_object` (a dark object that is not the pin; top width vs the width learned in this run, both flanks off-angle, or not cone-like); `find-pin` treats it like absent.
Validated on REAL frames with synthetic objects painted in (`tests/test_identity.py`; empty beam = real frame with the pin inpainted, contrast 0.08 like a real empty frame): pin picked among 3-5 other objects with
0.04 px error; plain / flared / narrow / short holders and an empty beam are never reported as the pin; real frames from 44/46/47 unchanged. NOT validated: a real holder (shape unknown), real wedge frames
(raw not saved yet), and a pin merged with a much wider holder under it beyond the simple block cases. Without a learned pin width (first frame of a run) the width test is skipped, so measure omega=0 first.

## 2026-10-28 — Post-beamline-test overhaul: detection guards, fast workflow, pin search (user feedback)

Feedback from the first live runs (`runs/20261028-103726`, `-112616`): hardware link fine, corrections correct, but (1) pin-edge detection failed at some positions, (2) the procedure
(calibrate x/z/aerox with 7-angle sweeps, many full rotations) was slow whereas "rotate to +-30 -> correct -> +-90 -> correct" was fast, (3) need pin-in-view detection + search.
Diagnosis from the saved overlay JPEGs (raw frames were NOT saved, so this is from overlays): (a) the "beam centre" (half-max box of whole-row/column means) was dragged by up to ~150 px by
an off-centre pin shadow (beam cx 1474-1828 vs 1615); (b) at |omega| ~ 60-90 the pin has a grey half-transparent flank (bevel) and pinfit fitted that boundary (near-vertical or wrong-slope side line),
yet reported status ok; (c) the "pin NOT measured (low_contrast)" frame was a genuinely empty beam (pin out of view), only mislabelled.
Changes: `measure.beam_footprint` (pin-excluded footprint: columns from rows above the pin top, rows from columns outside the pin; coarse p90 fallback); `_validate` accepts a frame only if both flanks have the
nominal half-angle (15.2 +- 3 deg), are not inferred, and corners are >= 30 px inside the footprint; if one flank is bad, the axis comes from the good corner +- half of the top width learned in this run
(`one_sided_*`); otherwise the frame is rejected with reasons, never guessed. `assess_view` = in_view | partial (+x/y hint) | absent (dark object contrast < 0.5) | no_beam; FOV = the lit footprint.
Raw frames are now saved per measurement (`runs/<id>/raw/*.npz`) so detection can be re-run offline. Workflow: `step-pm THETA [--apply] [--base]` and `fast-align` (+-30 -> +-90 -> verify), no calibration
(signs/scales confirmed: aerox -1431 px/mm measured today => BASE_COL_PER_AEROX = -1; z +1456, x -1458); per-move limit still enforced by splitting; sign-suspect guard if |b| fails to shrink after a z move.
`find-pin`: follows the hint when the pin is partly visible, else searches x then y outward in footprint-sized steps within SEARCH_RADIUS_X/Y_MM, returns to start if not found. y sign (IMAGE_ROW_PER_Y = -1: +y moves the pin up) was assumed, then
confirmed by the user from a hardware test the same day. Caveat: the grey-wedge rescue and thresholds are validated only on a simulated wedge (sim/tests), not yet on raw real frames.

## 2026-10-28 — One self-contained folder per run (user)

Stray files (CLI JSON redirected by the agent, gui/live-feed/test logs, figures) were piling up in `runs/` itself. Now everything for a run lives in `runs/<id>/`: `events.jsonl`, `state.json`,
`frames/`, plus `outputs/` (every CLI command's JSON is auto-saved by `cli._out` as `NNN_<cmd>.json`), `raw/` (.npy frames), `figures/`, `logs/`, `report/`. Helpers `Run.subdir()` / `Run.save_output()`
(plain folder names only). `scripts/grab_frame.py CAMERA [NAME]` and `scripts/save_beam_figure.py FRAME NAME` now write inside the current run; `tests/scripted_agent.py` logs to `logs/`; playbook tells agents
never to write into `runs/` itself. Only `runs/CURRENT` (pointer) remains at the top level. Legacy loose files from the two 2026-10-28 live runs were left untouched (not mapped to a run).

## 2026-10-28 — Per-camera pixel size; `samE.aerox` confirmed as base motor (user)

User: `samE.aerox` is the base motor that puts the pin axis on the beam centre. Tomo cameras: retiga2 (B hutch, 1 um/px), pg5 (C, 1.17), gh1 (E, high-res table, "69 micron" -> taken as
0.69 um/px: typo-by-factor-100 assumption, consistent with the ~0.69 inferred from the live calibration moves), pg1 (E, near back wall, 1.17). `scripts/align_config.py` now has `CAMERA_INFO`
+ `set_camera()`; `PIXEL_UM` is the active camera's value (default 1.0 with no camera). `Run` stores the camera in `state.inst.camera` and calls `set_camera` on load; `new-run --camera X` rejects
unknown names; GUI config follows the run's camera. retiga2 has no PV prefix yet, so the epics backend still refuses it. Sim test (`tests/scripted_agent.py`) passes.

## 2026-10-28 — Sign constants confirmed by the user: IMAGE_COL_PER_X=-1, ROT_SIGN=+1

User confirmed IMAGE_COL_PER_X = -1 and stated the Sector 1 stage is left-handed (+omega = clockwise seen from the top). Derivation: lab x = left, y = up, z = downstream
(right-handed); clockwise = rotation by -omega about +y, x' = x cos w - z sin w, image col = c - x' => a = -x_p, b = +z_p, so +z changes b by +1 per unit: ROT_SIGN = +1
(unchanged value; comment in `scripts/align_config.py` now records the derivation). Still not hardware-verified: `calibrate` measures both at run time; the base motor
(`aerox`) sign and identity remain open.

## 2026-10-28 — .gitignore: only the alignment software is tracked (user)

Ignored: `s1_data/`, `analysis/`, `runs/`, `scratch/`, caches, and the exploration/analysis scripts (h5_tree, make_*_figures, pin_segment, test_segmentation,
test_pinfit_*, test_axis_align_scan) - verified that nothing in `align.py`, `gui.py`, `balign/` or the core scripts (`align_config`, `axis_align`, `beam_center`, `pinfit`)
imports them. Tracked: code above + `tests/scripted_agent.py`, `environment.yml`, `AGENTS.md`, `ALIGNMENT_PLAYBOOK.md`, `.context/`. Caveat: the ignored scripts are then NOT
backed up by git (only matters once this becomes a repo); drop their lines from `.gitignore` if that is unwanted.

## 2026-10-27 — GUI redesigned around answers, not events

The first GUI showed every event with equal weight. New layout: header (run, status, live stage positions), 6-step progress tracker (derived from events; a step is
done only when a sweep taken after the last move confirms it), "Agent says" (last agent note), three plain-language verdict tiles (a, b, c-beam: value, pass/fail
vs tolerance, start value, history sparkline), a stale-data warning when a move came after the last fit, camera tab (last measurement with legend / live view),
pin-position plot with a plain-English caption, moves table (calibration test moves greyed), agent notes, and the raw event log collapsed. Calibration sweeps are
excluded from tiles/plot/progress. Still read-only; same event-log API.

## 2026-10-27 — Real backend written but gated; live view = separate read-only feed process

`balign/epics_backend.py` implements the instrument over pvapy (camera frames, read-only) + pyepics motor records (omega 1ide:m9, x/y/z 1ide1:m34/35/36, aerox m101), copying
midas-gui's PVA reading. It refuses to construct unless BALIGN_ENABLE_HARDWARE=1 and an explicit camera is given, checks motor units (mm), soft limits and readbacks, never
writes to camera/IOC PVs, and has NEVER been run (project rule: no hardware from development sessions). The GUI live view = `align.py live-feed` writing runs/<id>/live.jpg
(~1 Hz) that the page polls; calculations still come from the event log. Not decided by the user yet: camera (gh1/pg1/pg5).

## 2026-10-27 — Phase-1 software architecture: agent-driven CLI + passive web GUI + simulated backend

The user starts the alignment from Claude Code / Codex ("start the alignment") and wants full visibility in a GUI, with all decisions made by the agent.
So: (1) `align.py` = a small JSON CLI of primitives (measure, sweep+fit, calibrate, propose, move, note, finish) - the agent calls them and decides;
agent-neutral because it is plain commands (no MCP needed yet); `ALIGNMENT_PLAYBOOK.md` is the procedure/decision rules. (2) Every command appends to
`runs/<id>/events.jsonl` (+ overlay JPEGs); `gui.py` is a read-only stdlib web server that tails it (camera view with detections, x(omega) plot with fit,
convergence table, moves, event log incl. agent notes). File-based event log (not a socket) so CLI calls stay independent processes and the GUI/agent can restart.
(3) Backend is simulated only (`balign/sim.py` renders 1490x1940 frames like the real ones with hidden ground truth); the real backend is deliberately not
implemented - `get_backend` refuses anything else - until the user enables hardware. (4) Unverified signs/sizes are learned at run time by `calibrate`
(small undone test moves) instead of trusted from config; `propose` prefers calibrations. (5) Per-step move limits in config. (6) Sweep fit of
x(omega)=c+a cos+b sin replaces the sequential +-theta loop as the main estimator (robust, one equation); `estimate-pm` kept for the user's original small-angle scheme.
Results on the simulator: full run converges to a,b<0.03 px and c-beam<0.01 px; with all hidden signs flipped the calibration step handles it (see STATE).

## 2026-10-27 — Prior work reviewed; our model matches theirs (no change of method)

`auto_beamline_alignment_tomo` (Hemant Sharma et al., SAM + sinusoid fit) fits off + rad*sin(theta+st) and moves x by rad*sin(st), z by -rad*cos(st),
aerox by (off - beam centre). Algebraically identical to our (c, a, b) and the same signs (IMAGE_COL_PER_X=-1, ROT_SIGN=+1), which raises confidence in
those signs but is not hardware verification. We keep classical segmentation + the +-theta loop, adopt their global fit as a final check, treat `samE.aerox`
as the candidate base motor, and do not copy their beam-width-as-centre bug. Details in `.context/REFERENCE_prior_work.md`.

## 2026-10-27 — Axis fixed by base; pixel size 1 um in one config place; loop extended (user)

Rotation axis is fixed by the base, samE.x/y/z only move the pin. So the loop (1) puts the pin marker at the beam centre, (2) cancels b with
z at +-1..90 deg, (3) cancels a with x using the >=30 deg estimate, (4) reports c (now the pin column at any omega) and the base shift needed to
bring c to the beam centre - report only, base motors TBD. Pixel size 1 um/px confirmed; `scripts/align_config.py` holds PIXEL_UM and the sign
constants (IMAGE_COL_PER_X, ROT_SIGN) and is the only place they are defined (pinfit.stage_x_hint now defaults to it). Replay on file 47:
a,b left -1.3/-2.0 px, c=817.1 (global fit 818.1). Replay bug fixed on the way: pin x/z moves act in the rotating frame (dx*cos w, db*sin w), not as constant shifts.

## 2026-10-27 — Stage-1 alignment procedure (user) and the dry-run loop

omega -> 0; move pin (x) so the axis column sits at the beam centre; then for theta = 1, 5, 10, 30, 60, 90 deg measure the axis
column at -theta and +theta, get the along-beam offset b = (x(+t)-x(-t))/(2 sin t) (a and axis column cancel), move z by -k*b,
go to the next angle. Why increasing angles: small angles are a safe, coarse first guess (the small-angle linearisation is valid);
larger angles divide the measurement noise by sin t, so they refine b. `scripts/axis_align.py` implements it with injected
measure/move callables (no hardware) and a synthetic-pin simulator: converges (noise 0.3 px -> |b| ~0.2 px after 90 deg), and
stops if |b| grows after a move (wrong sign k). Residual x offset a = (x(0)-s)/(1-cos t) is reported but NOT corrected (user asked for z only).
Unverified: k (sign of z vs rotation sense), that samE.x/z ride on the rotation, pixel size (1 um placeholder).

## 2026-10-27 — Beam centre = midpoint of the half-maximum footprint (user)

Per-axis: smoothed mean profile, plateau = 90th percentile, base = 5th percentile, edges where profile crosses base + 0.5*(plateau-base); centre = midpoint of the two edges (box found iteratively cols->rows->cols). On `tomo_beam.png`: (959.5, 625.0) px, 625 x 822 px. Why: robust to the saturated, lopsided core; core-intensity peak and outer (10 %) footprint shifted the centre by tens of px. Code: `scripts/beam_center.py::half_max_footprint`; QA figure `analysis/beam_center.png` via `make_beam_center_figure.py` (needs cmcrameri, e.g. `midas-env`).

## 2026-10-27 — Wedge correction deferred (user)

This phase ignores axis tilt (wedge) vs APS Y; only pin axis column == beam centre. Why: keep stage 1 to one measurable quantity; wedge needs its own measurement/stage.

## 2026-10-27 — Staged rollout: stage 1 = rotation axis on the beam only (user)

Current stage assumes the beam is already on the tomo detector, so NO slit control and NO absorption-edge/flux optimisation.
Only goal: the stage rotation axis (`samE.ry`) lies on the beam. Direct-beam reference image (no sample): one bright,
roughly rectangular blob (~1/3 of the 1920x1200 frame wide), saturated structured core, soft vignetted edges, dark
background with sparse hot pixels; Java ImageJ-style viewer of `1idSP5:Pva1:Image` (16-bit). Why: de-risk by adding
automation in stages; slit/edge/flux stages deferred. Implication: beam centroid/footprint from the blob (robust to
saturation, e.g. threshold-at-fraction footprint centre rather than intensity peak) is the "beam position" to compare
with the pin-derived axis column.

## 2026-10-27 — "Aligned" definition and rotation stage fixed (user)

Aligned = flux maximized at the edge + pin in view + pin axis stationary over -90..+90 deg. Rotation motor = `samE.ry`, the
far-field-scan rotation in E (confirmed in `mpe_bluesky`: PSO fly module, used by `hedmscan_sw`/`switch_to_ff`). Why: user
decision; gives the agent a concrete, measurable stop criterion for each stage.

## 2026-10-27 — Classical segmentation (beam-model ratio + 50 % level), not a learned model, as the baseline

Pin is a high-contrast dark silhouette, so: lit-area box -> subtract outside-area dark level -> divide by a polynomial beam
model -> threshold at the midpoint of measured beam and pin levels -> opening, largest component, hole fill. Tested against
naive global Otsu (fails, merges pin with outside) and box Otsu (fails with gradients). Tried a step-edge lit-area finder: it
regressed under noise/blur/crop and was reverted (kept as `_footprint_steps`, unused). Virtual top corners (side line meets
top line) define the axis because the real tip is bevelled on one side. Caveat: reference mask in tests is this same
method on the clean frame, so agreement is a robustness check, not independent ground truth.

## 2026-10-26 — Scaffold agent-neutral context; EAA-Pi as base, mpe_bluesky as device reference

Project dir `beam_alignment_s1` uses `AGENTS.md` + `.context/` (no CLAUDE.md).
EAA-Pi is the agent host; `mpe_bluesky` s1id devices/plans are read only to
pick which devices/PVs matter. No hardware/EPICS access from this project.
