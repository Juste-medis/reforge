# Hero part and ground-truth guide

This is non-coding preparation you can do before the kickoff (Mon 26 Oct, 17:00 Paris). The demo's credibility depends on this step more than on any code: we can only claim accuracy we have measured.

## 1. What makes a good hero part

Per the approval directives, the primary demo is a **flat, mirror-symmetric plastic part with mounting holes**.

### Must have

| Criterion | Why |
|---|---|
| **Flat (2.5D):** one constant thickness, lies flat, ideally 2–8 mm thick | The MVP builds a single-thickness extrusion |
| **Mirror-symmetric outline when intact** | Symmetry is the evidence we use to rebuild the missing side |
| **≥ 2 round through-holes**, ideally a symmetric pair | Holes are fit-critical, easy to verify by caliper and screw test, and good for the demo |
| **Opaque, matte, one colour** that contrasts with white paper (black, dark grey, blue, red, green) | White, transparent and chrome parts break segmentation and edge accuracy |
| **Size 30–120 mm** | Fits the mat's free zone with margin, and is big enough for photo metrology |
| **Non-safety-critical** | No load-bearing, heat, pressure or electrical-insulation role |
| **The break removes material on one side only** (a snapped ear, tab or arm), leaving the mirror side intact | Otherwise there is no evidence to reconstruct from (risk R3) |

### Nice to have

- **A real story:** a part that actually broke on something you own (furniture, an appliance, a curtain rod, a shelf). This makes the best demo narrative.
- **An intact twin:** the identical part from the other side, such as left and right brackets. It gives you ground truth for free, plus a second demo mode.
- **Somewhere to test-fit it:** the screws and mounting points the printed replacement must match.

### Avoid for the hero part

These either can't be seen from above or can't be represented by a single-thickness extrusion (see PLAN §5.1):
- steps or several thickness levels
- ribs on the back
- snap-fit hooks
- threads
- flexible or rubbery material
- strong draft angles
- reflective or transparent material

### Where to look

Use generic categories; any brand works:
- plastic mounting plates and wall brackets (curtain-rod supports, router or smoke-detector mounting plates)
- cable clips with two screw holes
- flat furniture connectors and shelf-support plates
- plastic perforated construction-kit strips

DIY stores and furniture spare-part counters are the fastest sources. **Buy two of each**, so one stays intact.

## 2. Measuring with the caliper (before breaking anything)

1. **Caliper:** a digital caliper with 0.01 mm resolution.
   - Close it and zero it before each session.
   - Measure at room temperature.
   - Don't press hard on soft plastic.
2. **Measure each dimension 3 times**, re-seating the caliper each time, and record all three readings in `docs/ground_truth_template.csv`. The mean is computed later; please don't round.
3. **Dimensions to record for a flat 2-hole part:**

| Dimension | How to measure |
|---|---|
| Overall length and width | Outside jaws |
| Thickness | Outside jaws, at **3 places** (a draft or warp shows up as variation) |
| Each hole diameter | Inside (upper) jaws; take the largest reading while rotating gently |
| Hole centre-to-centre distance | Inside jaws spread across the **far** edges of both holes gives L_far. Then centre distance = L_far − (D1 + D2) / 2 |
| Each hole's centre to its nearest outer edge | Depth rod or step measurement, edge to the near side of the hole, + D / 2 |
| Any other clear feature (corner radius, slot width, notch) | Note what you measured and how |

4. **On the broken part,** measure the same dimensions where they still exist. Mark the missing ones `n/a (broken)`.

## 3. Photos

- **Before the mat exists (now):** take reference photos of each intact part:
  - top view with a ruler alongside
  - side view
  - the part in its assembly, if any
- **After D1, once the mat is printed:** re-photograph intact parts on the mat following the capture protocol in PLAN §5.2 (revised 2026-10-27):
  - top view, phone roughly parallel and above the part
  - **2× or 3× lens**, stepping back until the mat fills the frame (less parallax, more pixels on the part)
  - diffuse light, no flash
  - 2–3 shots, moving the part between shots
  - **keep the original files** (JPEG; on iPhone, Settings → Camera → Formats → Most Compatible). Screenshots and messaging apps drop the EXIF focal length, which the height correction needs
- **Only then break the sacrificial parts.** Snap one tab or ear with pliers (wear eye protection), on one side of the symmetry axis. **Keep the broken-off fragment**, since it's extra ground truth. Then photograph the broken part on the mat, plus a close-up of the fracture.

## 4. The physical demonstration (if a 3D printer becomes available)

1. **Print** the reconstructed STL at 100 % scale (PLA or PETG, 0.2 mm layers are fine). Record the printer, material and settings.
2. **Measure the print** with the same caliper protocol, and add rows with `state = printed`.
3. **Fit test:** do the screws pass through the holes, and does the part seat in its place? Record pass or fail with a photo, plus any hole compensation used.
4. **If no printer is available,** we say so in the demo and the write-up. We never imply a print that didn't happen.

Options for getting a print: a university fablab, a local makerspace, or a friend's printer. Online printing services may not deliver before 4 Nov.

## 5. Status

| Item | Status |
|---|---|
| Digital caliper | ⏳ to be confirmed |
| 3D printer access | ⏳ to be confirmed |
| Hero part selected | ⏳ to be selected |
| Sacrificial parts bought (×2 each) | ⏳ |
| Intact parts measured | ⏳ |
