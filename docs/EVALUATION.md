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

---

## 2026-10-27 · Real-photo physics: part height and linear-light optics · SIMULATION and SYNTHETIC

**Why this entry exists.** An audit of the test harness found two physical effects of a real photo missing from every synthetic number above:
- **Height:** the renderer drew parts flat on the paper, but a real part's top face is h mm above the mat, closer to the camera.
- **Optics:** the renderer blended and blurred sRGB-encoded values, but lenses blur and pixels integrate *linear light*, which the camera then encodes.

The earlier entries stay valid for the conditions they state, but they did not predict real-photo accuracy. Both effects are now modelled in the renderer (`tests/synthetic/scene.py`: exact prism projection, linear-light coverage and blur) and corrected in the pipeline.

### 1. Size of the effects (exact simulation, `backend/tools/real_photo_biases.py`)

**Height parallax.** Conditions:
- The bracket: 80 × 28 mm, 3.0 mm thick, holes Ø 4.2 at x = ±30.
- Measured through the mat-plane homography. "Nadir offset" is the distance from the part centre to the point under the camera.
- "Observed" is what the M1 pipeline (git `380c1bc`) would have measured.
- "Two-copy" is the correction first planned in PLAN v0.4 (O ∩ O/m).

| camera height | nadir offset | observed L × W (mm) | observed hole Ø (mm) | two-copy hole Ø, max deviation (mm) |
|---|---|---|---|---|
| 250 mm | 0 | 80.972 × 28.340 | 3.989 / 3.989 | 4.198, 0.030 |
| 250 mm | 58 mm | 81.093 × 28.534 | **3.527** / 3.940 | 4.154, **0.248** |
| 400 mm | 0 | 80.605 × 28.212 | 4.070 / 4.070 | 4.199, 0.012 |
| 400 mm | 58 mm | 80.680 × 28.332 | 3.791 / 4.040 | 4.189, 0.095 |
| 500 mm | 0 | 80.483 × 28.169 | 4.096 / 4.096 | 4.200, 0.008 |
| 750 mm | 58 mm | 80.361 × 28.177 | 3.987 / 4.116 | 4.198, 0.027 |

- Both formulas recover the outline extents exactly (80.000 × 28.000) on this convex outline.
- The two-copy formula is not exact for holes, nor (see §3) for non-convex outlines.

**Edge threshold.** A 1-D step, pixel-integrated, with the t = 0.5 crossing computed as `refine.py` does. Negative values sit inside the part, in px:

| paper / part grey | blur σ | old harness (encoded blur, Lab threshold) | real camera (linear blur, Lab threshold) | linear-light threshold |
|---|---|---|---|---|
| 235 / 30 | 0.6 / 1.0 / 1.5 px | −0.064 / −0.102 / −0.150 | −0.480 / −0.754 / −1.112 | −0.002 / +0.001 / −0.001 |
| 235 / 55 | 0.6 / 1.0 / 1.5 px | −0.050 / −0.080 / −0.119 | −0.381 / −0.600 / −0.886 | −0.000 / +0.001 / +0.003 |
| 235 / 120 | 0.6 / 1.0 / 1.5 px | −0.030 / −0.047 / −0.069 | −0.200 / −0.319 / −0.469 | +0.001 / −0.002 / −0.001 |

At 7.6 px/mm (a 12 MP 1× phone photo from 40 cm), −0.60 px is −0.079 mm per edge: L −0.16 mm and hole Ø +0.16 mm.

### 2. Fixes, measured on the realistic harness

**Boundary refinement.** Same scene as the D2 entry above (4.5 px/mm, blur σ 0.8 px, noise 2), flat part, four coarse-mask variants:

| configuration | mean boundary error (mm) | max (mm) | hole Ø error (mm) |
|---|---|---|---|
| old harness, old code (reproduces the D2 entry) | 0.0105–0.0154 | 0.049 | +0.006…+0.009 |
| **realistic optics, old code** | **0.0601–0.1001** (inside the part) | 0.132 | **+0.189…+0.193** |
| realistic optics, linear-light rectification only | 0.0607–0.1007 | 0.134 | +0.190…+0.193 |
| realistic optics, linear-light threshold only | 0.0111–0.0155 | 0.065 | −0.021 |
| realistic optics, current code | 0.0107–0.0154 | 0.065 | −0.022 (before the curvature correction below) |

