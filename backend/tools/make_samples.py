"""Bundle the app's example photos (``assets/samples/``): successes only.

Every example is verified end to end (offline, and live for the rebuilds): a broken sample must rebuild against its
truth, an intact one must measure against it with nothing invented. A declined sample, however honest the decline, is
not bundled — the homepage shows what works. (That excludes the chipped cog: four ragged teeth are below the mirror's
exact-cover ability, EVALUATION.)

Sources: one rendered part from ``tools/make_test_photos.py``, two SYNTHETIC COMPOSITES from user-provided photos
(``tools/make_wanted_samples.py``, used with the user's permission), one from a Wikimedia Commons photo
(``tools/make_commons_samples.py``, author and licence travel with it). The JPEG data is copied byte for byte (no
recompression, so the metrology sees exactly what was evaluated); only the EXIF description is rewritten to say what
the image is. The thumbnail is the pipeline's own rectified crop of the part, from an offline run (classical outline,
geometric rule: no AI, no cost).

    cd backend && uv run python -m tools.make_samples --tests ../tmp/tests --wanteds ../tmp/wanted_parts/composites \\
        --composites ../tmp/commons/composites
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import struct
import tempfile
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from reforge.config import REPO_ROOT
from reforge.spec.confidence import min_rect_mm

OUT = REPO_ROOT / "assets" / "samples"
RENDERED = {"id": "broken-flange", "source": "22_mflange_black_broken", "title": "Broken mounting flange (rendered)",
            "story": "A rendered part, no photo: a 56 mm flange snapped off on one side, taking two of its four bolt "
                     "holes with it. It shows a complete mirror rebuild, lost holes included.",
            "thickness_mm": 5.0,
            "label": ("SYNTHETIC EXAMPLE: a rendered part on a rendered Re-Forge mat, shot by a simulated phone camera "
                      "(RE-FORGE tools/make_test_photos.py). Not a photo of a real part."),
            "truth": {"basis": "the intact part, as rendered", "length_mm": 56.0, "width_mm": 56.0,
                      "holes": [{"diameter_mm": 24.0, "count": 1}, {"diameter_mm": 6.5, "count": 4}],
                      "photographed": "45.6 mm wide: two Ø6.5 holes were lost in the break"}}
SAMPLES = [
    {"id": "broken-sprocket", "srcdir": "wanteds", "source": "sprocket_broken",
     "title": "Broken chain sprocket (06A21)",
     "story": "A real 21-tooth chain sprocket (stamped 06A21, marking visible), snapped along a diameter: the top "
              "half with about ten teeth is gone. The bore survives, so the mirror stays pinned while it rebuilds "
              "the missing teeth.",
     "thickness_mm": 5.0, "round_holes": "all", "provided_by": "user",
     "photographed": "64.6 mm tall: the top half snapped off along a diameter"},
    {"id": "square-gasket", "srcdir": "commons", "source": "square_gasket",
     "title": "Square engine-style gasket",
     "story": "A real square gasket with a round bore and eight passages, intact and placed at an angle. Nothing "
              "to rebuild: it's measured as photographed, ready to cut a copy from gasket sheet.",
     "thickness_mm": 1.0, "round_holes": "largest"},
    {"id": "intact-sprocket", "srcdir": "wanteds", "source": "sprocket_intact",
     "title": "Chain sprocket (06A21), intact",
     "story": "The same 21-tooth chain sprocket (06A21), intact: measured as photographed. The pipeline must "
              "rebuild nothing — proof it does not invent damage.",
     "thickness_mm": 5.0, "round_holes": "all", "provided_by": "user",
     "photographed": "placed at 25° to the mat, whole"},
    {"id": "broken-bracket", "srcdir": "tests", "source": "15_bracket_orange_broken",
     "title": "Mounting bracket, end snapped off",
     "story": "An 80 × 28 mm bracket with its right end snapped off. Both bolt holes survive, so the mirror has "
              "evidence to use and the end comes back.",
     "thickness_mm": 3.0, "round_holes": "all", "photographed": "77.6 mm long: the right end snapped off"},
    {"id": "l-plate", "srcdir": "tests", "source": "19_l_plate_green",
     "title": "L-shaped plate, intact",
     "story": "An asymmetric L plate with three holes: with no break and no symmetry claim, it is measured as "
              "photographed.",
     "thickness_mm": 3.0, "round_holes": "all", "photographed": "whole on the mat"},
    {"id": "broken-flange-50", "srcdir": "tests", "source": "20_flange_black_broken",
     "title": "Square flange, side snapped off",
     "story": "A 50 mm square flange with its right side snapped off, taking two of the four bolt holes with it. "
              "Only the bore pins the axis — and both lost holes come back.",
     "thickness_mm": 3.0, "round_holes": "all", "photographed": "40.4 mm wide: two holes lost in the break"},
    {"id": "broken-bumper-bracket", "srcdir": "tests", "source": "21_bumper_graphite_broken",
     "title": "Bumper bracket, ear snapped off",
     "story": "A 94 × 30 mm bumper mounting bracket with its right ear snapped off. The intact ear and both bolt "
              "holes survive, so the mirror rebuilds the missing ear.",
     "thickness_mm": 4.0, "round_holes": "all", "photographed": "86.8 mm long: the right ear snapped off"},
    {"id": "green-gasket", "srcdir": "commons", "source": "green_gasket",
     "title": "Fibre flange gasket, intact",
     "story": "A real green fibre flange gasket, Ø100 mm: bore plus four bolt holes, all five fitted as circles "
              "within 0.05 mm. Nothing to rebuild: the baseline for real-gasket texture.",
     "thickness_mm": 1.0, "round_holes": "all", "photographed": "whole on the mat"},
    {"id": "broken-adjuster-link", "srcdir": "tests", "source": "27_alink_red_broken",
     "title": "Adjuster link, ear-tip snapped off",
     "story": "An 80 × 20 mm adjuster link with its right ear-tip snapped off. The slot and both holes survive, "
              "so the mirror rebuilds the missing tip exactly.",
     "thickness_mm": 5.0, "round_holes": "all_but_largest", "photographed": "76.4 mm long: the ear-tip snapped off"},
    {"id": "broken-shim", "srcdir": "tests", "source": "29_shim_grey_broken",
     "title": "Alignment shim, end snapped off",
     "story": "A 64 × 40 mm alignment shim with its right end snapped off past the hole. Both holes survive the break, "
              "mirror brings the end back.",
     "thickness_mm": 1.0, "round_holes": "all", "photographed": "60.5 mm long: the right end snapped off"},
    {"id": "broken-sprocket-r2", "srcdir": "wanteds", "source": "sprocket_broken_r2",
     "title": "Chain sprocket, other side snapped off (user photo)",
     "story": "The same real 21-tooth sprocket with another side snapped off. The bore stays round, the teeth "
              "come back by mirror.",
     "thickness_mm": 5.0, "round_holes": "largest", "provided_by": "user", "photographed": "snapped on the other side"},
    {"id": "key-blade", "srcdir": "wanteds", "source": "blade_intact",
     "title": "Key blade (blank), intact (user photo)",
     "story": "An uncut key blade cropped from the user's fob product shot, 50 mm long. Pale metal on white, "
              "measured whole: nothing rebuilt.",
     "thickness_mm": 2.5, "round_holes": "all", "provided_by": "user", "photographed": "whole on the mat"},
    {"id": "broken-washer", "srcdir": "tests", "source": "30_washer_red_broken",
     "title": "Flat washer, rim segment snapped off",
     "story": "A Ø30 / Ø12 mm washer with a rim segment snapped off past the bore. The bore survives, "
              "so the mirror brings the rim back.",
     "thickness_mm": 2.0, "round_holes": "all", "photographed": "24.8 mm wide: a rim segment snapped off"},
    {"id": "broken-slotted-link", "srcdir": "tests", "source": "31_link_yellow_broken",
     "title": "Slotted link, ear-tip snapped off",
     "story": "A 70 × 18 mm link with its right ear-tip snapped off past the hole. Both holes and the "
              "slot survive, so the mirror brings the tip back.",
     "thickness_mm": 4.0, "round_holes": "all_but_largest", "photographed": "67.9 mm long: the ear-tip snapped off"},
    {"id": "intact-pulley", "srcdir": "tests", "source": "32_pulley_steel",
     "title": "Crankshaft pulley, intact (rendered)",
     "story": "A small car's crankshaft pulley, Ø130 mm: Ø30 bore, four Ø8 bolt holes, four Ø6 lightening holes. "
              "Measured whole on the mat: nothing rebuilt.",
     "thickness_mm": 8.0, "round_holes": "all", "photographed": "whole on the mat"},
    {"id": "broken-pulley", "srcdir": "tests", "source": "33_pulley_cast_broken",
     "title": "Crankshaft pulley, rim segment snapped off (rendered, guided)",
     "story": "A Ø130 mm crankshaft pulley with a rim segment snapped off, taking one bolt hole and two lightening "
              "holes with it. A circle's every diameter mirrors it, so the axis can't be discovered — guided in the "
              "Studio (vertical axis through the bore, the S4–S21 cut), the mirror rebuilt the cap and all three "
              "lost holes exactly.",
     "thickness_mm": 8.0, "round_holes": "all",
     "photographed": "88.6 mm wide: one bolt hole and two lightening holes lost in the break",
     "guidance": {"axis": None, "assert_angle": 90.0, "assert_point": [105.0, 148.5],
                  "fracture": [f"S{i}" for i in range(4, 22)], "exclude": [], "damage": [],
                  "family_override": False,
                  "note": "Studio: vertical axis through the bore, S4-S21 cut (a circle needs its axis asserted)"}},
]
GUIDED = [  # real user photos with a stored Studio session (photo + SAM mask + guidance): ruler mode, no mat
    {"id": "broken-bougie", "photo_src": "bougie.casse.png", "rundir": "bougie_sam",
     "title": "Spark plug, ceramic wall broken out (user photo)",
     "story": "A real Bosch EVO spark plug (user's photo): the right ceramic wall and hex flat broke out, exposing "
              "the inner rod. Guided in the Studio — a vertical axis through the plug centre, the S35–S40 break "
              "spans, the thread helix and hook electrode kept as designed asymmetry — the mirror rebuilt "
              "the missing wall from the intact left side.",
     "thickness_mm": 10.0, "provided_by": "user", "known_length_mm": 100.0,
     "guidance": {"axis": None, "assert_angle": 90.0, "assert_point": [54.217, 58.862],
                  "fracture": ["S35", "S36", "S37", "S38", "S39", "S40"],
                  "exclude": ["S43", "S44", "S45", "S46", "S47", "S48", "S49", "S50", "S51", "S52",
                              "S53", "S54", "S55", "S56", "S57"],
                  "damage": [], "sources": None, "family_override": True,
                  "note": "Studio: vertical axis, S35-S40 break, helix/hook kept as designed asymmetry"},
     "label": ("REAL USER PHOTO with a Studio session: a user-provided photo of a Bosch spark plug with its right "
               "ceramic wall broken out, ruler-scaled at an assumed 100 mm, rebuilt from the stored guidance "
               "(asserted vertical axis, S35-S40 break, helix and hook electrode kept as designed asymmetry). "
               "Not a render, not a composite."),
     "provenance": {"source_file": "tmp/realpicts/bougie.casse.png",
                     "what": "Bosch EVO spark plug, right ceramic wall and hex flat broken out",
                     "size_basis": ("RULER ASSUMPTION: longest side assumed 100 mm on both the broken and the "
                                    "intact photo; station width ratios agree within 6 % across the two vendor "
                                    "shots, absolute scale assumed"),
                     "thickness_basis": "CHOSEN 10 mm placeholder; the demo is the silhouette rebuild"},
     "truth": {"basis": ("the intact plug photo (same Bosch EVO model, different vendor shot, same assumed 100 mm; "
                         "station width ratios within 6 %)"),
               "exact": False, "length_mm": 110.12, "width_mm": 18.74, "holes": [],
               "photographed": ("right wall broken out over S35–S40; rebuilt 100.03 × 19.82 mm, notch fill "
                               "25.4 mm² from the mirrored left, helix and hook kept as photographed")}},
    {"id": "broken-wheel", "photo_src": "ALCARJante.casse.png", "rundir": "wheel_guided/accept",
     "title": "Steel car wheel, vents hidden by damage (user photo)",
     "story": "A real ALCAR steel car wheel (user's photo): a white blob hides three vents on the right. Guided "
              "in the Studio — a vertical axis through the hub bore, the blob marked as damage, the visible vents "
              "trusted — the mirror rebuilt the three hidden vents where the intact photo shows them.",
     "thickness_mm": 10.0, "provided_by": "user", "known_length_mm": 400.0,
     "guidance": {"axis": None, "assert_angle": 90.0, "assert_point": [229.8, 214.8], "fracture": [],
                  "damage": ["H7"],
                  "sources": ["H0", "H1", "H2", "H3", "H4", "H6", "H8", "H10", "H11", "H12", "H14",
                              "H15", "H21", "H23", "H24", "H32", "H33", "H36", "H37", "H38"],
                  "family_override": True,
                  "note": "Studio: vertical axis through the hub bore, white blob marked as damage"},
     "label": ("REAL USER PHOTO with a Studio session: a user-provided photo of an ALCAR steel wheel with three "
               "vents hidden by a white blob, ruler-scaled at an assumed 400 mm, rebuilt from the stored guidance "
               "(vertical axis through the hub, blob marked as damage). Not a render, not a composite."),
     "provenance": {"source_file": "tmp/realpicts/ALCARJante.casse.png",
                     "what": "ALCAR steel car wheel, three right vents hidden by a white blob",
                     "size_basis": ("RULER ASSUMPTION: longest side assumed 400 mm (a 15-inch steel wheel) on both "
                                    "the broken and the intact photo, so the comparison is valid while the absolute "
                                    "scale is assumed"),
                     "thickness_basis": "CHOSEN 10 mm: rim centre assumed; the demo is the vent rebuild"},
     "truth": {"basis": "the intact wheel photo (same product-shot series, same assumed 400 mm ruler length)",
               "exact": False, "length_mm": 400.56, "width_mm": 389.62,
               "holes": [{"diameter_mm": 52.9, "count": 1}, {"shape": "traced vent", "count": 14},
                         {"shape": "traced hub hole", "count": 4}, {"shape": "traced valve hole", "count": 1}],
               "photographed": ("white blob hides 3 right vents; rebuilt 400.57 × 389.51 mm against intact "
                               "400.56 × 389.62 mm; the 3 inferred vents sit within ~2 mm of the intact photo's")}},
    {"id": "broken-volant", "photo_src": "volant.casse.png", "rundir": "volant/casse_guided", "mask_ai": False,
     "title": "Sparco steering wheel, rim notch (user photo)",
     "story": "A real Sparco suede steering wheel (user's photo) with a notch cut out of the upper-right rim. Guided "
              "in the Studio — a vertical axis through the hub, the S98–S33 notch spans, the 3 cutouts and 6 hub "
              "bolts trusted (logo and lettering left out) — the mirror rebuilt the missing rim arc from the "
              "intact left side, landing within 1 mm of the same photo before the cut.",
     "thickness_mm": 10.0, "provided_by": "user", "known_length_mm": 350.0,
     "guidance": {"axis": None, "assert_angle": 90.0, "assert_point": [201.515, 255.808],
                  "fracture": [f"S{i}" for i in list(range(98, 119)) + list(range(0, 34))],
                  "exclude": [],
                  "damage": [], "sources": ["H0", "H15", "H16", "H1", "H2", "H5", "H19", "H20", "H21"],
                  "family_override": True,
                  "note": "Studio: vertical axis through hub, S98-S33 notch, cutouts+bolts trusted"},
     "label": ("REAL USER PHOTO with a Studio session and a digitally-cut notch: a user-provided photo of a Sparco "
               "steering wheel, ruler-scaled at an assumed 350 mm, with a notch cut out of the upper-right rim in "
               "this copy; rebuilt from the stored guidance (asserted vertical axis, S98-S33 notch, 3 cutouts and "
               "6 bolts trusted). Not a render, not a composite; only the damage is digital."),
     "provenance": {"source_file": "tmp/wanteds/Image collée (2).png",
                     "what": "Sparco suede steering wheel, notch cut digitally out of the upper-right rim",
                     "size_basis": ("RULER ASSUMPTION: longest side assumed 350 mm; the break extents don't change "
                                    "the photo's longest side, so the broken and intact twins share the exact same "
                                    "scale — the comparison is exact, only the absolute scale is assumed"),
                     "thickness_basis": "CHOSEN 10 mm placeholder; the demo is the rim-arc rebuild"},
     "truth": {"basis": "the same photo before the notch was cut (same pixels, same assumed 350 mm: exact)",
               "exact": True, "length_mm": 347.681, "width_mm": 345.413,
               "holes": [{"shape": "traced cutout", "count": 3}, {"shape": "hub bolt hole", "count": 6}],
               "photographed": ("rim notch over S98–S33; rebuilt 347.68 × 345.41 mm against intact 347.68 × "
                               "345.41 mm; the 77.5 mm inferred rim arc sits within 1.0 mm (mean 0.67 mm) of the "
                               "intact twin")}},
]


def _replace_exif(jpeg: bytes, description: str) -> bytes:
    """Swap the JPEG's APP1/Exif segment for one with ``description``, keeping the focal length; no recompression."""
    exif = Image.open(io.BytesIO(jpeg)).getexif()
    exif[0x010E] = description  # ImageDescription
    payload = b"Exif\x00\x00" + exif.tobytes()
    app1 = b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload
    assert jpeg[:2] == b"\xff\xd8"
    pos, out = 2, bytearray(b"\xff\xd8")
    replaced = False
    while pos < len(jpeg):
        marker = jpeg[pos:pos + 2]
        if marker == b"\xff\xda":  # start of scan: copy the rest untouched
            if not replaced:
                out += app1
            out += jpeg[pos:]
            break
        length = struct.unpack(">H", jpeg[pos + 2:pos + 4])[0]
        segment = jpeg[pos:pos + 2 + length]
        if marker == b"\xff\xe1" and segment[4:10] == b"Exif\x00\x00":
            out += app1
            replaced = True
        else:
            out += segment
        pos += 2 + length
    return bytes(out)


