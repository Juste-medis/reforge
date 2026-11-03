# Hackathon submission: the form, field by field

The submission form (Cerebral Valley portal) has the fields below, in this order. Required fields are marked *. Draft
answers are written from measured facts only (`docs/EVALUATION.md`, the usage ledger). Questions that ask for an
opinion are left to the submitter, with the relevant facts listed beside them.

**Deadline: Thu 5 Nov 2026, 03:00 Paris (Wed 4 Nov, 21:00 ET).** Internal target: Wed 4 Nov, 22:00 Paris.

## Checklist before submitting

| # | Item | Status |
|---|---|---|
| 1 | Repository public at https://github.com/Juste-medis/reforge, with this branch pushed | ⏳ submitter: push, then check the visibility setting |
| 2 | 3-minute demo video uploaded (YouTube, public or unlisted), following `docs/DEMO_SCRIPT.md` | ⏳ submitter |
| 3 | Meta Model API credits claimed by 4 Nov, 21:00 ET (Credit Terms) | ⏳ submitter, if not done |
| 4 | Texts below pasted, and the opinion questions answered | ⏳ submitter |
| 5 | Consent checkbox (Meta and Cerebral Valley may publish the materials) | ⏳ submitter's decision |

---

## Team Name*

Submitter's choice. Suggestion: **Re-Forge**.

## Team Members

Juste-Medis ADIDO (@juste), pre-filled. Solo.

## Which track are you submitting to?*

**Indie Developer Track.**

## Which problem statement did you build towards?*

**Push the Frontier.**

## Most Viral Track: X post link

Optional. Only if a post of the demo is published on X (engagement counts until 8 Nov).

## Project Description*

> Re-Forge rebuilds broken flat parts from one phone photo. You lay the broken piece on a printed calibration mat and
> enter its thickness. Re-Forge then measures the surviving outline in true millimetres, and Meta's SAM 3.1 and Muse
> Spark find the part and read the damage: what the object is, whether it is a flat part, which edges are fractures,
> and which mirror axis can rebuild the missing piece. Every AI claim is checked against the geometry before anything
> is rebuilt. The result is a validated, watertight STL for your slicer and an editable OpenSCAD file. Every dimension
> is labelled measured, rebuilt by symmetry, or uncertain, with a 2σ estimate from the photo's own error budget.
>
> It solves the gap between "a small plastic part broke" and "I have a file I can print". Most people have no CAD
> skills, and generic image-to-3D tools invent geometry without saying which parts are real. Re-Forge refuses what it
> can't support: 3D objects, varying thickness, a trace that is only part of an object. It tells you why instead of
> producing a confident-looking but wrong model.
>
> On the three bundled synthetic examples, sizes come out within 0.04 mm of the known truth, and a broken flange's two
> lost bolt holes are inferred with diameters within 0.005 mm. On a first real part photographed on the printed mat, the height came
> out within 0.41 mm of the caliper reading.

## Public GitHub Repository*

https://github.com/Juste-medis/reforge (must be public before submitting).

## 3-Minute Demo Video*

The YouTube link, once recorded. Plan: `docs/DEMO_SCRIPT.md`.

## Describe your use of Meta products to build the submitted project*

> Two Meta models run in the product, through the Meta Model API (standard tier; the contributor tier is blocked for
> user uploads in code):
>
> - **SAM 3.1** segments the part on the rectified mat view through the Responses API. We use box prompts derived from
>   a local colour proposal, with a noun-phrase fallback, request confidences, and decode the box-local masks with
>   meta-sam-parser. Live measurements on the mat showed text prompts returning 0 instances while box and point prompts
>   reached 0.99 confidence, so the segmenter is box-first. Over 74 calls: median latency 3.0 s, $0.0025 per image.
> - **Muse Spark 1.3** interprets the part from two images: the photo of the mat's free zone, and a Set-of-Mark view
>   where the outline is cut into numbered segments S#, candidate mirror axes are drawn as A#, and holes are labelled
>   H#. It also receives measured facts as JSON: segment lengths, hole sizes, each axis's measured support and the
>   material its mirror would add. It answers through a strict JSON schema whose enums are generated per request from
>   the ids actually drawn, so it can only point at things that exist. It never estimates a dimension. Every answer is
>   then verified geometrically: a "fracture" that matches its mirror image is rejected, and an axis that can't
>   rebuild the break is replaced by one that passes the same checks, with the correction reported. Over 62 calls at
>   reasoning effort "low": median latency 12.6 s, about $0.015 per call.
>
> Every call goes through one client with timeouts, retries, a daily budget guard and a usage ledger, so the app shows
> each job's real AI cost: $0.016 to $0.023 per analysis on the examples. Total spend while building: $1.22 of the
> $150 credits (ledger, 2026-10-28 to 2026-11-03). If the API is unreachable, the UI offers to run the same photo
> without AI, clearly labelled.

## Why are Meta's models important to your solution?*

> Geometry can measure an outline to a fraction of a millimetre, but it can't tell what it is looking at. Muse Spark
> supplies the judgements a repair needs and a geometry engine can't make:
>
> - Is this a flat part at all, or a pipe, a knob, a forged tool? Spark refused six forged-metal tools, a glass vial
>   and a tapered ferrule with a stated reason, instead of letting them become confident-looking extrusions.
> - Which edges are broken rather than moulded?
> - Which symmetry can rebuild the missing piece?
>
> SAM 3.1 makes the outline robust on real materials. On a real stamped-metal part, our classical fallback traced the
> cast shadow (+4.4 mm), while SAM followed the metal edge.
>
> The models matter because they plug into a verifiable pipeline. Spark's strict structured output, with enums that
> admit only the ids drawn on the image, lets us treat its answer as data and check every claim against measurements.
> The AI decides what to look at, and geometry checks it.

## Provide feedback from your experience using partner technologies (Fireworks, Modal, Baseten)

> We didn't use Fireworks, Modal or Baseten for this project: everything runs on the Meta Model API plus local
> geometry code on a CPU-only server.

(Optional field. The above is the factual answer.)

## Survey questions (the submitter's own opinions)

These are personal ratings. Facts from this project that may help:

| Question | Facts from this project |
|---|---|
| How likely are you to build with Meta Model API?* | It's OpenAI-SDK compatible, and we used Chat Completions and Responses through `AsyncOpenAI` with a `base_url`. Strict `json_schema` output with enums was accepted and respected in every logged call |
| Overall opinion of Meta Model API?* | 140 ledger records. Failures were only our own tests with an unreachable host (3), and 1 `META_ERROR` traced to our test script reusing a client across event loops |
| Recommend the Meta Model API (0–5) | — |
| Recommend Muse Code (0–5) | Answer only from your own experience of Muse Code |
| Biggest obstacle | SAM 3.1 text prompts returned 0 instances on the mat view (design changed to box-first). Muse Spark's answer varies between runs on borderline parts: a family verdict, and the mirror axis of the same flange. Verification catches these, but outcomes vary |
| Meta's models compared with others | Your own comparison; none was run in this project |
| What matters most / hardest to switch / what would stop production use | Your own priorities. The product depends on structured outputs with enums, vision input, and SAM's prompt types |
