# RE-FORGE AI: progress log

**Resume here:** read `docs/PLAN.md`, then the newest entry below.

Status labels:
- ✅ implemented and tested
- 🟡 implemented, unverified
- 🧪 experimental
- 📋 planned
- ⛔ unsupported

---

## 2026-10-22 (Thu): Session 1, discovery and planning

**Done**
- Environment inventory:
  - Ubuntu 25.10, 4 vCPU, 15 GiB RAM, no GPU, 35 GB free disk.
  - Python 3.13 without pip, Node 20.19, Docker 29.7 (user is in the docker group), git.
  - OpenSCAD isn't installed (the apt candidate is 2021.01). No Python CV or geometry libraries are installed.
- Researched the Meta Model API from the official docs (see PLAN §1.2):
  - Model IDs: `sam-3.1`, `muse-spark-1.3`, `muse-wonder-1.0`, `muse-image-1.0`.
  - Endpoints, pricing and rate limits.
  - Two constraints found: Muse Image has no mask inpainting, and Muse Code has no documented headless mode.
- Wrote `docs/PLAN.md` v0.1 (draft) and the local session notes.

**Code:** none, by design. Waiting for (1) plan approval and (2) the official rules on prior work and AI tools.

**Open questions** (PLAN §12):
- plan approval
- caliper, printer and hero part
- daily availability
- contributor tier
- pre-kickoff code

**Next:** after approval and the kickoff (Mon 26 Oct, 17:00 Paris), run D1 from PLAN §9:
- read the rules
- initialise the repo
- run the API spike on the §1.2 unknowns
- build the mat PDF

---

## 2026-10-23 (Fri): Session 2, plan approved; preparation phase

**Decisions**
- PLAN approved, now v0.2, with 8 directives at the top of `PLAN.md`:
  - Primary demo: a flat, mirror-symmetric part with mounting holes. Gears are secondary.
  - The physical journey (broken part → STL → print → fit) is a key objective.
  - Protect the core MVP.
  - The Confidence Engine is central.
  - Standard-tier models by default.
  - No project code before the rules are checked.
- **Overriding goal:** an outstanding working demo over feature count.

**Rules check:** still not published on the official pages (checked 2026-10-23). So: no project code yet.

**Done**
- ✅ **Tooling,** all user-space and checksum-verified: uv 0.13.5, Python 3.12.15 (uv-managed), Node 24.22.1 LTS. The system Node 20 (EOL) and Python 3.13 are untouched.
- ✅ **Python stack smoke-tested** in a throwaway env:
  - OpenCV 4.14 ArUco detection works through a perspective warp.
  - manifold3d: a 2-hole plate is watertight with the exact expected volume and genus = 2, built in 6.3 ms.
  - The `meta-sam-parser` API, scikit-image sub-pixel contours and the OpenAI SDK Responses/Images APIs are all present.
- ✅ **Frontend versions checked:**
  - TypeScript pinned to 5.9, because `openapi-typescript` needs `^5`.
  - Vitest 5 needs Node ≥ 22.12, hence Node 24.
- ✅ **Docker images** verified to exist (not pulled): `python:3.12-slim`, `node:24-slim`, `openscad/openscad:latest`, `caddy:2`.
- ✅ **SAM mask placement** mostly resolved from the parser source and docs: masks are box-local at native resolution. Live confirmation pending.
- ✅ **Contributor-tier terms** confirmed in Meta's docs: content may be used to train Meta models, and retention isn't stated. Policy recorded in PLAN §1.2.
- 🟡 **`prep/verify_meta_api.py`:** throwaway and git-ignored; synthetic image only; standard tier; about $0.01. Its offline parts passed a self-test; the live run is blocked on the API key.
- ✅ **Repo hygiene:** git initialised (no commits). `.gitignore` covers `.env*`, `prep/` and `tmp/` (checked with `git check-ignore`). `.env.example` added.
- ✅ **Docs:** `docs/ENVIRONMENT.md`, `docs/DEMO_PART_GUIDE.md` and `docs/ground_truth_template.csv` added; PLAN v0.2; session notes updated.

**Blocked / waiting on the user**
- An API key in `.env`, then run `~/.local/bin/uv run prep/verify_meta_api.py` (or have the assistant run it).
- The official rules (re-check daily).
- Caliper, printer, hero part, daily availability.

**Next**
- As soon as the key exists: run the verification and record its findings in PLAN §1.2 (unknowns 2–6) and here.
- At kickoff, or earlier if the rules explicitly allow it: D1 per PLAN §9.

---

## 2026-10-26 (Mon): Session 3, Official Rules published; kickoff day

**Rules.** They were found on the waiver page, dated 2026-10-25 and titled "Hackathon Terms & Conditions ('Official Rules') and Event Waiver". Summary in PLAN §1.1:
- **Prior work:** not explicitly allowed, so project code starts at the kickoff (17:00 Paris), per directive 6.
- **Judging is weighted:** Impact 30 % · Use of Meta AI Tooling 25 % · Technical Depth & Execution 20 % · Demo 25 %, including video quality and "holds up live".
- **Assistance:** third-party technical assistance is allowed if the participant owns all rights. AI assistance will be disclosed in the submission.
- **Open source:** allowed if licences are followed.
- **Licence to organisers:** they get a perpetual licence, and nothing shared is confidential. So no employer code or data goes in.
- **Credits:** $150 per accepted participant.
  - Claim via the form in the "know before you go" email, with the Team ID.
  - A payment method is required on the account.
  - Credits are applied within about 2 business days and don't expire once applied.
- **Submission portal:** requires a Cerebral Valley login, so its fields are 🔎.

**Plan v0.3:** M3 is re-ranked by the official weights. The new top candidate is (g) SAM 3.1 video capture → multi-frame metrology (empirical ±U). The core MVP and the directives are unchanged.

**Kickoff automation:** one-shot job `496b1799`, scheduled in the assistant session for 26 Oct 16:03 UTC (17:03 Paris).
- It re-reads the docs.
- If the key exists, it runs the API verification.
- It then starts D1 → D2, offline-first.
- It's session-only: it won't fire if that session has been closed.

**Waiting on the user:**
- acceptance email (by 14:00 Paris), then claim the credits
- API key in `.env`
- the submission-portal fields
- hero part, caliper, printer, daily availability
- approval for local git commits

**Next:** D1 at the kickoff per PLAN §9.

---

## 2026-10-26 (Mon, from 17:42 Paris): Session 4, coding started after the kickoff (D1)

**Context**
- The Participant Guide (pasted by the user) is now in PLAN §1.1 (v0.4). Key requirements:
  - public repo
  - new work only, identifiable as such
  - a 3-minute video
  - "Simple Image Analyzers" is an anti-project
  - bonus prizes
- The kickoff job didn't survive the session restart. Coding started manually at 17:42 Paris, after the 17:00 kickoff.
- Possible ambiguity: the guide's "Building period: Oct 27 – Nov 4" (PLAN §1.1). 🔎 Confirm in Discord.

**Built today** (`backend/`, uv project, Python 3.12, `uv.lock`):
- ✅ **Scaffold:** `pyproject.toml` with deps numpy, opencv-contrib-headless `<5` and fpdf2; dev deps pytest, pypdfium2 and ruff; ruff config; pytest markers (`live` excluded by default).
- ✅ **`reforge/capture/mat.py`:**
  - One layout drives both the PDF and the detector: 12 DICT_4X4_50 markers, A4 IDs 0–11, Letter IDs 12–23.
  - The free zone is 142×229 mm (A4), with two 100 mm caliper check bars.
  - Includes a vector PDF writer, an anti-aliased projective renderer, and the `reforge-mat` CLI.
- ✅ **`reforge/capture/calibration.py`:**
  - Sub-pixel ArUco detection with automatic page inference, then RANSAC followed by a least-squares homography.
  - Reports fit RMS, max and leave-one-marker-out RMS.
  - Applies the per-axis print-scale correction from the bar readings (range-checked).
  - Reports local px/mm and the perspective ratio.
  - Typed errors: `CAL_MARKERS_INSUFFICIENT`, `CAL_LAYOUT_AMBIGUOUS`, `CAL_SCALE_OUT_OF_RANGE`, `CAL_HOMOGRAPHY_FAILED`, `IMAGE_INVALID`.
  - Warnings: partial or clustered markers, high residual, low resolution, strong tilt, overexposed background.
  - Includes `rectify()` to a metric top-down view.
