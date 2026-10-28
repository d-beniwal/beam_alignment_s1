# Decisions

Add new decisions at the top using:

## YYYY-MM-DD — Short title

What was decided and why.

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
