# RE-FORGE: what it covers and what it does not

The honest-scope companion to the README (the Gatekeeper `guard-threat-model.md` pattern). Every claim here is
checkable in the code or in `docs/EVALUATION.md`. Status labels: ✅ implemented and tested · 🟡 implemented,
unverified · 🧪 experimental · 📋 planned · ⛔ unsupported.

## What it covers

- ✅ One flat part of uniform thickness, photographed from above: on the printed mat (12 ArUco markers), or in
  ruler mode (plain background + the longest side entered by hand). Single colour preferred.
- ✅ Through-holes (round, measured; traced shapes, built as photographed) and mirror-symmetry rebuilds of the
  missing material, with every dimension labelled MEASURED / INFERRED / UNCERTAIN and a modelled ±2σ.
- ✅ Smooth-bridge reconstruction where no mirror applies: a broken corner or nick is closed by extending the
  intact edges beside the break (fitted lines, arc end-tangents) to their intersection. Gated: clean long
  neighbours, believable angle and reach, never cuts photographed material, adds at most 5 % / 500 mm².
  No hole inference by bridge (v1): lost holes on a bridged part stay lost and are reported.
- ✅ Machine-checked outputs: mesh checks before the write (`validation.mesh`), then the artifact verdict on the
  files as handed out (`validation.verdict` → `validation.json`, reloaded from disk, sha256-fingerprinted).
- ✅ Refusals with a typed reason and a fix instead of a confident-looking wrong model (no mat, 3D object, pipe,
  varying thickness, partial trace).
- ✅ Offline mode: without an API key a classical tracer and a geometric rule run the same pipeline, labelled
  "not AI" everywhere they appear.

## What it does not cover (accepted)

- ⛔ Non-flat parts: anything revolved, sculpted or of varying thickness is refused (`FAMILY_UNSUPPORTED`), not
  approximated. There is no 2.5D/3D reconstruction: no depth camera, no multi-view, no NeRF/Gaussian path.
- ⛔ Absolute scale from the photo alone: the mat (or the entered ruler length) sets the scale. A wrongly printed
  mat (scaled to fit the page) breaks every dimension, which is why the UI asks for the caliper bar check. There
  is no ArUco capture-sheet pose path yet (📋, the bevell-3d pattern).
- ⛔ The ±2σ values are *modelled* uncertainties from the photo's error budget, not guarantees. Coverage against
  caliper readings is measured in `docs/EVALUATION.md` and is still growing; every surface calls them estimates.
- ⛔ A reconstruction is not a fit test. No print here proves the part fits your device: print one and check.
  Not for safety-critical use (see the README warning).
- ⛔ The AI never sets a dimension, but it does choose *what* to rebuild (fracture edges, mirror axis). Those
  choices are re-checked by geometry (`reasoning.verify`: unknown ids rejected, weak axes rejected, smooth edges
  kept with a warning), and a failed Spark call falls back to the geometric rule with the reason recorded
  (`fallback_reason`). The geometric rule is conservative: it rebuilds nothing rather than risk a wrong rebuild.
- ⛔ Printability warnings (min wall 0.8 mm, min hole Ø1.0 mm) are FDM guidelines, not a slicer check. Slicer,
  material shrinkage and printer calibration are outside this tool.
- ⛔ The Studio trusts the user on purpose: asserted axes (U0) and redrawn outlines are labelled as user input in
  the report, and only containment + hole-contradiction checks apply to them.

## What is sent where

- With an API key, the photo (or crops) go to the Meta Model API for segmentation (SAM 3.1) and reading
  (Muse Spark). Standard-tier models by default; the contributor tier only for synthetic or our own test images.
- Every AI call is recorded in the job report (model, latency, cost) and in the server-side usage ledger, which
  feeds the daily budget guard. The key never reaches the browser.
- Without a key, nothing leaves the machine.
