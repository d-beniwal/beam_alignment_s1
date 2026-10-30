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
2. Start the GUI in a second terminal (`python -I gui.py`) and open http://localhost:8765.
3. Paste a prompt like the one below. **Say explicitly that you are on the real beamline and which camera/hutch** — that is what tells the agent to connect to the
   hardware (the simulator is the default otherwise) and fixes the pixel size.

### Prompt to paste at the beamline

```
Read AGENTS.md and ALIGNMENT_PLAYBOOK.md in this folder, then .context/STATE.md.

We are on the REAL beamline (APS 1-ID) and I want you to connect to the hardware and run the stage-1 alignment now.
Tomo camera: <gh1 | pg1 | pg5>  (hutch <E | E | C>). The camera is already acquiring. The alignment pin is in the sample position.
You are authorised to move samE.x, samE.y, samE.z, samE.aerox and to rotate samE.ry within +-90 deg. Don't ask me for confirmation.

Do this:
1. python -I align.py new-run --backend epics --camera <camera>   (the GUI is already running and follows the run)
2. note the plan, then python -I align.py adaptive-align
   It sets omega to 0, brings the pin into view (find-pin if needed), centres the pin axis on the beam centre, rotates + and - until the pin
   leaves the field of view, fits, corrects z / x / aerox and repeats until |a|,|b| < 1 px and the axis is on the beam centre (+-2 px).
3. Narrate each decision with `align.py note`. If adaptive-align stops (ok=false), read its `reason`, tell me what happened and try the
   suggested remedy ONCE (e.g. find-pin, or re-run adaptive-align); if it still fails, finish the run as failed and stop.
4. When done: python -I align.py finish --status ok --summary "<final a, b, c-beam in px and the motor positions>".
Keep every file for this run inside runs/<id>/ (the CLI does that). Tell me the final numbers when finished.
```

Notes on the prompt:
- Replace `<camera>` — it sets the pixel size (retiga2 1.0 µm/px, pg5 1.17, gh1 0.69, pg1 1.17). `retiga2` (B hutch) has no PV prefix recorded yet, so it only works in the simulator until one is added to `scripts/align_config.py` (`CAMERAS`).
- Equipment protection is always on and is not a confirmation prompt: per-move step limits (larger moves are split), motor soft limits, mm-units check, readback check after every move, rotation limited to ±90°.
- If the pin is not in the beam at all, `adaptive-align` calls `find-pin`, which searches x then y within ±3 mm / ±2 mm of where it started and returns to the start if it finds nothing.
- Variations: to align only partway ("first move the pin 1 mm down, then ..."), say so in the prompt; the agent can use the building blocks listed in the playbook
  (`measure`, `step-pm`, `fast-align`, `move`, `find-pin`).
- Every frame is saved in `runs/<id>/raw/` — keep them: they are how detection problems are debugged afterwards. Send any frame that misbehaved.

## Try it without hardware (simulator)

```
python -I tests/scripted_agent.py            # full alignment on the simulator, ~20 s
python -I tests/test_detection.py            # detection logic on simulated frames
python -I tests/test_identity.py             # pin vs holder/other objects (needs the local s1_data/ folder)
python -I tests/test_partial.py              # partly visible pin (needs s1_data/)
```

For a sim run by an agent, use the same prompt without "REAL beamline" and with `new-run` (no `--backend`).

## What a run produces

Everything for one run is in `runs/<id>/`: `events.jsonl`, `state.json`, `frames/` (overlay JPEGs the GUI shows), `outputs/` (the JSON each CLI command printed), `raw/` (raw frames),
`figures/`, `logs/`, `report/`. Only `runs/CURRENT` (a pointer) lives directly in `runs/`.

## Camera / geometry constants

All constants (pixel sizes per camera, sign conventions, tolerances, step limits, search radii) live in `scripts/align_config.py` — nowhere else.
Confirmed on hardware (2026-10-28): +samE.x moves the pin left in the image, +samE.y moves it up, +samE.aerox moves the axis column down by ~1431 px/mm (gh1).
