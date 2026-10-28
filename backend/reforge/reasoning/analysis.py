"""The PartAnalysis contract between the reasoning model and the geometry: a per-request JSON schema and its validation.

The schema's enums hold only the marks present in that request (S…, A…, H…), so the model cannot refer to a segment,
axis or hole that doesn't exist. It stays inside the strict subset verified live on 2026-10-27: every object has
``additionalProperties: false`` and lists every key as required, with no anyOf/allOf/oneOf. The answer is untrusted
data: it's validated again here (ids, lengths), then checked against the geometry (``reasoning.verify``).
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, ValidationInfo, field_validator

from reforge.errors import ReforgeError

FAMILIES = ("extruded_profile", "revolved", "multi_view", "unsupported")
SYMMETRY_KINDS = ("mirror", "rotational", "none", "unsure")
HOLE_ROLES = ("mounting", "locating", "clearance", "unknown")
MEASUREMENT_KINDS = ("thickness", "overall_length", "overall_width", "hole_diameter", "hole_spacing",
                     "fracture_region", "other")
NONE_ID = "none"
MAX_TEXT = 300
MAX_MISSING = 6
MAX_MEASUREMENTS = 8


def _obj(properties: dict) -> dict:
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def build_schema(seg_ids: list[str], axis_ids: list[str], hole_ids: list[str]) -> dict:
    text = {"type": "string"}
    segs = {"type": "string", "enum": list(seg_ids)}
    holes = {"type": "string", "enum": list(hole_ids) or [NONE_ID]}
    return _obj({
        "object_name": text,
        "family": {"type": "string", "enum": list(FAMILIES)},
        "family_reason": text,
        "is_broken": {"type": "boolean"},
        "fracture_segment_ids": {"type": "array", "items": segs, "maxItems": len(seg_ids)},
        "fracture_reason": text,
        "symmetry": {"type": "string", "enum": list(SYMMETRY_KINDS)},
        "mirror_axis_id": {"type": "string", "enum": [*axis_ids, NONE_ID]},
        "symmetry_reason": text,
        "holes": {"type": "array", "maxItems": max(len(hole_ids), 1),
                  "items": _obj({"hole_id": holes, "role": {"type": "string", "enum": list(HOLE_ROLES)}})},
        "missing_features": {"type": "array", "maxItems": MAX_MISSING,
                             "items": _obj({"description": text,
                                            "near_segment_ids": {"type": "array", "items": segs, "maxItems": 6}})},
        "required_measurements": {"type": "array", "maxItems": MAX_MEASUREMENTS,
                                  "items": _obj({"kind": {"type": "string", "enum": list(MEASUREMENT_KINDS)},
                                                 "target_id": {"type": "string",
                                                               "enum": [*hole_ids, *seg_ids, NONE_ID]},
                                                 "why": text})},
    })


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _clip(value: object) -> object:
    return value.strip()[:MAX_TEXT] if isinstance(value, str) else value


def _allowed(info: ValidationInfo, key: str) -> set[str]:
    return set((info.context or {}).get(key, ()))


class HoleRole(_Strict):
    hole_id: str
    role: Literal["mounting", "locating", "clearance", "unknown"]

    @field_validator("hole_id")
    @classmethod
    def _known(cls, v: str, info: ValidationInfo) -> str:
        if v not in _allowed(info, "hole_ids"):
            raise ValueError(f"unknown hole id {v!r}")
        return v


class MissingFeature(_Strict):
    description: str = Field(max_length=MAX_TEXT)
    near_segment_ids: tuple[str, ...] = Field(max_length=6)

    _clip_description = field_validator("description", mode="before")(lambda cls, v: _clip(v))

    @field_validator("near_segment_ids")
    @classmethod
    def _known(cls, v: tuple[str, ...], info: ValidationInfo) -> tuple[str, ...]:
        unknown = set(v) - _allowed(info, "seg_ids")
        if unknown:
            raise ValueError(f"unknown segment ids {sorted(unknown)}")
        return tuple(dict.fromkeys(v))


class MeasurementRequest(_Strict):
    kind: Literal["thickness", "overall_length", "overall_width", "hole_diameter", "hole_spacing", "fracture_region",
                  "other"]
    target_id: str
    why: str = Field(max_length=MAX_TEXT)

    _clip_why = field_validator("why", mode="before")(lambda cls, v: _clip(v))

    @field_validator("target_id")
    @classmethod
    def _known(cls, v: str, info: ValidationInfo) -> str:
        if v != NONE_ID and v not in _allowed(info, "hole_ids") | _allowed(info, "seg_ids"):
            raise ValueError(f"unknown target id {v!r}")
        return v


class PartAnalysis(_Strict):
    object_name: str = Field(max_length=MAX_TEXT)
    family: Literal["extruded_profile", "revolved", "multi_view", "unsupported"]
    family_reason: str = Field(max_length=MAX_TEXT)
    is_broken: bool
    fracture_segment_ids: tuple[str, ...]
    fracture_reason: str = Field(max_length=MAX_TEXT)
    symmetry: Literal["mirror", "rotational", "none", "unsure"]
    mirror_axis_id: str
    symmetry_reason: str = Field(max_length=MAX_TEXT)
    holes: tuple[HoleRole, ...]
    missing_features: tuple[MissingFeature, ...] = Field(max_length=MAX_MISSING)
    required_measurements: tuple[MeasurementRequest, ...] = Field(max_length=MAX_MEASUREMENTS)

    _clip_text = field_validator("object_name", "family_reason", "fracture_reason", "symmetry_reason",
                                 mode="before")(lambda cls, v: _clip(v))

    @field_validator("fracture_segment_ids")
    @classmethod
    def _known_segments(cls, v: tuple[str, ...], info: ValidationInfo) -> tuple[str, ...]:
        unknown = set(v) - _allowed(info, "seg_ids")
        if unknown:
            raise ValueError(f"unknown segment ids {sorted(unknown)}")
        return tuple(dict.fromkeys(v))

    @field_validator("mirror_axis_id")
    @classmethod
    def _known_axis(cls, v: str, info: ValidationInfo) -> str:
        if v != NONE_ID and v not in _allowed(info, "axis_ids"):
            raise ValueError(f"unknown axis id {v!r}")
        return v

    @field_validator("holes")
    @classmethod
    def _one_role_per_hole(cls, v: tuple[HoleRole, ...]) -> tuple[HoleRole, ...]:
        seen: dict[str, HoleRole] = {}
        for h in v:
            seen.setdefault(h.hole_id, h)
        return tuple(seen.values())


def parse_analysis(content: str | dict, seg_ids: list[str], axis_ids: list[str], hole_ids: list[str]) -> PartAnalysis:
    """Validate a model answer against this request's marks. Raises ``INTERPRETATION_INVALID``."""
    try:
        data = json.loads(content) if isinstance(content, str) else content
        holes = [h for h in data.get("holes", []) if h.get("hole_id") != NONE_ID] if isinstance(data, dict) else []
        if isinstance(data, dict):
            data = {**data, "holes": holes}
        return PartAnalysis.model_validate(data, context={"seg_ids": seg_ids, "axis_ids": axis_ids,
                                                          "hole_ids": hole_ids})
    except (json.JSONDecodeError, ValidationError, AttributeError, TypeError) as exc:
        raise ReforgeError("INTERPRETATION_INVALID", f"The reasoning model's answer failed validation: {exc}"[:500],
                           "The reconstruction falls back to geometry only.") from exc
