# Domain knowledge — 1-ID beamline model (from user screenshots, 2026-10-26)

Source: four operator-screen photos (B, C, E "Beamline Control" panels and
"1ID All Slits"). Beam travels **left→right on every panel**; hutch order
downstream: **A → B → C → E**. Panel header (C/E): user operation, ~200 mA,
undulator gap ~10.012 mm, 71.676 keV (snapshot, not a setpoint). C-station
shutter was closed, A/B/E open; fast shutters FS_B off, FS_E on.

Caveat: the screens are *schematics* — order is reliable, **distances are not
given**. Red numbers under each IC are almost certainly ion-chamber readings
(counts), not positions. "IC" = ion chamber (diagnostic intensity monitor).
Items marked (?) are my reading of the picture; confirm with the user.

## Device order along the beam

```
SOURCE (undulator, gap RO) ─ A: WB slits ─ A shutter
 B hutch:  Al-CRL · IC1 · IC2 · CRL · IC3 · HRM(2 xtals; IC4 between) · IC5 ·
           Foil · Atten · IC8 · Stack1 · Stack1(sic) · B-FS (fast shutter) ·
           Cork · B-Kohzu slit · IC6 · B-TOM
           ── then 2nd box downstream: BL3 · BL4 · BL5 · IC7 · (magenta
              circle = sample/endpoint? ?)
 C hutch:  IC1 · IC2 · Slit1 (C_Kuz_US) · [IC1+2 trans] · fourC (circle) ·
           BCS: IC3 · L1 · L2 · L3 · L4 · L5(RD,grey) · L6(RD,grey) ·
           AttenC · Slit2 (C_Kuz_DS) · IC4 ──┤ LabMotion SMS · DBA ·
           Tomo D1 · Stop · Shield · Varex D2 · Lens7
 E hutch:  BCS: IC1+2 · Slit US (Kohzu_E_up) · IC3 · FS (fast shutter) ·
           Lens1 · Lens2 · Lens3 · Lens4 · Slit DS (Kohzu_E_dn) · IC4 ──┤
           Aero SMS / Aero_Tr · Tomo D1 · NF D2 (HL-SMS above) ── IC5 · D3 ──
           IC6 · Hydra D4 ── VFF D5 · Radiograph · IC8 · SAXS D6 → exit
```

Per-hutch notes:
- **B:** the HRM is drawn as two blue triangles (crystals) with IC4 between.
  Foil and Atten have position readouts (both "0 pos" = out/air). Cork shows
  112 mm with an On/Off control; B-FS is the fast shutter (green dot).
- **C:** lenses L1–L4 show in/out indicators (L1,L3 low; L2,L4 high);
  L5/L6 "(RD)" greyed (read-only/unused). Dotted line splits Beam
  Conditioning System from the detector/sample section. C is the 4-circle
  hutch ("fourc").
- **E:** BCS (IC1+2, slits, lenses 1–4, FS) feeds the sample stations;
  several detectors in series (D1 tomo, D2 NF, D3, D4 Hydra/FF, D5 VFF,
  D6 SAXS) with ICs 5/6/8 interleaved. Cameras CAM-1/5/7/9 exist.

## Slits ("1ID All Slits"; H/V size and center, mm; RBV mode)

| Slit (panel)  | Size H×V | Center H, V    | Code device (mpe_bluesky) | PV prefix / name |
|---------------|----------|----------------|---------------------------|------------------|
| WB_slits      | 0.300×0.300 | 0.000, 0.000 | read-only: `WB_hsize`/`WB_vsize` | `1ida:Slit1Ht2.C` / `Slit1Vt2.C` |
| B_Kohzu       | 2.000×2.000 | 0.087, −0.115 | `slitB`   | `1idb:Slit` (m32/m60/m58/m61) |
| C_Kuz_US      | 0.700×0.700 | 0.089, 0.035  | `slitCus` | `1idc:Kslitus` |
| C_Kuz_DS      | 0.800×0.800 | 0.141, −0.233 | `slitCds` | `1idc:Kslitds` |
| Kohzu_E_up    | 0.590×0.540 | 0.142, −0.563 | `slitEus` | `1ide1:Kohzu_E_up` (e.g. `…upVsize.VAL`) |
| Kohzu_E_dn    | 0.880×0.700 | (cut off)     | `slitEds` | `1ide1:Kohzu_E_dn` |

