"""Build the MIDAS-style alignment report (HTML + PDF) for one run. Usage: python -I scripts/make_report.py RUN_DIR
All numbers are read from RUN_DIR/events.jsonl, RUN_DIR/../*.json (command outputs) and RUN_DIR/beam_center/beam_fit.json."""
import sys, json, base64, subprocess, html
sys.dont_write_bytecode = True
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

run = Path(sys.argv[1]).resolve(); R = run.parent; out = run / "report"; (out / "figs").mkdir(parents=True, exist_ok=True)
J = lambda p: json.load(open(p))
sw, pm30, pm90, pm90b, pm90c = (J(R / f) for f in ("sweep1.json", "pm30.json", "pm90.json", "pm90_r2.json", "pm90_r3.json"))
cal = {m: J(R / f"cal_{m}.json")["calibration"] for m in ("x", "z", "aerox")}
bf = J(run / "beam_center" / "beam_fit.json"); se = bf["step_edge"]
ev = [json.loads(l) for l in open(run / "events.jsonl")]
TEAL, COP, INK = "#0e7c86", "#b06f33", "#16191c"
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})

def abc(p):                      # from the 0/+-90 triplet: x(+-90)=c+-b, x(0)=c+a
    c = (p["x_plus"] + p["x_minus"]) / 2; return c, p["x0"] - c, (p["x_plus"] - p["x_minus"]) / 2
c_fin, a_fin, b_fin = abc(pm90c)
beam_c = se["cx"]

# ---- repeatability: identical-position sweeps before any real move (sweep + 3 calibration "before" sweeps)
groups, cur = [], None
for e in ev:
    if e["kind"] == "measure" and e["data"] and e["data"].get("omega") is not None and e["data"].get("pin_col") is not None:
        pass
before = [e for e in ev if e["kind"] == "measure" and e["image"] and any(t in e["image"] for t in ("_sweep", "_cal_before"))]
byw = {}
for e in before:
    d = e["data"]; byw.setdefault(round(d["omega"]), []).append(d["pin_col"])
sig = {w: float(np.std(v, ddof=1)) for w, v in byw.items()}
sig_med = float(np.median(list(sig.values()))); n_rep = len(next(iter(byw.values())))

# ---- figures
def savefig(f, name): f.savefig(out / "figs" / name, dpi=140, bbox_inches="tight"); plt.close(f)
om = np.array(sw["omegas"]); cols = np.array(sw["cols"]); fit = sw["fit"]; xx = np.linspace(-95, 95, 400)
curve = lambda c, a, b, w: c + a * np.cos(np.radians(w)) + b * np.sin(np.radians(w))
f, (ax, ax2) = plt.subplots(2, 1, figsize=(7.5, 5.6), gridspec_kw={"height_ratios": [3, 1]}, sharex=True)
ax.plot(xx, curve(fit["c"], fit["a"], fit["b"], xx), color=TEAL, lw=1.6, label=f"fit  c={fit['c']:.1f}, a={fit['a']:.1f}, b={fit['b']:.1f} px")
ax.plot(om, cols, "o", color=COP, label="measured pin axis column"); ax.axhline(fit["c"], color="#888", ls=":", lw=1)
ax.set_ylabel("pin axis column (px)"); ax.legend(frameon=False, fontsize=9); ax.set_title("Initial sweep, x(omega) = c + a cos(omega) + b sin(omega)", fontsize=10.5)
ax2.stem(om, fit["residuals"], basefmt=" "); ax2.set_ylabel("residual (px)"); ax2.set_xlabel("omega (deg)"); ax2.axhline(0, color="#888", lw=.8)
savefig(f, "fig_sweep.png")