async def _thumbnail(photo: Path, thickness: float, dest: Path) -> None:
    from reforge.pipeline import photo_to_stl
    from reforge.vision.segment import ClassicalSegmenter

    with tempfile.TemporaryDirectory() as tmp:
        await photo_to_stl(photo, Path(tmp), thickness, ClassicalSegmenter(), job_id="sample")
        crop = cv2.imread(str(Path(tmp) / "photo.jpg"))
    scale = 720 / crop.shape[1]
    cv2.imwrite(str(dest), cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA),
                [cv2.IMWRITE_JPEG_QUALITY, 84])


def _truth(record: dict, round_holes: str) -> dict:
    """The comparison the app shows: caliper-style size of the intact part, and its holes by kind. ``round_holes``
    says which holes the composite drew as circles: "all", "largest" (the gasket's bore; its passages are traced
    shapes), or "all_but_largest" (links: round holes plus one traced slot)."""
    intact = record["intact_footprint"] or record["footprint"]
    length, width, _ = min_rect_mm(np.asarray(intact["outline_mm"]))
    holes = sorted(intact["holes"], key=lambda h: -h["area_mm2"])
    is_round = [round_holes == "all" or (round_holes == "largest" and i == 0)
                or (round_holes == "all_but_largest" and i > 0) for i in range(len(holes))]
    counts = Counter(round(h["equivalent_diameter_mm"], 1) for h, r in zip(holes, is_round, strict=True) if r)
    shapes = sum(1 for r in is_round if not r)
    return {"length_mm": round(length, 2), "width_mm": round(width, 2),
            "holes": [{"diameter_mm": d, "count": n} for d, n in sorted(counts.items(), reverse=True)]
            + ([{"shape": "traced passage", "count": shapes}] if shapes else [])}