The threshold is the fix. Linear-light rectification is kept because it's physically right, but it changed nothing measurable here.

**Marker corners.**
- **The bias:** OpenCV's sub-pixel ArUco corners sit inside the true corners along each marker's diagonal. The offset is **0.85–0.89 px** with realistic optics (0.20–0.22 px in the old harness), measured directly against the true projections.
- **Why it matters:** it's symmetric about each marker, so it barely moves the homography. But it dominated the residual: 0.160–0.187 mm, which raised `CAL_HIGH_RESIDUAL` on every image.
- **The fix:** the bias is now fitted jointly with the homography as one shared parameter in pixels, which on a real print also absorbs dot gain. The fitted value is 0.845–0.885 px, matching the direct measurement.
- **AT-1 re-measured** (same cases as the 2026-10-26 table):

| tilt x/y/roll (°) | markers | native px/mm | fit RMS (mm) | leave-one-out RMS (mm) | max scale error (100 mm) | max free-zone point error (mm) |
|---|---|---|---|---|---|---|
| 0/0/0 | 12 | 5.51 | 0.008 | 0.010 | 0.009 % | 0.008 |
| 10/0/5 | 12 | 4.90 | 0.017 | 0.019 | 0.002 % | 0.009 |
| 0/18/-10 | 12 | 4.52 | 0.023 | 0.025 | 0.002 % | 0.009 |
| 20/12/30 | 12 | 4.09 | 0.028 | 0.030 | 0.005 % | 0.009 |
| 25/0/90 | 12 | 5.93 | 0.018 | 0.019 | 0.002 % | 0.004 |
| 17.7/17.7/0 | 12 | 4.76 | 0.024 | 0.025 | 0.002 % | 0.009 |
| 12/-8/15, 5 markers occluded | 7 | 4.40 | 0.021 | 0.023 | 0.004 % | 0.010 |

**Camera pose** (`reforge/capture/pose.py`). The focal length comes from the homography's orthonormality constraints, with a bootstrap over markers giving 1σ. Synthetic cameras, true f = 1900 / 3800 / 5700 px:
- **Tilted views (5–25°):** the homography focal length is within 0.2–1.6 % (estimated 1σ 1.0–3.1 %), and the camera height within 0.1–1.6 %.
- **Flat-on views:** the homography can't measure the focal length, so the EXIF value (35 mm equivalent, rounded to 1 mm) is used. The camera height is then within 0.2–1.5 %.
- **No EXIF and flat-on:** a 26 mm prior is used and `POSE_FOCAL_ASSUMED` is raised. With a 3× lens that prior put the camera at 324 mm instead of 1025 mm, so this case must not be trusted (§4).

**Height correction** (`reforge/geometry/height.py`, unit tests on exact silhouettes):
- **Outline:** the exact inverse is the intersection of the photographed outline scaled by every factor in [1/m, 1]. It's computed as (O ∩ O/m) minus the trapezoids each boundary edge sweeps.
  - Convex outlines are recovered to < 0.002 mm (Hausdorff) for camera heights 250–750 mm and nadirs up to 144 mm away.
  - A U-shaped notch lost no material (< 1e-4 mm²). Its only extra material is the single-view occlusion zone of §3.
- **Round holes:** a two-disc visibility model (bottom opening ∩ projected top opening) recovers Ø and centre to < 0.002 mm. A plain circle fit on the same data reads up to 0.67 mm small.
- **Non-round holes:** the dual sweep formula recovers a square hole's bounds to 0.002 mm, never enlarges the hole, and misses only its occluded corner (0.28 mm²).

