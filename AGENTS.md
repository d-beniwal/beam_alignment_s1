# Agent instructions

## Project context

Agentic **beamline alignment for APS Sector 1 (1-ID)**, built on the **EAA-Pi**
assistant (`../EAA-Pi/`) and driving the Sector 1 Bluesky stack
(`../mpe_bluesky/`) for device/PV discovery. This directory holds the
alignment-specific config, skills, workflows, and the curated device/PV list.

**Hardware (updated 2026-10-30, user decision):** when the user says they are on the real beamline and want to align on hardware, just connect and run it
(`align.py new-run --backend epics --camera <gh1|pg1|pg5>`) — do not ask for confirmation again and again. Default is still the simulator when the user
does not say so (development sessions, tests). Equipment protection stays on and is not a prompt: per-move step limits, motor soft limits, mm units check,
readback verification, rotation within ±90°.

Distinct codebases — don't conflate: `../mpe_bluesky` (Sectors 1/20),
`../3idc-bits` (3-ID-C), `../b-pilot` (PyQt GUI for mpe_bluesky).

## At the start of a task

Read `.context/STATE.md` for current focus, next steps, blockers, and recent
changes. Read only the relevant portions of the on-demand references — do not
bulk-read them:

- `.context/ARCHITECTURE.md` — EAA-Pi summary, mpe_bluesky s1id layout, planned design
- `.context/DOMAIN.md`       — beamline facts supplied by the user (optics, motors, PVs)
- `.context/DECISIONS.md`    — dated decisions and why (newest first)
- `.context/REFERENCE_prior_work.md` — summary of the earlier `auto_beamline_alignment_tomo` repo (mechanism, motors, bugs)

**Environment:** `conda env create -f environment.yml && conda activate beam-align-s1` (python 3.12, numpy 1.26.4, scipy, pillow, h5py, matplotlib, cmcrameri; pvapy/pyepics are installed for the gated real backend only). Run everything with `python -I ...`.

**To run an alignment:** read `ALIGNMENT_PLAYBOOK.md` and drive `python -I align.py ...` (simulated backend only). The user watches it in the GUI
(`python -I gui.py`, http://localhost:8765). Code: `balign/` (+ `scripts/` for pinfit/beam_center/axis_align/`align_config.py` = the single place for the
pixel size and sign constants).

For Bluesky/ophyd work use the global `bluesky` skill.

## After significant work

Update `.context/STATE.md` (keep it under ~1 page) and prepend a dated entry
with reasoning to `.context/DECISIONS.md`. Do not overwrite prior decisions.
Trivial edits and pure Q&A don't need an update.