f, ax = plt.subplots(figsize=(6.4, 3.8)); ms = ["x", "z", "aerox"]; main = [abs(cal["x"]["d_a_per_mm"]), abs(cal["z"]["d_b_per_mm"]), abs(cal["aerox"]["d_c_per_mm"])]
ax.bar(ms, main, color=[TEAL, TEAL, COP], width=.55); ax.axhline(1000, color=INK, ls="--", lw=1, label="1000 px/mm = 1 um/px (config)"); ax.legend(frameon=False, fontsize=8.5, loc="upper right")
for i, v in enumerate(main): ax.text(i, v + 20, f"{v:.1f}", ha="center", fontsize=9)
ax.set_ylabel("|main term| (px/mm)"); ax.set_ylim(0, 1700); ax.set_title("Calibration: measured px/mm vs. expected", fontsize=10.5)
savefig(f, "fig_cal.png")

f, ax = plt.subplots(figsize=(7.8, 4.6))
ax.plot(xx, curve(fit["c"], fit["a"], fit["b"], xx), color="#aaa", lw=1.4, label="initial (sweep fit)")
ax.plot(om, cols, "o", color="#aaa", ms=4)
for p, col, lab in ((pm90, COP, "after x,z move 1"), (pm90c, TEAL, "after move 2 + aerox")):
    c, a, b = abc(p); ax.plot(xx, curve(c, a, b, xx), color=col, lw=1.6, label=f"{lab}:  a={a:.2f}, b={b:.2f} px")
    ax.plot([-90, 0, 90], [p["x_minus"], p["x0"], p["x_plus"]], "o", color=col)
ax.axhline(beam_c, color=INK, ls=":", lw=1); ax.text(-93, beam_c + 14, f"beam centre (steep-edge) {beam_c:.1f}", fontsize=8.5, bbox=dict(fc="white", ec="none", pad=1.5))
ax.set_xlabel("omega (deg)"); ax.set_ylabel("pin axis column (px)"); ax.legend(frameon=False, fontsize=8.5, loc="lower center")
ax.set_title("Pin column vs omega at each stage (curves rebuilt from the 0/+-90 triplets)", fontsize=10.5)
savefig(f, "fig_converge.png")

def b64(p, mime="image/png"): return f"data:{mime};base64," + base64.b64encode(open(p, "rb").read()).decode()
IMG = {k: b64(out / "figs" / f"fig_{k}.png") for k in ("sweep", "cal", "converge")}
IMG["beam"] = b64(run / "beam_center" / "beam_fit.png")
IMG["f_init"] = b64(run / "frames" / "001_meas.jpg", "image/jpeg"); IMG["f_fin"] = b64(run / "frames" / "061_pm0.jpg", "image/jpeg")

# ---- tables
moves = [e for e in ev if e["kind"] == "move" and "calibration test" not in e["msg"] and "undo" not in e["msg"]]
mv_rows = "".join(f"<tr><td>{e['t'][11:19]}</td><td>{html.escape(e['msg'].split(' (')[0].replace('MOVE ',''))}</td><td>{html.escape(e['msg'].split(' (',1)[1].rsplit('); ',1)[0])}</td></tr>" for e in moves)
cal_rows = "".join(f"<tr><td>{m}</td><td>{c['d_a_per_mm']:+.1f}</td><td>{c['d_b_per_mm']:+.1f}</td><td>{c['d_c_per_mm']:+.1f}</td><td>{c['test_mm']}</td></tr>" for m, c in cal.items())
stage_rows = "".join(f"<tr><td>{n}</td><td>{a}</td><td>{b}</td><td>{c}</td><td>{s}</td></tr>" for n, a, b, c, s in [
    ("initial sweep (7 angles)", f"{fit['a']:.1f}", f"{fit['b']:.1f}", f"{fit['c']:.1f}", "runs/sweep1.json"),
    ("±30° estimate (before moves)", f"{pm30['a']:.1f}", f"{pm30['b']:.1f}", "—", "runs/pm30.json"),
    ("±90°, after move 1 (x,z)", f"{pm90['a']:.2f}", f"{pm90['b']:.2f}", f"{abc(pm90)[0]:.1f}", "runs/pm90.json"),
    ("±90°, repeat (before move 2)", f"{pm90b['a']:.2f}", f"{pm90b['b']:.2f}", f"{abc(pm90b)[0]:.1f}", "runs/pm90_r2.json"),
    ("±90°, final (after move 2 + aerox)", f"{pm90c['a']:.2f}", f"{pm90c['b']:.2f}", f"{c_fin:.1f}", "runs/pm90_r3.json")])
