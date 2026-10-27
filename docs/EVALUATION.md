# Evaluation log: measured results only

Every entry states its **date, conditions and data source**. **SYNTHETIC** means rendered test scenes with exact ground truth; those results show the algorithms work, not that real photos will match. Real-part results will be added as they're measured, against caliper ground truth. Nothing here is estimated or extrapolated.

**Synthetic renderer:** exact area coverage, 8× supersampled, with OpenCV's boundary-inclusive bias cancelled. Measured bias is within ±0.03 px; an annulus comes out within 0.05 % of its true area (2026-10-26).

---

## 2026-10-26 · AT-1 calibration accuracy · SYNTHETIC

**Conditions**
- Rendered A4 mat (layout v1) seen by a virtual pinhole camera: 2400×1800 px, f = 1900 px, page filling about 92 % of the frame.
- Gaussian blur σ = 0.8 px and noise σ = 2 grey levels.
- Corners from OpenCV 4.14 ArUco with sub-pixel refinement.
- "Scale error" is the worst relative error over three 100 mm segments in the free zone.
- "Point error" is the worst error over a 6×6 grid of free-zone points.

| tilt x/y/roll (°) | markers | native px/mm | fit RMS (mm) | leave-one-out RMS (mm) | max scale error (100 mm) | max free-zone point error (mm) |
|---|---|---|---|---|---|---|
| 0/0/0 | 12 | 5.51 | 0.038 | 0.038 | 0.014 % | 0.014 |
| 10/0/5 | 12 | 4.90 | 0.048 | 0.049 | 0.007 % | 0.011 |
| 0/18/-10 | 12 | 4.52 | 0.051 | 0.052 | 0.004 % | 0.008 |
| 20/12/30 | 12 | 4.09 | 0.061 | 0.062 | 0.004 % | 0.011 |
| 25/0/90 | 12 | 5.93 | 0.041 | 0.042 | 0.004 % | 0.006 |
| 17.7/17.7/0 | 12 | 4.76 | 0.049 | 0.050 | 0.006 % | 0.009 |
| 12/-8/15, 5 markers occluded | 7 | 4.40 | 0.059 | 0.063 | 0.007 % | 0.013 |

**Result:** AT-1 passes on synthetic data. The worst scale error is 0.014 % against the 0.2 % threshold. A print at 97 % scale is corrected to within threshold by the caliper-checked bars.

**Correction (same day).** A first run of this table used OpenCV's anti-aliased fill to render markers. That fill inflates shapes by 0.47–1.03 px (measured), which overstated the errors: fit RMS 0.11–0.18 mm, scale error up to 0.047 %, point error up to 0.061 mm. The table above is re-measured with the exact-coverage renderer.

**Finding for the Confidence Engine:**
- Per-corner residuals (0.04–0.06 mm) are about 3–4× the actual mapping error at the part (≤ 0.014 mm), because corner jitter averages out across up to 48 corners.
- So `u_cal` must be the homography's *prediction* error at the part's location (for example from a bootstrap over markers), not the corner residual.
- 📋 D5.

**Printed-mat geometry check** (the PDF rendered by pdfium): marker centres deviate from the layout by at most about 1 render pixel (0.109 / 0.046 / 0.014 mm at 300 / 600 / 1200 dpi). The deviation tracks pixel size, so it comes from rasterisation, not PDF geometry. A physical printer has its own error, which the 100 mm check bars measure.

---

## 2026-10-26 · D2 boundary refinement and holes · SYNTHETIC

**Scene**
- Hero-like bracket: 80×28 mm, corner radius 4 mm, two Ø4.2 mm through-holes 60 mm apart.
- Grey 55 on paper 235. Camera tilt 8/−5/10°, blur σ = 0.8 px, noise σ = 2.
- Calibrated, then rectified at **4.5 px/mm** (pixel = 0.222 mm).

**Coarse masks** are a labelled **test backend**: exact ground truth rasterised, then degraded. They are not SAM 3.1 output.

**Refinement:** band ±0.3 mm (2 px); the two-colour edge model gives sub-pixel iso-contours. Errors are distances from the refined contour to the true polygon. Holes are measured by circle fit.

| coarse mask (test backend) | boundary error mean / max (mm) | coarse→refined shift mean / max (mm) | hole Ø error (mm) | hole centre error (mm) |
|---|---|---|---|---|
| exact rasterisation | 0.0132 / 0.0398 | 0.024 / 0.222 | 0.0094 | 0.0056 |
| dilated 1 px | 0.0105 / 0.0494 | 0.214 / 0.311 | 0.0062 | 0.0055 |
| eroded 1 px | 0.0132 / 0.0398 | 0.214 / 0.444 | 0.0168 | 0.0049 |
| blocky (½ resolution) | 0.0154 / 0.0494 | 0.112 / 0.222 | 0.0062 | 0.0055 |
| holes filled in the mask | both holes found by colour | — | 0.0062 | 0.0055 |

**Result:**
- The mean boundary error is about 1/15 px, with masks that were up to 0.44 mm off.
- Through-holes are recovered even when the mask fills them.
- A glare highlight on the part is flagged as `glare_suspect` rather than accepted as a hole.
- A low-contrast part (ΔE < 12) keeps the coarse boundary and raises `PROFILE_LOW_CONTRAST`.

**Not yet shown** (needs real photos):
- shadows, real lens blur, JPEG artefacts
- part thickness (perspective)
- how far real SAM 3.1 masks sit from the edge

---

## 2026-10-26 · M1 pipeline end to end (`reforge run`) · SYNTHETIC

