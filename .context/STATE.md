# Project state

Last updated: 2026-10-27

## Now working on

**Scope (2026-10-27): stage 1 only — beam assumed on tomo detector; just put the `samE.ry` rotation axis on the beam. No slits/edge/flux, no wedge correction.**

Pin segmentation + geometry (user-approved 2026-10-27, SAM-type models skipped). Code: `scripts/pinfit.py`;
QA figures: `analysis/geometry_*.png` (regenerate with `python -I scripts/make_geometry_figures.py [examples|zoom|scan0|scan90|dfov]`).

## Next steps

0. **Stage-1 target (2026-10-27): move the pin so its measured axis stays fixed in the image under rotation (eccentricity -> 0), then axis column = beam centre (959.5 on test screenshot).** Plan: fit pin x(omega)=c+a*cos+b*sin at several omega (c = axis, (a,b) = offset in the rotating frame); cancel (a,b) with the two horizontal translations that ride ON the rotation stage. samE.x/z move the pin (axis is fixed by the base). Remaining blockers: base motors for moving the axis (unknown), and the sign checks (ROT_SIGN, IMAGE_COL_PER_X).
1. Beam-order model of B/C/E hutches + all slits recorded in DOMAIN.md
   (2026-10-26, from screenshots). Still need: distances, IC↔PV mapping,
   alignment sequence, what "aligned" means.
2. Filter `mpe_bluesky` s1id devices/PVs down to the alignment-relevant set
   (slits, mirrors/focusing, monochromator, shutters, motors, scalers/
   detectors/cameras) and store the list here.
3. Decide integration path with EAA-Pi (MCP server wrapping Bluesky/QS vs.
   skills + workflow) — not yet decided; ask the user.

## Open questions / blockers

- **Base motor that moves the rotation axis: candidate `samE.aerox` (m101) from prior work, needs user confirmation + sign.**
- Integration path to the instrument (read-only/simulated first?).
- EAA-Pi officially supports Linux only; this machine is macOS (darwin) —
  runtime location (beamline Linux host?) unknown.
- Which of 1-ID-A/B/C/E stations are in scope for alignment.

## Recent changes

- 2026-10-27: GUI redesigned (progress tracker, agent-says, verdict tiles with sparklines, stale warning, collapsed raw log); verified with mid-run and final headless screenshots on sim.
- 2026-10-27: `environment.yml` (env `beam-align-s1`, built + verified: full sim alignment, figure script, backend gate all OK in it). numpy pinned 1.26.4 to match midas-gui/pvapy 5.4.1.
- 2026-10-27: gated real backend `balign/epics_backend.py` (never run), `align.py live-feed` + GUI live panel (tested on sim); camera PVs from midas-gui recorded. Needs user: camera choice (gh1/pg1/pg5 - screenshot was pg5), review before enabling hardware.
- 2026-10-27: **Phase-1 software built (simulated backend only).** `align.py` CLI (agent), `gui.py` web monitor, `balign/` (sim, session/event log, measure), `ALIGNMENT_PLAYBOOK.md`,
  `tests/scripted_agent.py`. Sim run: a,b,c-beam all <0.03 px in ~90 s. Real backend intentionally NOT implemented (needs user go-ahead + review). Not yet done: live camera stream
  (GUI shows the latest acquired frame), real EPICS/PV backend, MCP wrapper, pg1 vs gh1 selection.
- 2026-10-27: reviewed prior repo (cloned to gitignored `scratch/`): same model/signs as ours; base-axis motor candidate = samE.aerox (m101), unconfirmed. See REFERENCE_prior_work.md.
- 2026-10-27: axis is fixed by the base (base motors TBD); pixel size 1 um/px confirmed, single constant in `scripts/align_config.py`. `axis_align.run` now also
  corrects x (a) and reports c + the base shift; replay on file 47 -> a,b left ~1-2 px.