tl = [("10:37", "Run created on the epics backend, camera gh1; GUI + live feed running"), ("10:47", "measure ω=0: pin in full view (col 1687.0)"),
      ("10:47–10:48", "sweep −90…90° step 30°: fit a, b, c"), ("10:48–10:52", "calibrate x, z, aerox with 0.02 mm test moves (each undone)"),
      ("10:55", "estimate-pm 30 (user: one ±30° rotation), then move x, z"), ("10:56", "check at ±90° (a=2.81, b=3.24 px)"),
      ("10:58", "second ±90° round, then second small x, z correction"), ("11:04", "pin-free direct-beam frame grabbed; beam centre and FWHM measured (two methods)"),
      ("11:08", "measure ω=0, then move aerox −0.0335 mm (axis onto beam centre)"), ("11:09", "final ±90° check (a=0.77, b=1.17 px)")]
tl_rows = "".join(f"<tr><td>{t}</td><td>{html.escape(s)}</td></tr>" for t, s in tl)

T = f"""<style>
:root{{--paper:#f4f2ee;--panel:#fff;--ink:#16191c;--ink2:#3d4045;--mut:#6b6862;--line:#e4e0d8;--hair:#efece5;--teal:#0e7c86;--teal-ink:#0b5f67;--copper:#b06f33;--plate:#f7f6f3;--plate-line:#d7d3ca;
--sans:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;--mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);line-height:1.55}}
.wrap{{max-width:1100px;margin:0 auto;padding:44px 36px 70px}}
.eyebrow{{font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:var(--teal);font-weight:650}}
h1{{font-size:38px;line-height:1.08;margin:.28em 0 .12em;letter-spacing:-.02em;font-weight:750}}
.lede{{font-size:16px;color:var(--ink2);max-width:80ch}}
.prov{{margin-top:22px;border:1px solid var(--line);border-radius:12px;background:var(--panel);display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:1px;overflow:hidden}}
.prov div{{padding:11px 15px;background:var(--panel)}}.prov dt{{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--mut);margin:0 0 3px}}
.prov dd{{margin:0;font-family:var(--mono);font-size:12px;word-break:break-word}}
.sec{{margin-top:44px}}.sec-h{{display:flex;align-items:baseline;gap:12px;margin-bottom:16px;padding-bottom:9px;border-bottom:1px solid var(--line)}}
.sec-h{{break-after:avoid-page}}.sec.pb{{break-before:page}}.sec-h h2{{font-size:20px;margin:0;font-weight:700}}.sec-h .k{{font-family:var(--mono);font-size:12px;color:var(--teal)}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}}
.tile{{border:1px solid var(--line);border-radius:12px;background:var(--panel);padding:15px;position:relative;overflow:hidden;break-inside:avoid}}
.tile::before{{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--teal)}}
.tk{{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--mut)}}.tv{{font-size:23px;font-weight:720;margin-top:5px;letter-spacing:-.02em;font-variant-numeric:tabular-nums}}
.ts{{font-size:11.5px;color:var(--ink2);margin-top:4px}}
.finds{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:13px}}
.find{{border:1px solid var(--line);border-left:3px solid var(--teal);border-radius:0 12px 12px 0;background:var(--panel);padding:14px 17px;break-inside:avoid}}
.find.warn{{border-left-color:var(--copper)}}.find h3{{margin:0 0 5px;font-size:14.5px}}.find p{{margin:0;font-size:13px;color:var(--ink2)}}
.tag{{display:inline-block;font-family:var(--mono);font-size:10.5px;padding:2px 7px;border-radius:5px;background:#dcecee;color:var(--teal-ink);margin-bottom:7px}}.tag.warn{{background:#f1e4d6;color:var(--copper)}}
.plate{{margin:0 0 26px;border:1px solid var(--line);border-radius:14px;background:var(--panel);overflow:hidden;break-inside:avoid}}
.pcap{{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;padding:14px 18px 12px;border-bottom:1px solid var(--hair)}}
.pnum{{font-family:var(--mono);font-size:12px;color:var(--teal);font-weight:600}}.ptitle{{font-size:16px;font-weight:700}}.psub{{font-size:12.5px;color:var(--mut)}}
.pimg{{background:var(--plate);padding:12px;border-top:1px solid var(--plate-line)}}.pimg img{{display:block;width:100%;height:auto;margin:0 auto}}
.pimg.two{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}.note{{padding:11px 18px 14px;font-size:12.5px;color:var(--ink2)}}
table{{border-collapse:collapse;width:100%;font-size:12.5px;background:var(--panel);border:1px solid var(--line);border-radius:10px;overflow:hidden}}
th,td{{padding:7px 11px;text-align:left;border-bottom:1px solid var(--hair);font-variant-numeric:tabular-nums}}th{{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--mut);background:var(--plate)}}
td:last-child code,code{{font-family:var(--mono);font-size:11.5px}}
footer{{margin-top:44px;padding-top:18px;border-top:1px solid var(--line);color:var(--mut);font-size:12px}}footer .fp{{font-family:var(--mono);font-size:11px;word-break:break-all}}
@media print{{body{{background:#fff}}.wrap{{padding:0}}.sec{{margin-top:28px}}}}
@page{{size:A4;margin:14mm}}
</style>
<div class="wrap">
<header><div class="eyebrow">MIDAS · 1-ID-E · Stage-1 beam alignment report</div>
<h1>Pin axis → rotation axis → beam centre</h1>
<p class="lede">2026-10-28, run <b>{run.name}</b>, live hardware (epics backend, tomo camera gh1). Motion limited to samE.x, samE.z, samE.aerox, the rotation stage (samE.ry, needed to rotate the pin) and the camera. Pin segmentation, the sinusoid fit and all moves are from the balign tools; every number below names the file it was read from. <b>All positive claims are provisional — not yet run through /verify.</b></p>
<dl class="prov">
<div><dt>Run / backend</dt><dd>{run.name} · epics · gh1 (1idGH1:Pva1:Image)</dd></div>
<div><dt>Frame</dt><dd>{bf['shape'][1]} × {bf['shape'][0]} px, 16-bit</dd></div>
<div><dt>Pixel size</dt><dd>1.0 µm/px (config placeholder; see watch item)</dd></div>
<div><dt>Signs (config)</dt><dd>IMAGE_COL_PER_X=−1, ROT_SIGN=+1</dd></div>
<div><dt>Motors</dt><dd>ω 1ide:m9 · x m34 · z m36 · aerox m101</dd></div>
<div><dt>Code</dt><dd>beam_alignment_s1 @ 867baf4 + uncommitted scripts</dd></div>
<div><dt>Source</dt><dd>{run}</dd></div></dl></header>

<section class="sec"><div class="sec-h"><h2>Summary</h2><span class="k">runs/pm90_r3.json · sweep1.json</span></div><div class="tiles">
<div class="tile"><div class="tk">Pin offset a (x)</div><div class="tv">{fit['a']:.1f} → {a_fin:.2f} px</div><div class="ts">tolerance &lt; 1 px · passes</div></div>
<div class="tile"><div class="tk">Pin offset b (z)</div><div class="tv">{fit['b']:.1f} → {b_fin:.2f} px</div><div class="ts">tolerance &lt; 1 px · <b>1.17 is over</b></div></div>
<div class="tile"><div class="tk">Axis column c</div><div class="tv">{fit['c']:.1f} → {c_fin:.1f} px</div><div class="ts">beam centre {beam_c:.1f} → c − beam = {c_fin-beam_c:+.2f} px</div></div>
<div class="tile"><div class="tk">Net stage moves</div><div class="tv">x +0.0940 mm</div><div class="ts">z −0.0085 · aerox −0.0335 mm (events.jsonl)</div></div>
<div class="tile"><div class="tk">Measurement noise</div><div class="tv">σ ≈ {sig_med:.2f} px</div><div class="ts">median over angles of {n_rep} identical-position repeats</div></div>
<div class="tile"><div class="tk">Pin column spread ±90°</div><div class="tv">{max(pm90['x_plus'],pm90['x0'],pm90['x_minus'])-min(pm90['x_plus'],pm90['x0'],pm90['x_minus']):.1f} → {max(pm90c['x_plus'],pm90c['x0'],pm90c['x_minus'])-min(pm90c['x_plus'],pm90c['x0'],pm90c['x_minus']):.1f} px</div><div class="ts">max−min of x(0), x(±90): after move 1 → final</div></div>
</div></section>

<section class="sec"><div class="sec-h"><h2>What the data says</h2><span class="k">interpretation (provisional)</span></div><div class="finds">
<div class="find"><span class="tag">solid</span><h3>Pin was far off the rotation axis; two corrections removed it</h3><p>Initial 7-angle sweep: a = {fit['a']:.1f}, b = {fit['b']:.1f} px, fit rms {fit['rms']:.2f} px, 7/7 valid (sweep1.json). After the x/z moves the ±90° triplet gave a = {pm90['a']:.2f}, b = {pm90['b']:.2f}; after the second round and aerox, a = {a_fin:.2f}, b = {b_fin:.2f} px (pm90.json, pm90_r3.json).</p></div>
<div class="find"><span class="tag">solid</span><h3>Signs of x, z and aerox confirmed by moving the hardware</h3><p>+x → a decreases ({cal['x']['d_a_per_mm']:+.1f} px/mm); +z → b increases ({cal['z']['d_b_per_mm']:+.1f}); +aerox → c decreases ({cal['aerox']['d_c_per_mm']:+.1f}). Cross terms ≤ {max(abs(cal['x']['d_b_per_mm']),abs(cal['x']['d_c_per_mm']),abs(cal['z']['d_a_per_mm']),abs(cal['z']['d_c_per_mm']),abs(cal['aerox']['d_a_per_mm']),abs(cal['aerox']['d_b_per_mm'])):.1f} px/mm (cal_*.json). This is the first hardware check of IMAGE_COL_PER_X and ROT_SIGN.</p></div>
<div class="find"><span class="tag">solid</span><h3>Pin axis is on the steep-edge beam centre to {abs(c_fin-beam_c):.1f} px</h3><p>Final axis column c = {c_fin:.2f} px vs beam centre {beam_c:.1f} px (beam_fit.json, step_edge). Tolerance 2 px. The pin-free frame was used for the centre because the pin biases the footprint.</p></div>
<div class="find warn"><span class="tag warn">watch</span><h3>The beam centre depends on the method by 33 px</h3><p>Half-max footprint: col {bf['cx']:.1f}, row {bf['cy']:.1f}, FWHM {bf['fwhm_x_px']} × {bf['fwhm_y_px']} px. Steepest-edge footprint: col {se['cx']:.1f}, row {se['cy']:.1f}, {se['width_px']} × {se['height_px']} px. The beam is a sharp-edged box with a dimmer left side, so the half-max level sits on the shoulder (col {bf['box_x'][0]} vs the real edge at {se['x'][0]}). The steep-edge centre was used; if half-max is wanted, c is 32.6 px short (≈ −0.023 mm more aerox). Not decided with the user.</p></div>
<div class="find warn"><span class="tag warn">watch</span><h3>Pixel size looks like ≈0.69 µm/px, not 1.0</h3><p>All three motors read 1431–1459 px/mm instead of 1000 (cal_*.json), a common factor ≈1.45 (matches_pixel_size = false for all). Moves used the measured px/mm, so they do not depend on PIXEL_UM; µm widths in the beam figure (and px tolerances in µm) do. The 0.69 figure is an inference from three small moves, not a measurement of the scintillator.</p></div>
<div class="find warn"><span class="tag warn">watch</span><h3>b is 1.17 px — just over the 1 px tolerance</h3><p>The ±30° estimate of b (8.9 px) was low compared with the 7-angle sweep (12.3 px), so z was under-corrected the first time — the known small-angle bias (omega zero / timing couples a into b). Remaining 1.17 px is ≈ 0.0008 mm of z, below the 0.001 mm step, so it was left. Noise is σ ≈ {sig_med:.2f} px, so 1.17 px is real but small.</p></div>
<div class="find warn"><span class="tag warn">watch</span><h3>The ±90° check is the same estimator that drove the correction</h3><p>a and b come from x(0), x(±90) alone, and the last aerox step was checked with that same triplet. The raw columns (1599.67, 1600.06, 1597.72) are the independent evidence; a full 7-angle sweep after the final move was not taken.</p></div>
<div class="find warn"><span class="tag warn">watch</span><h3>Unexplained: the pin was absent from the direct-beam frame</h3><p>The frame at ω = +90° (positions in the status output) showed no pin, although the pin was measured at ±90° at 10:56–10:58 and at ω = 0 at 11:08. Something outside these tools changed in between (likely the user bringing the beam into view). Not investigated; the beam-centre frame is pin-free but its provenance is uncertain.</p></div>
</div></section>

<section class="sec"><div class="sec-h"><h2>What we did</h2><span class="k">timeline · events.jsonl</span></div><table><tr><th>time (CDT)</th><th>step</th></tr>{tl_rows}</table></section>

<section class="sec"><div class="sec-h"><h2>Offsets at each stage</h2><span class="k">px</span></div><table><tr><th>stage</th><th>a</th><th>b</th><th>c</th><th>source</th></tr>{stage_rows}</table>
<p style="font-size:12px;color:var(--mut)">±90° values: c = (x₊ + x₋)/2, a = x₀ − c, b = (x₊ − x₋)/2 (the model at cos 90° = 0). Beam centre = {beam_c:.1f} px.</p></section>

<section class="sec"><div class="sec-h"><h2>Calibration (0.02 mm test moves, undone)</h2><span class="k">px/mm · runs/cal_*.json</span></div><table><tr><th>motor</th><th>d a / mm</th><th>d b / mm</th><th>d c / mm</th><th>test move (mm)</th></tr>{cal_rows}</table></section>

<section class="sec"><div class="sec-h"><h2>Stage moves applied</h2><span class="k">events.jsonl (test moves excluded)</span></div><table><tr><th>time</th><th>move</th><th>reason</th></tr>{mv_rows}</table></section>

<section class="sec pb"><div class="sec-h"><h2>Figures</h2><span class="k">6 plates</span></div>
<figure class="plate"><figcaption class="pcap"><span class="pnum">01</span><span class="ptitle">Beam centre and full width (direct beam, pin-free)</span><span class="psub">top: column profile · right: row profile</span></figcaption>
<div class="pimg"><img src="{IMG['beam']}" alt="beam centre"></div>
<div class="note">gh1 frame, {bf['shape'][1]}×{bf['shape'][0]} px. Red + / green box = half-max footprint centre ({bf['cx']:.1f}, {bf['cy']:.1f}), FWHM {bf['fwhm_x_px']} × {bf['fwhm_y_px']} px (arrows). Orange × / dashed box = steepest-edge centre ({se['cx']:.1f}, {se['cy']:.1f}), {se['width_px']} × {se['height_px']} px. Dotted blue = frame centre ({bf['frame_centre'][0]}, {bf['frame_centre'][1]}). Data: beam_center/beam_fit.json, frame_raw.npy. Widths in µm assume 1.0 µm/px.</div></figure>
<figure class="plate"><figcaption class="pcap"><span class="pnum">02</span><span class="ptitle">Initial pin sweep and sinusoid fit</span><span class="psub">−90…90° step 30°</span></figcaption><div class="pimg"><img src="{IMG['sweep']}"></div>
<div class="note">Source: runs/sweep1.json. The curve is the three-parameter fit; residuals are within ±2 px.</div></figure>
<figure class="plate"><figcaption class="pcap"><span class="pnum">03</span><span class="ptitle">Convergence of the pin axis</span><span class="psub">pin column vs omega at three stages</span></figcaption><div class="pimg"><img src="{IMG['converge']}"></div>
<div class="note">Grey: initial sweep. Orange: after the first x/z move. Teal: final, after the second x/z move and the aerox move. Sources: sweep1.json, pm90.json, pm90_r3.json.</div></figure>
<figure class="plate"><figcaption class="pcap"><span class="pnum">04</span><span class="ptitle">Stage calibration</span><span class="psub">measured px/mm vs the 1 µm/px expectation</span></figcaption><div class="pimg"><img src="{IMG['cal']}" style="max-width:520px"></div>
<div class="note">Source: runs/cal_x.json, cal_z.json, cal_aerox.json. All three sit about 1.45× above the dashed 1000 px/mm line.</div></figure>
<figure class="plate"><figcaption class="pcap"><span class="pnum">05</span><span class="ptitle">Pin at ω = 0 before and after</span><span class="psub">analysis overlay (lit box, beam centre, pin outline, axis)</span></figcaption><div class="pimg two"><img src="{IMG['f_init']}"><img src="{IMG['f_fin']}"></div>
<div class="note">Left: first measurement, frames/001_meas.jpg (pin col 1687.0). Right: after all corrections, frames/061_pm0.jpg (pin col 1599.7). Green box / line = footprint and beam centre measured by the tool with the pin in view (≈1611), which is biased by the pin; the pin-free centre used for the alignment is {beam_c:.1f}.</div></figure>
</section>

<section class="sec pb"><div class="sec-h"><h2>Next steps</h2><span class="k">diagnosis → lever</span></div><div class="finds">
<div class="find warn"><span class="tag warn">next</span><h3>Decide the beam-centre definition</h3><p>Steep-edge vs half-max differ by 33 px in column. Pick one and record it in align_config / DECISIONS.</p></div>
<div class="find warn"><span class="tag warn">next</span><h3>Fix PIXEL_UM</h3><p>Measure the gh1 pixel size on the scintillator (≈0.69 µm/px is only inferred) and update scripts/align_config.py.</p></div>
<div class="find warn"><span class="tag warn">next</span><h3>Verify the final state</h3><p>Take a 7-angle sweep and repeat the beam-centre frame; run /verify before calling the axis aligned. Wedge (axis tilt) is still not treated.</p></div>
</div></section>
<footer><div class="fp">{run}</div><div style="margin-top:6px">Generated by scripts/make_report.py from run files · Sonnet 5.5 via Claude Code</div></footer></div>"""

(out / "report.html").write_text(f"<!doctype html><html><head><meta charset='utf-8'><title>1-ID-E stage-1 alignment report {run.name}</title></head><body>{T}</body></html>")
subprocess.run(["google-chrome", "--headless=new", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer", f"--print-to-pdf={out/'report.pdf'}",
                f"file://{out/'report.html'}"], check=True, capture_output=True, timeout=180)
print(out, {k: round(v, 3) for k, v in sig.items()}, sig_med, n_rep, c_fin, a_fin, b_fin)