**Blur-curvature bias of holes.** A blurred curve's 0.5 iso-contour sits σ²/(2R) towards its centre of curvature. Prediction for R = 2.1 mm at 5.5 px/mm: Ø −0.010 mm at σ = 0.8 px, −0.040 mm at 1.6 px. Measured: −0.0106 and −0.0409.
- The edge spread σ is now measured on each photo from ∫ t(1 − t) dn = σ/√π over the traced edges.
- Measured σ: 0.101–0.457 mm, against 0.105–0.458 mm actual (render blur 0.5–2.5 px, with pixel integration).
- Corrected hole Ø error: within ±0.001 mm without noise, and ≤ 0.012 mm at blur 2.5 px with noise 5 (raw: −0.004 to −0.110 mm).

**Outline smoothing.** The bounding box of a traced contour picks its noise extremes. The outline is now smoothed by one pixel along its arc length; the raw trace is kept as evidence. A circle of radius R shrinks by σ²/(2R) under smoothing, 0.003 mm at the bracket's 4 mm corners.

### 3. End to end: a 3.0 mm thick part, realistic optics

Conditions:
- `reforge run` path, classical segmenter (a test backend), blur σ 0.8 px, noise 2, three seeds per case.
- The EXIF value is passed as a rounded integer, as a phone writes it.
- Truth: 80 × 28 mm, Ø 4.2 mm, hole spacing 60 mm.

| lens, tilt, EXIF | camera height | code | L (mm) | W (mm) | hole Ø (mm) | hole spacing (mm) |
|---|---|---|---|---|---|---|
| 1×, 0/0/0, EXIF | 345 mm | `380c1bc` (before) | 80.574–80.582 | 28.075–28.078 | 4.207–4.211 | 60.253–60.257 |
| | | **current** | **80.020–80.024** | **27.998–28.003** | **4.196–4.197** | **59.997–60.000** |
| 1×, 12/0/0, no EXIF | 357 mm | before | 80.574–80.576 | 28.466–28.471 | 3.994–4.000 | 60.256–60.264 |
| | | **current** | **80.035–80.036** | **28.010–28.013** | **4.200–4.204** | **59.999–60.002** |
| 2×, 8/-5/10, EXIF | 765 mm | before | 80.194–80.201 | 28.378–28.382 | 4.055–4.059 | 60.128–60.133 |
| | | **current** | **80.025–80.028** | **28.014–28.029** | **4.193–4.195** | **59.996–60.001** |
| 3×, 0/0/0, EXIF | 1025 mm | before | 80.096–80.098 | 27.936–27.939 | 4.312–4.314 | 60.099–60.102 |
| | | **current** | **80.025–80.027** | **28.026–28.028** | **4.197–4.197** | **60.004–60.007** |

**The M1 reference scene,** now rendered at its real 3.02 mm thickness (tilt 6/−4/12, no EXIF):
- **Photographed vs corrected:** photographed 80.618 × 28.438 mm, corrected to **80.012 × 28.011 mm**.
- **Holes:** Ø 4.198 / 4.198, centres (−29.994, 0.004) / (30.003, 0.002).
- **Pose:** homography focal length +0.14 %; camera height 402 ± 4 mm.
- **Calibration:** fit RMS 0.017 mm, corner bias 0.876 px.
- **Time:** 1.12 s in total, of which pose and height correction take 0.25 s.

**Live SAM 3.1** (`tests/live`, 2 calls on this synthetic image, standard tier, about $0.005): both modes pass the 80 × 28 ± 0.1 mm and Ø 4.2 ± 0.05 mm assertions.

### 4. Limits, stated but not yet measured on real photos

- **Tone curve:** an sRGB transfer function is assumed. Phone tone curves and local tone mapping differ, and AT-3 will measure the effect.
- **Principal point:** assumed at the image centre, with 1σ = 1 % of the diagonal.
  - In these scenes that gives a nadir 1σ of 7–9 mm.
  - It moves edges facing away from the camera by (m − 1)·δN.
  - Reported as `u_persp_mm_2sigma`: 0.13 mm in the reference scene, and up to 0.19 mm from 25 cm. It matters only when the two ends of a dimension face opposite ways relative to the camera.