Step sizes on panel: WB 0.05 (size)/0.01 (center); B 1.0/0.001; C_US
0.001/0.1; C_DS 0.1/0.001; E_up 0.1(H)/0.01(V); E_dn 0.01(H)/0.05(V). Each
has "Sync H/V" buttons. The WB slits are read-only in `mpe_bluesky`.
Values are an operator snapshot (E_up tooltip timestamp 2026-10-20), not
alignment targets.

## Cross-reference to `mpe_bluesky` (read-only discovery)

- Slits: `slitB, slitCus, slitCds, slitEus, slitEds` (`s1id_slits.py`,
  `MPE4Slits`, four blade motors each).
- B: `foilB` (1idb:m18), `attenB` (m50), `cork` (m41), `tomoB` (m52/m40),
  `lens4B`/`lens5B` (Al, 38.8/38.9 m from source — only distance info
  found so far; not obviously the "CRL" on the panel (?)).
- C: `attenC` (1idc:m82), `lens1C`–`lens4C` (1idc / 1idfoc), hexapod `con`.
- E: `lens1E`–`lens4E` (1ide1), `samE`/Aero SMS, `tomoEus/Eds`, `d2E`, `ff`
  (Hydra), `vff`, `saxs`, `saxs_pin`.
- Shutters: `shutter_a/b/c` (`S01ID-PSS:{FES,SBS,SCS}:`), fast shutters
  `GenericFastShutter`. Scalers/ICs: `scaler1` (`1id:S1:scaler1`),
  `scaler1E`/`scaler2E` (`1ide2:S{1,2}:scalerN`), `keyence_c/e`.
- Not yet found in code: HRM, CRL/Al-CRL, DBA, Varex/Hydra detector PVs
  (may live in area-detector or other modules) — to locate when needed.

## Open questions for the user

1. Distances along the beam (source→each element) — needed for a proper
   geometric model.
2. What are the red numbers (IC readings?) and which IC maps to which
   scaler channel/PV?
3. Magenta circle and BL3/BL4/BL5 box downstream of B: what are they?
4. Which sequence defines "aligned" (slit centering on IC maxima, lens
   centering, HRM tuning, …) and which hutch(es) first?

# Physics / alignment concepts (taught by user, 2026-10-26)

Chain: **electron beam → undulator → monochromator → single-energy x-ray beam**.

