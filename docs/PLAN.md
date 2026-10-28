# RE-FORGE AI: Technical Plan v0.5

> **Status: APPROVED (2026-10-23).** The Official Rules (published 2026-10-25) don't explicitly allow prior work, so **project code starts at the kickoff: Mon 26 Oct, 17:00 Paris (16:00 UTC)**. See `docs/PROGRESS.md`.
> v0.1 drafted 2026-10-22 · v0.2 (2026-10-23): approval directives and preparation findings · v0.3 (2026-10-26): Official Rules, credit terms, and M3 re-ranked by the official judging weights · v0.4 (2026-10-26): Participant Guide requirements (§1.1) and two new M3 candidates · v0.5 (2026-10-27): real-photo physics (height correction, linear-light edges) moved forward and implemented; capture protocol revised (§4 R1, §5.2, §6.3, §9, §10) · sources in §14.
>
> Labels used throughout:
> - ✅ verified in official docs (2026-10-22)
> - 🔎 unverified, to check in the Day-1 spike
> - 🧪 experimental
> - 📋 planned
> - ⛔ rejected / unsupported

---

## Approval directives (2026-10-23)

These override anything below that conflicts with them.

1. **Primary demo:** a simple, flat, mirror-symmetric plastic part with mounting holes. Gear reconstruction is secondary (M3 at most).
2. **The physical journey matters:** a real broken part → STL → and, if a 3D printer becomes available, a printed replacement with a fit test.
3. **Protect the core MVP.** Experimental work never puts the working pipeline at risk (rule in §5.3).
4. **The Confidence Engine is the central differentiator** (§6.6).
5. **Standard Meta models by default.** Contributor models only for synthetic images or our own non-sensitive test images. Their data-use terms are now confirmed (§1.2).
6. **No project code before the official rules are checked.** Non-coding preparation continues meanwhile.
7. **Engineering autonomy:** challenge implementation decisions when evidence supports a better option.
8. **Keep `PLAN.md` and `PROGRESS.md` in sync.**

**Overriding goal:** an outstanding working demonstration matters more than the number of features.

---

## 0. Summary

**Verdict.** The pipeline from the application (SAM 3.1 segments → Muse Image hallucinates the missing geometry → Muse Spark converts it to parameters → Muse Code writes OpenSCAD) won't work reliably, for two reasons:
- Its weakest links, a generated image and an LLM's numeric guesses, sit exactly where a repair part needs precision.
- It executes model-written code.

A tighter version is feasible in the window, and it's more convincing to judges:

> **Calibrated photo metrology + Meta-model interpretation + deterministic symmetry-based reconstruction + an explicit evidence layer → a validated, editable, printable model.**

- **SAM 3.1** finds the part.
- **Muse Spark** interprets it: what the part is, which edges are fractures, which symmetry applies, and what still has to be measured.
- **Deterministic code** measures, completes and builds the part.
- **Every dimension carries its evidence:** MEASURED / OBSERVED ±U / INFERRED / UNCERTAIN.
- **Muse Image** is demoted to an experimental, cross-checked second opinion.
- **Muse Code** is a development tool, never a runtime component.
- **MVP scope:** flat ("2.5D") non-safety-critical plastic parts photographed on a printed ArUco calibration mat. **The primary demo part is flat, mirror-symmetric and has mounting holes** (a bracket, mounting plate or clip). Gears are secondary.
- **First milestone (Wed 28 Oct):** real photo → real SAM 3.1 → calibrated mm profile → solid → validated STL download.
- **Two timing facts:**
  - The submission deadline is **Thu 5 Nov, 03:00 Paris time**.
  - The Official Rules (published 25 Oct) don't explicitly allow prior work, so project code starts **at the kickoff (Mon 26 Oct, 17:00 Paris)**.
- **Official judging weights:** Impact 30 % · Use of Meta AI Tooling 25 % · Technical Depth & Execution 20 % · Demo 25 % (§1.1).

---

## 1. Verified facts

### 1.1 Hackathon (official pages 2026-10-22; Official Rules and Credit Terms read 2026-10-26)

| Item | Official (ET) | Paris |
|---|---|---|
| Acceptance notifications sent by | Mon 26 Oct 09:00 | 14:00 CET |
| Kickoff | Mon 26 Oct 12:00 | 17:00 CET |
| **Submission deadline** | Wed 4 Nov 21:00 | **Thu 5 Nov 03:00 CET** |
| Judging · finals | 4–8 Nov · 9 Nov | |

- **Official Rules** ✅ published 2026-10-25 as the "Hackathon Terms & Conditions ('Official Rules') and Event Waiver" on the waiver page (§14).
- **Credits** ✅: $150 of Meta Model API credits per accepted participant (Official Rules and Credit Terms).
- **Partner credits** for open-weights hosting, for select participants: Modal $100, Baseten $100, Fireworks $25.

**Judging criteria (Official Rules, weighted):**

| Criterion | Weight | What it asks | What it means for us |
|---|---|---|---|
| **Impact** | 30 % | "real-world potential… who benefits, how much it matters, whether it could become something people use, and whether it fits one of the problem statements" | A real broken household part and the full repair journey; "Push the Frontier" theme. 📋 Right-to-repair framing for the write-up, with sources verified before citing |
| **Use of Meta AI Tooling** | 25 % | "how creatively the team used Meta's AI tooling, whether they went beyond a basic integration, and whether they surfaced unexpected capabilities" | Set-of-Mark-constrained Spark reasoning with dynamic enum schemas, plus SAM 3.1 text and point prompts in the core. M3 is re-ranked toward deeper uses (§5.3). Record any unexpected capability **with evidence** |
| **Technical Depth & Execution** | 20 % | "whether the engineering is sound and thoughtfully refined and the Project demonstrates real craft" | Metrology, the Confidence Engine, validation, tests |
| **Demo** | 25 % | "whether the Project has a working, impressive demo, whether the product holds up live, and the quality of the demo video" | Robust live demo (finals are live on 9 Nov), the "try a sample" mode, a deployed instance, a rehearsed video |

**Other rules that affect us:**
- **Prior work:** not addressed explicitly. Submissions must be the participant's *"original work product"* and *"solely owned"* by them. Under directive 6, coding starts at the kickoff.
- **Assistance:** *"Participants may contract with a third party for technical assistance, provided the Submission components remain the Participant's own work and the Participant owns all rights to them."* Our reading: AI-assisted development is compatible, because the user owns the output. We'll disclose the assistance in the submission. This is a reading, not legal advice.
- **Open source:** allowed *"provided applicable open source licenses are followed and the Submission enhances or builds upon the underlying open source product"*. ✅ `THIRD_PARTY_NOTICES.md` ships, generated from the installed packages' metadata (2026-10-28).
- **Licence to organisers:** entrants keep ownership but grant the Organizers a perpetual, royalty-free, non-exclusive licence to use the Submission, and nothing shared is treated as confidential. So **no employer (DriveOnly) code, data or proprietary material goes in**, and the project is built on the user's own time and resources.
- **Tracks:** Indie track allows teams of up to 4. One track per participant and per project.
- **Prizes:**
  - Indie track: $400k (1st $150k · 2nd $100k · 3rd $75k · 4th $50k · 5th $25k).
  - Bonus prizes of up to $50k, possibly including a community vote and "most viral project".
- **Submission portal:** https://cerebralvalley.ai/e/meta-ai-developer-hackathon/hackathon/submit. It requires a Cerebral Valley login, so the fields are 🔎 to be checked by the user.
- **Age:** participants must be 18+.

**Credit Terms (read 2026-10-26):**
- **Claiming:** claim via the form in the "know before you go" email, using the application email and the Model API **Team ID**, by **4 Nov, 21:00 ET**.
- **Account requirements:** a payment method must be on file.
- **Timing:** credits are applied **within about 2 business days**, in batches, and may take longer. Until then, usage is billed to the card.
- **Validity:** once applied, credits **don't expire**, and they can be used beyond the hackathon.
- **After credits run out:** usage is charged at standard prices, so the app's daily budget guard matters.
- **Employer rules:** claiming confirms compliance with any employer rules on accepting things of value.