**Input**
- A synthetic photo of the hero-like bracket with an **asymmetric notch** at its upper-left (as photographed). The notch catches mirrored output.
- Camera tilt 6/−4/12°, blur σ = 0.8 px, noise σ = 2.
- Segmented by the **classical fallback (not AI)**, used here as a test backend.
- Thickness 3.02 mm (entered value).

| quantity | result | truth | error |
|---|---|---|---|
| overall length × width | 80.013 × 27.999 mm | 80 × 28 mm | +0.013 / −0.001 mm |
| thickness | 3.02 mm | 3.02 mm | 0 (entered value) |
| hole H0 Ø, centre | 4.211 mm, (−30.005, 0.002) | 4.2 mm, (−30, 0) | +0.011 mm, 0.005 mm |
| hole H1 Ø, centre | 4.214 mm, (30.000, 0.003) | 4.2 mm, (30, 0) | +0.014 mm, 0.003 mm |
| handedness | notch upper-left seen from above | upper-left | ✅ not mirrored |
| validation | valid, no warnings | — | — |

- **Calibration:** 12 markers; fit RMS 0.052 mm; leave-one-out RMS 0.052 mm; 4.67 px/mm native.
- **Refinement:** ΔE 70; the coarse mask moved 0.094 mm on average (0.222 mm max).
- **Stage timings** (4 vCPU VPS): load 0.10 s · calibrate + rectify 0.15 s · segment 0.08 s · refine 0.14 s · spec + build + validate 0.03 s · write 0.03 s, for about **0.53 s in total**.

**Not yet measured:** the same chain on a real photo with SAM 3.1 (AT-2, AT-3, AT-5 live). It's blocked on the API key and the printed mat.

---

## 2026-10-27 · Live Meta Model API spike (Day-1 unknowns) · SYNTHETIC images, standard tier

Source: `prep/verify_meta_api.py`, report `prep/out/verify_report_20261027_085331.json` (git-ignored).

| Check | Result |
|---|---|
| Models visible to the key | 9: `muse-image-1.0`, `muse-spark-1.1/1.2/1.3`, `muse-spark-1.2/1.3-contributor`, `muse-voice-transcribe-1.0`, `muse-wonder-1.0`, `sam-3.1` |
| Spark 1.3 text structured output (strict json_schema) | conformed (`{"ok": true, "n": 42}`), 2.4 s, 77 in / 32 out tokens |
| Spark 1.3 vision + structured output (`enum`, `minimum`, `maximum`, `minItems`, `maxItems` accepted) | holes 2 ✓, markers 4 ✓, shape `rounded_rectangle` ✓, bbox `[500, 448, 1100, 752]` px against the true `[500, 450, 1100, 750]` (≤ 2 px). 5.0 s, 2,520 in / 418 out tokens, about $0.0049 |
| SAM 3.1 text prompt "grey plate" (full 1600×1200 scene) | 1 instance, confidence 0.66, IoU 0.986, holes kept open, box-local raster at native resolution, mean boundary error 0.97 px (mask about 1 px inside the edge). 3.4 s |
| SAM 3.1 point prompt (full scene) | 1 instance, confidence 0.988, IoU 0.936; **one of the two holes was filled in** by the mask. 2.8 s |
| Image input tokens | 4032×3024 JPEG: 4,264 · 1600×1200 JPEG: 2,662 |

### SAM 3.1 prompt types on the rectified mat view (the production input)

The scene is the synthetic hero-like bracket (grey 55 on paper 235), rectified at 4.5 px/mm (639×1030 px). Six calls:

| prompt | instances | confidence | IoU vs truth |
|---|---|---|---|
| text "plastic part" | **0** | — | — |
| text "black plastic bracket" | **0** | — | — |
| text "object" | **0** | — | — |
| point at the part centre | 1 | 0.992 | 0.984 |
| box around the part (+4 px) | 1 | 0.988 | **0.994** |
| text "plastic part" on the full 2400×1800 photo | **0** | — | — |

**Consequence:** the production segmenter is box-first, with the box taken from the local colour candidate. A click becomes a point prompt, and text is the fallback. 🔎 Real photos of real plastic may favour text prompts more than this flat synthetic rendering does; re-measure on the hero part.

### AT-2: production path end to end (`tests/live/test_sam_live.py`)

The input is the synthetic asymmetric bracket photo, through `SamSegmenter` → refinement → PartSpec → STL.

| mode | SAM calls | confidence | SAM latency | overall (truth 80 × 28) | holes Ø (truth 4.2), centres (truth ±30, 0) |
|---|---|---|---|---|---|
| auto (box prompt) | 1 | 0.988 | 3.08 s | 80.016 × 28.002 mm | 4.208 / 4.211 mm, (−30.005, 0.002) / (30.000, 0.003) |
| click (point prompt) | 1 | 0.992 | 2.29 s | 80.016 × 28.002 mm | 4.208 / 4.211 mm, same centres |

The total pipeline is about 4 s, of which SAM is 2–3 s. Each call writes a ledger entry with latency and an estimated $0.0025 cost.

**Bug found by the live run and fixed:**
- On the first attempt, the box-prompt mask kept the holes open but slightly offset. The narrow refinement band clipped the true hole edge (0.19 mm deviation), so the holes were traced as non-round polygons.
- Holes are now always measured by colour inside the hole-filled outline, and the mask's opinion is kept as evidence (`mask_agrees`).
- A regression test covers masks whose holes are 2–3 px too small or too large.
- Both modes now give identical measurements.

**Spend:** about **$0.043** estimated for all of today's spike, diagnosis and live tests (17 SAM calls, 2 Spark calls). Whether SAM bills empty results is unknown; they're counted here.
