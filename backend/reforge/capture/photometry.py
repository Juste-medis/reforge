"""sRGB ↔ linear light (IEC 61966-2-1).

Optics blur light and sensor pixels integrate light, so resampling, compositing and edge models must work in
linear light. JPEG and PNG values are sRGB-encoded. Thresholding encoded values half-way between paper and part
puts a dark part's edge 0.4–1.1 px inside the true edge (simulated 2026-10-27, `docs/EVALUATION.md`).

Phone tone curves only approximate sRGB; the residual is an edge uncertainty, not something this module removes.
"""

from __future__ import annotations

import numpy as np


def _decode(v: np.ndarray) -> np.ndarray:
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


_DECODE_LUT = _decode(np.arange(256, dtype=np.float64) / 255.0).astype(np.float32)


def srgb_to_linear(image: np.ndarray) -> np.ndarray:
    """uint8 sRGB values → float32 linear light in [0, 1]."""
    image = np.asarray(image)
    if image.dtype != np.uint8:
        raise TypeError(f"srgb_to_linear expects uint8 sRGB values, got {image.dtype}")
    return _DECODE_LUT[image]


def linear_to_srgb(linear: np.ndarray) -> np.ndarray:
    """Linear light (any float array, clipped to [0, 1]) → uint8 sRGB values, rounded."""
    y = np.clip(np.asarray(linear, dtype=np.float32), 0.0, 1.0)
    v = np.where(y <= 0.0031308, 12.92 * y, 1.055 * np.power(y, np.float32(1 / 2.4)) - 0.055)
    return np.clip(np.round(v * 255.0), 0, 255).astype(np.uint8)