- **No EXIF on a flat-on view:** the focal length is a prior, so the correction is wrong with a zoom lens. The run is flagged (`POSE_FOCAL_ASSUMED`); 📋 the Confidence Engine must block or widen U.
- **Single-view occlusion:** a gap shorter than (m − 1)·distance along a ray is hidden by the top face. Near concave corners the footprint keeps that zone as material. U-notch test, 90 mm from the nadir, from 25 cm: a 0.94 × 0.55 mm triangle, as predicted. `occlusion_bound_mm` is reported, and a second viewpoint resolves it.
- **Harness ground truth:** the 8× supersampled renderer itself moves outer extents by up to ±0.02 mm (measured by varying the supersampling). That covers most of the remaining +0.02–0.036 mm on L.
- **Not modelled:** shadows, lens distortion, sharpening halos, draft angles, chamfers.

### 5. Corrections to earlier entries

- **AT-1 (2026-10-26):**
  - The fit and leave-one-out residuals (0.038–0.063 mm) were inflated by the 0.2 px corner bias, not by "corner jitter averaging out" as stated there.
  - With the bias fitted, the residuals are 0.008–0.030 mm. The scale errors stand.
  - The conclusion for D5 still holds: `u_cal` should be the homography's prediction error at the part.
- **D2 and M1 end to end (2026-10-26)** and **AT-2 (2026-10-27):**
  - Those were measured on flat parts with encoded-domain optics, so the 80.016 × 28.002 mm and Ø 4.208 / 4.211 figures don't describe a real 3 mm part. §3 does, for synthetic data.
  - Real-photo accuracy is still **unmeasured** (AT-3).

---

## 2026-10-28 · D4: reading a broken part and rebuilding it by mirror symmetry · SYNTHETIC, plus live Muse Spark

### 1. Geometry on exact outlines (`tests/unit/test_reconstruction_geometry.py`)

The hero bracket (80 × 28 mm, Ø 4.2 holes at ±30 mm) is the ground truth. It is broken with `broken_bracket`: a rough fracture with a millimetre meander plus sub-millimetre roughness, random but reproducible by seed.

- **Segments:**
  - Intact outline: 4 lines and 4 arcs, with no irregular segment, also with 0.01 mm noise.
  - Broken, seeds 0/3/7 with 0.01 mm noise: irregular segments only along the break, totalling more than 20 mm.
  - On the clean outline, moulded edges fit a line or an arc within ≤ 0.012 mm RMS; irregular segments miss by 0.25–0.36 mm.
- **Mirror axes:**
  - Intact part: both symmetry axes found, each with support > 0.99, angle within 0.01°, offset within 0.01 mm, both holes matched.
  - Broken part, fracture excluded:
    - Lengthwise axis: angle within 0.05°, offset < 0.02 mm, support > 0.99.
    - Also tested rotated −37° and +61° with noise.
- **A trap found and closed:**
  - **Symptom:** on a photo pipeline run, a vertical axis 3.4 mm off the true one kept 93 % of a score that mixed outline and holes, and the bracket was rebuilt **6.9 mm too long**.
  - **Cause:** the long straight edges can't fix the axis along the part, and the intact end's mirror lands where material is missing (no evidence).
  - **Fix:** outline support and hole agreement are now kept apart. An axis that more holes contradict than confirm is never used. `offset_ambiguity_mm` reports how far an axis can slide without losing support or a hole.
  - On a plate without holes, broken across its full width, the slide is > 0.5 mm and is reported as such (`AXIS_OFFSET_AMBIGUOUS`). The rebuilt length is then genuinely undetermined by the photo.
- **Completion:**
  - **Fit:** the broken bracket was rebuilt to **Hausdorff 0.004 mm** from the intact truth, area 2226.23 vs 2226.25 mm².
  - **Provenance:** OBSERVED and INFERRED runs, with UNCERTAIN only at the ≤ 4 junction points.
  - **Holes:** H0/H1 matched within 0.01 mm.
  - **Designed asymmetry:** a notch far from the break is reported ("real asymmetry") and kept as photographed, not filled.
