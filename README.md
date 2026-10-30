# beam_alignment_s1 — agentic stage-1 beam alignment at APS 1-ID

Puts the rotation axis (`samE.ry`) of the sample stage on the X-ray beam: the alignment pin is imaged on a tomo camera, rotated, and the stage
motors are corrected until the pin axis stays fixed in the image and sits at the beam centre. An AI agent (Claude Code, Codex, ...) drives it
through a small CLI; you watch it in a local web GUI.

- `align.py` — the CLI the agent uses (`python -I align.py <command>`; every command prints JSON and is saved in the run folder)
- `gui.py` — the live monitor (http://localhost:8765)
- `ALIGNMENT_PLAYBOOK.md` — the agent's instructions (commands, procedure, what the numbers mean). **The agent reads this.**
- `AGENTS.md`, `.context/` — project context for agents (state, decisions, domain notes)
- `balign/` (software), `scripts/` (pin fit, beam centre, constants in `align_config.py`), `tests/`

## Setup (once per machine)

```
conda env create -f environment.yml
conda activate beam-align-s1
```

Always run Python with `-I` (`python -I align.py ...`).

## Running on the real beamline

1. On the beamline workstation: `conda activate beam-align-s1`, then start Claude Code in this folder (`claude`). The camera must already be acquiring.
2. Open http://localhost:8765 in a browser (the agent starts the GUI if it is not running).
3. Tell the agent (this is the whole prompt):

```
Start the beam alignment at beamline. You can access hardware.
```

   Optionally add the camera (`... Use pg1.`; default is `gh1`) or a variation (`... First move the pin 1 mm down.`). That sentence authorises connecting to the hardware; everything else
   (read the playbook, start the GUI, run `adaptive-align`, retry once on failure, report the result) is in `AGENTS.md` / `ALIGNMENT_PLAYBOOK.md` ("Standard beamline run"), which the agent reads itself.

Notes:
- The camera sets the pixel size (retiga2 1.0 µm/px, pg5 1.17, gh1 0.69, pg1 1.17). `retiga2` (B hutch) has no PV prefix recorded yet, so it only works in the simulator until one is added to `scripts/align_config.py` (`CAMERAS`).
- Equipment protection is always on and is not a confirmation prompt: per-move step limits (larger moves are split), motor soft limits, mm-units check, readback check after every move, rotation limited to ±90°.
- If the pin is not in the beam, `adaptive-align` calls `find-pin`, which searches x then y within ±3 mm / ±2 mm of where it started and returns to the start if it finds nothing.
- Every frame is saved in `runs/<id>/raw/` — keep them: they are how detection problems are debugged afterwards. Send any frame that misbehaved.
- Without the words "at beamline" / "hardware" the agent uses the simulator.

## Try it without hardware (simulator)

```
python -I tests/scripted_agent.py            # full alignment on the simulator, ~20 s
python -I tests/test_detection.py            # detection logic on simulated frames
python -I tests/test_identity.py             # pin vs holder/other objects (needs the local s1_data/ folder)
python -I tests/test_partial.py              # partly visible pin (needs s1_data/)
```

For a sim run by an agent: *"Run the beam alignment on the simulator."*

## What a run produces

Everything for one run is in `runs/<id>/`: `events.jsonl`, `state.json`, `frames/` (overlay JPEGs the GUI shows), `outputs/` (the JSON each CLI command printed), `raw/` (raw frames),
`figures/`, `logs/`, `report/`. Only `runs/CURRENT` (a pointer) lives directly in `runs/`.

## Camera / geometry constants

All constants (pixel sizes per camera, sign conventions, tolerances, step limits, search radii) live in `scripts/align_config.py` — nowhere else.
Confirmed on hardware (2026-10-28): +samE.x moves the pin left in the image, +samE.y moves it up, +samE.aerox moves the axis column down by ~1431 px/mm (gh1).