- 2026-10-27: replay test of `axis_align.py` on file 47 (`scripts/test_axis_align_scan.py`, cache `analysis/scan47_axis_x.npz`; only 100 frames, 1.8 deg apart -> interpolated).
  Global fit c=818.1, a=-132.6, b=-10.4 px. Per-angle b estimates -17..-8 px (biased at small angles: omega zero/timing error couples a into b as ~ -a*sin(delta)).
  Loop leaves ~-2 px of b. Moving x(0) to beam centre does NOT put the axis there (axis stays a=132 px away): x offset a must also be corrected (large-angle estimate)
  and the axis column c then moved by a lab-fixed motor. z moves are simulated only (real scan has none).
- 2026-10-27: `scripts/axis_align.py` dry-run loop (0 deg -> x to beam centre -> +-1,5,10,30,60,90 deg z corrections) + simulator; wrong-sign guard. Next: wire to pinfit measurements, confirm k / stack order / pixel size.
- 2026-10-27: beam centre = half-max footprint midpoint adopted; QA figure `analysis/beam_center.png` (image + column/row profiles, edges, centre vs frame centre).
- 2026-10-27: `scripts/beam_center.py` (footprint centre at 10/25/50/75 % of plateau) tried on screenshot `~/ANL-research/S1ID/Pictures/sector1pics/tomo_beam.png`: cx 954-986 px depending on level (frame centre 959.5), cy ~620-655; edges soft, screenshot is 8-bit display-scaled, so use real 16-bit frames.
- 2026-10-27: wedge correction out of scope this phase (axis assumed vertical).
- 2026-10-27: axes (x horiz, y vert up+, z along beam +), image-left = +x, detectors gh1/pg1 recorded. **Pixel size placeholder 1 um/px, PENDING real values before real-time use.**
- 2026-10-27: stage motors recorded (samE.ry omega; samE.x/y/z translation; +x = pin left looking downstream). Image-column->x sign mapping still to confirm.
- 2026-10-27: staged-rollout decision (axis-on-beam first; slits/edge/flux deferred); direct-beam blob described in DECISIONS.md.
- 2026-10-27: user defined "aligned" (flux max at edge; pin in view; axis stationary -90..+90) and rotation stage = `samE.ry` (far-field motor, verified in code). Recorded in DOMAIN.md.
- 2026-10-27: deleted old exploratory scripts/plots (pin_look/measure/track*, old analysis outputs); generated 5 geometry QA figures.
  Finding: sinusoid residuals in scans are mostly omega/image timing (~-0.5 frame-step), not detection error.
- 2026-10-27: pin segmentation first (user request). `scripts/pin_segment.py` (3 classical methods) +
  `scripts/pinfit.py` (full fit, paused). Benchmark `scripts/test_segmentation.py`: beam-model ratio + 50 % level
  holds IoU>=0.99 vs clean under brightness, offset, noise, vignette, hot pixels, blur, FOV crop; naive global Otsu fails.
  Pin top is bevelled on one side that flips with omega (see DOMAIN.md). SAM-type models: not tried yet (awaiting user OK to download).
- 2026-10-26: analysed pin images (file 44 static, 46 off-center 0-180). Pin = vertical trapezoid silhouette, half-angle ~15.2 deg; off-center pin x(omega) fits sinusoid, axis column 814.7 px, offset 132 px. Recipe + code in `scripts/`, results in `analysis/`; DOMAIN.md updated (items 11-14 to confirm).
- 2026-10-26: alignment stages 1-2 (gh1 into beam; pin-tip rotation-axis alignment) + `gh1` code facts in DOMAIN.md; items 8-10 added to to-confirm list.
- 2026-10-26: slit concepts (size = trim, center = align) + `MPE4Slits` implementation recorded in DOMAIN.md; 3 slit items added to to-confirm list.
- 2026-10-26: added "To be confirmed" list to DOMAIN.md (HEM in/upstream of A; μ·t IC ratio unknown); transcription + plan-derived facts confirmed.
- 2026-10-26: recorded undulator-gap / monochromator-edge concepts and the
  deprecated `E_scan`/`emon` recipe (DOMAIN.md). Awaiting more concepts.
- 2026-10-26: ran init-context; created AGENTS.md and `.context/`.
- 2026-10-26: registered project in workspace `CLAUDE.md`, `CLAUDE/overview.md`,
  `CLAUDE/projects/beam_alignment_s1.md`; wrote beam model into DOMAIN.md.
