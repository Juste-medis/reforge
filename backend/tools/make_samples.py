"""Bundle the app's example photos (``assets/samples/``) from the composite test set.

The examples are the test set's *rendered* plastic parts (no stock photo involved), "photographed" by the test
harness's simulated phone camera on the rendered mat: SYNTHETIC images with an exact ground truth. They let anyone run
the real pipeline without printing the mat, and they are labelled as synthetic everywhere they appear.

The JPEG data is copied byte for byte (no recompression, so the metrology sees exactly what the test set measured); only
the EXIF description is rewritten to say what the image is. The thumbnail is the pipeline's own rectified crop of the
part, from an offline run (classical outline, geometric rule: no AI, no cost).

    cd backend && uv run python -m tools.make_samples --tests ../tmp/tests
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import struct
import tempfile
from pathlib import Path

import cv2
from PIL import Image

from reforge.config import REPO_ROOT

OUT = REPO_ROOT / "assets" / "samples"
LABEL = ("SYNTHETIC EXAMPLE: a rendered plastic part on a rendered Re-Forge mat, shot by a simulated phone camera "
         "(RE-FORGE tools/make_test_photos.py). Not a real photo.")
SAMPLES = [
    {"id": "broken-bracket", "source": "15_bracket_orange_broken", "title": "Broken mounting bracket",
     "story": "One end snapped off. The intact end and the second hole survive, so the mirror has evidence to use.",
     "thickness_mm": 3.0,
     "truth": {"basis": "the intact part, as rendered", "length_mm": 80.0, "width_mm": 28.0,
               "holes": [{"diameter_mm": 4.2, "count": 2}],
               "photographed": "77.6 mm long: 2.4 mm of the end is missing"}},
    {"id": "broken-flange", "source": "20_flange_black_broken", "title": "Broken square flange",
     "story": "A quarter of the flange is gone, and two of its four bolt holes with it.",
     "thickness_mm": 3.0,
     "truth": {"basis": "the intact part, as rendered", "length_mm": 50.0, "width_mm": 50.0,
               "holes": [{"diameter_mm": 22.0, "count": 1}, {"diameter_mm": 5.5, "count": 4}],
               "photographed": "40.4 mm wide: two Ø5.5 holes were lost in the break"}},
    {"id": "slotted-link", "source": "18_link_red", "title": "Slotted link, intact",
     "story": "An intact part placed at an angle: nothing to rebuild, measured as photographed.",
     "thickness_mm": 4.0,
     "truth": {"basis": "the part, as rendered", "length_mm": 70.0, "width_mm": 18.0,
               "holes": [{"diameter_mm": 6.0, "count": 2}, {"slot_mm": [20.0, 6.0], "count": 1}],
               "photographed": "placed at 30° to the mat"}},
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
        if marker in (b"\xff\xda",):  # start of scan: copy the rest untouched
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tests", type=Path, required=True, help="folder of make_test_photos.py output")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for sample in SAMPLES:
        source = args.tests / f"{sample['source']}.jpg"
        photo, thumb = f"{sample['id']}.jpg", f"{sample['id']}.thumb.jpg"
        (OUT / photo).write_bytes(_replace_exif(source.read_bytes(), LABEL))
        asyncio.run(_thumbnail(OUT / photo, sample["thickness_mm"], OUT / thumb))
        manifest.append({k: v for k, v in sample.items() if k != "source"}
                        | {"file": photo, "thumb": thumb, "kind": "synthetic", "label": LABEL})
        size_mb, thumb_kb = (OUT / photo).stat().st_size / 1e6, (OUT / thumb).stat().st_size // 1000
        print(f"{photo}: {size_mb:.2f} MB, thumbnail {thumb_kb} kB")
    (OUT / "samples.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