def _png_with_description(png: bytes, description: str) -> bytes:
    """The PNG with a Description text chunk; pixels untouched (lossless), verified pixel-identical."""
    from PIL.PngImagePlugin import PngInfo

    before = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"))
    info = PngInfo()
    info.add_text("Description", description)
    buf = io.BytesIO()
    Image.open(io.BytesIO(png)).save(buf, format="PNG", pnginfo=info)
    assert np.array_equal(before, np.asarray(Image.open(io.BytesIO(buf.getvalue())).convert("RGB")))
    return buf.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--composites", type=Path, required=True, help="folder of make_commons_samples.py output")
    parser.add_argument("--tests", type=Path, required=True, help="folder of make_test_photos.py output")
    parser.add_argument("--wanteds", type=Path, required=True, help="folder of make_wanted_samples.py output")
    parser.add_argument("--realpicts", type=Path, default=None, help="folder of real user photos (guided samples)")
    parser.add_argument("--guided-run", type=Path, default=None, help="folder of the verified guided run")
    parser.add_argument("--only", nargs="*", default=None, help="bundle only these sample ids (skips the rest)")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    srcdirs = {"commons": args.composites, "tests": args.tests, "wanteds": args.wanteds}
    manifest, credits, user_photos = [], [], []
    if args.only is not None and (old := OUT / "samples.json").is_file():  # keep the entries we're not rebuilding
        manifest = [s for s in json.loads(old.read_text()) if s["id"] not in args.only]
    rendered = RENDERED
    if args.only is None or rendered["id"] in args.only:
        photo, thumb = f"{rendered['id']}.jpg", f"{rendered['id']}.thumb.jpg"
        (OUT / photo).write_bytes(_replace_exif((args.tests / f"{rendered['source']}.jpg").read_bytes(),
                                                rendered["label"]))
        asyncio.run(_thumbnail(OUT / photo, rendered["thickness_mm"], OUT / thumb))
        manifest.append({k: v for k, v in rendered.items() if k != "source"}
                        | {"file": photo, "thumb": thumb, "kind": "synthetic", "rendered": True})
    for sample in SAMPLES:
        if args.only is not None and sample["id"] not in args.only:
            continue
        srcdir = srcdirs[sample["srcdir"]]
        record = json.loads((srcdir / f"{sample['source']}.truth.json").read_text())
        provenance = record.get("provenance", {})
        photo, thumb = f"{sample['id']}.jpg", f"{sample['id']}.thumb.jpg"
        label = RENDERED["label"] if sample["srcdir"] == "tests" else record["label"]
        (OUT / photo).write_bytes(_replace_exif((srcdir / f"{sample['source']}.jpg").read_bytes(), label))
        asyncio.run(_thumbnail(OUT / photo, sample["thickness_mm"], OUT / thumb))
        truth = _truth(record, sample["round_holes"]) | {
            "basis": ("the intact part, as rendered" if sample["srcdir"] == "tests"
                      else provenance["size_basis"]),
            "photographed": sample.get("photographed") or (
                f"{record['footprint']['overall_mm'][0]:.1f} × {record['footprint']['overall_mm'][1]:.1f} "
                "mm box on the mat" + (f"; {provenance['break']}" if provenance.get("break") else "")),
        }
        entry = {k: v for k, v in sample.items() if k not in ("source", "srcdir", "round_holes", "photographed")}
        if "source" in record:  # Wikimedia Commons photo: the author and licence travel with the example
            source = record["source"]
            entry["credit"] = {k: source[k] for k in ("title", "author", "licence", "licence_url", "page")}
            credits.append((photo, thumb, entry["credit"], provenance))
        elif sample["srcdir"] == "wanteds":  # user-supplied photo: used with permission, credited no further
            user_photos.append((photo, thumb, provenance))
        else:  # fully rendered test-set part: no photo at all
            entry["rendered"] = True
        manifest.append(entry | {"file": photo, "thumb": thumb, "kind": "synthetic", "label": label,
                                 "truth": truth})
        print(f"{photo}: {(OUT / photo).stat().st_size / 1e6:.2f} MB; truth {truth['length_mm']} × "
              f"{truth['width_mm']} mm, holes {truth['holes']}")
    for sample in GUIDED:
        if args.only is not None and sample["id"] not in args.only:
            continue
        if args.realpicts is None or args.guided_run is None:
            print(f"SKIP {sample['id']}: guided samples need --realpicts and --guided-run")
            continue
        run = args.guided_run / sample["rundir"]
        photo, thumb, mask = f"{sample['id']}.png", f"{sample['id']}.thumb.jpg", f"{sample['id']}.mask.png"
        (OUT / photo).write_bytes(_png_with_description((args.realpicts / sample["photo_src"]).read_bytes(),
                                                       sample["label"]))
        (OUT / mask).write_bytes((run / "mask.png").read_bytes())  # the verified run's SAM mask, byte for byte
        crop = cv2.imread(str(run / "photo.jpg"))  # the verified run's own rectified crop, as the thumbnail
        scale = 720 / crop.shape[1]
        cv2.imwrite(str(OUT / thumb), cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA),
                    [cv2.IMWRITE_JPEG_QUALITY, 84])
        manifest.append({"id": sample["id"], "title": sample["title"], "story": sample["story"],
                         "thickness_mm": sample["thickness_mm"], "provided_by": sample["provided_by"],
                         "file": photo, "thumb": thumb, "mask": mask, "mask_ai": sample.get("mask_ai", True),
                         "known_length_mm": sample["known_length_mm"], "guidance": sample["guidance"],
                         "kind": "photograph", "label": sample["label"], "truth": sample["truth"]})
        user_photos.append((photo, thumb, sample["provenance"]))
        print(f"{photo}: guided Studio session; truth {sample['truth']['length_mm']} × "
              f"{sample['truth']['width_mm']} mm (ruler-assumed)")
    order = [RENDERED["id"], *(x["id"] for x in SAMPLES), *(x["id"] for x in GUIDED)]
    manifest.sort(key=lambda s: order.index(s["id"]) if s["id"] in order else len(order))
    (OUT / "samples.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.only is not None:  # a partial bundling must not drop the other entries' credits
        have = (OUT / "CREDITS.md").read_text() if (OUT / "CREDITS.md").is_file() else ""
        extra = []
        for photo, thumb, provenance in user_photos:
            if photo not in have:
                extra += [f"## `{photo}`, `{thumb}`", "",
                          f"- **Source photo:** {provenance['source_file']} (supplied by the user for the examples).",
                          f"- **Part:** {provenance['what']}.",
                          f"- **Size basis:** {provenance['size_basis']}.",
                          f"- **Thickness:** {provenance['thickness_basis']}.", ""]
        if extra:
            (OUT / "CREDITS.md").write_text(have.rstrip("\n") + "\n\n" + "\n".join(extra), encoding="utf-8")
        return
    lines = ["# Example photos: credits and licences", "",
             "The Commons-based examples are SYNTHETIC COMPOSITES made by `backend/tools/make_commons_samples.py`: "
             "a real photo of a real part, cut out, its tilt corrected, sized from the stated basis, optionally "
             "broken digitally, and placed on a rendered Re-Forge mat shot by a simulated phone camera. Each "
             "composite (the `.jpg` file and its thumbnail) is an adaptation of the photo below and is shared "
             "under the same licence as its source photo.", ""]
    for photo, thumb, credit, provenance in credits:
        lines += [f"## `{photo}`, `{thumb}`", "",
                  f"- **Source photo:** [{credit['title']}]({credit['page']}) by {credit['author']}, Wikimedia "
                  "Commons.",
                  f"- **Licence:** {credit['licence']} ({credit['licence_url']}). The composite is shared under "
                  "the same licence.",
                  f"- **Part:** {provenance['what']}.",
                  f"- **Size basis:** {provenance['size_basis']}.",
                  f"- **Thickness:** {provenance['thickness_basis']}.",
                  "- **Changes:** cut out; tilt corrected; placed on a rendered mat"
                  + (f"; {provenance['break']}" if provenance.get("break") else "") + ".", ""]
    if user_photos:
        lines += ["## User-provided photos", "",
                  "The sprocket composites are made by `backend/tools/make_wanted_samples.py` from photos the user "
                  "supplied for the examples (the same 21-tooth chain sprocket, stamped 06A21), used with their "
                  "permission. Full provenance, including every CHOSEN size, is recorded in the tool.", ""]
        for photo, thumb, provenance in user_photos:
            lines += [f"## `{photo}`, `{thumb}`", "",
                      f"- **Source photo:** {provenance['source_file']} (supplied by the user for the examples).",
                      f"- **Part:** {provenance['what']}.",
                      f"- **Size basis:** {provenance['size_basis']}.",
                      f"- **Thickness:** {provenance['thickness_basis']}.", ""]
    rendered_files = ", ".join(f"`{s['id']}.jpg`" for s in [RENDERED, *SAMPLES]
                                if s["id"] == RENDERED["id"] or s.get("srcdir") == "tests")
    lines += [f"{rendered_files} are fully rendered (no photo). The rest of the repository is Apache-2.0.", ""]
    (OUT / "CREDITS.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
