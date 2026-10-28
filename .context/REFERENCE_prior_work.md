# Prior work: auto_beamline_alignment_tomo (read 2026-10-27)

Source: https://github.com/AdvancedPhotonSource/auto_beamline_alignment_tomo (cloned read-only to `scratch/`, gitignored; ~34 commits,
Hemant Sharma + a student, Jul-Aug 2024). One file, `beamline_alignment_with_motor_code.py` (Dash web GUI + PyEPICS + SAM). Never executed here.

## What it does (their workflow)
1. Take a flat: move `samXE` (m34) by -2 mm (relative) so the pin leaves the beam, acquire, move back. Normalise every frame by the flat.
2. SAM (Segment Anything, vit_h) segments the normalised frame. User draws a rectangle on the beam -> beam left/right edges at that row; user clicks
   the pin -> pin mask -> pin "midpoint" = middle of the mask row extent at the clicked row y.
3. Rotate in steps (default 5 deg, 0.3 s exposure), tracking the pin with SAM point prompts at the previous midpoint + beam edge. Rotate positive until the
   pin comes within 50 px of a beam edge, then go back to 0 and rotate negative until the same happens. (Not a full turn; covers whatever range keeps the pin in the beam.)
4. Fit midpoint(theta) = off + rad * sin(theta + st)  (scipy curve_fit, bounds off +-3000, rad 0..2000, st +-180 deg).
   off = rotation-axis column, rad = pin eccentricity, st = phase.
5. "Center pin and verify": move motors (mm = px * pixel_um / 1000):
     samXE  (m34, = our samE.x): +rad*sin(st)          # = our a
     "samYE" label samZE (m36, = our samE.z): -rad*cos(st)   # = -b
     aeroXE (m101, = samE.aerox): (off - beam_center/2)  # axis -> beam
   then repeats steps 1-4 to verify (new axis position + residual offset).

## Does it explain the mechanism? Yes - and it matches our model exactly
Their rad*sin(theta+st) = (rad sin st) cos theta + (rad cos st) sin theta, i.e. our a = rad sin st, b = rad cos st, c = off.
Their corrections: x by +a, z by -b  ==> same as ours (dz = -ROT_SIGN*b with ROT_SIGN=+1; x such that image column changes by -a with
+x lowering the column, IMAGE_COL_PER_X=-1). So the rotation stage (m9 = samE.ry), samE.x (m34), samE.z (m36) are the same motors/roles as ours,
and their signs agree with the signs the user gave/we assumed (still unverified by us on hardware; they ran 1idPG1, not necessarily our setup).
Two translation motors on the rotation stage cancel eccentricity; the axis itself is moved by the Aero base x-stage.

## Candidate base motor for moving the axis
`aeroXE` = PV `1ide1:m101` = `samE.aerox`. The authors themselves flagged it: "#Is this the right mtr??". Matches DOMAIN.md's Aero stack
(`switch_to_ff` zeros aerox + ry). `aeroz` (m102) is along the beam. NOT confirmed by the user.

## Weaknesses / bugs to not copy
- `beam_center = edges[1] - edges[0]` is the beam WIDTH, then `off - beam_center/2` -> only correct if the beam's left edge is at col 0. Should be
  (edge0+edge1)/2.
- Axis shift sign/direction of aeroX untested ("VERIFY!!!!" comments); no readback checks, limits, or dry-run.
- Needs SAM (torch, GPU/weights), a human clicking the beam and pin (not autonomous); pin tracking by SAM prompts can lose the pin.
- Pin "midpoint" at one clicked row; our pin is a bevelled trapezoid whose tip flips with omega, so a row midpoint is biased; we use the fitted virtual top corners.
- Single global sinusoid fit: sensitive to omega-vs-image timing (our scan: rms 3.4 px, ~1.2 px after a -0.5 frame lag) and needs wide angle coverage.
- Default pixel size 1.172 um for pg1 vs the 1.0 um we use (user-confirmed tomo detector value).
- Safety: it caputs camera PVs and moves motors directly; we must keep everything dry-run/read-only.

## Takeaways for us
- Keep our measure -> (a,b,c) -> {x, z, base} structure; it is the same physics.
- Their wide-angle global fit is a good cross-check/final verification of our +-theta loop (fit x(omega) over -90..+90 and check a, b ~ 0).
- Base-axis move: aerox candidate; compute it from c vs the beam-footprint centre (we already have half-max centre), with the sign confirmed first.
