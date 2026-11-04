"""HTTP API: a photo of a part on the mat → a validated STL, an editable OpenSCAD file, and an evidence report.

Uploads are untrusted:
- size and pixel limits are enforced
- the image is decoded and re-encoded as PNG, which strips EXIF/GPS before any processing or API call; the one
  value read from the metadata first is the lens focal length (35 mm equivalent), which the height correction needs
- job IDs are validated, and only whitelisted output files are served
The API key never reaches a response.

A job runs in the background (``reforge.api.jobs``): ``POST /api/jobs`` with ``wait=false`` answers at once with the
job id, and ``GET /api/jobs/{id}`` reports the pipeline's real stage events, then the result. Without ``wait=false``
the request waits for the result, as before.

Each job folder keeps ``request.json`` (the options chosen) and, when the job stops, ``error.json`` (the typed error
shown to the user), so a failed run can be diagnosed afterwards. Neither is served.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import re
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from shapely.geometry import Polygon

from reforge.api.jobs import JobRegistry
from reforge.capture.pose import focal_35mm_from_exif
from reforge.config import REPO_ROOT, Settings, get_settings
from reforge.errors import ReforgeError

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 40_000_000
JOB_ID = re.compile(r"^[a-f0-9]{12}$")
SAMPLE_ID = re.compile(r"^[a-z0-9-]{1,40}$")
OUTPUTS = {
    "model.stl": "model/stl",
    "model.scad": "text/plain; charset=utf-8",
    "model.dxf": "application/dxf",
    "model.svg": "image/svg+xml",
    "spec.json": "application/json",
    "report.json": "application/json",
    "photo.jpg": "image/jpeg",
    "texture.jpg": "image/jpeg",
    "overlay.png": "image/png",
    "setofmark.png": "image/png",
    "mask.png": "image/png",
}
SAMPLES_DIR = REPO_ROOT / "assets" / "samples"
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": ("default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
                                "script-src 'self'; connect-src 'self'; font-src 'self' data:; object-src 'none'; "
                                "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"),
}


def _decode_upload(data: bytes) -> np.ndarray:
    if not data:
        raise ReforgeError("UPLOAD_EMPTY", "The uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ReforgeError("UPLOAD_TOO_LARGE", f"Uploads are limited to {MAX_UPLOAD_BYTES // 2**20} MB.")
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)  # applies EXIF orientation
    if image is None:
        raise ReforgeError("UPLOAD_NOT_IMAGE", "The file is not a supported image (JPEG, PNG, WebP…).")
    if image.shape[0] * image.shape[1] > MAX_PIXELS:
        raise ReforgeError("UPLOAD_TOO_MANY_PIXELS", f"Images are limited to {MAX_PIXELS // 1_000_000} megapixels.")
    return image


def load_samples(samples_dir: Path = SAMPLES_DIR) -> list[dict]:
    """The bundled example photos (``assets/samples/samples.json``). Every one is labelled as what it is."""
    manifest = samples_dir / "samples.json"
    if not manifest.is_file():
        return []
    samples = json.loads(manifest.read_text(encoding="utf-8"))
    return [s for s in samples
            if SAMPLE_ID.fullmatch(s.get("id", "")) and (samples_dir / s["file"]).is_file()
            and ("mask" not in s or (samples_dir / s["mask"]).is_file())]


def _public_sample(sample: dict) -> dict:
    return {**{k: v for k, v in sample.items() if k not in ("file", "thumb")},
            "image_url": f"/api/samples/{sample['id']}/photo.jpg",
            "thumb_url": f"/api/samples/{sample['id']}/thumb.jpg"}


def _files(job_id: str) -> dict[str, str]:
    return {name: f"/api/jobs/{job_id}/{name}" for name in OUTPUTS}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    jobs_dir = settings.reforge_data_dir / "jobs"
    registry = JobRegistry(settings.reforge_max_running_jobs, settings.reforge_max_queued_jobs)
    samples = {s["id"]: s for s in load_samples()}
    app = FastAPI(title="RE-FORGE AI", version="0.2.0")

    @app.middleware("http")
    async def _headers(request: Request, call_next):
        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        return response

    @app.exception_handler(ReforgeError)
    async def _typed_error(_, exc: ReforgeError) -> JSONResponse:
        status = {"UPLOAD_TOO_LARGE": 413, "SERVER_BUSY": 429, "JOB_NOT_FOUND": 404}.get(exc.code, 422)
        body: dict = {"error": exc.to_dict()}
        if getattr(exc, "job_id", None):
            body["job_id"] = exc.job_id
        return JSONResponse(body, status_code=status)

    def _ai_ready() -> bool:
        key = settings.meta_model_api_key
        return bool(key and key.get_secret_value().strip())

    @app.get("/api/health")
    async def health() -> dict:
        body = {"ok": True, "meta_key_configured": _ai_ready(),
                "segmentation_model": settings.reforge_model_segmentation,
                "reasoning_model": settings.reforge_model_reasoning,
                "busy": registry.active() >= settings.reforge_max_running_jobs}
        if _ai_ready():
            from reforge.meta_api.client import Ledger

            spent = Ledger(settings.reforge_data_dir / "usage" / "ledger.jsonl").spent_today()
            body["ai_budget"] = {"cap_usd": settings.reforge_daily_budget_usd, "spent_today_usd": round(spent, 4)}
        return body

    @app.get("/api/mat/{page}.pdf")
    async def mat(page: str) -> FileResponse:
        if page not in ("A4", "Letter"):
            raise HTTPException(404)
        return FileResponse(REPO_ROOT / "assets" / "mat" / f"reforge-mat-{page}-v1.pdf", media_type="application/pdf",
                            filename=f"reforge-mat-{page}-v1.pdf")

    @app.get("/api/samples")
    async def list_samples() -> list[dict]:
        return [_public_sample(s) for s in samples.values()]

    @app.get("/api/samples/{sample_id}/{name}")
    async def sample_file(sample_id: str, name: str) -> FileResponse:
        sample = samples.get(sample_id)
        if sample is None or name not in ("photo.jpg", "thumb.jpg"):
            raise HTTPException(404)
        path = SAMPLES_DIR / sample["file" if name == "photo.jpg" else "thumb"]
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path, media_type="image/jpeg")

    async def _work(job_id: str, job_dir: Path, opts: dict, progress) -> dict:
        from reforge.pipeline import photo_to_stl
        from reforge.reasoning.interpret import GeometricInterpreter, SparkInterpreter
        from reforge.reasoning.reconstruct import Guidance
        from reforge.vision.segment import ClassicalSegmenter, SamSegmenter, Segmentation

        try:
            client = None
            use_spark = opts["interpreter"] == "spark"
            if opts["segmenter"] == "sam" or use_spark:
                from reforge.meta_api.client import MetaClient

                client = MetaClient(settings)
            if opts["segmenter"] == "sam":
                seg = SamSegmenter(client, prompt=opts["prompt"], job_id=job_id)
            else:
                seg = ClassicalSegmenter()
            reader = SparkInterpreter(client, job_id=job_id) if use_spark else GeometricInterpreter()
            guidance = None
            guide_fields = ("guide_axis", "guide_fracture", "guide_exclude", "guide_damage", "guide_sources",
                                  "guide_family_override", "guide_assert_angle", "guide_assert_x_mm",
                                  "guide_assert_y_mm")
            if any(opts[f] for f in guide_fields):
                picked = tuple(s for s in opts["guide_sources"].replace(",", " ").split() if s)
                px, py = opts["guide_assert_x_mm"], opts["guide_assert_y_mm"]
                if (px is None) != (py is None):
                    raise ReforgeError("GUIDE_BAD_POINT", "The axis pivot needs both x and y.",
                                       "Send guide_assert_x_mm and guide_assert_y_mm together, in millimetres.")
                guidance = Guidance(axis_id=opts["guide_axis"] or None,
                                    assert_angle_deg=opts["guide_assert_angle"],
                                    assert_point_mm=None if px is None else (px, py),
                                    fracture_ids=tuple(s for s in opts["guide_fracture"].replace(",", " ").split()
                                                       if s),
                                    exclude_ids=tuple(s for s in opts["guide_exclude"].replace(",", " ").split()
                                                      if s),
                                    damage_hole_ids=tuple(s for s in opts["guide_damage"].replace(",", " ").split()
                                                          if s),
                                    source_hole_ids=picked or None,
                                    family_override=opts["guide_family_override"], note=opts["guide_note"])
            reuse, mask_png = None, (jobs_dir / str(opts["from_job"]) / "mask.png"
                                     if opts["from_job"] and guidance is not None else None)
            sample_mask: Path | None = None
            if mask_png is None and opts["sample"] in samples and guidance is not None:
                entry = samples[opts["sample"]]
                if entry.get("mask"):
                    sample_mask = SAMPLES_DIR / entry["mask"]
            if sample_mask is not None and sample_mask.is_file():  # a guided example: its stored segmentation
                entry = samples[opts["sample"]]
                reuse = Segmentation(mask=cv2.imread(str(sample_mask), cv2.IMREAD_GRAYSCALE) > 127,
                                     method="sample-mask", is_ai=bool(entry.get("mask_ai")),
                                     detail={"reused_from": f"sample:{opts['sample']}"})
            elif mask_png is not None and mask_png.is_file():
                source_report = jobs_dir / str(opts["from_job"]) / "report.json"
                source_request = jobs_dir / str(opts["from_job"]) / "request.json"
                method, is_ai = "reused", False
                if source_report.is_file():
                    old = json.loads(source_report.read_text()).get("segmentation", {})
                    method, is_ai = f"reused-{old.get('method', '?')}", bool(old.get("is_ai"))
                elif source_request.is_file():  # failed jobs have no report: the request names the segmenter
                    sam = json.loads(source_request.read_text()).get("segmenter") == "sam"
                    method, is_ai = f"reused-{'sam-3.1' if sam else 'classical-fallback'}", sam
                reuse = Segmentation(mask=cv2.imread(str(mask_png), cv2.IMREAD_GRAYSCALE) > 127, method=method,
                                     is_ai=is_ai, detail={"reused_from": opts["from_job"]})
            return await photo_to_stl(job_dir / "input.png", job_dir, opts["thickness_mm"], seg,
                                      bar_x_mm=opts["bar_x_mm"], bar_y_mm=opts["bar_y_mm"], job_id=job_id,
                                      focal_35mm=opts["focal_35mm"], interpreter=reader, progress=progress,
                                      known_length_mm=opts["known_length_mm"], guidance=guidance,
                                      reuse_segmentation=reuse, ruler_px_per_mm=opts["deskew_px_per_mm"])
        except ReforgeError as exc:
            exc.job_id = job_id
            (job_dir / "error.json").write_text(json.dumps({"job_id": job_id, **exc.to_dict()}, indent=2))
            raise
        except Exception as exc:  # an unexpected failure still leaves a trace
            (job_dir / "error.json").write_text(json.dumps(
                {"job_id": job_id, "code": "INTERNAL_ERROR", "message": type(exc).__name__, "hint": None}, indent=2))
            raise

    @app.post("/api/jobs")
    async def create_job(
        thickness_mm: Annotated[float, Form(gt=0.4, le=200)],
        photo: Annotated[UploadFile | None, File()] = None,
        sample: Annotated[str | None, Form(max_length=40)] = None,
        from_job: Annotated[str | None, Form(max_length=12)] = None,
        bar_x_mm: Annotated[float | None, Form()] = None,  # range-checked by the calibration, with a typed hint
        bar_y_mm: Annotated[float | None, Form()] = None,
        known_length_mm: Annotated[float | None, Form(gt=0, le=5000)] = None,  # ruler mode: no mat, longest side
        deskew_px_per_mm: Annotated[float | None, Form(gt=0)] = None,  # Studio: exact scale of a deskewed photo
        guide_axis: Annotated[str | None, Form(max_length=8)] = None,  # Studio: candidate axis id (A0…), or "none"
        guide_fracture: Annotated[str, Form(max_length=200)] = "",  # Studio: segment ids, comma/space separated
        guide_exclude: Annotated[str, Form(max_length=200)] = "",  # Studio: designed-asymmetry spans, same format
        guide_damage: Annotated[str, Form(max_length=200)] = "",  # Studio: hole ids marked as damage, same format
        guide_sources: Annotated[str, Form(max_length=500)] = "",  # Studio: hole ids to mirror from (empty = auto)
        guide_assert_angle: Annotated[float | None, Form(ge=0, lt=180)] = None,  # Studio: asserted axis U0, degrees
        guide_assert_x_mm: Annotated[float | None, Form()] = None,  # Studio: U0 pivot x, mm (needs y too)
        guide_assert_y_mm: Annotated[float | None, Form()] = None,  # Studio: U0 pivot y, mm
        guide_family_override: Annotated[bool, Form()] = False,  # Studio: assert a flat model of a non-flat reading
        guide_note: Annotated[str, Form(max_length=280)] = "",
        segmenter: Annotated[str, Form(pattern="^(sam|classical)$")] = "sam",
        prompt: Annotated[str, Form(max_length=60)] = "plastic part",
        interpreter: Annotated[str | None, Form(pattern="^(spark|geometric)$")] = None,
        wait: Annotated[bool, Form()] = True,
    ):
        sources = [s for s in (photo, sample, from_job) if s]
        if len(sources) != 1:
            raise ReforgeError("SOURCE_INVALID", "Send exactly one of: a photo, an example id, or a previous job id.")
        registry.check_capacity()
        focal_35mm: float | None
        previous: dict = {}
        if photo is not None:
            data = await photo.read(MAX_UPLOAD_BYTES + 1)
            image = _decode_upload(data)
            focal_35mm = focal_35mm_from_exif(data)  # the only metadata kept: the height correction needs it
        elif sample:
            if sample not in samples:
                raise ReforgeError("SAMPLE_NOT_FOUND", f"There is no example called {sample!r}.")
            data = (SAMPLES_DIR / samples[sample]["file"]).read_bytes()
            image, focal_35mm = _decode_upload(data), focal_35mm_from_exif(data)
        else:
            source_dir = jobs_dir / str(from_job)
            if not JOB_ID.fullmatch(str(from_job)) or not (source_dir / "input.png").is_file():
                raise ReforgeError("JOB_NOT_FOUND", "That earlier analysis isn't on this server any more.",
                                   "Upload the photo again.")
            image = None
            record = source_dir / "request.json"
            previous = json.loads(record.read_text()) if record.is_file() else {}
            focal_35mm = previous.get("focal_35mm")
        job_id = uuid.uuid4().hex[:12]
        job_dir = jobs_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=False)
        input_path = job_dir / "input.png"
        if image is not None:
            cv2.imwrite(str(input_path), image)  # re-encoded: no EXIF/GPS survives
            size = [image.shape[1], image.shape[0]]
        else:
            shutil.copyfile(jobs_dir / str(from_job) / "input.png", input_path)
            size = previous.get("image_size")
        use_spark = (interpreter or ("spark" if segmenter == "sam" else "geometric")) == "spark"
        opts = {"thickness_mm": thickness_mm, "bar_x_mm": bar_x_mm, "bar_y_mm": bar_y_mm, "segmenter": segmenter,
                "prompt": prompt.strip() or "plastic part", "interpreter": "spark" if use_spark else "geometric",
                "focal_35mm": focal_35mm, "known_length_mm": known_length_mm,
                "deskew_px_per_mm": deskew_px_per_mm, "from_job": from_job, "sample": sample,
                "guide_axis": (guide_axis or "").strip() or None, "guide_fracture": guide_fracture,
                "guide_exclude": guide_exclude, "guide_damage": guide_damage, "guide_sources": guide_sources,
                "guide_assert_angle": guide_assert_angle, "guide_assert_x_mm": guide_assert_x_mm,
                "guide_assert_y_mm": guide_assert_y_mm,
                "guide_family_override": guide_family_override, "guide_note": guide_note.strip()}
        if sample and sample in samples:  # a guided example carries its Studio session; explicit fields win
            guided = samples[sample].get("guidance") or {}
            if opts["known_length_mm"] is None and samples[sample].get("known_length_mm") is not None:
                opts["known_length_mm"] = samples[sample]["known_length_mm"]
            point = guided.get("assert_point") or [None, None]
            fill = {"guide_axis": guided.get("axis"), "guide_fracture": " ".join(guided.get("fracture") or []),
                    "guide_exclude": " ".join(guided.get("exclude") or []),
                    "guide_damage": " ".join(guided.get("damage") or []),
                    "guide_sources": " ".join(guided.get("sources") or []),
                    "guide_assert_angle": guided.get("assert_angle"), "guide_assert_x_mm": point[0],
                    "guide_assert_y_mm": point[1], "guide_family_override": guided.get("family_override", False),
                    "guide_note": guided.get("note", "")}
            for key, value in fill.items():
                if not opts[key]:
                    opts[key] = value
        request_record = {"job_id": job_id, "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
                          "image_size": size, "sample": sample, "from_job": from_job, **opts}
        (job_dir / "request.json").write_text(json.dumps(request_record, indent=2))
        job = registry.submit(job_id, lambda progress: _work(job_id, job_dir, opts, progress))
        if not wait:
            return JSONResponse({"job_id": job_id, "status_url": f"/api/jobs/{job_id}"}, status_code=202)
        assert job.task is not None
        report = await asyncio.shield(job.task)
        if job.exception is not None:
            raise job.exception
        return {"job_id": job_id, "report": report, "files": _files(job_id)}

    def _request_summary(job_dir: Path) -> dict:
        path = job_dir / "request.json"
        if not path.is_file():
            return {}
        req = json.loads(path.read_text())
        keep = ("created_at", "image_size", "sample", "from_job", "reshaped_from", "thickness_mm", "bar_x_mm",
                "bar_y_mm", "segmenter", "prompt", "interpreter", "focal_35mm", "known_length_mm",
                "deskew_px_per_mm", "guide_axis", "guide_fracture", "guide_damage", "guide_sources",
                "guide_assert_angle", "guide_assert_x_mm", "guide_assert_y_mm", "guide_family_override",
                "guide_note")
        summary = {k: req.get(k) for k in keep}
        if req.get("sample") in samples:
            summary["sample_info"] = _public_sample(samples[req["sample"]])
        return summary

    @app.get("/api/jobs/{job_id}")
    async def job_status(job_id: str) -> dict:
        if not JOB_ID.fullmatch(job_id):
            raise HTTPException(404)
        job_dir = jobs_dir / job_id
        if not job_dir.is_dir():
            raise HTTPException(404)
        body: dict = {"job_id": job_id, "request": _request_summary(job_dir)}
        job = registry.get(job_id)
        report_path, error_path = job_dir / "report.json", job_dir / "error.json"
        if job is not None and job.state in ("queued", "running"):
            body.update(state=job.state, stages=job.stage_list(), elapsed_s=job.elapsed_s)
            return body
        if report_path.is_file():
            report = json.loads(report_path.read_text())
            body.update(state="done", result={"report": report, "files": _files(job_id)},
                        stages=[{"id": k, "state": "done", "seconds": v} for k, v in report["timings_s"].items()],
                        elapsed_s=job.elapsed_s if job else round(sum(report["timings_s"].values()), 2))
        elif error_path.is_file():
            error = json.loads(error_path.read_text())
            if error.get("code") == "INTERNAL_ERROR":  # the exception's type stays in the file, not in the response
                error = {"code": "INTERNAL_ERROR", "message": "The analysis stopped on an unexpected error.",
                         "hint": "Try again; if it happens again, report the job id."}
            body.update(state="failed", error={k: error.get(k) for k in ("code", "message", "hint")},
                        stages=job.stage_list() if job else [], elapsed_s=job.elapsed_s if job else None,
                        files={k: v for k, v in _files(job_id).items()
                               if (job_dir / k).is_file()})  # what exists: input, mask, setofmark…
        else:
            body.update(state="interrupted", stages=[], elapsed_s=None, error={
                "code": "JOB_INTERRUPTED", "message": "This analysis was stopped before it finished (the server "
                "restarted).", "hint": "Run it again."})
        partial = job_dir / "reconstruction.json"
        if partial.is_file():  # the Studio's candidates survive success and refusals alike
            body["reconstruction"] = json.loads(partial.read_text())
        feedback_path = job_dir / "feedback.json"
        if feedback_path.is_file():
            body["feedback"] = json.loads(feedback_path.read_text())
        return body

    @app.post("/api/jobs/{job_id}/feedback")
    async def post_feedback(job_id: str, verdict: Annotated[str, Form(pattern="^(ok|wrong)$")],
                            note: Annotated[str, Form(max_length=500)] = "") -> dict:
        """The human-in-the-loop record: was this result right? Stored on the job, shown with it, and reviewed to
        steer the pipeline (which refusals and rebuilds to trust next)."""
        if not JOB_ID.fullmatch(job_id):
            raise HTTPException(404)
        job_dir = jobs_dir / job_id
        if not job_dir.is_dir():
            raise HTTPException(404)
        path = job_dir / "feedback.json"
        entries = json.loads(path.read_text()) if path.is_file() else []
        entries.append({"created_at": datetime.now(UTC).isoformat(timespec="seconds"), "verdict": verdict,
                        "note": note.strip()})
        path.write_text(json.dumps(entries, indent=2))
        return {"ok": True, "count": len(entries)}

    @app.post("/api/jobs/{job_id}/reshape", status_code=202)
    async def post_reshape(job_id: str, body: dict) -> dict:
        """The Studio's outline editor: rebuild from a hand-redrawn boundary.

        The editor shows the built outline over ``photo.jpg``; the user drags it and the photo comes back here as
        ``outline_px`` (photo pixels, implicitly closed). The pipeline re-runs on the parent's photo, mask and
        calibration with the redrawn boundary, re-judging everything; the report records the edit. Fracture and
        exclusion spans are re-picked by geometry (the redraw renumbers them), the asserted angle/pivot and the
        hole lists carry over (same frame, same holes), and only the candidate axis id is dropped as stale."""
        from reforge.pipeline import photo_to_stl
        from reforge.reasoning.interpret import GeometricInterpreter, SparkInterpreter
        from reforge.reasoning.reconstruct import Guidance
        from reforge.studio.reshape import carry_span_picks, parent_segmentation, photo_px_to_view_mm, validate_outline
        from reforge.vision.segment import Segmentation

        if not JOB_ID.fullmatch(job_id):
            raise HTTPException(404)
        parent = jobs_dir / job_id
        parent_report = parent / "report.json"
        if not parent_report.is_file():
            raise ReforgeError("JOB_NOT_FOUND", f"No finished analysis {job_id} to reshape.",
                               "Reshape from a finished analysis.")
        frame_path = parent / "frame.json"
        if not frame_path.is_file():
            raise ReforgeError("RESHAPE_NO_FRAME", "This analysis predates the outline editor (no photo frame).",
                               "Run the photo once more, then reshape the new analysis.")
        for name in ("input.png", "request.json", "mask.png"):
            if not (parent / name).is_file():
                raise ReforgeError("JOB_NOT_FOUND", f"The analysis {job_id} is missing its {name}.",
                                   "Run the photo once more, then reshape the new analysis.")
        try:
            outline_px = np.asarray(body.get("outline_px"), dtype=float).reshape(-1, 2)
            baseline_px = np.asarray(body.get("baseline_px", outline_px), dtype=float).reshape(-1, 2)
        except (ValueError, TypeError) as err:
            raise ReforgeError("RESHAPE_INVALID", "Can't read the redrawn outline.",
                               "Send outline_px as [[x, y], …] in photo pixels.") from err
        wait = bool(body.get("wait", False))
        frame = json.loads(frame_path.read_text())
        photo_w, photo_h = (int(v) for v in frame["photo_size_px"])
        if bool((outline_px[:, 0] < 0).any() or (outline_px[:, 0] > photo_w).any()
                or (outline_px[:, 1] < 0).any() or (outline_px[:, 1] > photo_h).any()):
            raise ReforgeError("RESHAPE_INVALID", "The redrawn outline leaves the photo.",
                               "Keep the outline inside the photo you were shown.")
        report = json.loads(parent_report.read_text())
        cal = report["calibration"]
        view_mm = photo_px_to_view_mm(outline_px, frame, cal["px_per_mm_exact"], tuple(cal["origin_mm"]))
        base_mm = photo_px_to_view_mm(baseline_px, frame, cal["px_per_mm_exact"], tuple(cal["origin_mm"]))
        edit_moves = np.hypot(*(view_mm - base_mm).T) if len(base_mm) == len(view_mm) else np.zeros(0)
        parent_spec = json.loads((parent / "spec.json").read_text())
        parent_area = float(Polygon([tuple(p) for p in parent_spec["outline"]["points"]]).area)
        validate_outline(view_mm, parent_area)
        parent_req = json.loads((parent / "request.json").read_text())
        carried = {k: parent_req.get(k) for k in
                   ("guide_assert_angle", "guide_assert_x_mm", "guide_assert_y_mm", "guide_damage",
                    "guide_sources", "guide_family_override")}
        dropped = {"guide_axis": parent_req.get("guide_axis")} if parent_req.get("guide_axis") else {}
        note_bits = [f"Reshaped in the Studio from {job_id}"]
        if parent_req.get("guide_note"):
            note_bits.append(str(parent_req["guide_note"])[:200])
        if dropped:
            note_bits.append(f"dropped stale picks: {', '.join(sorted(dropped))}")
        parent_mask = cv2.imread(str(parent / "mask.png"), cv2.IMREAD_GRAYSCALE) > 127
        parent_seg = await asyncio.to_thread(parent_segmentation, parent / "input.png", parent_mask, parent_req)
        carried_fracture = carry_span_picks(
            tuple(str(parent_req.get("guide_fracture") or "").replace(",", " ").split()), parent_seg, view_mm)
        carried_exclude = carry_span_picks(
            tuple(str(parent_req.get("guide_exclude") or "").replace(",", " ").split()), parent_seg, view_mm)
        if parent_req.get("guide_fracture") and not carried_fracture:
            note_bits.append("the redraw moved the picked break away; no fracture carried")
        if parent_req.get("guide_exclude") and not carried_exclude:
            note_bits.append("the redraw moved the kept spans away; no exclusions carried")
        guidance = Guidance(assert_angle_deg=carried["guide_assert_angle"],
                            assert_point_mm=(None if carried["guide_assert_x_mm"] is None else
                                             (carried["guide_assert_x_mm"], carried["guide_assert_y_mm"])),
                            fracture_ids=carried_fracture, exclude_ids=carried_exclude,
                            damage_hole_ids=tuple(str(carried["guide_damage"] or "").replace(",", " ").split()),
                            source_hole_ids=(tuple(str(carried["guide_sources"]).replace(",", " ").split())
                                             if carried["guide_sources"] else None),
                            family_override=bool(carried["guide_family_override"]), note="; ".join(note_bits))
        registry.check_capacity()
        child_id = uuid.uuid4().hex[:12]
        child_dir = jobs_dir / child_id
        child_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(parent / "input.png", child_dir / "input.png")
        child_req = {k: parent_req.get(k) for k in
                     ("thickness_mm", "bar_x_mm", "bar_y_mm", "segmenter", "prompt", "interpreter",
                      "focal_35mm", "known_length_mm", "deskew_px_per_mm")}
        child_req.update({"job_id": child_id, "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
                          "reshaped_from": job_id, "guide_assert_angle": carried["guide_assert_angle"],
                          "guide_assert_x_mm": carried["guide_assert_x_mm"],
                          "guide_assert_y_mm": carried["guide_assert_y_mm"],
                          "guide_fracture": " ".join(carried_fracture),
                          "guide_exclude": " ".join(carried_exclude),
                          "guide_damage": carried["guide_damage"], "guide_sources": carried["guide_sources"],
                          "guide_family_override": carried["guide_family_override"],
                          "guide_note": "; ".join(note_bits)})
        (child_dir / "request.json").write_text(json.dumps(child_req, indent=2))
        old_seg = report.get("segmentation", {})
        reuse = Segmentation(mask=cv2.imread(str(parent / "mask.png"), cv2.IMREAD_GRAYSCALE) > 127,
                             method=f"reused-{old_seg.get('method', '?')}", is_ai=bool(old_seg.get("is_ai")),
                             detail={"reused_from": job_id})
        reshape_info: dict = {"from_job": job_id, "guidance_carried": {k: v for k, v in carried.items() if v},
                              "fracture_carried": list(carried_fracture),
                              "fracture_from": str(parent_req.get("guide_fracture") or ""),
                              "exclude_carried": list(carried_exclude),
                              "guidance_dropped": dropped,
                              "edited_points": int((edit_moves > 0.05).sum()),
                              "edit_max_mm": round(float(edit_moves.max()) if len(edit_moves) else 0.0, 2),
                              "edit_mean_mm": round(float(edit_moves.mean()) if len(edit_moves) else 0.0, 2)}

        async def _reshape_work(progress) -> dict:
            from reforge.meta_api.client import MetaClient
            from reforge.vision.segment import ClassicalSegmenter

            try:
                client = None
                use_spark = child_req["interpreter"] == "spark"
                if use_spark:
                    client = MetaClient(settings)
                reader = SparkInterpreter(client, job_id=child_id) if use_spark else GeometricInterpreter()
                return await photo_to_stl(
                    child_dir / "input.png", child_dir, child_req["thickness_mm"], ClassicalSegmenter(),
                    bar_x_mm=child_req["bar_x_mm"], bar_y_mm=child_req["bar_y_mm"], job_id=child_id,
                    focal_35mm=child_req["focal_35mm"], interpreter=reader, progress=progress,
                    known_length_mm=child_req["known_length_mm"], guidance=guidance,
                    reuse_segmentation=reuse, ruler_px_per_mm=child_req["deskew_px_per_mm"],
                    outer_override_mm=view_mm, reshape_info=reshape_info)
            except ReforgeError as exc:
                exc.job_id = child_id
                (child_dir / "error.json").write_text(json.dumps({"job_id": child_id, **exc.to_dict()}, indent=2))
                raise
            except Exception as exc:
                (child_dir / "error.json").write_text(json.dumps(
                    {"job_id": child_id, "code": "INTERNAL_ERROR", "message": type(exc).__name__, "hint": None},
                    indent=2))
                raise

        job = registry.submit(child_id, _reshape_work)
        if not wait:
            return JSONResponse({"job_id": child_id, "status_url": f"/api/jobs/{child_id}"}, status_code=202)
        assert job.task is not None
        result = await asyncio.shield(job.task)
        if job.exception is not None:
            raise job.exception
        return JSONResponse({"job_id": child_id, "report": result, "files": _files(child_id)}, status_code=200)

    @app.post("/api/deskew")
    async def post_deskew(photo: Annotated[UploadFile, File()],
                          corners: Annotated[str, Form(max_length=400)],
                          length_mm: Annotated[float, Form(gt=0, le=5000)],
                          width_mm: Annotated[float, Form(gt=0, le=5000)]) -> dict:
        """The Studio's "flatten" step: a perspective photo of a rectangular part back to top-down, at the entered
        L×W. Returns the rectified PNG (base64) with its exact scale; the Studio shows it for approval, then runs
        a normal ruler-mode job from it with the long side as the length."""
        from reforge.studio.deskew import deskew_quad

        data = await photo.read(MAX_UPLOAD_BYTES + 1)
        image = _decode_upload(data)
        try:
            pts = np.asarray(json.loads(corners), dtype=float)
        except (ValueError, TypeError) as err:
            raise ReforgeError("DESKEW_BAD_CORNERS", f"Can't read the corners ({corners[:60]}…).",
                               "Send the four corners as [[x, y], …] in pixels.") from err
        result = deskew_quad(image, pts, length_mm, width_mm)
        ok, png = cv2.imencode(".png", result.image_bgr)
        assert ok
        long_mm, short_mm = max(length_mm, width_mm), min(length_mm, width_mm)
        return {"png_b64": base64.b64encode(png.tobytes()).decode(), "px_per_mm": result.px_per_mm,
                "length_mm": long_mm, "width_mm": short_mm, "margin_px": list(result.margin_px),
                "corners_used": [list(c) for c in result.corners_px]}

    def _compensated(job_dir: Path, name: str, hole_offset_mm: float, outline_offset_mm: float) -> tuple[bytes, str]:
        """Rebuild the job's validated PartSpec with a printer compensation: same evidence, offset holes/outline."""
        from reforge.cad.build import build_part
        from reforge.cad.flat import emit_dxf, emit_svg
        from reforge.cad.scad import emit_scad
        from reforge.spec.partspec import parse_spec
        from reforge.validation.mesh import summarize, validate_part

        data = json.loads((job_dir / "spec.json").read_text())
        data["fit"] = {"hole_offset_mm": hole_offset_mm, "outline_offset_mm": outline_offset_mm}
        spec = parse_spec(data)  # every semantic check runs again: walls, hole spacing, sizes
        if name == "model.scad":
            return emit_scad(spec, job_dir.name).encode(), "text/plain; charset=utf-8"
        if name == "model.dxf":
            return emit_dxf(spec, job_dir.name).encode(), "application/dxf"
        if name == "model.svg":
            return emit_svg(spec, job_dir.name).encode(), "image/svg+xml"
        part = build_part(spec)
        validation = summarize(validate_part(part, spec))
        if not validation["valid"]:
            raise ReforgeError("SPEC_INVALID", "With this compensation the model fails validation: "
                               + ", ".join(validation["errors"]), "Use a smaller compensation.")
        buf = io.BytesIO()
        part.to_trimesh().export(buf, file_type="stl")
        return buf.getvalue(), "model/stl"

    @app.get("/api/jobs/{job_id}/{name}")
    async def job_file(job_id: str, name: str,
                       hole_offset_mm: Annotated[float, Query(ge=-1.0, le=1.0)] = 0.0,
                       outline_offset_mm: Annotated[float, Query(ge=-1.0, le=1.0)] = 0.0):
        if not JOB_ID.fullmatch(job_id) or name not in OUTPUTS:
            raise HTTPException(404)
        job_dir = jobs_dir / job_id
        path = job_dir / name
        if not path.is_file():
            raise HTTPException(404)
        if name.startswith("model.") and (hole_offset_mm or outline_offset_mm):
            content, media = await asyncio.to_thread(_compensated, job_dir, name, hole_offset_mm, outline_offset_mm)
            stem, ext = name.split(".")
            tag = f"-holes{hole_offset_mm:+.2f}" if hole_offset_mm else ""
            tag += f"-outline{outline_offset_mm:+.2f}" if outline_offset_mm else ""
            return Response(content, media_type=media, headers={
                "Content-Disposition": f'attachment; filename="reforge-{job_id}-{stem}{tag}.{ext}"'})
        return FileResponse(path, media_type=OUTPUTS[name], filename=f"reforge-{job_id}-{name}")

    dist = REPO_ROOT / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="ui")
    return app


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(create_app(settings), host=settings.reforge_host, port=settings.reforge_port)
