# Agent instructions

## Project context

Agentic **beamline alignment for APS Sector 1 (1-ID)**, built on the **EAA-Pi**
assistant (`../EAA-Pi/`) and driving the Sector 1 Bluesky stack
(`../mpe_bluesky/`) for device/PV discovery. This directory holds the
alignment-specific config, skills, workflows, and the curated device/PV list.

**Safety (absolute):** never connect to beamline hardware or EPICS PVs and
never run code that talks to instruments. Read and edit source only. Any
tooling written here must default to read-only/simulated until the user
explicitly says otherwise.

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
