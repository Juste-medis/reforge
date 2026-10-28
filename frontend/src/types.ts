// Mirrors backend/reforge/pipeline.py report.json (M1). To be generated from OpenAPI in a later milestone.

export interface Issue {
  code: string;
  message: string;
}

export interface Calibration {
  page: string;
  markers: number;
  fit_rms_mm: number;
  loo_rms_mm: number | null;
  px_per_mm: number;
  perspective_ratio: number;
  scale_correction: [number, number];
  corner_bias_px: number;
  warnings: Issue[];
}

export interface Pose {
  focal_source: "exif+homography" | "exif" | "homography" | "prior";
  focal_px: number;
  focal_35mm: number;
  focal_rel_sigma: number;
  exif_focal_35mm: number | null;
  camera_height_mm: number;
  camera_height_sigma_mm: number;
  nadir_mm: [number, number];
  nadir_sigma_mm: number;
  warnings: Issue[];
}

export interface HeightCorrection {
  magnification: number;
  photographed_extent_mm: [number, number];
  footprint_extent_mm: [number, number];
  max_shift_mm: number;
  u_persp_mm_2sigma: number;
  occlusion_bound_mm: number;
}

export interface Segmentation {
  method: string;
  is_ai: boolean;
  confidence: number | null;
  latency_s: number;
  cost_usd: number;
  detail: Record<string, unknown>;
}

export interface Refinement {
  refined: boolean;
  contrast_delta_e: number;
  band_mm: number;
  coarse_shift_mean_mm: number;
  coarse_shift_max_mm: number;
  edge_sigma_mm: number | null;
  warnings: Issue[];
}

export interface Hole {
  id: string;
  kind: "circle" | "polygon";
  diameter_mm?: number;
  center_mm?: [number, number];
  source?: string;
}

export interface Part {
  overall_mm: [number, number, number];
  holes: Hole[];
  excluded_candidates: { hole: string; reason: string; status: string }[];
  unresolved: string[];
}

export interface Check {
  name: string;
  passed: boolean;
  detail: string;
  severity: "error" | "warning";
}

export interface Validation {
  valid: boolean;
  errors: string[];
  warnings: string[];
  checks: Check[];
}

export interface Report {
  job_id: string;
  photo: string;
  milestone: string;
  calibration: Calibration;
  segmentation: Segmentation;
  refinement: Refinement;
  pose: Pose;
  height_correction: HeightCorrection;
  part: Part;
  validation: Validation;
  timings_s: Record<string, number>;
  outputs: string[];
  disclaimer: string;
}

export interface JobResponse {
  job_id: string;
  report: Report;
  files: Record<string, string>;
}

export interface Health {
  ok: boolean;
  meta_key_configured: boolean;
  segmentation_model: string;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  hint: string | null;
}