1. **Undulator** (source): electrons passing through it emit x-rays. Intensity
   is maximized by adjusting the undulator **gap** (user's words: "band of the
   width"; reading as gap **confirmed**). Gap is the knob; the figure of merit
   is intensity (IC reading) vs gap.
2. **Monochromator** (energy selection): passes one energy/wavelength.
   Optimize for **maximum transmission close to an absorption edge**,
   judged from the plot of **μ·t (mu-T) vs energy**. The "mu transmission"
   signal is the **ion-chamber reading after the monochromator**.
   (Transcribed speech: "iron chamber" = ion chamber, "undo" = undulator —
   transcription **confirmed** by user.)

## What the existing code says (read-only; `mpe_bluesky`, deprecated 2025-08-12)

`plans/s1id_plans/s1id_energy_calibration.py` (fully commented out) holds the
old recipe — a useful template, not working code. **User confirmed (2026-10-26)
that the facts below taken from this plan are correct**, except the two
inferences flagged in the bullets after them (Re edge, IC ratio), which are
mine and listed under "To be confirmed":
- Mono = **HEM** (`hem`, `hem_energy.a` in keV); undulator = `pmu`
  (`pmu.gap.setpoint`; plans `undsetgap`, `undscangap`); `emon()` records a
  snapshot (muT, HEM energy, gap, foil, atten, WB slit size, IC reading,
  ring current, fill pattern).
- `E_scan`: centered on a K-edge (default width 300 eV, step 5 eV, 5 s count,
  1 s settle): move **foilB** in, **attenB** out, close shutters and check
  mu·T has no negatives (calc8 offsets J/K), open A/B shutters + `fsB`, scan
  `hem_energy.a` over the edge, record `scaler1` + `scaler1_calcs.calc8` (= muT,
  signal `muT` = `1id:S1:scaler1_calc8.VAL`) + ring current. Channels used:
  `IC1_B_HEM`, `IC5_B_HRM2`, `IC8_B_Foiltr`. Edge is fit with an error
  function (midpoint = edge energy) and HEM is moved to it. Refuses if
  requested energy is >200 eV from the current HEM energy.
- So **foilB (Re, Au, Pt, Ir, Ta, Hf, Pb, Tm…) is the energy reference**:
  its K-edge gives the calibration point. The panel's 71.676 keV matches the
  **Re K-edge (~71.676 keV, from my memory — verify)**, suggesting Re foil.
- Likely mapping (inferred): IC8 ("Foiltr") sits after the foil, IC5 before
  it, so muT ≈ ln(I_before/I_after) across the foil. Confirm.

## Alignment objectives so far (model for the agent)

| Stage | Knob | Readout | Objective |
|-------|------|---------|-----------|
| Undulator | gap (`pmu`) | IC intensity | maximize intensity at the harmonic for target E |
| Monochromator | energy (`hem_energy`) | muT (IC after mono, with foil) | place/verify the foil absorption edge; max transmission near edge |

# Slit concepts (taught by user, 2026-10-26)

We mostly use the **Kohzu** slits (B_Kohzu, C_Kuz_US/DS, Kohzu_E_up/dn). Each
slit has two horizontal and two vertical blades; the panel/device exposes
four *derived* axes per slit:

| Axis | What it does | Blades | Beam effect |
|------|--------------|--------|-------------|
| **size** (H or V) | the opening (gap) between the two blades | both move the **same amount, opposite directions** | cuts down the beam; center stays fixed |
| **center** (H or V) | position of the opening | both blades move **together, same direction** | opening size unchanged; **aligns the opening to the beam path** |

Rule of thumb: **size = trim/define the beam; center = align the slit to the
beam.** Alignment of a slit therefore means scanning its H/V *center* (with a
small enough size) against an IC signal; size is set for beam definition.

## How `mpe_bluesky` implements this (`devices/generic_slits.py`, `MPE4Slits`)

- Real blade motors (names from `s1id_slits.py`): `ib`, `ob` (inboard/outboard,
  horizontal) and `bot`, `top` (vertical) — motor PVs like `1idb:m32`.
- Virtual/soft axes (apstools `PVPositionerSoftDone` on a synApps `Slit2`
  record): `hsize`, `hcenter`, `vsize`, `vcenter` (readbacks `t2.C`/`t2.D`),
  plus per-blade soft axes `ibs, obs, bots, tops` (`t2.B`/`t2.A`).
  `motion_mode` is always "virtual" for `MPE4Slits`.
- Helpers: `get_size()` -> `(H, V, Hcenter, Vcenter)`, `set_size(w, h)`
  (checks motors enabled), `set_center(xc, yc)`, `sync_horizontal/vertical/all()`
  (writes the `…Hsync`/`…Vsync` `.PROC`, the panel's "Sync H/V" buttons).
  `MPE4SlitsXY`/`…XYTilts` add whole-slit X/Y (and tilt) stages for some slits.
- Code quirk: `set_slit(h, v)` with only 2 args raises "ambiguous number of
  arguments" (only the 4-arg form passes); use `set_size` / `set_center`.
- Panel units are mm (H-size 0.300 = 300 µm opening, for example).

# Alignment procedure (taught by user, 2026-10-26) — in progress

Stage 1 — **get the tomo detector (`gh1`) into the beam.** Move the detector
(translation stages) around until beam is visible on it. Signal: beam
(intensity) on the tomo camera image. (User will share real camera images
later.)

Stage 2 — **align the sample-stage rotation axis with the beam** using a
**pin** and the **top tip of the pin** as the reference feature.

Pin (photo supplied, not an x-ray image): a small cylindrical holder with a
fluted/knurled body, a domed top and a threaded base, carrying a thin
conical-tipped needle on top (arrow-like tip). A purple ink mark sits on the
needle just above the dome (purpose unknown). The tip is a sharp, high-contrast
point — the feature to track on the camera while rotating the stage (an
off-axis tip traces a circle/sinusoid in the image; on-axis it stays put).
That last sentence is my reasoning about the method, not user-stated.

Further stages: TBD (user is feeding them one at a time).

## What `mpe_bluesky` says about `gh1`

- `gh1` (`s1id_area_detectors.py`): Point Grey / Spinnaker camera, prefix
  `1idGH1:`, default ROI `[0,0,2992,2400]`, `PG_ROI_H5_CONTROL` plugins
  (pva1 cropped, hdf1 from ROI1), `pva1` exists. Selected by `switch_det(gh1)`
  in `s1id_shortcuts.py`; `s1id_userrecs.py` maps `gh1` -> 2 (detector index).
- Tomo-related motors in code: `tomoB` (1idb m52/m40), `tomoEus` (1ide1
  m63/m40/m62/rz m38), `tomoEds` (1ide1 m111/m112), `d2E`, `samE` (SMS/Aero
  stage with rx/ry/rz/aero axes). Which of these moves `gh1` and which is the
  rotation stage is **not yet known** (see to-confirm).

# Pin on the tomo camera — what it looks like and how to measure it (2026-10-26)

Data: `s1_data/tomo_alignment/` (all `exchange/data`, uint16, 1490x1940 px,
gh1 = Point Grey Grasshopper3 GS3-U3-123S6M, 0.1 s exposure; Linux path
`.../s1c/stock_oct26/gh1/<sample>/`). Analysed: `alignment_pin_000044.h5`
(5 static frames) and `alignment_pin_off_center_0_180_000046.h5` (100 frames,
omega 0->180). Other folders present, **not yet analysed**:
`alignment_pin_off_center_000045`, `..._n90_p90_000047`, `pin_double_fov_000049`
(~5 GB). Code (2026-10-27, final): `scripts/pinfit.py` (segmentation + geometry, numpy/scipy only), `pin_segment.py`
(segmentation-only benchmark), `test_*.py`, `make_geometry_figures.py` -> `analysis/geometry_*.png`. Run with
`python -I` in any env with numpy/scipy/h5py/matplotlib (e.g. `bpilot-mpe`).

## File contents worth knowing (HDF5 layout)

- `exchange/data` frames; **`data_dark`/`data_white` exist but are all zeros** (no
  usable flat/dark correction — use the raw image).
- **Omega = `instrument/SMS/E/HR/samRy`** (per-frame, deg). In the 0-180 file it
  runs 0->180 over 100 frames but is **not uniform**: many frames sit at exactly
  0 and at 180, and steps are uneven (continuous motion during acquisition).
  Always read omega per frame; don't assume `linspace`.
- Per-frame/static metadata is rich: slits (`BCS/*/*_slits`), lens stacks
  (`BCS/{C,E}/LENS_STACK*`), `HEM/Energy`=71.676, `HRM/Energy`, `InsertionDevice/
  IDGap`=10.0135, `Scalers/{B,C,E}/IC1..IC9` (+ sensitivities), ring current
  (200.17 mA), `SMS/E/{HL,HR}/*` stages, `DMS/DetX/Y/Z`, `active_instrument/`
  (SMS=`samE`, DMS=`E-HYDRA`, SE=`MPE_compact_lf`). Metadata is already in each
  file, so an agent need not query PVs to know the state a dataset was taken in.
- In the rotation file the other HR axes are constant: `samX=-0.1453`,
  `samY=25.6471`, `samZ=-0.0412`, `samRx=samRz=0` (the static file has
  `samX=-0.2453`, `samZ=7.9588`).

## What the image shows (pin in X-ray transmission)

- A **bright rectangle** = beam footprint on the detector: columns ~444-1502,
  rows ~336-1167 (1058x831 px; ratio 1.27 matches the E downstream slit
  0.88x0.70 mm, ratio 1.26). Outside it is ~black (background ~5-6 kcounts;
  open beam ~25-30 kcounts, brighter on the right side).
- The **pin is a dark silhouette** (absorbs, ~10-15 kcounts): an upright
  **trapezoid / truncated cone** — flat top, edges widening downward,
  continuing down past the bottom of the beam footprint (row ~1160, clipped
  there). It is *not* a sharp point in this image.
  - flat top at row **~478** (477-482 over a full rotation), top width
    **~131-141 px**;
  - edges straight, **half-angle 15.1-15.4 deg** (full cone ~30.4 deg; width
    grows 0.545 px per row): width ~197-207 px at row 600, ~500 px near row 1150;
  - **axis vertical** in the image (center-line slope |dx/dy| < 0.01).
- Photo vs X-ray: the photo's needle has a sharp tip, the X-ray silhouette a
  flat 130-140 px top. Likely the thin apex is too transmissive at 71.7 keV to
  show (or the tip is blunt) — unconfirmed. Extrapolating the edges, a sharp
  apex would sit near row ~230, above the beam footprint (top at row ~336), so
  the apex could not be seen anyway. The measurable "tip" is therefore the
  **flat-top edge row + the two top corners**, not a point.

## Measurement recipe (final, in `scripts/pinfit.py`; supersedes the early hand-rolled one)

Lit-area box -> subtract the dark level measured outside the box -> divide by a polynomial beam model -> threshold at the
50 % level between measured beam and pin levels -> opening, largest component, hole fill. Per-row sub-pixel edges use a
*local* 50 % level; sides are fitted robustly (Theil-Sen, soft-L1, MAD inliers) on rows away from the lit-area rim
(24 px guard) and with sharp edges only; top plateau = longest run where the top boundary is flat. Axis = bisector of the two
side lines, anchored at the midpoint of the *virtual* top corners (side line meets top line), so it ignores the tip bevel.
Typical numbers on this pin: virtual top width ~146 px (flat plateau 84-108 px, bevel 3-65 px on one side that flips with
omega), cone half-angle 14.9 deg (std 0.03 deg over a scan), flat-top roughness ~0.6 px, axis tilt <0.5 deg.
Outputs: top corners/width/midpoint/flatness, axis, `full_view`, signed `shift_px` (+ = pin must move right in the image).
Segmentation benchmark: IoU >= 0.99 vs the clean mask under brightness, background offset, noise, vignetting, hot pixels,
blur and FOV crop; refuses (status `low_contrast`) rather than guessing when CNR < 5.

## Off-axis pin during rotation (what the user described) — quantified

_Update 2026-10-27 with the final method: axis column 815.6 px (0-180 scan, rms 0.9 px) and 816.8 px (-90..+90 scan, rms 1.2 px after
allowing an omega lag); offset radius 131-132 px. Numbers below are from the first, simpler measurement._

- Pin x-position vs omega is a clean sinusoid: **x(w) = c + A cos(w + phi)**
  with **c = 814.7 px, |A| = 132 px, phi = -9.3 deg**, residual 0.7 px.
  x = 684 px at w=0 and 945 px at w=180.
- **c is the image column of the rotation axis** = (x0 + x180)/2 =
  814.5. Pin offset from axis = **~132 px** (= 0.5*(x0 - x180)).
- The axis column (815) is ~158 px **left of the beam/image center column**
  (~973 / 970). In-image offset to remove = c - x_pin.
- **Tip row barely changes** (478->480, ~2 px over 180 deg) and the edges stay
  vertical: no visible axis wobble or tilt in this stage setup.
- Silhouette width at row 600 drifts 207->197 px and top width 141->131 px
  with omega — the pin is slightly non-axisymmetric/tilted about the beam.
- Pixel scale is **not in the file**. If the footprint equals the 0.88x0.70 mm
  downstream slit (inference only) pixels are ~0.83-0.84 um, i.e. the 132 px
  offset ~ 0.11 mm and the axis lies ~0.13 mm from the beam center. Confirm.

**Alignment rule implied** (my inference, matches the user's description):
two frames at omega = 0 and 180 are enough to find the axis column
c = (x0+x180)/2 and the correction (c - x0) to move the pin onto the axis;
verify afterwards that x(w) is flat (A -> 0). Mapping image-x to the right
sample-stage motor (`samX` vs `samZ`) and its sign is **not yet known**.

# Definition of "aligned" + rotation stage (user-stated, 2026-10-27)

Beam is **aligned** when ALL hold:
1. **Flux maximized** for the chosen absorption edge (undulator gap `pmu` + mono `hem_energy`, readout IC/muT).
2. **Pin is in the view** of the tomo camera (`gh1`).
3. **Pin axis is stationary under rotation:** rotating the pin from -90 to +90 deg, its axis stays at the same image position.

**Rotation stage = the motor used for far-field scans in E hutch.** Code check (`mpe_bluesky`, read-only): `samE`
(`s1ide_motors.py`) has `ry` = PV `1ide:m9` (note `1ide:`, not `1ide1:`), a `RotationMotor` with
`_fly_modules={'ry':'s1_pso'}` (PSO-triggered flying). `scans_standard.py` (`hedmscan_sw`, fly/sweep plans) say "sms (samC/D/E): its
y/ry sub-axes are driven by the plan"; `switch_to_ff` zeros `samE.aerox` and `samE.ry`. => omega = `samE.ry`.
Translation under it: `samE.aerox` (`1ide1:m101`) / `samE.aeroz` (`1ide1:m102`) are the Aero stack; `samE.x/y/z` are `m34/m35/m36`.
Which of these moves the pin horizontally in the image (and sign) is still to be confirmed.

# To be confirmed (running list — move items up once the user confirms)

1. **HEM location:** user says it is in the **A hutch, or even upstream of it**
   (so upstream of B). Exact position unknown; it is on no B/C/E panel.
   (Beam-order sketch above starts at A; HEM sits between source and B.)
2. **μ·t ion-chamber ratio:** which ICs form the transmission ratio is
   **not yet known to the user**. My guess (IC5 before foil / IC8 "Foiltr"
   after → ln(IC5/IC8)) is only a guess. Code detail: `scaler1_calc8` is the
   μ·t calc (inputs/formula not yet read from the calc record config).
3. **Foil / edge identity:** whether the 71.676 keV on the panels is the Re
   K-edge via the Re foil (my recollection of the edge energy, unverified).
4. Earlier open questions (see above): source→element distances; red numbers
   under ICs = IC readings?; IC↔scaler-channel/PV map; magenta circle and
   BL3/BL4/BL5; `lens4B/5B` vs panel "CRL"; slit panel name mapping
   (Slit1/2 ↔ C_Kuz_US/DS, Slit US/DS ↔ Kohzu_E_up/dn); E_dn slit centers;
   what "aligned" means and which hutch first; location of HRM/CRL/DBA/
   Varex/Hydra PVs in the code.
5. **Slit sync:** what the "Sync H/V" buttons (`…Hsync.PROC`) actually do
   (re-synchronize the soft size/center axes to the blade motors?) and when an
   agent should call it after moves.
6. **Slit sign/zero convention:** direction of +H/+V center, and whether the
   center values on the panel (e.g. B −0.115 V) are relative to a defined
   beam axis or arbitrary motor zero.
7. **Which slits are used for what:** B_Kohzu (2×2 mm) vs C/E slits (sub-mm);
   which are for beam definition vs alignment, and typical size during
   alignment scans. WB slits appear read-only in `mpe_bluesky`.
8. **`gh1` location/motors:** which hutch (B, C or E) and which motors move
   it into the beam (candidates: `tomoEds`, `tomoEus`, `tomoB`); tomo "D1" on
   the panels vs `gh1` naming.
9. **Rotation stage:** which device is "the stage" whose rotation axis is
   aligned (candidate: `samE`/Aero SMS `rz`/`aerox`/`aeroz`) and which
   motors adjust the axis position relative to the beam.
10. **Pin:** which pin tip feature is tracked, meaning of the purple mark,
    and how alignment is judged (tip stays fixed over rotation?). Also what
    "beam on detector" criterion (intensity threshold/centroid) is used.
11. **Resolved by data (user to confirm):** red panel numbers *are* ion-chamber
    counts (file `Scalers/B/IC2`=181871, `IC3`=612992, `E/IC5`=429, `E/IC6`=746
    vs panel 181877, 613014, 430, 738). Some ICs differ (B IC6/IC7/IC8, E IC3/IC4)
    between panel snapshot and file — different shutter/foil states.
12. **Rotation stage = `samE.ry` (user-confirmed 2026-10-27, matches code).** Still open: Which
    of `HR/samX|samY|samZ` moves the pin horizontally in the image, with what
    sign and units (mm?), and which axis lies along the beam.
13. **Pixel size / magnification** of gh1 in E (and whether the bright
    rectangle is the DS-slit footprint), and **why the pin top is flat**.
14. Are the 0-frames/180-frames duplicates (extra frames at the ends) expected,
    and is omega read at the frame time or interpolated?
15. **omega vs image timing:** fitting the pin position needs an omega lag of ~-0.5 frame-steps (0-180: rms 0.99->0.91 px;
    -90..+90: 3.43->1.16 px, axis column 818.1->816.8 px). Is the omega readback taken at exposure start/end rather than mid-exposure
    (exposure 0.1 s, period 0.122 s)? Matters for any alignment done on frames recorded while rotating.
16. **Double-FOV file:** `SMS/E/HR/samRy` has 3631 entries for 3601 frames (extra 30). Which entries belong to which frame?
    Its dark/white frames are valid (non-zero); the 0-180/-90..90 files' are all zeros.
17. **Clipped pin magnitude:** the full-view shift is only a lower bound when a side is outside the detector (double-FOV). Supplying the
    expected top width needs the pixel scale of that ROI (not known).

## Sample-stage motors and sign convention (user, 2026-10-27)

- `samE.ry` = omega (rotation). `samE.x/y/z` = pin translations.
- **+x moves the pin LEFT when looking downstream along the beam; -x moves it RIGHT.**
- To confirm: how image columns map to that left/right (is image-left = beam-left looking downstream?), which of y/z is vertical vs along-beam,
  and that x is the correct axis to cancel the horizontal axis-to-beam offset. Until confirmed, the sign of any x move derived from
  image columns must be verified by a small, user-approved test move.

## Axes, image direction, detectors (user, 2026-10-27)

- Looking along the beam at the pin and its on-screen image: **+x shifts the pin and its image to the viewer's LEFT** (so image-left = +x; a pin at
  image column c right of the target needs +x ... i.e. dx has the opposite sign of the column change: column decreases as x increases).
- `samE.x` horizontal (transverse), `samE.y` vertical (negative at floor, positive toward roof), `samE.z` along the beam (+z downstream).
  Only x (and y for vertical centring) matter for putting the axis on the beam; z does not move the axis column.
- Two tomo detectors in E: **gh1** (on the high-res table) and **pg1** (near the back wall, by the SAXS detector).
- **Tomo detector pixel size = 1 um/pixel (confirmed by user 2026-10-27; which of gh1/pg1 not stated - assumed the one in use, gh1).** Defined ONCE in
  `scripts/align_config.py::PIXEL_UM`; all code imports it - never hard-code it.

## Wedge out of scope for this phase (user, 2026-10-27)

Do NOT correct the wedge (tilt of the rotation axis relative to the APS Y axis) in this phase. Assume the axis is vertical; the only
goal is that the pin axis column lines up with the beam centre. Wedge correction is a later stage.

## Rotation axis is fixed by the base (user, 2026-10-27)

The rotation axis does NOT move with `samE.x/y/z`: those move the sample (pin) around while the axis stays put. Moving the axis
needs the BASE motors - **which motors those are is not yet known (TBD).** Consequence: samE.x/z can only put the pin ON the axis
(a, b -> 0); putting the axis column c on the beam centre needs a base move.

Candidate (from prior work, see REFERENCE_prior_work.md): the base motor that moves the axis is `samE.aerox` (`1ide1:m101`); the previous authors
used it for the axis-to-beam move but flagged doubt. Awaiting user confirmation.

## Camera PVs and live view (from `midas-gui`, read 2026-10-27)

`midas-gui/midas_gui/live_sources.py` streams cameras via **pvAccess**: PV = `<prefix>Pva1:Image` (NTNDArray), `pvapy.Channel.monitor` with request
`field(value,dimension,uniqueId,attribute,codec,uncompressedSize)`, decoded by `AdImageUtility.reshapeNtNdArray`. 1-ID-E profile (`settings.py`): `gh1`=`1idGH1:`,
`pg1`=`1idPG1:`, `pg5`=`1idSP5:`, `s1varex1`=`1idVarex1:`. **The user's direct-beam screenshot was titled `1idSP5:Pva1:Image` = pg5**, not gh1/pg1.
`pvapy` is installed only in the `midas-gui` conda env. **Open: which camera is used for alignment (gh1 / pg1 / pg5) and its pixel size (1 um/px was confirmed for "the tomo detector").**
Constants: `scripts/align_config.py` (CAMERAS, MOTOR_PVS).

