"""Helpers to build PartSpec test data (plain dicts, as an API client or AI proposal would send)."""

from __future__ import annotations

import numpy as np
from shapely.geometry import Polygon, box
from shapely.geometry.polygon import orient


def param(value: float, status: str = "OBSERVED", unc: float | None = None) -> dict:
    return {"value": value, "status": status, "uncertainty_mm": unc, "evidence": []}


def rounded_rect(w: float, h: float, r: float) -> Polygon:
    return orient(box(-w / 2, -h / 2, w / 2, h / 2).buffer(-r, quad_segs=16).buffer(r, quad_segs=16), 1.0)


def spec_dict(outline: Polygon | np.ndarray, holes: list[tuple[str, float, float, float]] = (),
              thickness: float = 3.0, **extra) -> dict:
    pts = np.asarray(outline.exterior.coords)[:-1] if isinstance(outline, Polygon) else np.asarray(outline)
    data = {
        "outline": {"points": [tuple(p) for p in pts.tolist()],
                    "runs": [{"start": 0, "end": len(pts) - 1, "status": "OBSERVED", "source": "test"}]},
        "holes": [{"kind": "circle", "id": hid, "center_x": param(x), "center_y": param(y), "diameter": param(d)}
                  for hid, x, y, d in holes],
        "thickness": param(thickness, "MEASURED", 0.02),
    }
    data.update(extra)
    return data


def bracket_dict(**kw) -> dict:
    return spec_dict(rounded_rect(80, 28, 4), [("H0", -30, 0, 4.2), ("H1", 30, 0, 4.2)], **kw)
