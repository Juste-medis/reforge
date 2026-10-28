# RE-FORGE AI

**From a photo of a broken plastic part to a measured, editable, printable replacement model.**
Every dimension says where it came from: MEASURED, OBSERVED ±U, INFERRED, or UNCERTAIN.

Built for the Meta Global AI Developer Hackathon (Indie track, "Push the Frontier"). **All code in this repository was written during the hackathon**, starting after the kickoff on 26 Oct 2026, 17:00 Paris. The git history and `docs/PROGRESS.md` record what was built and when. Development was assisted by AI coding tools.

> ⚠️ A reconstruction is not a verified replacement part. Not for safety-critical use.

## How it works (M1, current)

1. **Calibrate.** You photograph the part on the printed Re-Forge mat (`assets/mat/`). Twelve ArUco markers give a metric homography, with a residual and a leave-one-out error. Two caliper-checked 100 mm bars correct the print scale.
2. **Segment.** **SAM 3.1** (Meta Model API) segments the part from a box prompt around a local colour proposal, or from your click; a noun phrase is the fallback. A classical fallback, labelled *not AI*, exists for offline use.
3. **Measure.** A two-colour edge model, in linear light, refines the mask to sub-pixel accuracy against the known mat background. Through-holes are found by colour and measured by circle fit, corrected for the measured edge blur.
4. **Correct for height.** The part's top face is closer to the camera than the mat, so it looks bigger: +0.6 mm on an 80 mm part 3 mm thick, photographed from 40 cm. The camera pose comes from the mat (focal length from the mat's perspective and/or the photo's EXIF). The footprint is then recovered exactly, holes included, with the uncertainty reported.
5. **Build.** A typed, validated `PartSpec` is compiled deterministically (manifold3d) into a watertight solid, plus an editable OpenSCAD file. **No model output is ever executed.**
6. **Validate.** Checks: watertight, single body, genus equal to the hole count, volume and bounding box against the spec, and FDM printability.

**Next:** Muse Spark interpretation and symmetry-based reconstruction of the broken region, and the Confidence Engine (±U per dimension). See `docs/PLAN.md`.

## Status (honest labels)

| Status | Items |
|---|---|
| ✅ Implemented and tested | calibration, refinement, PartSpec, CAD build, validation, `.scad` export, CLI, API, web UI |
| ✅ Implemented, tested on synthetic photos | camera pose, height (parallax) correction, linear-light edges: a 3 mm thick part comes out within +0.036 mm on length and ±0.007 mm on hole Ø across 1×–3× lenses (`docs/EVALUATION.md`) |
| ✅ Verified live (synthetic photo) | SAM 3.1 segmentation via the Meta Model API: box-first prompting, about 2–3 s per call |
| ⏳ Not yet measured | accuracy on real photos against caliper ground truth (`docs/EVALUATION.md` lists only what has been measured) |

## Run it

Requires uv and Node ≥ 22.12; see `docs/ENVIRONMENT.md`.

```bash
cp .env.example .env        # then set META_MODEL_API_KEY
cd frontend && npm install && npm run build && cd ..
cd backend && uv sync && uv run reforge-api     # http://127.0.0.1:8000
# or the CLI:
uv run reforge run --photo part.jpg --thickness 3.02 --bar-x 100.0 --bar-y 100.0
```

Tests: `cd backend && uv run pytest`. Live API tests are opt-in with `-m live`.

## Docs

- `docs/PLAN.md`: architecture and decisions
- `docs/PROGRESS.md`: build log
- `docs/EVALUATION.md`: measured results only
- `docs/DEMO_PART_GUIDE.md`: choosing and measuring the demo part
- `docs/ENVIRONMENT.md`: toolchain and setup

## Licence

Apache License 2.0: see `LICENSE` and `NOTICE`. Third-party packages keep their own licences, listed in `THIRD_PARTY_NOTICES.md` (generated from their metadata by `backend/tools/third_party_notices.py`). SAM 3.1 and Muse Spark are used through the Meta Model API under Meta's terms; no model weights are included.
