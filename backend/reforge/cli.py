"""Command line: ``reforge run`` (photo → STL) and ``reforge mat`` (printable mat)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

from reforge.capture.mat import main as mat_main
from reforge.errors import ReforgeError


def _run(args: argparse.Namespace) -> int:
    from reforge.pipeline import photo_to_stl
    from reforge.vision.segment import ClassicalSegmenter, SamSegmenter

    job_id = args.job or uuid.uuid4().hex[:10]
    if args.segmenter == "sam":
        from reforge.meta_api.client import MetaClient

        point = tuple(int(v) for v in args.point.split(",")) if args.point else None
        segmenter = SamSegmenter(MetaClient(), prompt=args.prompt, point_px=point, job_id=job_id)
    else:
        segmenter = ClassicalSegmenter()
        print("note: classical fallback segmentation (not AI) was requested", file=sys.stderr)
    from reforge.config import get_settings

    out = args.output or get_settings().reforge_data_dir / "jobs" / job_id
    report = asyncio.run(photo_to_stl(args.photo, out, args.thickness, segmenter, bar_x_mm=args.bar_x,
                                      bar_y_mm=args.bar_y, job_id=job_id))
    summary = {k: report[k] for k in ("segmentation", "part", "timings_s")}
    summary["valid"] = report["validation"]["valid"]
    summary["output_dir"] = str(out)
    print(json.dumps(summary, indent=2, default=str))
    return 0 if report["validation"]["valid"] else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="reforge")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="photo of a part on the mat → validated STL (M1: observed geometry)")
    run.add_argument("--photo", type=Path, required=True)
    run.add_argument("--thickness", type=float, required=True, help="caliper thickness in mm")
    run.add_argument("--bar-x", type=float, default=None, help="caliper reading of the horizontal 100 mm bar")
    run.add_argument("--bar-y", type=float, default=None, help="caliper reading of the vertical 100 mm bar")
    run.add_argument("--segmenter", choices=["sam", "classical"], default="sam")
    run.add_argument("--prompt", default="plastic part", help="SAM 3.1 noun phrase")
    run.add_argument("--point", default=None, help="SAM point prompt 'x,y' in rectified-view pixels")
    run.add_argument("--job", default=None)
    run.add_argument("-o", "--output", type=Path, default=None)
    sub.add_parser("mat", help="write the printable calibration mat", add_help=False)
    args, rest = parser.parse_known_args(argv)
    try:
        if args.command == "mat":
            mat_main(rest)
            return 0
        return _run(args)
    except ReforgeError as exc:
        print(json.dumps({"error": exc.to_dict()}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
