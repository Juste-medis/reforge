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

---

## 2026-11-02 · A 20-photo test set from stock photos of real parts; four robustness fixes · SYNTHETIC COMPOSITES, plus live SAM 3.1 + Muse Spark

**Why:** the user's own test uploads were all one web image of a rusty pipe (on and off the mat PDF), correctly refused. There is still no real photo of a real part on the printed mat (AT-3).

**Conditions (`backend/tools/make_test_photos.py`; images and truth files in the gitignored `tmp/tests/`)**
- **Real:** each part's texture and outline come from a stock photo (Unsplash License; author and page in each truth file). The sources are 4 guitar picks on wood, open-end spanners and keys on black, a skeleton key, and a 200 mm adjustable wrench.
- **Chosen, so exact ground truth:** the size (longest side 30–200 mm), thickness (0.8–6 mm), placement and any break. A side-broken pick's intact outline is first made exactly symmetric (its intersection with its mirror image), because a stock photo taken at an angle makes a symmetric part look asymmetric.
- **Plus 7 rendered plastic parts in flat colours:** the hero bracket (intact, and broken with seeds 0 and 3), a washer, a slotted link, an L-plate, and a 50 mm square flange whose break took two of its four holes.
- **Camera:** the test harness (pinhole, the part's height parallax, linear-light blur σ 0.9 px), with colour, a mild illumination gradient, noise σ 1.5, JPEG q92 and EXIF 52 mm (the 2× lens of PLAN §5.2), at 3024 × 4032 px.
- **Not modelled:** shadows, lens distortion, phone sharpening. Every file says SYNTHETIC COMPOSITE in its EXIF description.

### 1. Offline: classical segmentation + geometric rule (not AI), final code

| image | truth L × W (mm) | outcome | ΔL, ΔW (mm) | outline Hausdorff / p95 (mm) | holes found / truth (doubted) |
|---|---|---|---|---|---|
| 01 pick, red | 18.72 × 29.07 | built | −0.019, −0.027 | 0.552 / 0.016 | 0 / 0 |
| 02 pick, blue | 18.83 × 28.86 | built | −0.041, −0.072 | 0.611 / 0.042 | 0 / 0 |
| 03 pick, green | 25.33 × 31.28 | built | −0.008, −0.035 | 0.812 / 0.334 | 0 / 0 |
| 04 pick, white (low contrast) | 22.00 × 29.99 | built | −0.074, −0.310 | 1.543 / 0.891 | 0 / 0 |
| 05 pick, red, side broken | 17.10 × 29.13 intact | not rebuilt | (as photographed) | | 0 / 0 |
| 06 pick, green, side broken | 24.21 × 29.60 intact | not rebuilt | (as photographed) | | 0 / 0 |
| 07–10, 13 spanners and wrench (metal) | | built | up to −5.1, −9.8 | up to 25.4 / 7.8 | spurious 1–10 kept (2–47 doubted) |
| 11 key (metal) | 39.52 × 45.39 | built | −0.366, −0.015 | 0.328 / 0.179 | 1 / 1 |
| 12 skeleton key (metal) | 36.52 × 85.78 | built | −0.026, −0.067 | 0.386 / 0.046 | 1 / 1 (2) |
| 14 bracket | 80.00 × 28.00 | built | +0.010, +0.024 | 0.013 / 0.009 | 2 / 2 |
| 15 bracket, broken | 80.00 × 28.00 intact | rebuilt | +0.030, +0.039 | 0.020 / 0.016 | 2 / 2 |
| 16 bracket, dark, broken | 80.00 × 28.00 intact | rebuilt | +0.016, +0.008 | 0.013 / 0.006 | 2 / 2 |
| 17 washer | 30.00 × 30.00 | built | +0.036, +0.041 | 0.031 / 0.025 | 1 / 1 |
| 18 slotted link | 63.03 × 44.00 | built | +0.003, +0.003 | 0.012 / 0.008 | 3 / 3 |
| 19 L-plate | 60.49 × 57.64 | built | +0.003, −0.001 | 0.136 / 0.010 | 3 / 3 |
| 20 flange, broken | 50.00 × 50.00 intact | rebuilt, both lost holes inferred | +0.024, +0.026 | 0.033 / 0.021 | 5 / 5 |

- The outline distances are against the intact part for rebuilt parts.
- **The picks' Hausdorff of 0.5–0.8 mm is a real local defect:** a glossy highlight at the edge pulls the traced edge about 0.5 mm inwards over a short stretch. The p95 stays at 0.02–0.04 mm on the red and blue picks.
- **Metal tools are out of scope** (not single-colour, not uniform thickness). Polished steel near paper brightness defeats the classical boundary.

### 2. Live: SAM 3.1 + Muse Spark 1.3 (standard tier, `reasoning_effort` low), final code, 20 images

- **Built, 14 images.** 01–06 match the offline numbers within 0.03 mm; the white pick is better with SAM (−0.053, +0.021). Also 11 key, and 14–20 (rebuilt parts within 0.04 mm of the intact truth, both of the flange's lost holes inferred).
- **Refused `FAMILY_UNSUPPORTED`, 6 images (07, 08, 09, 10, 12, 13).** Spark's reasons, e.g. "Drop-forged steel wrench with dished handle and tapered jaws", "3D metal key with round shank, turned collar and thick bit".
- **Spark named the parts** "red guitar pick", "flat washer", "slotted flat link bar", "L-shaped mounting bracket", "square mounting flange plate", "rectangular mounting strap plate". The side-broken picks it called "red petal-shaped fragment" and "green petal fragment".
- **Spark is not consistent on borderline metal parts.** An earlier run on the first 16 images (before fixes 3 and 4) accepted 08 and refused 11 (`multi_view`); the final run did the opposite.
- **Spend:** this run $0.370 for 20 SAM and 20 Spark calls ($0.015–0.021 per image). The earlier 16-image run was about $0.26. Ledger total for 2026-11-02: $0.69, including the user's own runs.

### 3. Four defects the set exposed, fixed the same day (before → after)

1. **Reflections taken for holes, and a crash.**
   - **Before:** a hole was any paper-light region along the paper→part colour line. Polished steel qualifies, so the classical path found up to 57 candidates on the adjustable wrench, and three images failed with `SPEC_INVALID` (holes too close to an edge or to each other).
   - **Measured separation** (the hole's core against the paper within 15 mm, lightness half-weighted): real holes ΔE p90 ≤ 3.1 with compactness ≥ 0.78; reflections and engravings ΔE p90 ≥ 5.6, compactness mostly < 0.5.
   - **Fix:** a candidate that isn't paper-coloured (p90 > 5) *and* isn't round (< 0.75) is doubted: excluded, UNCERTAIN, "confirm to include", like glare. A hole the solid can't be built with is excluded the same way, instead of failing the spec.
   - **Caveat:** both thresholds are calibrated on composites only; shading inside a real hole may raise its ΔE (which is why round holes are kept regardless). To be checked at AT-3.
2. **A confident wrong rebuild of a side-broken pick.**
   - **Before:** the break was about 40 % of the outline. Every axis then reached 100 % support on what was left, and the rule took the one adding the most material: rebuilt 29.9 × 39.6 mm for a 17.1 × 29.1 mm pick. On a rendered teardrop, 3 seeds of 4 came out 28–31 mm wide for 26 mm.
   - **Fix:** the mirror must be confirmed by at least as much outline (plus matched holes' circumference) as it invents (`AXIS_UNDERSUPPORTED`). The picks are now built as photographed, and the report says why.
3. **The flange's rebuilding axis wasn't a candidate, then a diagonal was used.**
   - Candidates came from hole *pairs*; the bore alone was on the vertical axis.
   - **Fix, part 1:** axes through each hole centre are now candidates. Ties at 100 % support rank by confirming outline. A tie in hole votes counts against an axis.
   - The square's diagonal, a real symmetry, then rebuilt only part of the break, leaving a corner off (Hausdorff 10 mm).
   - **Fix, part 2:** every candidate is trial-rebuilt on the irregular segments. The rule uses only axes whose rebuild covers the break and is confirmed. Any interpreter's choice must pass the same checks (`AXIS_PARTIAL`, `AXIS_UNDERSUPPORTED`).
4. **An axis angle the fit couldn't correct.**
   - **Before:** the flange's evidence is straight edges, which give every midpoint on the current axis. The axis stayed 0.37° off, and the flange came out 0.25 mm too large against a stated 2σ of 0.205 mm.
   - **Fix:** a final least-squares fit of angle and offset on the mirror images' distance to the outline. Result: 90.025°, +0.024/+0.026 mm, 2σ 0.015 mm.

Six offline tests cover these: a streak doubted, holes left out, the side-broken pick (3 seeds), the bracket's evidence, the flange rebuilt, and a diagonal rejected. 142 pass.

### 4. Still open

- **The flange's inferred hole centres are 0.058 mm off, against a mirror-only 2σ of 0.031 mm.** That U leaves out the source hole's own error; 📋 the Confidence Engine (D5) adds it.
- **The composites prove the pipeline on real textures, not on real photos:** no shadows, no phone processing. AT-3 is still needed.
- **Spark's family verdict varies between runs on borderline (metal) parts.** No accuracy rate is claimed.

## 2026-11-03 · First real photos of the printed mat · REAL PHOTOS, classical + rule offline, plus live SAM 3.1 + Muse Spark on two

**Conditions**
- **Phone:** iPhone 15 Plus, main camera, 1× (26 mm equivalent), f/1.6, 5712 × 4284 px.
- **Setting:** indoor office light, hand-held. The user's own photos, in gitignored `tmp/realpictures/`.
- **Mat:** A4 v1, printed by the user. Print scale is **unverified**: the two 100 mm bars have not been calipered yet.
- **Code:** as of this entry.

**Objects** (8 photos)
- a glass perfume vial, 3 photos (1058–1060)
- a stamped metal heart, about 52 × 48 mm, with a black plastic shard beside it (1061)
- a small screwdriver (1062)
- a digital caliper, 3 photos (1063–1065)

Only the heart is in scope: a flat part of roughly uniform thickness.

### 1. Calibration on a real print

| photo | markers used / found | fit RMS (mm) | leave-one-out RMS (mm) | px/mm | outcome |
|---|---|---|---|---|---|
| 1058 vial, near top-down | 11 / 12 (marker 0 rejected) | 0.191 | 0.283 | 16.9 | calibrated |
| 1059 vial, oblique | 10 / 10 | 0.283 | 0.369 | 15.0 | calibrated, `CAL_STRONG_TILT` 1.79 |
| 1060 vial, oblique | 11 / 12 | 0.255 | 0.320 | 14.3 | calibrated, `CAL_STRONG_TILT` 1.88 |
| 1061 heart, near top-down | 11 / 12 (marker 0 rejected) | 0.238 | 0.352 | 17.3 | calibrated |
| 1062 screwdriver, mat on a binder | 3 / 11 agree | — | — | — | refused, `CAL_MAT_NOT_FLAT` (markers off a flat sheet by up to 1.6 mm) |
| 1063 caliper | 8 / 12 | 0.436 | 0.876 | 16.8 | calibrated |
| 1064 caliper, very oblique, mat on a binder | 3 / 7 agree | — | — | — | refused, `CAL_MAT_NOT_FLAT` (up to 1.5 mm) |
| 1065 caliper | 5 / 6 | 0.251 | 0.866 | 17.0 | calibrated, markers clustered |

- **The real fit residual is 30–70× the synthetic one** (0.006–0.007 mm on composites). It is above the 0.15 mm warning on every photo.
- **Not lens distortion.** Adding a radial k1, k2 term to the fit leaves the RMS almost unchanged: 0.312 → 0.310 mm on 1058, 0.329 → 0.305 mm on 1061.
- **The paper isn't flat.**
  - Marker 0, at the top-left corner, is off by about 0.5 mm in the same direction on 1058 and 1061, and its own corners disagree by 0.4 mm. That is a lifted corner.
  - On a binder the markers are off by up to 1.6 mm.
- **In-photo check of the printed 100 mm bars.** Tick centres were located in each calibrated photo. Bars and markers share the print, so this tests the fit's local consistency, not the print scale.
  - On the two near top-down photos the X bar reads 100.042 and 100.007 mm.
  - The Y bar reads 100.443 and 100.355 mm: **about +0.4 %, the same on both photos**. That is systematic, consistent with a non-uniform paper feed or a bow. Which one is unconfirmed: the caliper reading of the Y bar would tell.
  - On the oblique photos the X bar reads +0.55 to +0.58 mm.

### 2. Outcomes

- **Offline, $0** (classical segmentation and geometric rule, not AI)
  - **Vial ×3:** a model is built. The classical path has no family check.
  - **Heart:** 52.81 × 47.52 mm, no holes.
  - **Caliper ×2:** refused, `TRACE_PARTIAL` (9 % and 2 %). It is a multi-coloured object.
  - **1062 and 1064:** refused at calibration, as above.
- **Live, $0.044** (SAM 3.1 + Muse Spark 1.3, standard tier)
  - **Heart:** built, 52.04 × 47.52 × 1.5 mm. SAM confidence 0.992.
    - Spark called it a "heart-shaped souvenir plaque" (`extruded_profile`) and claimed a break. Its evidence was "a separate black shard on the mat", which is an unrelated fragment.
    - Verification rejected all four fracture picks as smooth (fit residual 0.019–0.055 mm, `FRACTURE_SMOOTH`), so nothing was rebuilt.
    - No candidate axis reached the 0.6 support needed to be shown. The best near-vertical axis has 0.60 on the classical trace: a real stamped heart isn't mirror-symmetric to 0.3 mm.
  - **Vial:** refused, `FAMILY_UNSUPPORTED`. Spark: "glass perfume spray vial (revolved): 3D cylinder not flat plate; trace is label portion only".
- **The two heart outlines differ by up to 0.77 mm, along the left half only** (p50 0.11 mm). That side shows the part's side wall and a soft shadow. Which trace is right is **unverified until the caliper reading**.
- **The user's UI runs this morning**, reconstructed from the job folders and the ledger:
  - vial, classical: model built;
  - vial, SAM + Spark: `FAMILY_UNSUPPORTED`;
  - caliper, classical: `TRACE_PARTIAL`.
  - Failed jobs left no trace of their error. They now do (`error.json`, `request.json`).

### 3. Second series, same day: mat flat on a table, shot from above (`tmp/realphotos.2/`, 5 photos)

**Calibration**
- 12 of 12 markers on all five photos, perspective ratio 1.01–1.04.
- Fit RMS 0.190–0.254 mm, still above the 0.15 mm warning. On a flat table, shot from above, this residual is not a tilt effect.
- Bar check: X +0.16 to +0.34 mm, Y +0.13 to +0.21 mm over 100 mm.
- On all 11 calibrated photos of both series, every bar reads long: +0.01 to +0.58 mm, mean about +0.25 mm. A sheet bowed up by about 0.5 mm inside the marker ring would do that (magnification 245/244.5 at this camera height). Unconfirmed.

**Live, $0.079 for 11 calls**, including one SAM re-run of photo 1061 at 2 mm (SAM 3.1 + Muse Spark 1.3, standard tier)
- **Heart** (2.0 mm, the user's caliper): built, SAM confidence 0.992.
  - Spark called it a "heart-shaped Disneyland tag" broken at S18, "attachment point broken away". S18 is the burr on the left lobe, which the geometry also calls irregular. A missing hanging loop is plausible, but unverified.
  - Spark called the heart mirror-symmetric, but offered no axis. None was offered: the best support is ≤ 0.52, because this stylised heart's tip sits off-centre. The result is `AXIS_MISSING` and a build as photographed.
- **Vial:** `FAMILY_UNSUPPORTED` (revolved).
- **Cone:** `FAMILY_UNSUPPORTED`, "tapered metal ferrule".
- **Key:** `FAMILY_UNSUPPORTED`, "EMKA small metal key … milled groove and cut teeth".
- **Caliper:** `TRACE_PARTIAL` (1 %).
- A first attempt on the key stopped with `META_ERROR` after 17 ms. The test script, not the app, reused one API client across two event loops; the rerun alone succeeded.

**Classical fallback (not AI) on the heart (1066):** the cast shadow below the tip is traced as part, making the heart 4.4 mm too tall. SAM follows the metal edge.

### 4. Against the caliper (AT-3, the user's readings)

Photo values simulate the caliper on the traced outline. For the height, one jaw rests on both lobe tops (the convex-hull edge over the notch) and the other on the tip. The width is measured across the lobes, perpendicular to that edge.

| | caliper | photo 1061 (SAM) | photo 1066 (SAM) | photo − caliper |
|---|---|---|---|---|
| height, tip to lobe tops | **45.14** (first given as 46) | 45.55 | 45.45 | **+0.41 / +0.31** |
| width across the lobes | **53** (no decimals; first given as 25) | 52.07 | 51.84 | **−0.93 / −1.16** |
| thickness | 2 | entered | entered | — |

**Repeatability and sensitivity**
- The two photos agree to 0.10 mm on height and 0.23 mm on width.
- Turning the jaws ±5° changes the height by up to 1.7 mm (the tip is off-centre), the width by 0.25 mm or less.

**Checks on the photo side** (1066)
- **Print scale, from the sheet itself.** Through the marker calibration, the A4 sheet's edges against the yellow table measure 210.41–210.58 × 296.60–296.88 mm on the five photos of the second series (1066's top edge was too poorly visible and is excluded). That is 210 × 297 within 0.3 %: the mat is printed at 100 %. The user's bar readings ("50 and 50") cannot be tick-to-tick lengths and are not used.
- **Edges at the width contacts.** At 60 px/mm, the traced edge sits on the metal edge on the left (0.04 mm) and 0.23 mm outside it on the right, in a shadow. That makes the width read larger, not smaller.
- **The burr isn't behind the height difference.** Smoothing it out changes the simulated height by 0.04 mm.
- **No direction is 53 mm wide.** The traced heart's largest extent in any direction is 52.10 mm (1066) and 52.51 mm (1061). A caliper cannot read more than that on a flat part.

**Verdict: AT-3 partly met.**
- ✅ Height is within the ±0.5 mm target on both photos.
- ❌ Width misses it by about 1 mm against a whole-mm reading. The miss has the opposite sign to the height error. An isotropic cause (print scale, height correction) cannot do that, and the sheet check rules out an anisotropic print. The width reading is therefore the first suspect and is to be repeated to 0.01 mm. If it stands, the photo under-reads this part's width by about 2 %, for an unexplained reason.

### 5. Not yet measured

- **AT-3 width:** three caliper readings of the heart's full width, to 0.01 mm.
- **Why every bar reads long in the photos.**
- **A part with holes** (hole Ø, the other half of AT-3).
- **Edge spread on textured metal:** the estimator went negative (−0.37 mm on 1066). It is now reported as unmeasured; it only affects the hole-curvature correction.

## 2026-11-03 (afternoon) · The finished product, tested end to end · SYNTHETIC examples and REAL photos, live SAM 3.1 + Muse Spark 1.3 (standard tier, effort low)

Conditions: the new UI (production build) served by the API on the VPS, driven by headless Chromium 156 (Playwright
driver, a verification tool outside the repo). Desktop 1440 × 900, tablet 834 × 1112, phone 390 × 844 and 360 × 800
emulated. Live AI calls on the project key; the costs below are the ledger's.

### 1. Live runs through the API and the UI

The three bundled examples are SYNTHETIC: rendered parts on the rendered mat, shot by the test harness's camera, so
their truth is exact. The other runs are the user's REAL photos (iPhone 15 Plus, `tmp/realphotos.2/`).

| Input | Job | Outcome | Size (smallest rectangle) vs truth | Holes | Time / AI cost |
|---|---|---|---|---|---|
| broken-bracket (UI) | `ea5b7c44290f` | Rebuilt, 107 mm² mirrored | 80.03 × 28.04 vs 80 × 28 (intact) | 2 × Ø4.18 vs 4.2 | 31 s / $0.0175 |
| broken-flange (API) | `b8dc78fe2e63` | **Not rebuilt**: see §2 | 50.01 × 40.42 (as photographed) | 3 observed | 40 s / $0.0231 |
| broken-flange (API, after the §2 fix) | `deecc951a3e2`, `9eda9a779a4d` | Rebuilt, 536 mm² | 50.02 × 50.02 vs 50 × 50 (intact) | 3 observed + 2 inferred Ø5.495, 5.497 vs 5.5 | $0.018–0.019 each |
| slotted-link (API) | `f0978dc3f9a0` | Measured, nothing to rebuild | 70.01 × 18.02 vs 70 × 18, placed at 30° | 2 × Ø5.99 vs 6, slot traced | 24 s / $0.016 |
| REAL heart, IMG_1066 (UI upload) | `86e2d4b54954` | Built as photographed; 2 doubtful holes left out, export gated | 48.95 × 43.50 ±0.84 (smallest rectangle, so diagonal on a heart) | — | 39 s in the browser |
| REAL ferrule, IMG_1068 (UI upload) | `922cdd703c96` | Refused `FAMILY_UNSUPPORTED`: "3D tapered metal ferrule, not flat uniform plate" | — | — | 37 s in the browser |
| REAL photo without the mat, IMG_1050 (UI upload) | `3306d5df6176` | Refused `CAL_MARKERS_INSUFFICIENT` before any AI call | — | — | 3.9 s, $0 |

- **Stage timings** (bracket): the SAM 3.1 segment took 4.7 s and Muse Spark's reading 23 s, out of 31 s.
- **Ledger, all time:** median latency 3.0 s for SAM 3.1 (74 calls) and 12.6 s for Muse Spark (62 calls, p90 21.4 s).
  All 62 Spark answers parsed against the strict schema.

### 2. A real failure of the AI's axis choice, and the fix

On `b8dc78fe2e63`, Muse Spark found the break correctly (S0–S7, the jagged right edge) but chose axis A0.
- **Why A0 couldn't work:** A0 is the flange's top-bottom mirror, a real symmetry of the part, but it maps the break
  onto itself.
- **What verification did:** it rejected all eight fracture picks (`FRACTURE_MATCHES_MIRROR`, 65–97 % of each edge
  matched its own mirror image), so nothing was rebuilt and nothing was invented.
- **The axis that would work:** A2, the vertical axis through the bore, passed every check in the trial rebuild.

**Fix** (`reasoning/reconstruct.py`):
- **When it applies:** the AI calls the part broken and names its fractures, but its axis yields no rebuild.
- **What happens:** the geometric rule's axis gets a second chance. It must pass the same checks, with the AI's own
  fracture picks re-verified under it.
- **How it is reported:** an `AXIS_CORRECTED` note. The AI's analysis is kept as it answered.
- **Tests:**
  - a test interpreter choosing the crosswise axis reproduces this run;
  - another one chooses a diagonal axis (`AXIS_PARTIAL`);
  - both end rebuilt with the two lost holes at Ø 5.5 ± 0.05;
  - a third test checks that geometry never rebuilds a part the reading calls intact.

The two later live runs didn't exercise the fix: Spark chose A2 itself both times. So the fix is **✅ tested offline**
on this exact case, and **not yet observed live**.

### 3. The Confidence Engine (D5) against known truths

A 2σ estimate per dimension, from the photo's error budget (`spec/confidence.py`: calibration leave-one-out RMS, print
scale, edges, height correction; a mirror term for INFERRED geometry).

| Case | Dimension | Error | ±U (2σ) | Inside? |
|---|---|---|---|---|
| synthetic bracket | length, width | +0.03, +0.04 | 0.42, 0.20 | yes, yes |
| synthetic bracket | holes Ø | −0.02, −0.02 | 0.12 | yes |
| synthetic flange (rebuilt) | inferred holes Ø | −0.005, −0.003 | 0.12 | yes |
| REAL heart, IMG_1066's budget | height 45.14 (caliper) | +0.31 (1066), +0.41 (1061) | 0.83 | yes, yes |
| REAL heart, IMG_1066's budget | width 53 (caliper, no decimals) | −1.16 (1066), −0.93 (1061) | 0.84 | **no, no** |

- **On synthetic images the check is weak.** The rendered mat has an exact scale, so the assumed ±0.5 % print-scale
  term dominates U.
- **On the real part:** 2 of 4 comparisons fall inside. The 2 outside are the width whose caliper reading is suspect
  (§4 of the morning entry).
- **Coverage is not established yet.** Every surface calls these values estimates.

### 4. The exports, checked by OpenSCAD itself

`backend/tools/check_exports.py`: OpenSCAD's WASM build (`openscad-wasm-prebuilt` 1.2.0) compiles each job's
`model.scad`, and the result is compared with `model.stl`.

| Job | Holes | OpenSCAD | Watertight | Volume (STL / SCAD) | Rel. diff | Bounds | Genus |
|---|---|---|---|---|---|---|---|
| bracket `ea5b7c44290f` | 2 | 4.1 s, no warnings | yes / yes | 6602.875 / 6602.875 mm³ | 5 × 10⁻⁸ | identical | 2 / 2 |
| flange `deecc951a3e2` | 5 (2 inferred) | 10.6 s | yes / yes | 5983.129 / 5983.125 | 7 × 10⁻⁷ | identical | 5 / 5 |
| link `f0978dc3f9a0` | 3 (1 slot) | 6.7 s | yes / yes | 4089.279 / 4089.278 | 4 × 10⁻⁷ | identical | 3 / 3 |
| REAL heart `86e2d4b54954` | 0 | 0.2 s | yes / yes | 3273.388 / 3273.388 | 5 × 10⁻⁸ | identical | 0 / 0 |
| flange, holes +0.2 mm (served by the API) | 5 | — | yes / yes | 5941.237 / 5941.259 | 4 × 10⁻⁶ | — | 5 / 5 |

### 5. The UI in a real browser (headless Chromium)

| Check | Result |
|---|---|
| Home, new repair and my repairs at 1440, 834 and 390 px | no console errors, no horizontal overflow (after fixing a hero background and a table) |
| Result page at 390 and 360 px | no page overflow; the wide tables scroll inside their cards |
| An example run from the home page, with AI | real stage list; the result renders the 3D view, the before/after slider, the evidence and the downloads; known-answer card: "within ±U: yes" |
| Upload of a real photo, with AI | client checks (format, 4284 × 5712 px), then live stages, then the result; the uncertain items lock the downloads until acknowledged |
| Meta API unreachable (a server pointed at a closed port) | "The AI service didn't answer"; "Run again without AI" re-runs the stored photo, rebuilt, labelled `classical-fallback` |
| A shell script named `.jpg`; a HEIC file; an empty form | blocked in the browser with the reason; nothing is sent |
| Out-of-scope object; photo without the mat | refusal screens with the reason and what to do |
| Accessibility audit, axe-core 4.14.0 (WCAG 2 A/AA, 2.1 AA, best practice): home, new repair, my repairs, a result with its technical details, a refusal | 0 violations on every screen (30–49 rules passed per screen), colour contrast included |
| Content-Security-Policy | blocks injected inline scripts: the audit had to bypass it to run |
| A job saved before today (no uncertainty in its report) | an "older version" screen instead of a crash |
| Offline suite / live suite | 170 passed / 3 passed (`pytest -m live`: SAM 3.1 and Muse Spark on the new pipeline) |

### 6. Deployment recipe

- **Build:** `docker build` of the new `Dockerfile` succeeds; the image is 1.75 GB.
- **Run:** `docker run -p 127.0.0.1:8013:8000` with no key serves the UI (200) and `/api/health`. It runs a no-AI job on
  the slotted-link example: valid, 70.009 × 18.018 mm, identical to the local run.
- **Image hygiene:** it runs as uid 10001 and contains no `.env`.

### 7. Not measured

- Real phones and tablets: only Chromium's mobile emulation was used; Safari and iOS were not tested.
- Screen readers: not tested with one. The automated audit above checks labels, roles and contrast, not the experience.
- WebGL on real GPUs: headless Chromium rendered with SwiftShader.
- Coverage of ±U on more real parts, and hole diameters on a real part (no real part with holes yet).
