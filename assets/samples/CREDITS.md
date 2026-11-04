# Example photos: credits and licences

The Commons-based examples are SYNTHETIC COMPOSITES made by `backend/tools/make_commons_samples.py`: a real photo of a real part, cut out, its tilt corrected, sized from the stated basis, optionally broken digitally, and placed on a rendered Re-Forge mat shot by a simulated phone camera. Each composite (the `.jpg` file and its thumbnail) is an adaptation of the photo below and is shared under the same licence as its source photo.

## `square-gasket.jpg`, `square-gasket.thumb.jpg`

- **Source photo:** [Gasket01.jpg](https://commons.wikimedia.org/wiki/File:Gasket01.jpg) by Miya.m, Wikimedia Commons.
- **Licence:** CC BY-SA 3.0 (https://creativecommons.org/licenses/by-sa/3.0/). The composite is shared under the same licence.
- **Part:** a real square gasket with a round bore and eight passages.
- **Size basis:** 82.2 mm long side, from the same photo's scale, which is CHOSEN: the round flange gasket beside it on the same sheet at Ø100 mm (the outside diameter of a JIS B 2404 10K 20A full-face gasket); the photo has no ruler.
- **Thickness:** CHOSEN 1.0 mm.
- **Changes:** cut out; tilt corrected; placed on a rendered mat.

## `green-gasket.jpg`, `green-gasket.thumb.jpg`

- **Source photo:** [Gasket01.jpg](https://commons.wikimedia.org/wiki/File:Gasket01.jpg) by Miya.m, Wikimedia Commons.
- **Licence:** CC BY-SA 3.0 (https://creativecommons.org/licenses/by-sa/3.0/). The composite is shared under the same licence.
- **Part:** a real green fibre flange gasket: bore plus four bolt holes.
- **Size basis:** 100.0 mm outside diameter (the JIS-anchor gasket itself).
- **Thickness:** CHOSEN 1.0 mm.
- **Changes:** cut out; tilt corrected; placed on a rendered mat.

## User-provided photos

The sprocket composites are made by `backend/tools/make_wanted_samples.py` from photos the user supplied for the examples (the same 21-tooth chain sprocket, stamped 06A21), used with their permission. Full provenance, including every CHOSEN size, is recorded in the tool.

## `broken-sprocket.jpg`, `broken-sprocket.thumb.jpg`

- **Source photo:** tmp/wanteds/Image collée (3).png (supplied by the user for the examples).
- **Part:** a real 21-tooth chain sprocket, stamped 06A21 (mark visible in the photo).
- **Size basis:** CHOSEN 70.0 mm outside diameter: a 06A chain's 9.525 mm pitch gives a 21-tooth pitch diameter of 63.9 mm and an outside diameter of about 69.7 mm.
- **Thickness:** CHOSEN 5.0 mm, a plausible single-sprocket thickness.

## `intact-sprocket.jpg`, `intact-sprocket.thumb.jpg`

- **Source photo:** tmp/wanteds/Image collée (3).png (supplied by the user for the examples).
- **Part:** the same real 21-tooth chain sprocket (06A21), intact: nothing to rebuild.
- **Size basis:** CHOSEN 70.0 mm outside diameter (same basis as the broken one).
- **Thickness:** CHOSEN 5.0 mm, a plausible single-sprocket thickness.

## `broken-sprocket-r2.jpg`, `broken-sprocket-r2.thumb.jpg`

- **Source photo:** tmp/wanteds/Image collée (3).png (supplied by the user for the examples).
- **Part:** the same real 21-tooth chain sprocket (06A21) with another side snapped off.
- **Size basis:** CHOSEN 70.0 mm outside diameter (same basis as the broken one).
- **Thickness:** CHOSEN 5.0 mm.

## `key-blade.jpg`, `key-blade.thumb.jpg`

- **Source photo:** tmp/realpicts/M Modecar Coque de clé.png (blade cropped out, fob excluded) (supplied by the user for the examples).
- **Part:** an uncut key blade (blank), intact: no bitting, no holes.
- **Size basis:** CHOSEN 50.0 mm long (product shot, no scale; a plausible blade).
- **Thickness:** CHOSEN 2.5 mm, a plausible blade thickness.

`broken-flange.jpg`, `broken-bracket.jpg`, `l-plate.jpg`, `broken-flange-50.jpg`, `broken-bumper-bracket.jpg`, `broken-adjuster-link.jpg`, `broken-shim.jpg`, `broken-washer.jpg`, `broken-slotted-link.jpg` are fully rendered (no photo). The rest of the repository is Apache-2.0.

## `broken-wheel.png`, `broken-wheel.thumb.jpg`

- **Source photo:** tmp/realpicts/ALCARJante.casse.png (supplied by the user for the examples).
- **Part:** ALCAR steel car wheel, three right vents hidden by a white blob.
- **Size basis:** RULER ASSUMPTION: longest side assumed 400 mm (a 15-inch steel wheel) on both the broken and the intact photo, so the comparison is valid while the absolute scale is assumed.
- **Thickness:** CHOSEN 10 mm: rim centre assumed; the demo is the vent rebuild.

## `broken-bougie.png`, `broken-bougie.thumb.jpg`

- **Source photo:** tmp/realpicts/bougie.casse.png (supplied by the user for the examples).
- **Part:** Bosch EVO spark plug, right ceramic wall and hex flat broken out.
- **Size basis:** RULER ASSUMPTION: longest side assumed 100 mm on both the broken and the intact photo; station width ratios agree within 6 % across the two vendor shots, absolute scale assumed.
- **Thickness:** CHOSEN 10 mm placeholder; the demo is the silhouette rebuild.

## `broken-volant.png`, `broken-volant.thumb.jpg`

- **Source photo:** tmp/wanteds/Image collée (2).png (supplied by the user for the examples).
- **Part:** Sparco suede steering wheel, notch cut digitally out of the upper-right rim.
- **Size basis:** RULER ASSUMPTION: longest side assumed 350 mm; the break extents don't change the photo's longest side, so the broken and intact twins share the exact same scale — the comparison is exact, only the absolute scale is assumed.
- **Thickness:** CHOSEN 10 mm placeholder; the demo is the rim-arc rebuild.