**Participant Guide (pasted by the user, 2026-10-26).** These requirements are binding:
- **Stage 1 (pass/fail):** the project must fit a problem statement, and it must "reasonably" use the Meta Model API and/or Meta open-weight models. Stage 2 scores the weighted rubric 0–10. Stage 3: the top 5 per track are ranked by final-round judges who **watch the videos live**.
- **Repositories must be public.** That needs a GitHub account, a `LICENSE`, and spotless secret hygiene. `prep/` and `tmp/` stay git-ignored.
- **New work only.** The demo "must only highlight the specific features, code, and functionality that you built during the Hackathon", and judges must be able to tell what was built during the event. Our evidence: dated git history from the kickoff, plus a README section on what was built and when.
- **A three-minute demo video is required.** It's "one of the primary artifacts", alongside the code and the live product.
- **Anti-projects include "Simple Image Analyzers".** Re-Forge must always be framed and demoed as *physical reconstruction to a printable part*, never as photo analysis.
- **Credits:**
  - Claim through the Google Form in the guide.
  - A card must be on the account (there's a temporary pre-authorisation charge).
  - Set a **Spend Limit notification at $150** on the Billing page.
- **Bonus prizes:**

  | Prize | Amount | What it takes |
  |---|---|---|
  | Most Viral | $20k | Engagement on an X post of the demo until 8 Nov |
  | Best Build on Meta Open-Weight Models | $10k | Muse Glimmer or Muse Spark Open, on our own hardware or partner inference |
  | Community Vote | $10k | Votes in the public gallery |
  | Best Agentic Use-Case | $5k | Strongest use of agents for multi-step work |
  | Best Creative Build | $5k | Built with Muse Image or Muse Wonder |

- **Sessions, converted to Paris time:**

  | Session | When (Paris) |
  |---|---|
  | Agents 101 | Tue 27 Oct, 17:00 |
  | **Agents 102: Best Practices for Verifiable Agents** (directly relevant to our verification-first design) | Wed 28 Oct, 17:00 |
  | Fireworks / open models | Fri 30 Oct, 17:00 |
  | Discord #office-hours, weekdays | 15:00–16:00 until 30 Oct; 16:00–17:00 from 2 Nov (US clocks change) |
  | Last full day for submission questions | Tue 3 Nov |
  | Closing ceremony (top 10 announced, live final round) | Mon 9 Nov, 18:00 |

- **Ambiguity:** the guide says "Building period: Oct 27 – Nov 4", but the event and the Credit Terms say the hackathon runs from 26 Oct (kickoff at 12:00 ET). We started coding after the kickoff (26 Oct, 17:00 Paris), which is during the event. 🔎 Worth confirming in Discord #questions.

**Rules questions (answered 2026-10-26):**

| Question | Answer |
|---|---|
| Is pre-existing work allowed? | Not addressed explicitly, so coding starts at the kickoff |
| Are third-party AI coding assistants allowed? | Third-party technical assistance is allowed if the participant owns all rights. We disclose it in the submission |
| Required deliverables | A demo video is judged (no length given). Other fields 🔎 (the portal needs a login) |
| Mandatory Meta model usage | Not mandatory as such, but "Use of Meta AI Tooling" is 25 % of the score |

> DST note: Europe leaves summer time on 25 Oct and the US on 1 Nov, so the ET→Paris offset changes mid-event. Times above were computed with the tz database.

### 1.2 Meta Model API (dev.meta.ai/docs, read 2026-10-22)

✅ Connection details:
- Base URL `https://api.meta.ai/v1`, Bearer key.
- OpenAI-SDK compatible (Chat Completions + Responses); other SDK compatibility layers exist but aren't used here.
- The Muse Spark launch blog said "US developers only". The later Meta Connect 2026 recap says the API is "generally available globally".
- You've used the API before, so 🔎 only confirm your key and credits.

| Model | ID | Capabilities that matter here (✅ docs) | Price | Rate limit | Role in Re-Forge |
|---|---|---|---|---|---|
| **SAM 3.1** | `sam-3.1` | `POST /v1/responses`. Image as `input_image` (URL or base64). Prompt: **one noun phrase**, or up to 16 **box/point** object prompts. Output per instance: box + mask (base85 raster, `lossless` or `one_bit`) + optional confidence. Video tracking. Python parser `meta-sam-parser` 0.1.0 (PyPI) | $2.50 / 1k images · $0.20 / 1k video frames | 3,000 RPM | Part segmentation, click refinement; video tracking 🧪 |
| **Muse Spark 1.3** | `muse-spark-1.3` (also 1.2, 1.1, plus `-contributor` variants) | Vision (`image_url`, ≤ 50 MB inline, ~50 images/request guideline). **Structured output** via `json_schema` with a strict subset (below). Tool calling. `reasoning_effort` minimal→xhigh. 1M context | $1.25 / $4.25 per M tokens (cached input $0.15). Contributor tier $0.10 / $0.20, but **content may be used to train future Meta models** (see below) | 3,000 RPM · 4M TPM | Interpretation, fracture/symmetry/feature reasoning, measurement requests, review |
| **Muse Wonder 1.0** | `muse-wonder-1.0` (preview) | Most capable model; agentic | $4 / $20 per M | 3,000 RPM · 4M TPM | Optional: A/B test against Spark on our labelled set; used only if measurably better |
| **Muse Image 1.0** | `muse-image-1.0` | `/v1/images/generations` and `/v1/images/edits` (1–10 input images). **No mask inpainting**: `mask` returns 400 `unsupported_parameter`. `size` only sets the aspect ratio, and returned dimensions "won't match exactly" | $0.01 / image | 150 RPM | 🧪 Generative completion hypothesis, re-registered and cross-checked (§6.7) |
| **Muse Code** | CLI, $5–200 / month | No documented headless or SDK mode | — | — | Optional development tool only |
| SAM 3D Objects | open weights, not on the Model API | Single image → generative mesh/splat; needs ≥ 32 GB of VRAM | Modal credits | — | ⛔ Not planned (§3) |

The strict structured-output subset for Muse Spark:
- `additionalProperties: false` on every object
- every key listed in `required`
- no `anyOf` at the root; no `allOf` or `oneOf` anywhere
- nesting depth ≤ 10

**Contributor-tier terms (confirmed in Meta's docs, 2026-10-23):**
- In contributor mode, "your content" (the prompts, files and context you send, plus the model's responses) "may be used to train future Meta models", in exchange for the lower price.
- In standard mode, "your content is not used to train Meta models".
- Retention isn't stated.
- Contributor variants exist for Muse Spark 1.2 and 1.3 only.
- **Our policy (directive 5):** the contributor tier is used only for synthetic images or our own non-sensitive test images. It sits behind the config flag `REFORGE_ALLOW_CONTRIBUTOR_TIER`, which defaults to off, and is never used for user uploads.

**Day-1 spike: live results (2026-10-27, SYNTHETIC images, standard tier; details in `docs/EVALUATION.md`).**
- **Access:** the key sees 9 models, including all four we use (`sam-3.1`, `muse-spark-1.3`, `muse-image-1.0`, `muse-wonder-1.0`).

1. ✅ **SAM mask placement:** **box-local masks at native pixel resolution** (a 598×298 raster for a 598×298 box), confirmed live.
2. ✅ **SAM prompt behaviour (design-changing):**
   - On the rectified view, **text prompts returned 0 instances** for "plastic part", "black plastic bracket" and "object", and also for "plastic part" on the full photo.
   - **Box and point prompts were confident:** 0.988 / 0.992, IoU 0.994 / 0.984.
   - The segmenter is therefore **box-first**:
     1. A user click becomes a point prompt.
     2. Otherwise a box prompt around the local colour candidate.
     3. The noun phrase is the fallback.
   - SAM masks don't reliably follow hole edges, so holes are always measured by colour (§6.3).
   - 🔎 Real photos may behave differently; re-measure on the hero part.
3. ✅ **Structured output:**
   - Spark accepts `enum`, `minimum`, `maximum`, `minItems` and `maxItems` without a 400.
   - Responses conformed to the schema.
   - Whether the server *enforces* the numeric bounds isn't tested; we validate server-side regardless.
4. ✅ **Image token cost:** a 4032×3024 JPEG costs 4,264 input tokens and a 1600×1200 JPEG 2,662. A vision call with low reasoning is about $0.005.
5. ✅ **Spark pixel coordinates:**
   - Asked for the plate's bounding box, Spark answered `[500, 448, 1100, 752]` in pixels; the truth is `[500, 450, 1100, 750]`, so it's within 2 px. It also counted the holes (2) and markers (4) correctly.
   - So Spark can give SAM a box prompt where the colour candidate fails (low contrast) — a D4 option.
   - 🔎 This is one synthetic image, not yet a measured accuracy.
6. ⏳ **Muse Image edit fidelity:** not run yet; it's optional (`--muse-image`, $0.01) and only matters for M3 (c).
7. ✅ **Python stream parsing:** verified live with `parse_responses_stream`.

---

## 2. Assumptions challenged

| Original assumption | Why it fails | Decision |
|---|---|---|
| Muse Image "hallucinates the missing geometry based on symmetry" | Image models don't measure. The edits endpoint takes no mask. The output is resampled, so generated pixels aren't registered to millimetres | Symmetry completion is computed **deterministically** (exact and measurable). Muse Image becomes an 🧪 independent hypothesis that is re-registered and compared, and is never trusted on its own |
| Muse Spark "translates the 2D reconstruction into geometric parameters" | A VLM isn't a calibrated instrument. Asked for mm values, it produces plausible but wrong numbers | **CV measures, Spark decides.** Spark chooses among candidates the geometry engine found (numbered contour segments, symmetry axes, holes). A per-request schema only allows IDs that actually exist |
| Muse Code "dynamically writes OpenSCAD/Python at runtime" | Muse Code is an interactive CLI with no documented headless API. Executing generated code is a security and reliability liability | The AI emits a **typed, validated `PartSpec`**: data, not code. A deterministic compiler builds the solid (manifold3d) and emits an editable `.scad`. **No model output is ever executed** |
| Zero-shot SAM segmentation is enough | Fit-critical features need roughly ±0.2 mm, and a mask boundary isn't metrology | SAM gives **localisation and topology**. The boundary is then refined sub-pixel against the known mat background, inside a narrow band |
| One photograph | No scale, no thickness, hidden faces | A printed **ArUco mat** gives metric scale. The top view is required, with 2–3 shots recommended for empirical uncertainty. Thickness comes from a caliper or a side view |
| Appliances **and robotics** | Load-bearing or moving robot parts are safety-relevant | The MVP covers **non-safety-critical plastic parts**. Classing a part as "unsupported" is a product feature, not a failure |
| "Zero CAD experience" | Still true, but fit-critical numbers need a ~€15 caliper | The app asks for **exactly** the measurements it needs, ranked by their impact on fit |

---

## 3. Feasibility and alternatives considered

| Approach | Verdict | Why |
|---|---|---|
| **A. Calibrated 2.5D metrology + AI interpretation + symmetry completion (chosen)** | ✅ Feasible in 10 days | Proven building blocks (ArUco, homography, contours, CSG), with Meta models used where they're strongest. Every step is measurable |
| B. SAM 3D Objects (single image → 3D) | ⛔ as the core · 🧪 maybe a comparison slide | The shape is generative (hallucinated back faces), metric scale is unverified, the output isn't parametric, and it needs a ≥ 32 GB GPU on Modal |
| C. Photogrammetry (SfM: COLMAP/Meshroom) | ⛔ | Molded plastic is textureless, so SfM fails. It also needs many photos, heavy compute, and gives non-parametric output |
| D. Pure generative (image → image → mesh) | ⛔ | No dimensional grounding; contradicts the core principle |
| E. **Phone video + SAM 3.1 tracking + mat-calibrated space carving** | 🧪 M3 candidate | Genuinely "frontier": a true 3D outer hull for non-prismatic parts, built on SAM 3.1 video tracking. About 2 days of work; decided at gate G3 |

**Confidence** (qualitative; no invented percentages):
- M1: high
- M2: moderate to high
- M3: depends on the time left at gate G3

---

## 4. The three greatest technical risks

### R1 · Photo metrology may not reach fit-grade accuracy (highest impact)

**Error sources:**
- **Mat print scale:** 0.5–3 % if someone prints with "fit to page".
- **Part height above the mat:** perspective error is roughly h divided by camera height. Simulated (2026-10-27) on the 3 mm hero bracket: L +0.61 mm from 40 cm, +1.09 mm from 25 cm, and a hole 0.67 mm too small when the camera isn't above the part.
- **Edge localisation under the camera's tone curve:** optics blur linear light and the JPEG stores encoded values, so a half-way threshold on encoded or Lab values puts a dark part's edge 0.4–1.1 px inside the true edge.
- **Boundary localisation:** shadows, glare, white-on-white contrast, SAM mask granularity.
- **Optics and paper:** lens distortion near the edges of the frame, and paper curl.

**Consequence:** holes and pins come out the wrong size and the part doesn't fit, which is exactly how a repair fails.

**Mitigations:**
- The mat carries a 100 mm caliper-checkable bar, which gives a MEASURED scale correction.
- Sub-pixel band refinement on a controlled background, thresholded in linear light (✅ synthetic, 2026-10-27).
- Height correction from the recovered camera pose (§6.3; ✅ synthetic, 2026-10-27).
- Two or more photos give an empirical spread.
- The app prompts for caliper values on fit-critical features.
- Errors are reported, never hidden.

**Early signal:** M1 test AT-3 on Wed 28 Oct (gate G2).

**Fallback:** "caliper-first" mode. The photo supplies topology and layout, and the caliper supplies fit-critical numbers.

### R2 · AI interpretation can be confidently wrong

**Failure modes:**
- Spark misidentifies fracture edges, picks the wrong symmetry, invents features or misclassifies the family.
- SAM grabs a shadow, the mat or a marker, or merges holes.

**Consequence:** a plausible-looking but wrong reconstruction, which is the worst possible outcome for credibility.

**Mitigations:**
- Choices are constrained to enums of existing IDs.
- **Every AI claim is checked geometrically**, with a measured support value.
- Disagreements are shown to the user.
- The user confirms before export.
- Accuracy is measured on a small labelled set.

**Early signal:** the Day-1 spike, then D4.

**Fallback:** manual-assist mode. The user clicks the fracture segments and the symmetry axis, while the AI still segments and explains.

### R3 · Real broken parts often don't fit a simple representation

**Hard cases:**
- **Hard to see or represent:** draft angles, multiple thickness levels, ribs, snap hooks and undercuts, blind holes, top-edge fillets and threads either can't be seen from above or can't be expressed as a single-thickness extrusion.
- **No surviving evidence:** a break that destroys both symmetric halves leaves nothing to mirror.

**Consequence:** wrong models, or a demo part that falls outside the supported families.

**Mitigations:**
- **Deliberate scope:** 2.5D with mirror and rotational completion first, then multi-view intersection and revolve.
- **Explicit "unsupported" classification**, with reasons.
- **UNCERTAIN regions** instead of invented geometry.
- **"Twin part" capture:** an intact sibling becomes OBSERVED evidence.
- **Demo parts chosen before the kickoff.**

**Fallback:** unsupported cases are shown honestly, as designed behaviour.

### Secondary risks

| Risk | Mitigation |
|---|---|
| Preview-API surprises (mask format, latency, outages) | Day-1 spike, recorded fixtures, retries, and a classical-segmentation fallback that is clearly labelled |
| Schedule (solo, about 9.4 days) | Vertical slice by D3, decision gates, feature freeze on 3 Nov |
| Rules (prior work, AI tools, deliverables) | Wait for the official rules before writing project code |
| Muse Image may add nothing | It's 🧪 and can be removed without touching the core |

---

## 5. MVP definition

### 5.1 Supported part families

| Family | Examples | Evidence needed | Milestone |
|---|---|---|---|
| **2.5D extruded profile**: constant thickness, through-holes. **Primary demo: flat, mirror-symmetric, with mounting holes** | Brackets, mounting plates, clips, latches, spacers | Top photo(s) on the mat + thickness (caliper or side photo) | **M1–M2** |
| 2.5D with **rotational symmetry** (secondary) | Spur gears with broken teeth, star knobs, hubs | Same as above | 📋 M3 candidate |
| Multi-view intersection (top ∩ side) | L-brackets, stepped blocks, hook profiles | + side photo | 📋 M3 |
| Revolved (axisymmetric) | Knobs, caps, bushings, feet | Side photo | 📋 M3 |
| Freeform, internal geometry, threads, flexible, transparent or safety-critical parts | — | — | ⛔ Classified "unsupported", with reasons |

### 5.2 Capture protocol

1. **Print the Re-Forge mat** (A4 or Letter). It has 12 ArUco markers around a plain central zone, a 100 mm check bar and a mat ID.
2. **Measure the bar once** with the caliper. The app stores the correction.
3. **TOP photo** (revised 2026-10-27, after the height-correction work):
   - Lay the part flat in the centre, and hold the phone roughly parallel, above the part.
   - **Use the 2× or 3× lens and step back until the mat fills the frame.** Parallax shrinks 2–3× and resolution on the part goes up.
   - Use diffuse light, no flash.
   - **Keep the original file.** Upload it as taken, in JPEG ("Most Compatible" on iPhone), not as a screenshot or a messaging-app copy, which drop the EXIF focal length that the height correction uses.
   - One photo is required; 2–3 are recommended, moving the part or the phone between shots.
4. **SIDE photo** (M3): the part on its edge.
5. **DETAIL photos** (optional): a close-up of the break, and the part in its assembly. These help Spark understand what the part does.
6. **TWIN photo** (optional): an intact identical part, if one exists.

### 5.3 In scope, stretch and out of scope

**MVP (M1 + M2):**
- Calibration and capture-quality checks
- SAM 3.1 segmentation with click refinement
- Sub-pixel boundary refinement and holes
- Spark interpretation
- Mirror-symmetry completion with provenance (rotational completion is an M3 candidate)
- Confidence engine
- PartSpec → solid → STL + `.scad` + report
- Mesh and printability validation
- Guided web UI with live parameter edits and an export gate
- Usage ledger
- Tests
- Real-part evaluation

**M3 candidates** (pick about two at G3):
- (a) Side view: thickness, multi-view intersection, revolve
- (b) Rotational symmetry and involute gear fit (module, teeth, standard-size suggestions). Secondary, per directive 1
- (c) 🧪 Muse Image hypothesis cross-check
- (d) Spark visual review, plus **natural-language edits** through tool calls over typed PartSpec patches
- (e) 🧪 Video space carving
- (f) Height (perspective) correction, if D7 didn't already do it
- (g) **SAM 3.1 video capture for multi-frame metrology** (new in v0.3):
  - A 5–10 s handheld phone video over the part on the mat.
  - **One** SAM 3.1 video call tracks the part across frames (about $0.06 for 300 frames).
  - Frames are chosen automatically by sharpness and calibration residual.
  - The many independent measurements give each dimension an **empirical** ±U.
  - It strengthens the Confidence Engine (directive 4) using a distinctive SAM 3.1 capability. It extends D5's multi-photo fusion, so it builds on the core rather than beside it.

- (h) **Hands-free caliper entry with Muse Voice Transcribe** (new in v0.4):
  - While both hands hold the part and the caliper, the user says "hole one diameter four point two one".
  - Voice Transcribe turns it into text, Spark maps it onto a typed `set_param` patch, and the value becomes MEASURED after on-screen confirmation.
  - Cheap ($0.18 per audio hour), a real workflow need, and it adds a fourth Meta model.
- (i) **Open-weight reasoning backend** (new in v0.4):
  - Run the interpretation step on Muse Spark Open (Baseten, model `meta-models/muse-spark-open-1026`) or Muse Glimmer.
  - A/B it against Spark 1.3 on our labelled set.
  - Opens the $10k open-weight bonus prize.
  - Depends on partner credits and on structured-output support there (🔎).

**G3 ranking by the official judging weights** (Meta tooling 25 %, Demo 25 %), protecting the core at all times:

1. (g) video multi-frame metrology
2. (d) Spark natural-language edits and visual review
3. (h) voice caliper entry
4. (c) 🧪 Muse Image cross-check
5. (i) open-weight backend
6. (f) height correction
7. (a) side view
8. (b) gears (secondary)
9. (e) space carving: too large for the window

If we're behind schedule at G3, M3 is dropped and D8 becomes buffer.

**Protecting the core (directive 3):** M3 work happens on a separate branch behind a feature flag. It merges only if every M1 and M2 acceptance test still passes and the demo flow is unchanged.

**Out of scope:** STEP/B-rep export, threads, FEA or strength claims, assemblies, a mobile app, user accounts.

---

## 6. Architecture

### 6.1 Pipeline

```
 CAPTURE ─ printed ArUco mat · TOP ×1–3 · SIDE · DETAIL · TWIN
   │
 1 CALIBRATE   local · OpenCV       markers → homography → reprojection RMS → mat-scale correction
   │                                → blur/tilt/glare/occlusion checks → rectified metric image (~10–15 px/mm)
 2 SEGMENT     Meta · SAM 3.1       rectified crop + noun phrase (or user click → point prompt) → instances
   │                                → target chosen (inside mat, not a marker, user-confirmable)
 3 REFINE      local · OpenCV       band-limited sub-pixel boundary vs mat background model → through-holes
   │                                → OBSERVED outline in mm + per-segment boundary uncertainty
 4 INTERPRET   Meta · Muse Spark    Set-of-Mark overlay (numbered segments S*, axes A*, holes H*) + photos + facts JSON
   │                                → strict-schema PartAnalysis (family, fractures, symmetry, features, questions)
 5 VERIFY &    local · geometry     every AI claim checked (roughness, symmetry support, landing tests)
   COMPLETE                         → mirror/rotational completion → outline with provenance runs
 6 PARAMETRISE local                circle/line/arc fits · design-intent proposals (opt-in) → PartSpec v1
 7 BUILD       local · manifold3d   PartSpec → solid → mesh  (+ deterministic .scad emitted from the same spec)
 8 VALIDATE    local · trimesh      watertight · genus = #holes · volume · bbox vs spec · min wall/hole · consistency
 9 REVIEW &    browser              provenance-coloured 2D/3D · edit params (~100 ms rebuild) · export gate
   EXPORT                           → model.stl · model.scad · report.json
```

**Design rule:** AI outputs are **untrusted data**.
- They enter only through strict schemas, then server-side Pydantic validation, then geometric verification.
- Nothing a model produces is ever executed.
- Every real AI call is logged to the usage ledger.

### 6.2 Components (modular monolith)

| Module | Responsibility |
|---|---|
| `capture/` | Mat PDF generator; marker detection; homography; rectification; quality checks; focal length and pose estimate |
| `meta_api/` | One client for all Meta models: timeouts, retries with jitter (429/5xx/timeout), budget guard, usage ledger, content-addressed dev cache |
| `vision/` | SAM 3.1 requests and mask decoding (`meta-sam-parser`); instance selection; band refinement; hole detection |
| `reasoning/` | Set-of-Mark overlay rendering; per-request JSON-schema builder (dynamic enums); Spark calls; response validation |
| `geometry/` | Contours and their split into S* segments; roughness; mirror and rotational symmetry search; completion; fitting; uncertainty budget |
| `spec/` | `PartSpec` (Pydantic); semantic validation (ranges, topology, limits); patch operations for the UI and natural-language edits |
| `cad/` | manifold3d builder; `.scad` emitter; STL export |
| `validation/` | Mesh, topology, printability and consistency checks → validation report |
| `jobs/` | Job state machine; filesystem store; SSE progress events with real stage timings |
| `api/` | FastAPI routes; upload hardening; rate limits |

### 6.3 Metrology details

- **Homography:** fitted from up to 48 marker corners (12 markers), jointly with one shared corner bias along the marker diagonals (✅ 2026-10-27). Sub-pixel corners sit about 0.9 px inside the true corners under realistic optics, and print dot gain pushes them out; unmodelled, that bias was the whole 0.16–0.19 mm residual. The remaining RMS residual, in mm, is reported as a quality figure.
- **Mat scale:** the user measures the 100 mm bar with the caliper, which gives a MEASURED correction factor for each printed mat.
- **Rectification:** done at the native resolution of the part region, with no upsampling. The rectified pixel grid is then directly in mm.
- **Band refinement:**
  - A robust colour model of the mat background and the part. Lab for the contrast and glare tests; **linear light for the edge position** (✅ 2026-10-27), since that's where optics blur. Rectification also interpolates in linear light.
  - A foreground-probability field inside a ±0.3 mm band around the SAM boundary.
  - A sub-pixel iso-contour of that field (marching squares), smoothed by one pixel along its length; the raw trace is kept as evidence and for roughness.
  - The edge spread σ is measured on each photo (∫ t(1 − t) dn = σ/√π). Hole radii get the blur-curvature correction σ²/(2R).
  - The discrepancy between the SAM and refined boundaries is reported per segment.
- **Through-holes:** interior regions that match the mat background, plus holes in the mask. A circle fit (algebraic start, then geometric least squares) gives the centre, Ø, roundness and residual.
- **Height correction** ✅ on synthetic data (2026-10-27); ⏳ real parts (AT-3):
  1. **Focal length:**
     - From H's orthonormality constraints, with a bootstrap over markers for its σ (square pixels and a centred principal point are assumed).
     - From EXIF (35 mm equivalent, the only metadata kept from an upload).
     - Fused when both exist; a mismatch is flagged. With neither, a 26 mm prior is used, flagged `POSE_FOCAL_ASSUMED`.
  2. **Camera centre:** recover the height Zc and the nadir point, with first-order σ from the focal length and the principal point.
  3. **Outline:** for a prism of thickness h, m = Zc / (Zc − h). The photographed outline is the union of the slices scaled by [1, m] about the nadir. The exact footprint is **the intersection of S scaled by every factor in [1/m, 1]**: (S ∩ S/m) minus the trapezoids S's edges sweep.
     - The v0.4 formula S ∩ S/m alone is exact only when every ray from the nadir crosses the outline once. A U-shaped notch left 0.55 mm spurious corners.
  4. **Round holes:** fit a two-disc visibility model (the bottom opening, intersected with the top opening as projected). Other holes: the dual sweep formula.
  5. **Single-view limit:** a gap shorter than (m − 1)·distance along a ray is hidden. Near concave corners the footprint keeps that zone as material; `occlusion_bound_mm` is reported, and two viewpoints (D5) resolve it.
  6. **Reported values:** `u_persp_mm_2sigma` and the photographed-vs-footprint extents. 📋 Measure before/after on real parts.

### 6.4 Muse Spark interpretation (grounded and constrained)

> **Status (2026-10-28):** ✅ implemented (`reforge/reasoning/`). Tested offline with labelled fixtures, and live on synthetic photos (3 runs). The user's real collage was refused correctly. Details in `docs/EVALUATION.md`.
> - **What Spark gets:** the whole free zone plus a marked close-up, and measured facts (segment lengths, hole Ø, each axis's support, matched and contradicting holes, the material its mirror would add, the trace's share of the objects on the mat, colour spread).
> - **What Spark doesn't get:** the geometric irregularity labels. Its fracture picks are an independent judgement that the verification checks.
> - **Verification rules:** the axis needs ≥ 90 % support and no hole contradiction; a fracture pick must not match its mirror image.
> - **Refusal gates:** family ≠ `extruded_profile` → `FAMILY_UNSUPPORTED`, no model built. A trace covering under 20 % of the objects on the mat → `TRACE_PARTIAL`, decided by geometry before any model call.
> - **Fallback:** a model failure falls back to the geometric rule, labelled not AI.

**Inputs:**
- The top photo, downscaled.
- A **Set-of-Mark overlay**: the outline split into about 20–40 numbered segments `S0…Sn`, the candidate axes `A0…Ak` drawn with their measured support, and the holes `H0…Hm`.
- The detail photos.
- A compact facts JSON: bounding box, holes, candidate scores, segment roughness.

**Output:** a `PartAnalysis` under a **per-request schema**. Its enums contain only the IDs present in that request, so the model can't reference a segment that doesn't exist. Fields:
- `family`: `extruded_profile | revolved | multi_view | unsupported`, with reasons
- `fracture_segment_ids`
- `symmetry`: `mirror | rotational | none | unsure`, plus the chosen candidate ID
- hole roles
- missing features (expressed through IDs)
- `required_measurements`, prioritised
- a short rationale for each decision

**Verification:**
- Fracture picks are compared with the geometric roughness measure.
- A chosen axis must have measured support above a threshold.
- A mirrored feature must land inside the reconstructed region.
- Anything that fails is downgraded to UNCERTAIN and shown to the user.

**Optional extras:**
- *Auto-prompt:* a tiny Spark call names the object (for example "plastic gear"), and that phrase becomes SAM's noun phrase.
- *Review:* Spark looks at the final overlay and lists discrepancies. This is advisory only.

### 6.5 Symmetry and completion (deterministic and measurable)

> **Status (2026-10-28):** ✅ mirror search and completion (`geometry/segments.py`, `symmetry.py`, `completion.py`). 📋 rotational search.
> - **Fracture evidence:** a primitive-piece decomposition; a fracture is a run of short pieces.
> - **Support and holes are kept apart:** a mixed score once let an axis 3.4 mm off rebuild the part 6.9 mm long. Holes pin the axis; `offset_ambiguity_mm` reports where nothing does.
> - **Mirrored holes:** a mirrored hole is added only inside added material.
> - **Uncertainty:** U for INFERRED geometry = 2·√(RMS² + (angle σ · lever)² + (2 · offset σ)²). 📋 D5: replace the bootstrap angle σ with a segment jackknife, since the bootstrap under-estimated it 4× in one test.

- **Mirror symmetry:**
  - *Candidates:* the principal axes, the perpendicular bisectors of equal-diameter hole pairs, and a coarse 1° sweep.
  - *Scoring:* reflect the **intact** boundary and compute two numbers. *Support* is the fraction of reflected points within τ (about 0.3 mm) of the intact boundary. The other is the inlier RMS, in mm.
  - *Refinement:* the best candidate is refined by least squares. Its axis-angle uncertainty is estimated by bootstrap.
- **Rotational order n** (M3 candidate, secondary):
  - Take the polar signature r(θ) around the bore or centroid, excluding fracture bins.
  - Find the period with a Lomb–Scargle periodogram, which tolerates the gaps.
  - Verify by rotating the outline by 360°/n and computing support and RMS.
- **Completion that doesn't erase real asymmetry:**
  - Add only the connected components of `reflect(P) \ P` (or of the rotated copies) **that touch fracture segments**.
  - Components elsewhere are reported as "asymmetry detected, not filled".
  - A mirrored hole is added only if it lands inside the added region.
- **Provenance runs on the outline:**
  - `OBSERVED(photo)`
  - `INFERRED(mirror A2 of S3–S7)`
  - `UNCERTAIN(bridge)`
  - `MEASURED/USER(edit)`
  - Fracture edges are kept for display, but excluded from the final solid wherever they've been replaced.

### 6.6 Confidence engine: statuses and a defensible uncertainty

| Status | Meaning | Uncertainty shown |
|---|---|---|
| **MEASURED** | A user caliper value, or a user-confirmed calibration | Instrument and reading error (default ±0.05 mm, user-editable) |
| **OBSERVED** | Computed from calibrated image evidence | ±U (mm, 2σ) from the error budget below |
| **INFERRED** | Derived from a stated rule (mirror, rotation, design intent) **with measured support** | U(source) ⊕ symmetry residual RMS ⊕ axis-angle error × lever arm, with the rule and its support shown |
| **UNCERTAIN** | No adequate evidence | No number shown. **Blocks export** until the value is measured, edited or explicitly accepted. An acceptance is stamped into the report and the `.scad` |

**Error budget for OBSERVED values** (combined root-sum-square):

`U = 2·√(u_cal² + u_scale² + u_edge² + u_fit² + u_persp²)`

- `u_cal`: homography residual
- `u_scale`: residual mat scale after the bar check
- `u_edge`: refinement band discrepancy and edge width
- `u_fit`: primitive-fit RMS
- `u_persp`: the height bound, or the residual after correction

With two or more independent top photos, the modelled random terms are replaced by the **empirical spread across photos**. Scale stays a systematic term.

**Checking the budget itself:** on real parts with caliper ground truth, we report **coverage**, the fraction of true values that fall inside ±U. If coverage is poor, the budget is inflated and the change is documented. No other "confidence" numbers are shown.

**In the UI**, each status is shown by **colour, pattern and label** (solid, dashed, hatched), so it's colour-blind safe. Every value has a "why?" popover that lists its evidence.

### 6.7 🧪 Muse Image as an independent hypothesis

1. Send the rectified crop as an instruction edit ("restore the broken section as when new; change nothing else").
2. Register the result back to the input frame with ECC or feature alignment on the intact region. This step is needed because the output is resampled.
3. Segment the result with SAM 3.1.
4. Compare it with the geometric completion **inside the missing zone only**: IoU, and Hausdorff distance in mm.
5. Show it as a toggle overlay together with its agreement score.
6. When a part has no symmetry, offer the result as a starting point, labelled UNCERTAIN (generative), which requires explicit acceptance.
7. If the spike shows it doesn't help, cut it.

### 6.8 PartSpec, build and export

**`PartSpec` v1** (JSON, Pydantic) contains:
- units (mm) and `family`
- outline points with their provenance runs
- holes (circle or polygon)
- thickness
- fit compensation (hole offset, outline offset)
- a `params{}` table, where each entry has a value, status, U and evidence[]

**Limits:**
- at most 2,000 outline points
- every coordinate within ±500 mm
- the outline is a simple, valid polygon
- holes lie strictly inside, with a wall of at least 0.4 mm
- thickness between 0.4 and 200 mm
- all numbers finite

**Build:** manifold3d runs in-process, with no subprocess.
1. A `CrossSection` from the outline and the compensated holes.
2. `extrude`, `revolve`, or an intersection of view extrusions.
3. Mesh → binary STL.

A rebuild takes milliseconds: a 2-hole plate built in 6.3 ms in the 2026-10-23 smoke test. Live parameter editing is therefore practical.

**`.scad` export:**
- Emitted deterministically from the same spec, with named parameters and provenance comments. Example: `hole_1_d = 4.20; // OBSERVED ±0.12 mm (circle fit, 3 photos)`.
- Never executed in production.
- A CI test renders it with OpenSCAD (in Docker) and checks volume and bounding box against the manifold3d result.

**Validation checks:**
- watertight and manifold, one body
- **genus equals the number of through-holes** (Euler check)
- volume ≈ area × thickness
- bounding box within 0.01 mm of the spec
- minimum wall ≥ 0.8 mm and minimum hole ≥ 1.0 mm (FDM defaults, configurable)
- zero degenerate triangles
- the share of outline length under each status

**Exports:** `model.stl`, `model.scad` and `report.json` (all evidence, validation results, AI calls and timings). Each carries the disclaimer: *a reconstruction, not a verified replacement; not for safety-critical use.*

### 6.9 Security and reliability

**Secrets:**
- `META_MODEL_API_KEY` lives only in `.env`, which is git-ignored. `.env.example` is committed.
- Loaded via pydantic-settings.
- Redacted from logs and never sent to the browser.
- An automated test greps the logs and the frontend bundle for it.

**Uploads:**
- Magic-byte check; at most 20 MB and 40 MP.
- EXIF orientation is applied, then **all metadata (including GPS) is stripped** before anything leaves the server.
- Job IDs are random; no path is user-controlled.

**AI input and output:**
- Strict schemas, server-side validation and geometric verification.
- A prompt injection hidden in a photo can at most choose among valid IDs.
- No code execution. OpenSCAD only runs in CI, on our own emitter's output.

**Meta API client:**
- Timeouts: 5 s to connect, 60 s to read.
- Up to 3 retries with exponential backoff and jitter on 429, 5xx and timeouts.
- Typed errors mapped to UI messages.
- Degradation per model:
  - Spark down → manual-assist mode.
  - SAM down → classical segmentation, **labelled as such in provenance**.

**Budget and abuse protection (public demo):**
- daily spend cap and per-IP job limit
- demo token
- CORS locked down and request-size limits
- non-root container

**Usage ledger:**
- A JSONL record per call: stage, model, latency, tokens (input, output, reasoning), images, estimated cost from the pricing table, and status.
- Shown per job and on `/usage`.

**Dev cache:**
- Responses are keyed by a hash of model, prompt version and inputs. This saves credits and keeps tests deterministic.
- Recorded fixtures are labelled *"recorded real response, model, date"*.

### 6.10 Stack (with reasons)

| Layer | Choice | Why |
|---|---|---|
| Backend | Python 3.12 · FastAPI · Pydantic v2 · uv (lockfile) | The CV and geometry ecosystem is in Python; typed I/O; reproducible environment |
| CV | OpenCV 4.14 (contrib, headless; pinned `<5`): ArUco, homography, contours · scikit-image (sub-pixel contours) · NumPy/SciPy | Mature, CPU-only and fast; ArUco verified on this VPS |
| Geometry | Shapely 2 (2D booleans and buffers) · manifold3d (CSG kernel with guaranteed-manifold output) · trimesh (checks, STL) | pip-installable, no external binaries, robust booleans |
| Meta API | `openai` SDK pointed at the Meta base URL · `meta-sam-parser` · httpx | The officially supported compatibility path |
| Frontend | Node 24 LTS · Vite 8 · React 19.3 · TypeScript 5.9 (pinned) · Tailwind 4 · three.js (react-three-fiber 9) · SVG overlays · types generated from the OpenAPI spec | Fast to build; typed end to end. Node 20 is EOL, and TypeScript 7 is incompatible with `openapi-typescript` (see `docs/ENVIRONMENT.md`) |
| Tests | pytest (unit, synthetic, recorded-fixture and `-m live` suites) · Vitest · tsc · ruff · mypy on core modules | Keeps deterministic tests separate from paid live tests |
| Deploy | One multi-stage Docker image (FastAPI also serves the SPA) + Caddy (HTTPS) via compose on the VPS. No database, queue or Redis; jobs are stored on the filesystem | Lowest operational complexity, since all heavy models are remote |

**Versions verified on this VPS (2026-10-23):** see `docs/ENVIRONMENT.md`.

**VPS fit:** 4 vCPU, 15 GiB RAM, no GPU, 35 GB of free disk. That's enough because inference is remote. Before deploying I'll inspect existing services and ports, and I won't touch anything existing without your approval.

### 6.11 Repository layout (created on D1, not before)

```
reforge/
├─ docs/  PLAN.md · PROGRESS.md · ARCHITECTURE.md · EVALUATION.md (measured results only) · DEMO.md
├─ backend/  pyproject.toml · uv.lock · reforge/{api,capture,meta_api,vision,reasoning,geometry,spec,cad,validation,jobs} · tests/{unit,synthetic,fixtures,live}
├─ frontend/  package.json · src/{steps,viewer,overlays,api}
├─ docker/  Dockerfile · compose.yaml · Caddyfile
├─ samples/  real photo sets for the "try a sample" demo (+ caliper ground-truth CSV)
├─ LICENSE · NOTICE · THIRD_PARTY_NOTICES.md
└─ .env.example
```

### 6.12 Cost estimate (to be replaced by ledger numbers)

| Item | Per job (estimate) | Basis |
|---|---|---|
| SAM 3.1 | 2–6 calls, about $0.005–0.015 | $2.50 per 1k images |
| Muse Spark 1.3 | 2–3 calls, about $0.03–0.10 | Depends on image tokens and reasoning; to be measured 🔎 |
| Muse Image | about $0.01–0.02 | Only if used |

- **Totals:** roughly **$0.05–0.15 per job**, or **$15–50 for all of development** (a few hundred jobs).
- **Model tier:**
  - The default is the **standard tier** for any user photos.
  - Contributor tiers are 10× cheaper, but content may be used to train Meta models. Per directive 5 they're allowed only for synthetic or our own non-sensitive test images, behind `REFORGE_ALLOW_CONTRIBUTOR_TIER` (default off).

---

## 7. Product experience

1. **Start.** "New repair": a capture guide, the mat download and example photos.
2. **Photos and calibration:**
   - Drag in several photos and tag each one's role.
   - Each photo gets a card, for example *"markers 11/12 · 13.8 px/mm · residual 0.04 mm · tilt 6° · sharpness OK"*.
   - Warnings explain how to reshoot.
3. **Segmentation.** The SAM 3.1 overlay. Click + and − points to fix it, then confirm.
4. **Interpretation:**
   - Spark's summary of the part, its family and the damage.
   - Numbered segments, with fractures highlighted and toggleable.
   - Symmetry candidates with their measured support.
   - Spark's measurement requests as inline inputs ("Thickness (caliper) ___ mm").
5. **Workbench:**
   - A 2D profile drawn in provenance styles.
   - A 3D viewer with walls coloured by provenance.
   - A parameter table: value, ±U, status chip, "why?" and edit, with about a 100 ms rebuild.
   - A validation card, fit compensation and an AI-usage panel showing real numbers.
6. **Export.** Gated. STL, `.scad` and report, with the disclaimer.

**Across all steps:**
- **Progress:** a stage stepper driven by **real** SSE events with measured durations. No simulated progress.
- **Look:** a dark engineering workspace, monospace numerics, a restrained palette.
- **"Try a sample":** bundled real photo sets let judges run the real pipeline without printing a mat.

---

## 8. Evaluation and demonstration

**Synthetic benchmark** (automated, labelled synthetic):
- Procedurally generated parts and breaks, rendered onto a virtual mat with random tilt, noise and blur.
- Measures metrology error, and completion IoU and Hausdorff distance, against exact ground truth.
- Isolates the geometry from SAM: a threshold segmenter is used here, **labelled as a test backend**.

**Real parts** (the core evidence): 3–5 cheap plastic parts, chosen and measured following `docs/DEMO_PART_GUIDE.md`, with ground truth recorded in `docs/ground_truth_template.csv`.
1. Caliper-measure 5–10 dimensions on each part **while it's still intact**, and photograph it intact.
2. **Break it.**
3. Reconstruct it.
4. Report:
   - per-dimension error and coverage of ±U
   - inferred-region IoU against the intact silhouette
   - stage timings and API cost per job

**Spark accuracy:** fracture-segment precision and recall on about 10–20 hand-labelled photos. This also decides between Spark and Wonder on evidence.

**Print and fit test** (a primary objective under directive 2, if a printer becomes available):
- Print the reconstructed STL.
- Measure the print with the caliper.
- Test the fit in the real assembly.
- Record pass or fail with photos.

Without a printer, that's stated rather than implied.

**Demo video** (about 3 minutes):
1. The broken part and its story.
2. Capture.
3. The live pipeline, with real timings.
4. The provenance view.
5. A caliper check on camera.
6. The STL and `.scad`.
7. The print, if there is one.
8. An **unsupported part being refused, with reasons**.
9. A slide of measured results.

---

## 9. Roadmap (Paris time)

| Day | Date | Focus | Exit criterion |
|---|---|---|---|
| Prep | Thu 22 → Mon 26 17:00 | Rules, parts, caliper, ✅ tooling, API verification (once the key is in `.env`). **No project code** | §11 checklist done |
| D1 | Mon 26 (evening) | Read the rules; project scaffold (pinned deps); **API spike** on whatever `prep/verify_meta_api.py` hasn't already answered; mat PDF; print the mat; photograph the intact parts | Gate **G1** recorded in PROGRESS.md: refinement depth, Spark grounding strategy, Muse Image viability |
| D2 | Tue 27 | Calibration, rectification and quality checks; SAM client and decoding; band refinement; holes; synthetic harness | A mm profile from a real photo |
| D3 | Wed 28 | PartSpec and validation; manifold3d build; mesh checks; `.scad` emitter; CLI; minimal API and an upload→3D→download page | **M1: AT-1…AT-7 (§10)** · gate **G2** (accuracy) |
| D4 | Thu 29 | Spark PartAnalysis (Set-of-Mark, dynamic enums); roughness; mirror and rotational search; completion with provenance | A broken part yields a completed profile with provenance. ✅ Done Wed 28 on synthetic photos, with live Spark; rotational search 📋 |
| D5 | Fri 30 | Confidence engine (budget, statuses, export gate); caliper overrides and scale correction; fitting and proposals; multi-photo fusion | The report shows ±U and a status for every parameter |
| D6 | Sat 31 | Full guided UI, SSE, live edits, exports, usage panel | **M2** · gate **G3** (pick the M3 features) |
| D7 | Sun 1 Nov | Real-part evaluation against caliper ground truth; accuracy fixes; print test. (Height correction and linear-light edges were moved forward and done on Tue 27 Oct, on synthetic data.) | `EVALUATION.md` with measured numbers |
| D8 | Mon 2 | Two M3 features (§5.3) | Shipped, or cut cleanly |
| D9 | Tue 3 | Hardening: tests, security review, Docker, deployment, docs, samples. **Feature freeze at 20:00** | Deployed demo; clean test run |
| D10 | Wed 4 | Video, write-up, final verification. **Submit by 22:00 CET** (5-hour buffer) | Submitted |

**M2 acceptance:**
- A completed profile is produced on at least 2 real broken parts that have intact ground truth.
- 100 % of the outline length, and every parameter, carries a status.
- Inferred dimensions are compared against the caliper and reported. The target is ≤ ±0.5 mm, and it's claimed only once measured.
- The export gate blocks unresolved UNCERTAIN values.
- The whole flow is usable in the browser without dev tools.

---

## 10. Milestone 1: first end-to-end vertical slice (target Wed 28 Oct)

> **Status (2026-10-28, evening):**
> - ✅ D4: a broken part is rebuilt from one synthetic photo, through SAM 3.1, Muse Spark, verification and mirror completion with provenance.
>   - Geometric rule, 24 photos: 24/24 rebuilt; L +0.008…+0.040 mm; W −0.003…+0.061 mm; Ø 4.192–4.201.
>   - Live Spark (3 runs): the fracture read matched the geometry, the right axis was chosen, and one over-pick was rejected by the verification.
> - ✅ Refusal gates for out-of-scope inputs, prompted by the user's first real test.
> - ⏳ AT-3 and M2 still need real photos of real parts.
>
> **Status (2026-10-27, evening):**
> - ✅ Real-photo physics in the harness and the pipeline: parts with real thickness, linear-light optics, camera pose, height correction, marker corner bias, edge-spread measurement. On a 3 mm part (synthetic, 1×–3× lenses, tilted or flat-on): L/W within +0.036 mm, hole Ø within ±0.007 mm, hole spacing within ±0.007 mm (`docs/EVALUATION.md`). Real photos are still unmeasured.
> - The M1 target for AT-3 (L/W ±0.5 mm, Ø ±0.3 mm) is unchanged. Without the height correction a 1× photo would likely have missed it on Ø (simulated −0.67 mm).
>
> **Status (2026-10-26, 18:30 Paris):**
> - ✅ AT-1, AT-4 and AT-5: pass on synthetic data (AT-5 with the labelled classical backend).
> - ✅ AT-6 web slice: verified in headless Chromium (upload → calibration card → outline overlay → 3D view → STL download; no page errors). Opening the STL in a slicer is still for the user.
> - ✅ AT-7 (partial): upload size and pixel limits, non-image rejection, EXIF/GPS stripping, traversal-proof file serving, typed errors, and the key never appears in responses or the ledger.
> - ✅ AT-2 (2026-10-27): passes live through the production code on a SYNTHETIC photo, in box-first and click modes. Each mode makes one SAM call (confidence 0.988 / 0.992, 3.1 s / 2.3 s); the ledger records latency and cost.
> - ⏳ AT-3 needs the printed mat and real photos.
> - Measured numbers are in `docs/EVALUATION.md`.

**Scope:**
- **Input:** one real TOP photo of **Part A** on the printed mat, plus a caliper thickness. Part A is a flat plastic part with at least one round through-hole, intact or broken.
- **Pipeline:**
  1. Calibration.
  2. A real SAM 3.1 call, then mask decoding.
  3. A sub-pixel refined outline in mm, plus holes.
  4. PartSpec.
  5. A manifold3d solid.
  6. A validated STL.
- **Delivery:** a CLI and a minimal web page.
- **Not yet included:** reconstruction of missing geometry. M1 proves the metrology chain that everything else stands on.

| # | Acceptance test | Type | Pass condition |
|---|---|---|---|
| AT-1 | Calibration on synthetic mats (tilt 0–25°, noise, blur, partial occlusion) | automated | Scale error < 0.2 %. Fewer than 4 detected markers gives the typed error `CAL_MARKERS_INSUFFICIENT`, not a crash |
| AT-2 | SAM 3.1 client | live (`-m live`) + recorded fixture | A real call returns at least one instance. The mask decodes with `meta-sam-parser` and matches its box within ±2 px. The ledger entry has a latency and a cost estimate |
| AT-3 | Metrology on real Part A | live, manual | Overall L/W and hole Ø are compared with the caliper and **reported**. M1 target: L/W within ±0.5 mm, Ø within ±0.3 mm. A miss triggers gate G2: one metrology day before reconstruction |
| AT-4 | Build and validation | automated | For synthetic specs (rectangles with holes, concave outlines, 500-point outlines): watertight, one body, genus = number of holes, volume = area × t within 0.5 %, bounding box within 0.01 mm. Invalid specs (self-intersection, hole outside, t ≤ 0, NaN, more than 2,000 points) are rejected with typed errors |
| AT-5 | End-to-end CLI | live | `reforge run --photo partA_top.jpg --thickness <caliper>` writes `model.stl`, `model.scad` and `report.json`, with per-stage timings recorded (target: under 90 s total) |
| AT-6 | Web slice | manual + screenshot | Upload → calibration card → mask overlay → 3D view → STL download works in Chrome. The STL opens in a slicer without repair prompts (if you have one) |
| AT-7 | Safety and robustness | automated | The API key is absent from logs, responses and the frontend bundle. A non-image or oversized upload returns 4xx. A simulated API timeout is retried, then returns a typed error |

---

## 11. Before kickoff: checklist for you

1. ✅ **Official rules:** published 25 Oct and summarised in §1.1. Accept them when prompted.
2. ✅ **Acceptance and credits:** the $150 credits were claimed (reported by the user, 2026-10-28). Still to do from the guide: set the **Spend Limit notification at $150** on the Billing page. For reference, the claim steps were:
   - Use the form in the "know before you go" email.
   - You'll need your Model API Team ID.
   - Your account must have a payment method on file.
   - Credits can take about 2 business days to arrive; until then, usage is billed to your card.
   - Also log in to the submission portal and note its required fields.
3. **Digital caliper** (0.01 mm resolution, about €15–25), if you don't have one.
4. **3–5 sacrificial plastic parts.** Ideally:
   - one flat, mirror-symmetric part with holes
   - one spur gear
   - one real broken part from an appliance (the "hero" story)

   Don't break them yet.
5. **Caliper-measure the intact parts**, 5–10 dimensions each. I'll provide a CSV template on D1.
6. **Printing:**
   - A paper printer for the mat, set to 100 % / "actual size".
   - Access to a **3D printer** (yours, a fablab, or the university's) for the fit test.
7. ✅ **Tooling** (done 2026-10-23):
   - uv 0.13.5, Python 3.12.15 and Node 24.22.1 LTS, all user-space and checksum-verified.
   - The Python stack is smoke-tested.
   - Docker images are verified and get pulled when first needed.
   - Details in `docs/ENVIRONMENT.md`.
8. ✅ **GitHub:** the public repository `Juste-medis/reforge`, first pushed 2026-10-27. Pushes are made by the user.
9. ⏳ **API key:** copy `.env.example` to `.env` and set `META_MODEL_API_KEY`. Then run `~/.local/bin/uv run prep/verify_meta_api.py` (about $0.01).
10. **Optional:** request the Baseten ($100) and Modal ($100) partner credits now; the forms are in the guide. Applying commits you to nothing, and it keeps M3 (i) possible.

---

## 12. Decisions needed from you

1. ✅ **Architecture:** approved 2026-10-23, with the directives at the top of this plan.
2. ⏳ **Hardware and parts:** caliper, 3D printer and hero part are still to be confirmed (see `docs/DEMO_PART_GUIDE.md`).
3. ⏳ **Availability:** realistic hours per day, 26 Oct to 4 Nov. This sets the M3 scope.
4. ✅ **Model tier:** standard by default; contributor only for synthetic or our own non-sensitive images (terms confirmed, §1.2).
5. ✅ **Pre-kickoff code:** none. The Official Rules don't explicitly allow prior work, so coding starts at the kickoff (directive 6).
6. ✅ **Git commits:** approved 2026-10-28. Commits are made locally as the work lands, and the user pushes them.
7. ✅ **Licence:** Apache-2.0 (2026-10-28): `LICENSE` (verbatim from apache.org), `NOTICE`, `THIRD_PARTY_NOTICES.md`.

---

## 13. Session protocol

- **Start of session:** read this plan and the latest `docs/PROGRESS.md` entry.
- **End of session:** append a dated entry with what changed, its status label and the next step.
- **Status labels** are mandatory for every feature claim:
  - ✅ implemented and tested
  - 🟡 implemented, unverified
  - 🧪 experimental
  - 📋 planned
  - ⛔ unsupported
- **`EVALUATION.md`** holds measured results only, each with its date, part and conditions.

---

## 14. Sources (read 2026-10-22)

**Hackathon**
- Event pages: https://cerebralvalley.ai/e/meta-ai-developer-hackathon · https://dev.meta.ai/events/global-hackathon
- **Official Rules and Event Waiver** (dated 2026-10-25): https://cerebralvalley.ai/e/meta-ai-developer-hackathon/waiver
- **Credit Terms** (PDF linked from the Official Rules): "Meta Model API: Global AI Developer Hackathon Credit Terms", read 2026-10-26
- $150 credits (third-party, unconfirmed): https://thegenaimagazine.com/meta-global-ai-developer-hackathon-ideas-prizes

**Meta Model API**
- Docs: https://dev.meta.ai/docs/
- Pricing and rate limits: https://dev.meta.ai/docs/pricing-rate-limits
- Structured output: https://dev.meta.ai/docs/structured-output
- Vision input: https://dev.meta.ai/docs/cookbook/vision-input
- Global availability: https://developers.meta.com/blog/meta-connect-recap/

**SAM 3.1**
- Model page: https://dev.meta.ai/models/sam-3-1/
- Docs: https://dev.meta.ai/docs/sam/overview · https://dev.meta.ai/docs/sam/segmenting · https://dev.meta.ai/docs/sam/reading-segmentation · https://dev.meta.ai/docs/sam/client-libraries
- Parser: PyPI `meta-sam-parser` 0.1.0

**Other Meta models**
- Muse Image: https://dev.meta.ai/models/muse-image/ · https://dev.meta.ai/docs/image-generation
- Muse Spark launch blog: https://dev.meta.ai/resources/blog/build-with-muse-spark/
- Muse Code: https://dev.meta.ai/products/muse-code/

**Preparation (2026-10-23)**
- Contributor-mode terms: https://dev.meta.ai/docs/models
- Node.js release index: https://nodejs.org/dist/index.json
- `meta-sam-parser` source (installed package; Meta "SAM License"): https://github.com/meta-models/meta-sam

**Secondary sources**
- SAM 3D Objects requirements: https://www.deeplearning.ai/the-batch/metas-sam-3-image-segmentation-suite-analyzes-and-creates-3d-bodies-and-other-objects
- Spark visual grounding in the consumer app: https://simonwillison.net/2026/Apr/8/muse-spark
