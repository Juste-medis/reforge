"""HTTP API for the M1 slice: upload a mat photo → validated STL, report and overlay.

Uploads are untrusted:
- size and pixel limits are enforced
- the image is decoded and re-encoded as PNG, which strips EXIF/GPS before any processing or API call; the one
  value read from the metadata first is the lens focal length (35 mm equivalent), which the height correction needs
- job IDs are validated
- only whitelisted output files are served
The API key never reaches a response.
"""

from __future__ import annotations

import re
import uuid
from typing import Annotated

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from reforge.capture.pose import focal_35mm_from_exif
from reforge.config import REPO_ROOT, Settings, get_settings
from reforge.errors import ReforgeError

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 40_000_000
JOB_ID = re.compile(r"^[a-f0-9]{12}$")
OUTPUTS = {
    "model.stl": "model/stl",
    "model.scad": "text/plain; charset=utf-8",
    "spec.json": "application/json",
    "report.json": "application/json",
    "overlay.png": "image/png",
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


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    jobs_dir = settings.reforge_data_dir / "jobs"
    app = FastAPI(title="RE-FORGE AI", version="0.1.0")

    @app.exception_handler(ReforgeError)
    async def _typed_error(_, exc: ReforgeError) -> JSONResponse:
        status = 413 if exc.code == "UPLOAD_TOO_LARGE" else 422
        return JSONResponse({"error": exc.to_dict()}, status_code=status)

    @app.get("/api/health")
    async def health() -> dict:
        key = settings.meta_model_api_key
        return {"ok": True, "meta_key_configured": bool(key and key.get_secret_value().strip()),
                "segmentation_model": settings.reforge_model_segmentation}

    @app.get("/api/mat/{page}.pdf")
    async def mat(page: str) -> FileResponse:
        if page not in ("A4", "Letter"):
            raise HTTPException(404)
        return FileResponse(REPO_ROOT / "assets" / "mat" / f"reforge-mat-{page}-v1.pdf", media_type="application/pdf",
                            filename=f"reforge-mat-{page}-v1.pdf")

    @app.post("/api/jobs")
    async def create_job(
        photo: Annotated[UploadFile, File()],
        thickness_mm: Annotated[float, Form(gt=0.4, le=200)],
        bar_x_mm: Annotated[float | None, Form()] = None,
        bar_y_mm: Annotated[float | None, Form()] = None,
        segmenter: Annotated[str, Form(pattern="^(sam|classical)$")] = "sam",
        prompt: Annotated[str, Form(max_length=60)] = "plastic part",
    ) -> dict:
        from reforge.pipeline import photo_to_stl
        from reforge.vision.segment import ClassicalSegmenter, SamSegmenter

        data = await photo.read(MAX_UPLOAD_BYTES + 1)
        image = _decode_upload(data)
        focal_35mm = focal_35mm_from_exif(data)  # the only metadata kept: the height correction needs it
        job_id = uuid.uuid4().hex[:12]
        job_dir = jobs_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=False)
        input_path = job_dir / "input.png"
        cv2.imwrite(str(input_path), image)  # re-encoded: no EXIF/GPS survives
        if segmenter == "sam":
            from reforge.meta_api.client import MetaClient

            seg = SamSegmenter(MetaClient(settings), prompt=prompt.strip() or "plastic part", job_id=job_id)
        else:
            seg = ClassicalSegmenter()
        report = await photo_to_stl(input_path, job_dir, thickness_mm, seg, bar_x_mm=bar_x_mm, bar_y_mm=bar_y_mm,
                                    job_id=job_id, focal_35mm=focal_35mm)
        return {"job_id": job_id, "report": report,
                "files": {name: f"/api/jobs/{job_id}/{name}" for name in OUTPUTS}}

    @app.get("/api/jobs/{job_id}/{name}")
    async def job_file(job_id: str, name: str) -> FileResponse:
        if not JOB_ID.fullmatch(job_id) or name not in OUTPUTS:
            raise HTTPException(404)
        path = jobs_dir / job_id / name
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path, media_type=OUTPUTS[name], filename=f"reforge-{job_id}-{name}")

    dist = REPO_ROOT / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="ui")
    return app


def main() -> None:
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=8000)

