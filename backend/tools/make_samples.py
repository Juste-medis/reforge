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
    {"id": "heart", "srcdir": "wanteds", "source": "heart_intact",
     "title": "Metal heart, intact (user photo)",
     "story": "A real engraved metal heart from the user's mat photo, measured 51.8 mm wide with a caliper. "
              "Traced as photographed: nothing rebuilt.",
     "thickness_mm": 3.0, "round_holes": "all", "provided_by": "user", "photographed": "whole on the mat"},
    {"id": "broken-heart", "srcdir": "wanteds", "source": "heart_broken",
     "title": "Metal heart, lobe-tip chipped off (user photo)",
     "story": "The same heart with its right lobe-tip chipped off. Symmetric by blank, so the mirror rebuilds "
              "the missing tip.",
     "thickness_mm": 3.0, "round_holes": "all", "provided_by": "user", "photographed": "right lobe-tip chipped off"},
    {"id": "heart-second-shot", "srcdir": "wanteds", "source": "heart2_intact",
     "title": "Metal heart, second photo, intact",
     "story": "The same trinket from the user's second mat photo (stronger angle, outline symmetrised as cast). "
              "Measured whole.",
     "thickness_mm": 3.0, "round_holes": "all", "provided_by": "user", "photographed": "whole on the mat"},
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
    {"id": "broken-heart-second-shot", "srcdir": "wanteds", "source": "heart2_broken",
     "title": "Metal heart, second photo, lobe-tip chipped off",
     "story": "The same trinket from the user's second mat photo with its left lobe-tip chipped off (the other "
              "side from the first heart). The mirror rebuilds the missing tip.",
     "thickness_mm": 3.0, "round_holes": "all", "provided_by": "user", "photographed": "left lobe-tip chipped off"},
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--composites", type=Path, required=True, help="folder of make_commons_samples.py output")
    parser.add_argument("--tests", type=Path, required=True, help="folder of make_test_photos.py output")
    parser.add_argument("--wanteds", type=Path, required=True, help="folder of make_wanted_samples.py output")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    srcdirs = {"commons": args.composites, "tests": args.tests, "wanteds": args.wanteds}
    manifest, credits, user_photos = [], [], []
    rendered = RENDERED
    photo, thumb = f"{rendered['id']}.jpg", f"{rendered['id']}.thumb.jpg"
    (OUT / photo).write_bytes(_replace_exif((args.tests / f"{rendered['source']}.jpg").read_bytes(),
                                            rendered["label"]))
    asyncio.run(_thumbnail(OUT / photo, rendered["thickness_mm"], OUT / thumb))
    manifest.append({k: v for k, v in rendered.items() if k != "source"}
                    | {"file": photo, "thumb": thumb, "kind": "synthetic", "rendered": True})
    for sample in SAMPLES:
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
    (OUT / "samples.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
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
