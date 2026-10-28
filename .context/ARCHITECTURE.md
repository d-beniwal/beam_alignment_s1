# Architecture

## EAA-Pi (`../EAA-Pi`, github AdvancedPhotonSource/EAA-Pi v1.0.0)

Standalone TypeScript host for the Pi agent SDK + EAA React web UI. Agent
backend is the `pi-experiment-ops` package (vendored in `vendor/`); do not
modify upstream packages — bridges live in `extensions/`
(`policy, mcp, terminal, archive, child, codemode`).

- Linux only officially; needs Node >= 22.19, uv, Git. Dev install:
  `bash scripts/install.sh --runtime-only`; CLI `bin/eaa-pi.mjs`.
- Workflow: `eaa-pi init --workspace DIR` -> `eaa-pi config` (provider/model,
  e.g. `argo`) -> `eaa-pi pi` (TUI) or `eaa-pi serve` (WebUI :8010).
- Extension points for us: **MCP servers** (`eaa-pi config add-mcp`, stored in
  `.pi/mcp.json`) to expose instrument tools; **skills** (`.pi/skills/<n>/
  SKILL.md`, `eaa-pi config add-skill`); **workflows**
  (`workflows/<n>/workflow.mjs`, pi-subagents `runs.run/all/host`, with
  `hostCommands` grants); permissions in
  `.pi-experiment-ops/agent/pi-permissions.jsonc`; plan mode blocks mutations.
- Docs: `docs/{configuration,workflows,security,architecture}.md`.

## Sector 1 Bluesky stack (`../mpe_bluesky`, read-only reference)

Queueserver-based. Relevant paths under `instrument/`:
- `devices/s1id_devices/`: `s1ida_motors.py` (WB slit readbacks
  `1ida:Slit1Ht2.C`/`Vt2.C`, undulator RO), `s1idb/c/e_motors.py`,
  `s1id_slits.py`, `s1id_shutters.py`, `s1id_scalers.py`,
  `s1id_area_detectors.py`, `s1id_positions.py`, FPGA, hydra, lights, linkam.
- `plans/scans_alignment.py` (`dscan`, `ascan`, `gaussian_fit` stub),
  `plans/s1id_plans/s1id_beam_delivery.py` (focusing in/out per station B/C/E,
  open slits, `recenter_slits`, `switch_to_HxV_beam_in_C/E`),
  `s1id_commissioning.py`, `s1id_energy_calibration.py`.
- Caution: Python files in the mpe_bluesky project root run at QS start.

## Planned design

TBD — pending beamline info and integration decision (see STATE.md).