- ✅ **Tests:** 22 pass and ruff is clean.
  - The printed PDF is verified at 600 dpi (page size, marker centres and sizes).
  - AT-1 is verified on SYNTHETIC views (tilt 0–25°, blur, noise, occlusion, a 97 % print, the Letter mat, rectification). Numbers are in `docs/EVALUATION.md`.
- ✅ **Printable mats:** `assets/mat/reforge-mat-A4-v1.pdf` and `-Letter-v1.pdf`, visually checked.

**Design corrections made from evidence:**
- **PDF geometry test:** it now checks marker centres and sizes. Corners shift by about 1 render pixel from rasteriser snapping, measured at 300/600/1200 dpi.
- **Glare check:** "glare" was really "white paper". Calibration now only flags an overexposed background; glare on the part moves to segmentation (D2), where the mask is known.
- **`u_cal`:** must be the homography's prediction error at the part, not the corner residual (EVALUATION.md). 📋 D5.

**Not done / blocked**
- 🔎 The API spike is still blocked on `.env`.
- No git commits yet (awaiting the user's OK).

**Next (offline, no key needed)**
- D2: band refinement, hole detection and contour extraction on synthetic part scenes (with a classical test-backend mask, labelled as such).
- D3: PartSpec, manifold3d builder, mesh validation.
- The SAM client gets written against a *real* recorded response as soon as the key exists.

**User actions**
- Print the mat and measure both bars.
- Photograph the intact parts.
- `.env` key, credits claim, submission-portal fields.
- Licence choice and commit approval.

---

## 2026-10-26 (Mon evening): Session 4, continued: D2 and D3 offline, M1 pipeline wired

**Built** (`backend/`). The suite has **68 tests passing** and ruff is clean.

- ✅ **`vision/refine.py`:** two-colour edge model (paper ↔ part in Lab, t = 0.5).
  - Boundary search limited to a ±0.3 mm band around the coarse mask.
  - Sub-pixel iso-contours.
  - Through-holes found by colour, even when the mask filled them.
  - Glare flagged, low-contrast fallback, band-saturation warning.
  - SYNTHETIC result: 0.010–0.015 mm mean boundary error at 4.5 px/mm (EVALUATION.md).
- ✅ **`geometry/circle.py`:** Kåsa fit refined by Gauss–Newton (unbiased on short arcs).
- ✅ **`spec/partspec.py`:** PartSpec v1 (Pydantic, `extra=forbid`, frozen).
  - Status enum MEASURED / OBSERVED / INFERRED / UNCERTAIN; `Param` with evidence.
  - Outline runs with provenance; circle **and polygon** holes.
  - Fit compensation.
  - Semantic validation: simple polygon, ±500 mm, ≤ 2000 points, 0.4 mm walls, thickness limits.
  - `unresolved()` feeds the export gate; `mat_to_model()` gives correct handedness.
- ✅ **`cad/build.py`:** manifold3d in-process, chord error ≤ 0.005 mm, offsets and compensation.
- ✅ **`cad/scad.py`:** deterministic parametric `.scad` with provenance comments; only sanitised text reaches comments.
- ✅ **`validation/mesh.py`:**
  - watertight, winding, single body, genus = number of holes, volume vs profile, bbox vs spec, degenerate triangles
  - FDM warnings: minimum hole and minimum wall (morphological opening)
- ✅ **`meta_api/client.py` and `config.py`:**
  - pydantic-settings from `.env`
  - OpenAI SDK pointed at Meta (timeout, 3 retries)
  - JSONL usage ledger with cost estimates and a daily budget guard
  - contributor-tier guard (flag and own/synthetic data); typed API errors with no key echo
- 🟡 **`vision/segment.py` SamSegmenter:** written against the documented API and the official parser; not yet run live. `ClassicalSegmenter` is the labelled non-AI fallback (✅).
- ✅ **`pipeline.py` and `cli.py`:** `reforge run --photo … --thickness …` writes `model.stl`, `model.scad`, `spec.json`, `overlay.png` and `report.json`, with real stage timings.
  - SYNTHETIC end to end: 80.013 × 27.999 mm against 80 × 28, holes Ø4.211 / 4.214 against 4.2, handedness correct, about 0.53 s.

**Evidence-driven corrections today**
1. **Test renderer bias.** OpenCV's anti-aliased fill inflates shapes by 0.47–1.03 px (measured), which skewed the first synthetic numbers.
   - Replaced with an exact-coverage rasteriser (bias ≤ 0.03 px).
   - AT-1 was re-measured and corrected openly in EVALUATION.md.
2. **SAM payload convention.** The decoder requires one-bit payloads to start with `!`, and the encoder output already includes it.
   - The test fixture was fixed. Production only decodes the parser's own records.

**M1 acceptance status**

| Test | Status |
|---|---|
| AT-1 calibration | ✅ synthetic |
| AT-2 SAM client | 🟡 blocked on the key |
| AT-3 real-part metrology | ⏳ needs the printed mat and photos |
| AT-4 build and validation | ✅ |
| AT-5 CLI end to end | ✅ synthetic with the classical backend; ⏳ live with SAM |
| AT-6 web slice | 📋 next |
| AT-7 safety | 🟡 partly. The key is never in the ledger or settings repr, and errors are typed. Upload limits come with the API. |

**Next**
- AT-6 minimal web slice: FastAPI upload → calibration card → mask overlay → 3D view → STL download.
- With the key: live SAM (AT-2), then the real photo (AT-3).
- Then D4: Spark interpretation and symmetry completion.

---

## 2026-10-26 (Mon, until 18:30 Paris): Session 4, continued: AT-6 web slice

**Built**
- ✅ **`reforge/api/app.py` (FastAPI):**
  - Endpoints: `GET /api/health` (key *presence* only), `GET /api/mat/{A4|Letter}.pdf`, `POST /api/jobs` (multipart: photo, thickness, bar readings, segmenter, prompt), and `GET /api/jobs/{id}/{whitelisted file}`.
  - Uploads: limited to 20 MB and 40 MP, decoded with EXIF orientation applied, then re-encoded as PNG (no EXIF/GPS survives).
  - Typed errors map to 413/422.
  - Serves the built UI. Entry point: `reforge-api`.
- ✅ **`frontend/` (Vite 8, React 19.3, TypeScript 5.9, plain three.js):**
  - A guided workflow: print mat → photograph → measure and run.
  - Result panels: summary, 3D STL viewer (z-up, 10 mm grid), cropped outline overlay, measurements with status chips, calibration card with warnings, segmentation card with an **AI / not AI** badge, validation checks, timings, downloads (STL, OpenSCAD, report) and the disclaimer.
  - Progress shows real elapsed time only.
  - `npm run build` passes, including `tsc`.
- ✅ **Tests:** 80 pass, including 12 API tests covering the hostile cases. Ruff is clean.
- ✅ **Browser check** (Playwright headless Chromium, a verification tool in the user cache): valid model, 12/12 checks, no page errors. The screenshot is `docs/media/ui-m1-synthetic-classical-backend.png` (SYNTHETIC photo, classical backend).
- UX fix found in the browser: the overlay is now cropped to the part (it was a speck on the full free zone).
- `README.md` added: honest status, a "built during the hackathon" statement, and the AI-assistance disclosure.

**Known follow-ups**
- 📋 The frontend bundle is 796 kB; lazy-load the 3D viewer (D9).
- 📋 CPU stages run on the event loop; move them to a thread (D9).

**Next**
- With the key: the live SAM call (AT-2), then a real photo of the hero part (AT-3), then M1 is done.
- D4: Spark interpretation (Set-of-Mark, dynamic enums) and mirror-symmetry completion.

---

## 2026-10-27 (Tue morning): Session 5, key in place, live API spike, AT-2

**Done**
- ✅ **Key check:** set (47 chars, never printed), `.env` git-ignored, all settings on the standard tier, budget $5/day.
- ✅ **Live spike** (`prep/verify_meta_api.py`, SYNTHETIC images): all checks succeeded; PLAN §1.2 is updated, with unknowns 1–5 and 7 resolved.
  - Spark structured output works with vision.
  - Spark gave a pixel bounding box within 2 px.
  - Image tokens: 4,264 for a 12 MP photo.
- ✅ **Design change from evidence:**
  - Measurement: SAM 3.1 text prompts returned 0 instances on the rectified view, while box and point prompts were 0.99 confident.
  - Change: `SamSegmenter` is now box-first (local colour candidate → box prompt; a click → point; text as fallback). It records each attempt (prompt, source, instances) in the report and ledger.
  - The unverified two-input-shape retry was removed (the `message` shape is verified).
- ✅ **Bug fix from the live run:** hole edges were clipped when SAM's mask kept slightly offset holes. Holes are now always found by colour inside the hole-filled outline. A regression test was added.
- ✅ **AT-2 passes live** (`uv run pytest -m live tests/live`): box and click modes both give 80.016 × 28.002 mm and Ø4.208 / 4.211 mm, with one SAM call each (2–3 s).
- Offline suite: 83 pass; ruff clean.
- **Spend today:** about $0.043 estimated.

**M1 status:** AT-1, AT-2, AT-4, AT-5 and AT-6 ✅. AT-7 is partial. **AT-3 (real photo against the caliper) is the last gate.**

**Next**
- The user prints the mat, measures both bars, and photographs the intact hero part. Then AT-3.
- Meanwhile, D4 offline: the Spark interpretation schema and prompt (Set-of-Mark), and the mirror-symmetry search and completion.

## 2026-10-27 (Tue afternoon and evening): Session 6, real-photo physics

**Why.** An audit before AT-3 found that the synthetic harness, which every accuracy figure so far came from, left out two effects of a real photo:
- it drew parts flat (no height), so it had no parallax;
- it blurred sRGB-encoded values instead of light.

Simulated on the hero bracket (80 × 28 × 3 mm), uncorrected:
- **Parallax:** +0.61 mm on length from 40 cm, +1.09 mm from 25 cm, and a hole 0.67 mm too small with the camera off-axis. Enough to miss the AT-3 targets and to fail a screw fit.
- **Edge threshold:** 0.4–1.1 px inside the true edge.

**Done** (measured numbers in `docs/EVALUATION.md`, 2026-10-27 entry)
- ✅ **Realistic harness:** parts are prisms (exact projection of every face) and optics work in linear light. The old optics stay available as `optics="encoded"` for comparison. 11 existing tests failed under realistic optics, which was the bias being exposed; after the fixes below, all pass.
- ✅ **Linear-light edges:** the edge threshold and rectification work in linear light; Lab is kept for ΔE and glare. Boundary error under realistic optics went from 0.060–0.100 mm back to 0.011–0.015 mm.
- ✅ **Marker corner bias:** fitted jointly with the homography.
  - The bias was 0.85–0.89 px under realistic optics, and 0.2 px even in the old harness.
  - Calibration residual: 0.16–0.19 → 0.008–0.030 mm, so `CAL_HIGH_RESIDUAL` no longer fires on clean images. AT-1 was re-measured, and the 2026-10-26 interpretation corrected in EVALUATION.
- ✅ **Camera pose** (`capture/pose.py`):
  - Focal length from the homography (bootstrap σ) and/or EXIF (35 mm equivalent, read before uploads are stripped; nothing else is kept), fused.
  - Warnings: `POSE_FOCAL_MISMATCH`, `POSE_FOCAL_ASSUMED`.
  - Camera height and nadir, each with σ.
- ✅ **Height correction** (`geometry/height.py`):
  - **Outline:** exact sweep formula. The PLAN v0.4 formula was found inexact for non-convex outlines (0.55 mm at a U-notch).
  - **Round holes:** two-disc visibility model. **Other holes:** the dual formula.
  - **Single-view occlusion limit:** derived, tested, and reported as `occlusion_bound_mm`.
- ✅ **Edge spread** σ measured on each photo (∫t(1 − t) = σ/√π); hole radii corrected for blur curvature (σ²/2R). Hole Ø error: −0.004…−0.110 mm before, ±0.012 mm after (≤ 0.001 without noise).
- ✅ **Outline smoothing** by 1 px along the edge; the raw trace is kept for roughness (D4).
- ✅ **Pipeline, CLI, API, UI:**
  - Report sections `pose` and `height_correction`; the CLI gains `--focal-35mm`.
  - New UI card: photographed vs footprint extents, parallax removed ± 2σ, camera height, lens source. Verified in headless Chromium; screenshot in `docs/media/ui-height-correction-synthetic.png`.
- ✅ **Results:** on a 3 mm part, synthetic, 1×/2×/3× lenses, flat-on or tilted, with or without EXIF:

  | | before | after |
  |---|---|---|
  | L | up to +0.58 mm | +0.020…+0.036 mm |
  | W | up to +0.47 mm | −0.002…+0.029 mm |
  | hole Ø | −0.21…+0.11 mm | −0.007…+0.004 mm |
  | hole spacing | up to +0.26 mm | ±0.007 mm |

- ✅ **Tests:** 102 offline pass (19 new), ruff clean, frontend type-check and build pass. Live: 2 pass on the new physics (about $0.005).
- **Dependencies:** `pillow` and `scipy` declared directly (both were already in the lock as transitive dependencies). `backend/tools/real_photo_biases.py` reproduces the simulation tables.
- **Docs:** EVALUATION (new entry and corrections), PLAN v0.5 (§4 R1, §5.2 capture protocol, §6.3, §9, §10), DEMO_PART_GUIDE (capture), README (status).

**Open limits** (stated in EVALUATION §4)
- 🟡 The sRGB tone curve and the centred principal point are assumptions; AT-3 measures the effect.
- 📋 Confidence Engine (D5):
  - With no EXIF on a flat-on view the focal length is a prior: block, or widen U.
  - Occluded concave corners → UNCERTAIN.
  - `u_cal` from the homography's prediction error.

**Capture protocol changed** (PLAN §5.2):
- 2× or 3× lens, with the mat filling the frame.
- Phone above the part.
- Original JPEG files, not screenshots or messaging-app copies.

**Next**
- AT-3 needs the user: print the mat, measure both bars and the part, and take 3 photos following the new protocol.
- D4: the Muse Spark interpretation (Set-of-Mark overlay, per-request schema) and mirror-symmetry completion.

## 2026-10-28 (Wed): Session 7, licence and repository housekeeping

**Done**
- ✅ **Licence: Apache-2.0.**
  - `LICENSE` is the verbatim text from apache.org (SHA-256 `cfc7749b…3d30`, 11,358 bytes).
  - `NOTICE` added, and `license = "Apache-2.0"` set in `backend/pyproject.toml` and `frontend/package.json`.
- ✅ **`THIRD_PARTY_NOTICES.md`**, generated from installed package metadata by `backend/tools/third_party_notices.py`.
  - `meta-sam-parser` is under Meta's SAM License. We don't redistribute it, and the use of SAM is acknowledged as that licence asks.
  - `fpdf2` is LGPL-3.0, used unmodified as a dependency.
- ✅ **Credits:** the $150 were claimed by the user. Remaining: the $150 Spend Limit notification on the Billing page.
- ✅ **Commits approved.** The physics work (Session 6) is committed.
- ✅ **Repository housekeeping:**
  - Local tool configuration is no longer tracked, and the wording in the docs is tool-neutral.
  - The initial commit was rewritten with git-filter-repo to match. Its author and commit dates are unchanged, and a full backup of the previous history is kept outside the repository.
  - The user publishes the rewritten history.

**Next**
- The user pushes. Then AT-3, once the mat is printed and photographed following PLAN §5.2.
- D4: the Muse Spark interpretation (Set-of-Mark overlay, per-request schema) and mirror-symmetry completion.

## 2026-10-28 (Wed, evening): Session 8, D4: reading and rebuilding a broken part

**Done** (measured numbers in `docs/EVALUATION.md`, 2026-10-28 D4 entry)
- ✅ **Fracture evidence** (`geometry/segments.py`): the outline is decomposed into line and arc pieces; a break is a run of short pieces. Segments S0…Sn feed the Set-of-Mark image.
- ✅ **Mirror axes** (`geometry/symmetry.py`):
  - Candidates from hole pairs, principal axes and a 2° sweep; ICP refinement; block-bootstrap σ; slide ambiguity.
  - Outline support and hole agreement are kept apart, after a mixed score let a 3.4 mm-off axis rebuild the part 6.9 mm too long.
- ✅ **Completion** (`geometry/completion.py`):
  - Only material next to an accepted fracture is filled. Designed asymmetry is reported, not filled. Mirrored holes are added only inside the added material.
  - Provenance runs: OBSERVED, INFERRED (mirror of S… about A…), UNCERTAIN junctions. The INFERRED uncertainty is stated.
- ✅ **Muse Spark interpretation** (`reasoning/`):
  - Set-of-Mark images (the whole free zone plus a marked close-up) and a per-request strict schema whose enums hold only the ids present.
  - Validation, then geometric verification (axis support and holes; a fracture pick must not match its mirror).
  - Fallback to the geometric rule, labelled not AI.
  - Spark is not told the geometric irregularity labels, so its reading is an independent check.
- ✅ **Refusal gates**, prompted by the user's first real test (a rusty pipe image pasted onto the mat):
  - `TRACE_PARTIAL` (geometry, before any API call) and `FAMILY_UNSUPPORTED` (from Spark's reading). Both refused that input.
  - New warnings: `PROFILE_PARTIAL` and `PROFILE_NONUNIFORM_COLOUR`.
- ✅ **Pipeline, CLI, API, UI:**
  - Spec outline runs with provenance, and INFERRED holes.
  - Report section `reconstruction`; `setofmark.png` output; CLI `--interpreter` and `--reasoning-effort`; the API's `interpreter` field.
  - New UI card "Reconstruction": what Spark saw, its reading, the verification notes, the requested measurements.
  - Provenance-coloured overlay at 1,400 px.
  - The length/width and hole statuses now follow the provenance. Verified in headless Chromium on the live path.
- ✅ **Results:**
  - **Geometry on exact outlines:** the broken bracket rebuilt to Hausdorff 0.004 mm.
  - **Geometric rule, 24 synthetic photos:** 24/24 rebuilt; L +0.008…+0.040 mm, W −0.003…+0.061 mm.
  - **Live Spark, 3 runs:** the fracture read matched the geometry and the right axis was chosen; one over-pick (S10) was rejected by the verification.
- ✅ **Tests:** 134 offline pass (32 new); 3 live tests pass on the new code (SAM ×2, SAM + Spark). Ruff clean; the frontend type-checks and builds.
- **Spend 2026-10-28:** about $0.13 (ledger $0.091, including 5 SAM calls from the user's own runs, plus about $0.04 of live tests).

**Open**
- 🟡 Spark's readings vary between runs. Three readings of one synthetic part are not an accuracy figure.
- 📋 D5:
  - Segment jackknife for the axis angle σ, since the bootstrap under-estimated it 4× once.
  - The Confidence Engine and export gate: UNCERTAIN junctions, prior focal lengths, axis slide ambiguity.
- 📋 Rotational symmetry (gears) remains secondary.
- ⏳ AT-3: needs a real photo of a real flat, single-colour plastic part on the printed mat. The user's test images were a web picture and a collage.

**Next**
- D5: the Confidence Engine (±U for every dimension, coverage check, export gate) and caliper overrides.
- The user: photos of a real part, following PLAN §5.2.

## 2026-11-02 (Mon, evening): Session 9, a test set for the app, and four robustness fixes

**Done** (measured numbers in `docs/EVALUATION.md`, 2026-11-02 entry)
- ✅ **Test set for the app** (`backend/tools/make_test_photos.py`):
  - **What it makes:** 20 JPEGs with truth files in the gitignored `tmp/tests/`. 13 come from Unsplash stock photos of real parts (4 guitar picks, spanners, keys, a 200 mm adjustable wrench), cut out and placed at chosen sizes; 7 are rendered plastic parts (bracket ×3, washer, slotted link, L-plate, broken flange).
  - **Camera:** the harness's, at 3024 × 4032 px, with an EXIF 52 mm focal.
  - **Labelling:** SYNTHETIC COMPOSITE in every file's EXIF and in the README.
  - Prompted by the user's own uploads, which were all one rusty-pipe web image (correctly refused).
- ✅ **Results:**
  - **Live (SAM 3.1 + Spark):** 14 built, 6 forged-metal tools refused `FAMILY_UNSUPPORTED` with reasons.
  - **Accuracy:** plastic parts within 0.07 mm. The broken bracket and flange were rebuilt within 0.04 mm of the intact truth, including the flange's two holes lost in the break.
- ✅ **Fixes found by the set:**
  1. **Reflections taken for holes:** they are doubted unless paper-coloured or round. A hole that can't be built is excluded, UNCERTAIN, instead of failing the spec.
  2. **The evidence rule:** a mirror must be confirmed by as much outline as it invents. A side-broken pick had been rebuilt 30 × 40 mm for 17 × 29.
  3. **Axis candidates:** axes through each hole centre are now candidates; every candidate is trial-rebuilt; any chosen axis must cover the break; tied axes rank by confirming outline; a tie in hole votes counts against an axis.
  4. **Axis fit:** a final least-squares fit of the axis angle and offset.
- ✅ **UI:** the reconstruction card shows the evidence balance (mm confirming vs mm invented).
- ✅ **Tests:** 142 offline pass, 8 of them new. Ruff clean; the frontend type-checks and builds.
- **Spend 2026-11-02:** ledger $0.69, of which about $0.63 is the two live runs of the test set and the rest the user's own app runs. About $0.85 in total of the $150.

**Open**
- 🟡 **Hole doubt thresholds** (ΔE 5, compactness 0.75) are calibrated on composites only; shading in real holes may raise ΔE.
- 🟡 **Spark's family verdict varies between runs** on borderline metal parts (08 and 11 swapped).
- 📋 **D5:** the Confidence Engine must add the source hole's own error to INFERRED holes. The flange's were 0.058 mm off, against a mirror-only 2σ of 0.031 mm.
- ⏳ **AT-3:** a real photo of a real part on the printed mat.

**Next**
- **The user:** try `tmp/tests/14…20` and `01…04` in the UI (thickness per `tmp/tests/README.md`), then photograph a real part.
- **D5:** the Confidence Engine and the export gate.

## 2026-11-03 (Tue): Session 10, user's real photos placed on the mat

**Done** (all in gitignored `tmp/realphotos_mat/`, labelled SYNTHETIC COMPOSITE in EXIF and README)
- ✅ **4 composites** from `tmp/realphotos/` (cut out, placed at known size, rendered by the test-set camera at 3024×4032, EXIF 52 mm):
  - `01_comb.jpg` (IMG_1050): 168.28 mm long, CHOSEN; thickness 3.0 CHOSEN. Teeth gaps preserved (minimal morphology: `cut_out`'s 29 px close would have filled them).
  - `02_case.jpg` (IMG_1051): 150.09 mm, CHOSEN; thickness 25.0 CHOSEN. Cut out by seeded full-resolution GrabCut intersected with a paper mask.
  - `03_screwdriver.jpg` (IMG_1052): scaled by MEASURED handle Ø 14.1 mm (caliper LCD in IMG_1053/1054); thickness 14.1.
  - `04_cone.jpg` (IMG_1055): scaled by MEASURED wide-end 12.51 mm (LCD in IMG_1057, angled photo so approximate); thickness 12.5.
  - Not placed: IMG_1053/1054/1057 are caliper shots (source of the two MEASURED sizes); IMG_1056 is a blurrier duplicate of IMG_1055.
- ✅ **Offline verification** (classical + geometric, $0): all four calibrate (fit RMS 0.006–0.007 mm, no warnings) and build valid models within 0.05 mm of truth on extents. Comb: 3 of 236 gap fragments kept as holes (the rest doubted as elongated — expected); screwdriver: 1 specular hole misread (minor).
- ✅ Generator archived as `tmp/realphotos_mat/make_realphoto_composites.py`; truth files record the size/thickness basis per image.

**Open**
- 🟡 Live behaviour (SAM 3.1 + Spark) untested on these four; case/screwdriver/cone are 3D out-of-scope probes and may be refused `FAMILY_UNSUPPORTED`.
- 📋 Caliper readings that would replace the CHOSEN sizes are listed in `tmp/realphotos_mat/README.md`.

**Next**
- **The user:** try the four composites in the UI (thickness per README), then photograph a real flat part on the printed mat (AT-3).
- **D5:** the Confidence Engine and the export gate.

## 2026-11-03 (Tue): Session 11, first real photos of the printed mat

**Done**
- ✅ **Diagnosed the user's 8 real mat photos** (`tmp/realpictures/`, iPhone 15 Plus 1×) and their 3 UI runs this morning. Full numbers are in `docs/EVALUATION.md` (2026-11-03).
  - The heart, the only flat part, is built live (SAM 3.1 + Spark, $0.044 for both live runs): 52.04 × 47.52 mm. Accuracy is 🟡 unverified (no caliper truth yet).
  - Spark's claim of a break, prompted by an unrelated black shard on the mat, was rejected by verification, so nothing was invented.
  - The vial is refused `FAMILY_UNSUPPORTED` and the caliper `TRACE_PARTIAL`, both correctly.
  - Calibration on the real print: 0.19–0.24 mm RMS. That is paper flatness, not the lens (a radial term doesn't help). In-photo bar check: X +0.01/+0.04 mm, Y +0.36/+0.44 mm over 100 mm.
- ✅ **`CAL_MAT_NOT_FLAT`:** markers that are found but disagree now say so, with the size of the disagreement and a hint to lay the mat on a hard table. Before, the error read "only 3 consistent markers remain". `CAL_MARKERS_REJECTED` names the offset too. Tested on a synthetic wavy sheet (1.5 mm amplitude, λ 100 mm).
- ✅ **The API keeps `request.json` and `error.json` in every job folder** (never served), and error responses carry the `job_id`, which the UI shows. This morning's failures could only be reconstructed from the ledger.
- ✅ **The geometric rule's reason now matches what it did.** It used to describe a chosen axis even when it chose none.
- 147 offline tests pass (5 new); ruff is clean; the frontend is rebuilt.
- ✅ **Second series** (`tmp/realphotos.2/`: mat flat on a table, shot from above). 12 of 12 markers on every photo, perspective ratio ≤ 1.04, fit RMS 0.19–0.25 mm.
  - Live: the heart is built; the vial, cone and key are refused `FAMILY_UNSUPPORTED`; the caliper `TRACE_PARTIAL`. Spend $0.079.
  - The classical fallback traces the heart's cast shadow (+4.4 mm in height); SAM doesn't.
- 🟡 **AT-3 partly met** (`docs/EVALUATION.md`, 2026-11-03 §4). Caliper: height 45.14 mm, width 53 mm (no decimals).
  - ✅ Height: photos 45.55 / 45.45 (+0.41 / +0.31 mm).
  - ❌ Width: photos 52.07 / 51.84 (about −1 mm), yet no direction of the traced heart reaches 53 mm. The width reading is to be repeated.
  - Print scale checked on the A4 sheet's own edges (210.4–210.6 × 296.6–296.9 mm): 100 % within 0.3 %. The user's bar readings ("50") are not used.
- ✅ **A negative edge spread** (−0.37 mm on textured metal) is now reported as unmeasured. +1 test; 148 pass.
- Two explanatory images for the user in `tmp/`:
  - `barres_a_mesurer.jpg`: where the 100 mm bars are;
  - `coeur_a_mesurer.jpg`: what to measure on the heart.

**Next**
- **The user:** caliper readings to 0.01 mm of the heart's full width and its height, and of both 100 mm bars.
- **D5:** the Confidence Engine and the export gate.

## 2026-11-03 (Tue, afternoon): Session 12, the finished product: UI redesign, Confidence Engine, delivery

Brief: finish the product end to end, redesign the UI (light, simple by default, technical details on demand), test
every path for real, and prepare the delivery. The reference `tmp/p3.txt` is the submission form; its fields are now
`docs/SUBMISSION.md`.

**Done** (measured numbers in `docs/EVALUATION.md`, 2026-11-03 afternoon entry)
- ✅ **Background jobs with real progress** (`api/jobs.py`, `pipeline.py`).
  - `POST /api/jobs` with `wait=false` answers at once; `GET /api/jobs/{id}` reports the pipeline's real stage events
    with measured durations, then the result or a typed error.
  - CPU stages run in a worker thread. Two jobs run at once, eight more may queue, then `SERVER_BUSY`.
  - A job that was running when the server stopped reads back as `interrupted`.
- ✅ **Confidence Engine (D5)** (`spec/confidence.py`).
  - A modelled 2σ for every dimension: calibration (leave-one-out), print scale (checked only when both bars are
    entered), edges, height correction, plus the mirror term for INFERRED geometry, including the source hole's own
    error (the D5 item from Session 9).
  - Hole parameters carry it into the `.scad` comments.
  - Size is caliper-style: the sides of the smallest enclosing rectangle, whatever the part's orientation.
  - Labelled "estimated" everywhere: coverage holds on 2 of 4 real comparisons, and the 2 misses are the suspect width.
- ✅ **Export gate (UI):** uncertain items must be acknowledged before the STL and SCAD links unlock. 🟡 It is UI-level:
  the server doesn't stamp the acceptance into the files.
- ✅ **Printer hole allowance:** `?hole_offset_mm=` on the model files. The server rebuilds from `spec.json`, every
  semantic check runs again, and the model is re-validated.
- ✅ **Examples:** three synthetic examples in `assets/samples/` (bracket, flange, link), labelled synthetic, with
  their truth. `POST /api/jobs` accepts `sample=` and `from_job=` (re-run a stored photo, which is how "Run again
  without AI" works).
- ✅ **Axis correction:** when the AI's verified reading can't rebuild with its own axis, the geometric rule's axis gets
  a second chance under the same checks (`AXIS_CORRECTED`). It was found live on the flange (Spark chose the crosswise
  axis). ✅ tested offline (3 new tests); not yet observed live.
- ✅ **New UI**, written from scratch (React, three.js, self-hosted Inter, no other new runtime dependency):
  - **The pages:** home (hero, how it works, the evidence legend, runnable examples, scope), new repair (dropzone with
    browser checks, a four-check photo guide, thickness, optional bar check, advanced AI options), progress (the real
    stages), result (verdict, 3D view with evidence edges and dimensions, before/after slider, what we know, before you
    print, files), technical details, my repairs (localStorage), and refusal and error screens with next actions.
  - **The identity:** paper, ink and ember. Solid lines are measured, dashed ember lines are rebuilt.
  - **The overlay:** the backend overlay now uses the same colours and hatches the rebuilt material.
- ✅ **Wording:** a hole doubt no longer says "confirm to include", an action that doesn't exist.
- ✅ **Tests:**
  - 170 offline (22 new; one older test rewritten for the new axis policy); ruff clean; the frontend builds.
  - In headless Chromium: every screen at 3 widths, with no overflow and no console errors; live AI runs; an outage
    and the no-AI re-run; invalid files; refusals.
  - axe-core: 0 violations.
- ✅ **Exports, checked by OpenSCAD itself** (`backend/tools/check_exports.py`, `tools/scad-check`): 5 cases compiled
  to the same solid as the STL (volume within 4 × 10⁻⁶, genus = holes).
- ✅ **Delivery:**
  - The README, rewritten with screenshots.
  - `docs/SUBMISSION.md`: every form field, with drafts from measured facts.
  - `docs/DEMO_SCRIPT.md`: the 3-minute shot list.
  - `Dockerfile`: built and run-checked; runs as non-root, with no secret in the image.
  - `.env.example` gains the server settings; the third-party notices are regenerated.
- **Spend today:** $0.34 on the app's ledger, all time $1.22 of $150. Add a few cents for the live test suite
  (`pytest -m live`, 3 tests), which keeps its own ledger in a temporary folder.

**Open**
- 🟡 **AT-3 width:** the heart's width reading is still to be repeated to 0.01 mm; no real part with holes yet.
- 🟡 Real devices: Safari, iOS and Android, and screen readers, are untested. Only Chromium's emulation was used.
- 📋 Caliper overrides of single dimensions in the UI; job retention or cleanup; HEIC decoding.

**Next**
- **The user:** push, make the repository public, record the video (`docs/DEMO_SCRIPT.md`) with a real unbranded part
  if possible, and fill the form (`docs/SUBMISSION.md`) by Wed 4 Nov, 22:00 Paris.

## 2026-11-03 (Tue, evening): Session 13, automotive-style demo examples

Brief: the examples looked like toys, and the user asked for real parts like the ones on OEM catalog sites (7zap,
PartSouq, RealOEM…). Catalog images are unusable twice over (sites' copyrighted content, and no calibration mat, so
no millimetres by design). The three examples were re-rendered as our own OEM-style parts instead: same ids, new
images, new truth.

**Done** (measured numbers in `docs/EVALUATION.md`, 2026-11-03 evening entry)
- ✅ **Three new synthetic parts** (`tests/synthetic/scene.py`, cases 21–23 in `tools/make_test_photos.py`):
  - broken-bracket → graphite **bumper bracket** 94 × 30, ears + 2 × Ø5.0, right ear snapped off, 4 mm thick;
  - broken-flange → black **mounting flange** 56 × 56, Ø24 bore + 4 × Ø6.5, two holes lost, 5 mm thick;
  - slotted-link → grey **adjuster link** 80 × 20, 24 × 6.5 slot + 2 × Ø6.5, intact at 30°, 5 mm thick.
- ✅ **Verified live** (SAM 3.1 + Muse Spark 1.3, standard tier): both broken parts rebuilt, sizes within 0.02 mm of
  truth (94.001 × 30.000, 56.014 × 56.014), inferred flange holes Ø6.498 / 6.496 vs 6.5, link 80.00 × 20.01.
  Spark names them "mounting strap", "flange mounting plate", "linkage strap". $0.0513 for the three runs.
- ✅ **Verified offline** (classical + geometric, 23/23 build, no regressions) and **bundled** (`assets/samples/`,
  `tools/make_samples.py` updated: new sources, titles, stories, truth). Same ids, so the API, the UI and the
  existing tests needed no changes.
- ✅ **Tests:** 170 offline pass (including the end-to-end API run of the new bracket sample); ruff clean; frontend
  builds (chunk-size warning pre-exists). Ledger total $1.33 of $150.
- ✅ **Docs:** EVALUATION (new entry), DEMO_SCRIPT, SUBMISSION and README figures updated to the measured numbers.

**Open**
- 🟡 Both broken samples carry the live `PROFILE_BAND_SATURATED` refinement warning; harmless here (errors above),
  shown honestly in the UI.
- 🟡 Screenshots in `docs/media/` and the README still show the previous examples; the numbers in the text are current.
- 🟡 AT-3 width re-measurement still pending (Session 12); unchanged.

**Next**
- **The user:** push, make the repository public, record the video (`docs/DEMO_SCRIPT.md`), fill the form
  (`docs/SUBMISSION.md`) by Wed 4 Nov, 22:00 Paris.

## 2026-11-03 (night) — Real wanted parts as examples: sprocket pair bundled, three geometry fixes

Brief: the user still found the examples unconvincing ("toys", no story) and asked to keep one and use real
car/motorcycle parts from `tmp/wanteds/` (breaking one if needed). Of the five photos, the 21-tooth 06A21 sprocket was
usable flat/single-thickness/mirror-symmetric; the hub carrier Spark refuses live as 3D (correctly); the engine
drawing, steering wheel and turned bushing are outside the family (3D/not-flat). Two sprocket composites (broken +
intact) replaced two examples; the flange was kept byte-identical.

**Done** (measured numbers in `docs/EVALUATION.md`, 2026-11-03 night entry)
- ✅ **Sprocket composites** (`tools/make_wanted_samples.py`): tilt-dewarped cutout at CHOSEN 70.0 mm OD / 5.0 mm,
  bore cut at the fitted disk centre, all provenance + CHOSEN bases in the truth files. Broken (diameter snap) and
  intact (25° pose) variants.
- ✅ **Three geometry fixes**, each verified trial-by-trial against the pick/flange-diagonal/crosswise guards (all
  still reject) and the 23-photo set (matches baseline, no regressions):
  - holes rank before outline in `_rank`, sub-mm twins no longer merge-coin-flip (`symmetry.py`);
  - counterparts relabelled OBSERVED across the part (`FAR_FROM_INVENTED_MM = 20.0`, measured 10.1 / 34.4);
  - `AXIS_REBUILDS_NOTHING` guard under 2.0 mm invented (`reconstruct.py`).
- ✅ **Verified offline**: broken sprocket rebuilt 68.986 × 69.876 vs 69.038 × 69.949; intact measured 69.169 × 71.066
  with nothing rebuilt; carrier 87.938 × 144.050, 4/4 holes.
- ✅ **Verified live** (SAM 3.1 + Spark 1.3, two runs each, bit-identical geometry): broken 68.864 × 69.819 rebuilt
  ("broken roller chain sprocket"), intact 69.168 × 70.989 with nothing rebuilt, carrier refused twice as 3D (stable,
  honest). Spark's one over-picked span on the broken sprocket was rejected by geometry live.
- ✅ **Bundled**: `broken-flange` kept byte-identical (md5-verified); `broken-sprocket` + `intact-sprocket` with
  concrete stories (21 teeth, 06A21 stamp, bore-pinned mirror). Bundler takes both source sets; API test runs the new
  sprocket end to end (box-vs-box comparator for round parts).
- ✅ **Tests:** 170 offline pass; ruff clean; frontend builds (chunk-size warning pre-exists). Ledger total $1.47
  of $150 (about $0.14 tonight).
- ✅ **Docs:** EVALUATION (new entry), PROGRESS, DEMO_SCRIPT, SUBMISSION figures updated to the measured numbers.

**Open**
- 🟡 Small parts (below ~40 mm) with half missing decline via the 20 mm counterpart gate instead of rebuilding — safe
  by design, documented in EVALUATION.
- 🟡 Screenshots in `docs/media/` and the README still show older examples; the numbers in the text are current.
- 🟡 AT-3 width re-measurement still pending; unchanged.

**Next**
- **The user:** push, make the repository public, record the video (`docs/DEMO_SCRIPT.md`), fill the form
  (`docs/SUBMISSION.md`) by Wed 4 Nov, 22:00 Paris.

## 2026-11-03 (Tue, late evening): Session 14, real photos of real parts; four safety fixes; cutting exports; textured 3D

Brief: "real parts, not toy figures, like the ones in OEM catalogues; push harder on features, models and real images;
change the hero figure". This session reviewed the previous session's work first. Measured numbers are in
`docs/EVALUATION.md` (2026-11-03 night entry).

**Review of Sessions 13 and night (previous session)**
- ✅ Kept: the rendered OEM-style parts in the test set, the symmetry-search changes (0.5° sweep, holes ranked first,
  per-axis mirror pass), and the `AXIS_REBUILDS_NOTHING` guard. The offline suite passed on them (170).
- ⛔ **Withdrawn:** the 20 mm "counterpart" relabelling. On a torn gasket it labelled an uncovered tear OBSERVED and let
  a partial rebuild pass. A replacement rule failed differently (it passed a pick's own fracture). No relabelling now.
- ⛔ **Not published:** the two sprocket examples. They were built from an image pasted from the web, with unknown
  rights; they are moved to `tmp/samples_removed/` and can come back if the user owns the photo.

**Done**
- ✅ **Examples from real photos**, freely licensed on Wikimedia Commons, credited in the app and in
  `assets/samples/CREDITS.md` (`tools/make_commons_samples.py`, `tools/make_samples.py`):
  - a real square gasket (Miya.m, CC BY-SA 3.0): live within 0.012 mm, 9 holes, nothing invented;
  - a real 18-tooth chain cog (public domain), four teeth broken off digitally: honestly declined;
  - one rendered broken flange, labelled rendered: rebuilt within 0.015 mm, lost holes within 0.005 mm.
- ✅ **New hero:** a before/after slider of Re-Forge's real output on the real gasket, with the measured numbers and
  the photo's credit, in place of the illustration.
- ✅ **Four safety fixes in the reconstruction:**
  - no counterpart relabelling;
  - `AXIS_ASYMMETRIC`: it stopped a false rebuild of the intact gasket, offline and when Spark claimed a break;
  - mirrored holes straddling the fracture are inferred;
  - `FRACTURE_EXTENDED`: a rough edge split by the decomposer is one break, which turned a hidden partial rebuild of
    the cog into an honest `AXIS_PARTIAL`.
- ✅ **Cutting exports** `model.dxf` (R12, mm) and `model.svg` (true size), with the hole allowance. The DXF is read back
  by `ezdxf` (new dev dependency) in the tests. The UI has a "Cut it" row.
- ✅ **Photo-textured 3D preview**: `texture.jpg` (the photo where photographed, ember where rebuilt, per pixel) mapped on
  the top face; the walls get the measured colour; a "Photo" toggle. The projection was checked.
- ✅ **Tests:** 172 offline pass; ruff clean; the frontend builds. In the browser: axe-core 0 violations (one contrast
  issue found and fixed), no overflow at 390 px.
- ✅ **Docs:** README, SUBMISSION, DEMO_SCRIPT, PLAN, THIRD_PARTY_NOTICES and the screenshots in `docs/media/` updated.
- **Spend today:** $0.90 on the ledger (92 calls); $1.77 in total of the $150.

**Open**
- ⛔ Broken toothed outlines aren't rebuilt (documented); 🟡 pale parts on white trace their holes roughly.
- 🟡 AT-3 width re-measurement still pending; no real part with holes yet.

**Next**
- **The user:** commit and push, make the repository public, record the video (`docs/DEMO_SCRIPT.md`), fill the form
  (`docs/SUBMISSION.md`) by Wed 4 Nov, 22:00 Paris.

## 2026-11-03 (Tue, late night): Session 15, successes-only gallery; sprocket rebuild restored (counterparts v2)

Brief: the user rejected the chipped cog sample (a declined broken part is not a demo) and asked for a homepage
section of all successes, everything working and well reconstructed — plus a note teaching the Session 14 agent (sent
via the peer channel, with the measurements below).

**Done** (measured numbers in `docs/EVALUATION.md`, 2026-11-03 late-night entry)
- ✅ **Counterpart relabelling v2** (`geometry/completion.py`): far-from-INFERRED + mirror-filled + mirror-ON-invented
  (≤ 0.2 mm). Sprocket exposed 12.0 → 0.2 mm, rebuilds again; all committed guards still reject; torn-gasket
  approximation unchanged. Plus loud `HOLES_UNPAIRED` warnings so no partial passes silently.
- ✅ **Cog honestly out**: rough chip declines (ragged edge exceeds exact cover), smooth chip turns invisible
  (matches its mirror, invents nothing) — measured both. Files in gitignored `tmp/declined_samples/`; a
  diameter-style cog break would rebuild (same mechanism as the sprocket) if a 5th sample is ever wanted.
- ✅ **Gallery of 4** (`assets/samples/`, bundler takes `--tests/--wanteds/--composites`): broken flange (rendered,
  rebuilt), broken + intact sprocket (user photos, restored with permission), square gasket (Commons, measured).
  Flange and gasket bytes md5-identical. CREDITS.md covers Commons + user-provided + rendered honestly.
- ✅ **Tests:** API test pins the 4 ids, runs gasket (intact, 9 holes) AND sprocket (rebuild, < 0.1 mm caliper) end
  to end; full suite 172 green; ruff clean; frontend builds. Homepage section reframed as successes with credit lines.
- ✅ **Verified live** (SAM 3.1 + Spark 1.3): broken sprocket rebuilt 68.864 × 69.819 ($0.0225), intact measured with
  nothing rebuilt ($0.0219), carrier refused a stable third time. Ledger total $1.92 of $150.
- ✅ **Docs:** EVALUATION (new entry), PROGRESS, DEMO_SCRIPT, SUBMISSION, README figures updated.

**Open**
- 🟡 Small parts (below ~40 mm) with half missing still decline via the 20 mm counterpart gate — safe by design.
- 🟡 Small ragged chips (cog-style) decline: below the mirror's exact-cover ability, documented.
- 🟡 AT-3 width re-measurement still pending; unchanged.

**Next**
- **The user:** commit and push, make the repository public, record the video (`docs/DEMO_SCRIPT.md`), fill the form
  (`docs/SUBMISSION.md`) by Wed 4 Nov, 22:00 Paris.

## 2026-11-04 (night) — 20 verified samples ✅

**Done**
- ✅ **Wave-1 rendered (9)**: bracket/washer/link/l-plate/flange/bumper/alink cases, all live-verified (model, right rebuilt flags).
- ✅ **Wave-2 rendered (6)**: intact flange, mounting flange, bumper + broken adjuster link, shim, broken shim — new `broken_link`/`shim`/`broken_shim` builders; all live ✅ (errors ≤ 0.022 mm). Breaks cut past the last hole (both holes pin the mirror).
- ✅ **Green Commons gasket**: live ✅ ("circular flange gasket"), 5/5 circles, bundled.
- ✅ **Honest drops**: blue gasket (streak), beige Pakking (mirror shadow / cropped-photo read), carrier (3D, Spark refuses correctly). Tmp quota: every user photo inventoried, only the 2 sprockets qualify → 2/20 (10 %), documented in EVALUATION.
- ✅ **Bundle 20** (`assets/samples/samples.json`), API test green, gallery shows all, suite 172 passed, ruff clean, frontend builds.

**Open**
- 🟡 Small-part counterpart gate + ragged-chip limits unchanged (safe by design).
- 🟡 AT-3 re-measure pending; `docs/media/` screenshots stale.

**Next**
- **The user:** commit/push, public repo, video (`docs/DEMO_SCRIPT.md`), form (`docs/SUBMISSION.md`) by Wed 4 Nov, 22:00 Paris.

## 2026-11-04 (dawn) — 24 samples, 25 % user photos ✅

**Done**
- ✅ **Tmp quota 6/24**: heart intact + broken (user photo, caliper 51.8 mm), heart 2nd shot, sprocket 2nd break — all live ✅ (Δ ≤ 0.06 mm, right rebuilt flags). Heart outlines symmetrised as cast (hand-finished trinket).
- ✅ **Key honestly dropped**: Spark family verdict unstable across runs + SAM −0.9 mm on teeth; kept as builder job, not bundled.
- ✅ **Pipeline untouched**: FRACTURE_CORRECTED retry prototyped then reverted (smoother chip sufficed; no honest synthetic trigger). Revert verified clean.
- ✅ **Bundle 24**, suite 172 green, ruff clean, frontend builds. Gallery shows all.

**Next**
- **The user:** commit/push, public repo, video (`docs/DEMO_SCRIPT.md`), form (`docs/SUBMISSION.md`) by Wed 4 Nov, 22:00 Paris.

## 2026-11-04 (morning): Session 16, deployment fix for medisadido.tech

**Done**
- 🟡 **Redirect loop diagnosed:** `/etc/nginx/sites-available/medisadido.tech` proxies `443 → http://127.0.0.1:80`, and port 80 on the same vhost answers `301 → https://…`, so the request loops until the browser gives up ("too many redirects"). The script was run with port `80`, which is never a valid proxy target.
- ✅ **Correction (user): `medisadido.tech` is NOT Re-Forge** — Re-Forge stays on `reforge.adidomedis.cloud` (→ 8000). `medisadido.tech` must serve the portfolio, which is the PHP site in `/var/www/adidomedis.cloud` ("Juste-Medis ADIDO - AI Engineer"), via PHP-FPM 8.4 (verified active). Neither `~/portfolio/superforfive` (job pipeline) nor `p_etatdeslieux` (already served) is the target. New vhost config (PHP root, no proxy) given to the user in chat.
- ✅ **Backend restarted anyway** (it was stopped, nothing on 8000): `uv run reforge-api` as `medis`, detached via `setsid`, log `/tmp/reforge-api.log`. `GET /api/health` → 200, key configured. Needed for `reforge.adidomedis.cloud`.
- 📋 **Nginx rewrite needs root** (this session runs as `medis`, no sudo): config given to the user in chat, not yet applied.
- ⛔ **Portfolio section abandoned:** staged in `/tmp/reforge_section/` (detail page, cards, screenshots, `apply.py`), then the user clarified the live URL belongs in the Re-Forge repo itself, not the portfolio. Nothing was written to `/var/www`.
- ✅ **Live URL in the repo:** `https://reforge.adidomedis.cloud` added to `README.md` (top, verified: home 200, `AI ready`) and as a recording alternative in `docs/DEMO_SCRIPT.md`. No code change: the app needs no self-link, and the submission form has no live-URL field.

**Next**
- **The user (as root):** replace the `medisadido.tech` vhost with the PHP config, reload nginx, open https://medisadido.tech. Then commit/push, public repo, video, form by Wed 4 Nov, 22:00 Paris.

## 2026-11-04 (day): Session 17, tmp/realpicts tested, key blade demo added

**Done**
- ✅ **Raw probe:** 12/12 `tmp/realpicts` shots fail calibration with no mat (CAL_MARKERS_INSUFFICIENT, $0) — expected; only the flat panel filter and the key blade were compostable.
- ✅ **Key blade admitted (25th sample):** uncut blank cropped from the fob shot, 50 mm CHOSEN; live SAM + Spark Δ −0.03/−0.06 mm, 0/0 holes. Tmp ratio now 7/25 = 28 %.
- ⛔ **Panel filter honestly declined live:** Spark correctly reads a 30 mm pleated composite, not a flat plate. Dropped, documented.
- ✅ **No pipeline change needed:** both live verdicts correct; suite 172 passed, ruff clean, frontend builds, gallery shows all 25.

**Next**
- **The user:** commit/push, public repo, video (`docs/DEMO_SCRIPT.md`), form (`docs/SUBMISSION.md`) by Wed 4 Nov, 22:00 Paris.

## 2026-11-04 (day): Session 18, every breakable part broken (28 demos, 13 broken)

**Done**
- ✅ **3 broken twins admitted live:** washer rim segment (Δ0.002), slotted-link ear-tip (Δ0.045, 3/3), heart2 left-tip chip (tmp). New cases 30/31 + `heart2_broken` job.
- ⛔ **Impossible by mirror, documented:** L-plate (no mirror axis), key blade (asymmetric blank). Intact demos stay: they prove nothing is invented.
- ⛔ **Square gasket honestly unbreakable:** traced holes don't pair (corner tear restores the outline but not the passage); hole-free chips ≤2.4 mm drown in grain (AXIS_WEAK). Job removed, files cleaned, boundary in EVALUATION.
- ✅ **No pipeline change:** the diagonal machinery was already correct (A1 at 100 %); traced-hole inference is scoped future work, not a deadline-day rush. Suite 172 passed, ruff clean, frontend builds, gallery shows all 28 (tmp 28.6 %).

**Next**
- **The user:** commit/push, public repo, video (`docs/DEMO_SCRIPT.md`), form (`docs/SUBMISSION.md`) by Wed 4 Nov, 22:00 Paris.

## 2026-11-04 (day): Session 19, ruler mode, 8 .casse declined honestly, hero = real sprocket

**Done**
- ✅ **Ruler mode (mat optional, 🟡):** `known_length_mm` through pipeline + API + CLI + frontend (checkbox + input); top-down assumed ≤10°, widened budget, mode-aware messages, `mode` in report. 3 maintained tests; synthetic bracket recovers 80/28.
- ⛔ **8 .casse all declined live:** full pipeline attempted (SAM segs + silhouette measured + Spark reads incl. damage); every one is a genuinely 3D part. Verdicts + reasons in EVALUATION. Nothing admitted — 0 demo invented.
- ✅ **Removals as asked:** bracket, broken-bracket-black, adjuster-link + 6 more intact synthetics with broken twins (washer, slotted-link, flange, mounting-flange, bumper-bracket, shim) → 19 samples (12 broken, 7 intact), tmp 42 %. Files moved to `tmp/samples_removed`; stories de-dangled.
- ✅ **Hero = real case:** broken sprocket user photo, actual live output (blue measured + orange 663 mm² rebuilt + mirror axis), readout + caption + CREDITS updated; gasket hero retired.
- ✅ **Suite 175 passed, ruff clean, frontend builds, gallery shows 19.** PLAN.md scope synced (ruler mode 🟡).

**Next**
- **The user:** commit/push, public repo, video (`docs/DEMO_SCRIPT.md`), form (`docs/SUBMISSION.md`) by Wed 4 Nov, 22:00 Paris.
- **To get more REAL demos:** photograph real FLAT broken parts (a snapped flat bracket, a torn flat gasket, a broken shim/clip) — 3D parts (wheels, shocks, springs, plugs) can never rebuild from one photo.

## 2026-11-04 (evening): Session 20, Studio human-in-the-loop + wheel admitted (20 demos)

**Done**
- ✅ **Studio human-in-the-loop (✅ implemented and tested):** `Guidance` (axis/assert-angle+pivot/fracture/damage/sources/family-override/note) through pipeline + API (`guide_*`, `from_job`, sample-carried sessions, `/api/deskew`, `/api/jobs/{id}/feedback`), Studio page (Guide + Flatten tabs), 👍/👎 feedback on every job. Guidance steers, geometry judges.
- ✅ **Steel wheel admitted (20th sample):** white blob hides 3 right vents; live SAM + Spark guided 90° through hub bore, HOLES_ONLY, 400.57×389.51 vs intact 400.56×389.62, 20 observed + 3 inferred (trusted positions within ~2.3 mm of thresholded truth). Bundled as `broken-wheel` (`kind: photograph`, `truth.exact: false`); free rerun identical; API test asserts U0 + 23 holes + ±0.5 mm. Tmp quota 9/20 = 45 %.
- ⛔ **Feu/coque/panel guided, refused with numbers:** feu best support 0.237 (3/4 perspective, asymmetric faces); coque 65 vs 139 mm² (0.47 > 0.35 gate, 3D fob); panel both axes refuse, intact control proves non-mirror family. All declined-honest, excluded.
- ✅ **Suite 192 passed, 3 deselected; ruff clean; frontend builds; gallery shows all 20.** `MAX_POINTS` 2000 → 8000 (test synced). EVALUATION/PLAN/README synced.

**Next**
- **The user:** commit/push, public repo, video (`docs/DEMO_SCRIPT.md`), form (`docs/SUBMISSION.md`) by Wed 4 Nov, 22:00 Paris.

## 2026-11-04 (night): Session 21, hearts out, bougie/volant/pulley, Studio reshape editor, showcase

**Done**
- ✅ **Hearts removed:** 4 metal-heart samples out everywhere (files → `tmp/samples_removed`).
- ✅ **Bougie fixed + bundled:** min-reach refine agreement + leaking-sea fill (real fixes, measured t values in EVALUATION); guided rebuild 100.03 × 19.82, 25.35 mm² fill; `broken-bougie` green.
- ✅ **Volant bundled:** relative-glare fix (real bug); rebuilt 347.68 × 345.41 = same-photo twin to 0.001 mm, inferred arc within 1.0 mm; `broken-volant` green (`exact: true`).
- ✅ **Symmetric case:** rendered Ø130 crankshaft pulley (bore + 8 holes), broken twin loses 3 holes; asserted-axis re-measurement fix (real bug); 130.000 exact, 3 holes inferred exactly; `intact-pulley` + `broken-pulley` green. Bushing skipped (top-down = washer).
- ✅ **tmp/errors fixed:** deskew blob decode + styled picker + retry; card margin; solid header; readable dark 3D walls; dead TS function removed.
- ✅ **Studio reshape editor:** SVG drag handles + undo/redo/reset + `POST /api/jobs/{id}/reshape` with geometric span carry + `reshaped`/`OUTLINE_RESHAPED` records; photographed outline kept for evidence splits; 3 tests.
- ✅ **Showcase:** `tmp/finalimageandinstuctions/` — 5 bluffing cases + INSTRUCTIONS.md (order, clicks, voiceover, guardrails).
- ✅ **Suite 196 passed, 3 deselected; ruff clean; frontend builds; gallery 20 (user tmp 35 %).** EVALUATION/PLAN/README synced.

**Next**
- **The user:** commit/push, public repo, video (`docs/DEMO_SCRIPT.md` + showcase), form (`docs/SUBMISSION.md`) by Wed 4 Nov, 22:00 Paris.

## 2026-11-05 (Thu, 00:40 to 01:30 Paris): Session 16, final checks and demo video v7

Brief: final conformity check against the participant guide (`tmp/p6.txt`), a better demo video (locked voice,
more real animation), YouTube texts. Decisions taken by the submitter at 00:50: Meta AI in the spotlight, 2:59 at
most, keep the Brian voice.

**Found**
- ⛔ v6 video ran 3:31 (the guide asks for a three minute video) and said "no AI" throughout, which works against
  Stage One (Meta models must be used) and the 25 % "Use of Meta AI Tooling" criterion.
- ⛔ `main` on GitHub was still `c0425d2`; the final work is on `real-samples` (default branch is `main`).

**Done**
- ✅ Live runs with SAM 3.1 + Muse Spark 1.3 on the bundled samples (`docs/EVALUATION.md`, 5 Nov entry): the
  sprocket rebuilt within 2σ, Spark's 20 fracture picks cut to 9 by geometry, $0.025 per analysis.
- ✅ Demo video v7 (`demo-video-v1/reforge-demo-v7.mp4`, 2:50, kept out of git): every scene a fresh screen recording
  of the app with a Meta key (genuine clicks, drags, scrolls, a live run as a labelled time-lapse), animated cards,
  lower thirds, transitions; same locked voice recipe; captions `.srt`; `script-v7.md`, `provenance-v7.md`.
- ✅ YouTube texts rewritten in `tmp/youtube/` (v6 copies kept as `v6-*`).
- ✅ `docs/SUBMISSION.md`: video field and spend ($4.40 of $150) updated.

**Next**
- **The submitter:** push `main` (fast-forwarded to the final work), upload v7 to YouTube with the captions, paste the
  link into the form, submit before 03:00 Paris.
