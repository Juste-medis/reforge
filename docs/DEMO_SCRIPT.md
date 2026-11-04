# Demo video: 3 minutes

Judged on: Impact 30 % · Use of Meta AI tooling 25 % · Technical depth 20 % · Demo 25 %. The final-round judges watch
the video live, so it has to stand on its own.

## Rules for the recording

- **Show only what happened.** No print, no fit test, no "it fits" unless you filmed it. An STL is not a repaired part.
- **Say "synthetic example"** whenever a bundled example is on screen. The UI labels them too.
- **Real photos stay real.** Use a part you photographed yourself on the printed mat.
  - Prefer an unbranded plastic part: a broken bracket, clip or spacer.
  - The stamped heart carries a brand logo and a marketing name; avoid it, or crop it out.
  - Never demo copying a key.
- **Don't show secrets.** Keep `.env` and the terminal history off screen, and the browser's dev tools closed.
- Record the browser at 1440 × 900 or larger, 100 % zoom, light mode. Run one warm-up analysis first.

## Before recording

```bash
cd frontend && npm ci && npm run build && cd ../backend && uv run reforge-api   # http://127.0.0.1:8000
```

Alternative: record against the public instance at https://reforge.adidomedis.cloud (no install; verified 2026-11-04:
home page 200, `AI ready`, key configured).

Then check that the header says **AI ready**. Prepare these on the desktop:
1. the real photo of your part on the mat;
2. its caliper thickness;
3. ideally a photo of an out-of-scope object, such as a bottle or a ferrule, for the refusal shot.

## Shot list (about 3:00)

| Time | Screen | Voice-over (draft) |
|---|---|---|
| 0:00–0:12 | The broken part in your hand, then on the printed mat | "A small part broke. No spare, no CAD skills. Can one photo get me a printable replacement, and can I trust it?" |
| 0:12–0:30 | Home page: hero, then "How it works" | "Re-Forge measures what survived, rebuilds what's missing by symmetry, and labels which is which." |
| 0:30–0:50 | Phone shot from above (real), then New repair: drop the photo (checks appear), type the thickness | "One photo, straight down, all twelve markers in view. And one caliper reading: the photo can't see thickness." |
| 0:50–1:15 | Analyse: the stage list advancing, with the "SAM 3.1" and "muse-spark-1.3" tags | "These are the real pipeline stages with their measured times. Meta's SAM 3.1 finds the part. Muse Spark reads the damage: what it is, which edges broke, which symmetry can rebuild it." |
| 1:15–1:45 | Result: the verdict, the 3D view (rotate, Top view, Sizes), the before/after slider | "Solid blue is measured from the photo. Orange is rebuilt as a mirror of the intact side. Every dimension carries a ± from this photo's own error budget." |
| 1:45–2:05 | "What we know" (open a "?" tooltip), "Before you print", the hole allowance, the acknowledgement checkbox | "Uncertain spots must be acknowledged before the files unlock. Printers make holes small, so the allowance rebuilds and re-validates the model." |
| 2:05–2:25 | Show technical details: the Set-of-Mark image, the verification notes, the AI cost line | "Spark answers only with the ids drawn on this image, through a strict schema, and geometry checks every claim. A fracture that matches its own mirror image is rejected. The AI cost of this analysis is right here: a couple of cents." |
| 2:25–2:40 | An out-of-scope object: the refusal screen | "And when it can't support a rebuild, it says so. A 3D object is refused, with the reason, instead of becoming a confident-looking wrong model." |
| 2:40–2:52 | Examples → the real gasket (credited photo), then the rendered broken flange → the "Known answer" cards, the textured 3D, "Cut it: DXF" | "On examples placed at a known size, the truth is known exactly: a real gasket within a hundredth of a millimetre, a broken flange rebuilt with its lost bolt holes. And a gasket you cut, not print: here's its DXF." |
| 2:52–3:00 | The downloads, then the `.scad` opened in OpenSCAD if you have it | "A printable STL and an editable OpenSCAD file. Re-Forge, from a broken part to evidence you can print." |

## If something goes wrong live

- **The AI service doesn't answer.** The error screen offers "Run again without AI": show it, it's designed behaviour.
- **Spark reads the part differently than expected.** Its answer varies between runs. The verification notes explain
  what was accepted; don't cut to a different run without saying so.
- **The mat isn't found.** Reshoot with all 12 markers visible and the mat flat. The error screen lists exactly this.

## Numbers you may quote (measured, `docs/EVALUATION.md`)

- Bundled examples, live, with SAM 3.1 + Muse Spark (2026-11-03, night):
  - **real photo of a real gasket** (composited at a known size): 82.21 × 79.44 mm for 82.20 × 79.45; 9 holes; not
    rebuilt, even in the run where Spark wrongly called it broken (geometry rejected it: `AXIS_ASYMMETRIC`);
  - **real photo of a broken chain sprocket** (06A21, user-provided photo): 68.86 × 69.82 mm for 69.04 × 69.95, the
    missing half with its teeth rebuilt; its intact twin measured 69.17 × 70.99 for 69.20 × 71.09 with nothing
    rebuilt — proof it invents no damage;
  - **rendered broken flange**: rebuilt 56.015 × 56.012 mm for 56 × 56, lost holes at Ø 6.497 and 6.495 for 6.5.
- AI cost per analysis on the examples: $0.019 to $0.028. Analysis time: 26 to 74 s with AI.
- The exported `.scad` compiles in OpenSCAD to the same solid as the STL: volume within 4 × 10⁻⁶. The DXF reads
  back in `ezdxf` with the spec's exact outline area and hole radii.
- First real part (a stamped heart): height within 0.31 and 0.41 mm of the caliper. Its width is still being
  re-measured, so don't quote a width figure.