- **A hole lost in the break is inferred** from its mirror image, once a surviving central hole pair pins the axis:
  - Diameter error ≤ 0.01 mm. Centre error 0.030 mm, against a reported 2σ of 0.043 mm, so U covers the error.
  - **Honest caveat:** the axis angle error (0.029°) was **4× its bootstrap σ**; U covered the error through its RMS term. 📋 D5 replaces the angle σ with a segment jackknife.

### 2. From a photo: the geometric rule (not AI), 24 photos

Conditions:
- Rendered photos of a 3.0 mm thick broken bracket, realistic optics (blur σ 0.8 px, noise 2), 12 fracture seeds × 2 camera poses (tilt 6/−4/12 without EXIF; flat-on with EXIF).
- Classical segmentation. The geometric interpretation rule, a labelled test backend.

| result | value |
|---|---|
| rebuilt correctly (mirror axis lengthwise, L and W within 0.1 mm) | **24 / 24** |
| length error | +0.008 … +0.040 mm |
| width error | −0.003 … +0.061 mm |
| hole Ø (truth 4.2) | 4.192 … 4.201 mm |
| reconstruction stage | 0.58 s median; about 1.4 s per photo end to end on 4 vCPU |

Two rule bugs were found by the campaign and fixed before this table. The table is the final run.
- **Over-fine tie-break:** supports of 1.00 vs 0.99 decided between the crosswise and lengthwise axes. The rule now ranks usable axes by holes matched, then material rebuilt.
- **Missed fracture piece:** a short smooth piece sandwiched inside a break wasn't labelled as fracture.

### 3. Live: SAM 3.1 + Muse Spark 1.3 (standard tier, `reasoning_effort` low)

Spark is sent the measured facts and two images. It is **not** told which segments the geometry finds irregular.

**Synthetic broken bracket photo** (tilt 6/−4/12):

| run | Spark's fracture pick | geometry's irregular set | axis | verification | rebuilt | Spark latency, cost |
|---|---|---|---|---|---|---|
| exploratory (production ledger) | S0–S3 | S0–S3 | A1 (lengthwise, "adds 106.8 mm²") | passed | 80.03 × 28.028 mm, Ø 4.194/4.196 | 10.1 s, $0.0131 |
| web UI | S0–S3 **+ S10** | S0–S3 | A1 | **S10 rejected** (matches its mirror 100 %) | 80.03 × 28.03 mm | 7.8 s, $0.0120 |
| live tests, ×2 | (asserted) | | | passed | L, W within 0.1 mm | |

- Spark named the part a "rectangular (two-hole) mounting plate", called both holes "mounting", and requested sensible caliper measurements (overall length, width, hole spacing and diameters, thickness, fracture extent).
- Its answer varies between runs. The verification caught the one over-pick, and the reconstruction stayed correct.

**The user's own test, 2026-10-28** (a photo of a rusty pipe pasted onto the mat PDF, 96 dpi):
- **Before the fix:**
  - Spark saw only a close-up crop of the traced region, a sliver of the pipe. It answered "narrow plastic clip fragment", `extruded_profile`, and a 5.4 × 29.6 mm STL was built.
  - The geometry's warnings (`PROFILE_PARTIAL`, `PROFILE_NONUNIFORM_COLOUR`) fired but didn't stop it.
- **After the fix (Spark now also gets the whole free zone, and the facts include the trace's share of the objects on the mat):**
  - **Geometric gate, not AI:** `TRACE_PARTIAL`. The trace covers 1 % of what's on the mat, so the job stops with no model and no API call.
  - **Spark, given the whole view:** "corroded steel pipe section", family `unsupported`: "Rusted 3D pipe, not flat uniform plate. Trace is 1 % of mat objects." So `FAMILY_UNSUPPORTED` refuses as well.

**Spend 2026-10-28:**
- **Production ledger:** $0.0906, from 10 SAM calls (5 from the user's own app runs) and 4 Spark calls.
- **Live tests (temporary ledgers):** about $0.04.
- **Spark per call:** $0.012–0.026, depending on image size; the tall crop-only image cost 9,579 input tokens.

### 4. Not yet measured

- A real photo of a real broken part (AT-3, then M2's "two real broken parts").
- Spark's agreement rate over many parts. Three readings of one synthetic part are not an accuracy figure.
