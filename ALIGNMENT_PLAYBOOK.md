# Stage-1 alignment playbook (for the agent: Claude Code, Codex, ...)

Goal: put the **pin on the rotation axis** (a, b → 0) and the **rotation axis on the beam centre** (c → beam centre).
Assumes the beam is already on the tomo detector (no slits / edge / flux, no wedge). Everything the user must see goes through the
CLI, which logs to `runs/<id>/events.jsonl`; the GUI (`python -I gui.py`, http://localhost:8765) follows it live.
**You make every decision; the tools never move or loop on their own** (except the explicit `sweep` and `calibrate` helpers).

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
| `estimate-pm THETA` | measure at 0, ±THETA; b = (x₊−x₋)/(2 sin θ); a only for θ ≥ 30 |
| `calibrate --motor M --mm D` | small test move (then undone): learns d(a,b,c)/mm, checks it against the pixel size |
| `propose` | moves that would cancel a, b and bring c onto the beam centre (**does not move**) |
| `move MOTOR MM --reason "…"` | the only command that moves a stage (motors: x, y, z, aerox) |
| `live-feed [--interval 1]` | (separate process) keeps `live.jpg` fresh for the GUI's live panel; read-only |
| `note "…"` / `finish --status ok\|failed --summary "…"` | narration / close the run |

## Model (what the numbers mean)
Pin column vs rotation angle: `x(ω) = c + a·cos ω + b·sin ω` (px). `c` = rotation-axis column (fixed by the base; **samE.x/y/z do not change it**),
`a` = pin offset along image-x at ω=0 (cancelled by **samE.x**), `b` = pin offset along the beam (cancelled by **samE.z**). The base motor
(`aerox`, candidate, unconfirmed) moves `c` (and the pin with it). Tolerances: |a|,|b| < `TOL_AB_PX`, |c − beam centre| < `TOL_C_PX`.
Beam centre = midpoint of the half-maximum footprint (median over the sweep frames).

## Procedure
1. `new-run`; `note` the plan. `measure --omega 0`: if `pin_col` is null or `status != ok`, stop and report (pin out of view / low contrast) — do not guess.
2. `sweep`. Sanity-check: `rms` small (≲1–2 px; large ⇒ look at the frames, maybe omega timing), all frames valid, pin fully in view at every angle
   (if some angles lose the pin, rerun over a narrower range, e.g. −60…60, and say so).
3. **Signs/scales are unverified on first use:** `calibrate` x, z and aerox with ~0.02 mm test moves. Require each motor's main term to be ≈ 1000/PIXEL_UM px/mm
   (`matches_pixel_size` true) and the cross terms ≈ 0. If not, stop and report. `propose` uses calibrations automatically.
4. Pin onto the axis: `propose` → `move z`, `move x` (skip if |Δ| < 0.0005 mm) → `sweep` → check `within_tol`. Repeat up to 3 times. If |a| or |b| grows after a move, stop
   (sign problem) and report.
5. Axis onto the beam: `propose` → `move aerox` → `sweep`. c − beam must be < `TOL_C_PX`, and a, b must stay in tolerance (the pin rides with the base).
6. `finish --status ok --summary "<final a, b, c−beam>"`. On any stop condition, `finish --status failed` with the reason and what you would try next.

## Reference run
`python -I tests/scripted_agent.py` is a scripted agent following exactly this procedure on the simulator (~90 s); useful to see the expected event flow.
