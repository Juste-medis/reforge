// Mirrors backend/reforge/pipeline.py (report.json) and backend/reforge/api/app.py (job status, samples).

export type Status = "MEASURED" | "OBSERVED" | "INFERRED" | "UNCERTAIN";

export interface Issue {
  code: string;
  message: string;
}

export interface Calibration {
  mode?: "mat" | "ruler"; // absent on reports from before ruler mode: they are mat jobs
  page: string;
  markers: number;
  known_length_mm?: number | null;
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

export interface VerificationNote {
  code: string;
  message: string;
  level: "info" | "warning" | "rejected";
}

export interface PartAnalysis {
  object_name: string;
  family: string;
  family_reason: string;
  is_broken: boolean;
  fracture_segment_ids: string[];
  fracture_reason: string;
  symmetry: string;
  mirror_axis_id: string;
  symmetry_reason: string;
  holes: { hole_id: string; role: string }[];
  missing_features: { description: string; near_segment_ids: string[] }[];
  required_measurements: { kind: string; target_id: string; why: string }[];
}

export interface Axis {
  id: string;
  angle_deg: number;
  point_mm?: [number, number];
  support: number;
  holes_matched: number;
  holes_contradicting: number;
  outline_confirming_mm: number;
  offset_ambiguity_mm: number | null;
}

export interface Completion {
  axis: string;
  added_area_mm2: number;
  inferred_u_mm_2sigma: number;
  inferred_outline_mm: number;
  confirmed_mm: number;
  extent_mm: [number, number];
  regions: { area_mm2: number; filled: boolean; echo: boolean; reason: string }[];
  inferred_holes: { from: string; center_mm: [number, number]; diameter_mm: number }[];
  runs: { status: string; source: string; length_mm: number }[];
}

export interface Reconstruction {
  interpretation: {
    method: string;
    is_ai: boolean;
    latency_s: number;
    cost_usd: number;
    fallback_reason: { code: string; message: string; hint: string | null } | null;
    detail: Record<string, unknown>;
    analysis: PartAnalysis;
  };
  verification: VerificationNote[];
  segments: { id: string; kind: string; length_mm: number; pieces: number; fit_rms_mm: number }[];
  axes: Axis[];
  completion: Completion | null;
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
  status: Status;
  diameter_mm?: number;
  diameter_u_mm?: number | null;
  center_mm?: [number, number];
  source?: string;
}

export interface ExcludedCandidate {
  hole: string;
  reason: string;
  status: string;
}

export interface Part {
  overall_mm: [number, number, number];
  overall_status: Status;
  size_mm: { length: number; width: number; thickness: number; angle_deg: number; basis: string };
  holes: Hole[];
  excluded_candidates: ExcludedCandidate[];
  unresolved: string[];
}

export interface Term {
  name: string;
  sigma_mm: number;
  basis: string;
}

export interface Dimension {
  id: string;
  label: string;
  value_mm: number | null;
  status: Status;
  u_mm: number | null;
  dominant: string | null;
  terms: Term[];
  note?: string;
}

export interface Confidence {
  note: string;
  budget: {
    calibration_mm: number;
    calibration_basis: string;
    scale_rel: number;
    scale_checked: boolean;
    scale_basis: string;
    edge_mm: number;
    edge_basis: string;
    height_mm: number;
    bars_checked: number;
  };
  dimensions: Dimension[];
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

export interface ArtifactRow {
  check: string;
  status: "pass" | "warn" | "fail";
  detail: string;
}

export interface Artifact {
  artifact_status: "verified" | "needs_review" | "failed";
  reasons: string[];
  rows: ArtifactRow[];
  files: Record<string, string | null>;
  photo_sha256: string | null;
  validated_at: string;
}

export interface Replay {
  measured_area_mm2: number;
  built_area_mm2: number;
  coverage: number;
  iou: number;
  note: string;
}

export interface Report {
  job_id: string;
  photo: string;
  /** Optional: reports written before the artifact verdict don't have these. */
  photo_sha256?: string | null;
  artifact?: Artifact;
  replay?: Replay;
  milestone: string;
  calibration: Calibration;
  segmentation: Segmentation;
  refinement: Refinement;
  pose: Pose;
  height_correction: HeightCorrection;
  reconstruction: Reconstruction;
  part: Part;
  confidence: Confidence;
  texture?: {
    image: string;
    size_px: [number, number];
    u: [number, number, number];
    v: [number, number, number];
    photographed_outline_mm: [number, number][];
    colour_hex: string;
  };
  validation: Validation;
  timings_s: Record<string, number>;
  outputs: string[];
  disclaimer: string;
  reshaped?: {
    from_job: string;
    guidance_carried: Record<string, unknown>;
    fracture_carried: string[];
    fracture_from: string;
    exclude_carried: string[];
    guidance_dropped: Record<string, unknown>;
    edited_points: number;
    edit_max_mm: number;
    edit_mean_mm: number;
    moved_points: number;
    max_move_mm: number;
    mean_move_mm: number;
    holes_dropped: string[];
  } | null;
}

export type Files = Record<string, string>;

export interface Credit {
  title: string;
  author: string;
  licence: string;
  licence_url: string;
  page: string;
}

export interface Sample {
  id: string;
  title: string;
  story: string;
  thickness_mm: number;
  kind: "synthetic" | "photograph";
  /** A rendered part with no source photo; otherwise a real photo of a real part, composited onto the mat —
   * or "photograph" for a real photo with a stored Studio session (no mat, ruler-scaled). */
  rendered?: boolean;
  credit?: Credit;
  provided_by?: string;
  label: string;
  image_url: string;
  thumb_url: string;
  truth: {
    basis: string;
    /** False when the truth shares a ruler assumption with the photo instead of being known exactly. */
    exact?: boolean;
    length_mm: number;
    width_mm: number;
    holes: { diameter_mm?: number; slot_mm?: [number, number]; shape?: string; count: number }[];
    photographed: string;
  };
}

export interface StageState {
  id: string;
  state: "pending" | "running" | "done" | "stopped";
  seconds: number | null;
}

export interface JobRequest {
  created_at?: string;
  image_size?: [number, number] | null;
  sample?: string | null;
  from_job?: string | null;
  thickness_mm?: number;
  bar_x_mm?: number | null;
  bar_y_mm?: number | null;
  segmenter?: "sam" | "classical";
  prompt?: string;
  interpreter?: "spark" | "geometric";
  focal_35mm?: number | null;
  known_length_mm?: number | null;
  deskew_px_per_mm?: number | null;
  guide_axis?: string | null;
  guide_fracture?: string | null;
  guide_exclude?: string | null;
  guide_damage?: string | null;
  guide_sources?: string | null;
  guide_assert_angle?: number | null;
  guide_assert_x_mm?: number | null;
  guide_assert_y_mm?: number | null;
  guide_family_override?: boolean | null;
  guide_note?: string | null;
  sample_info?: Sample;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  hint: string | null;
  job_id?: string; // the job folder that kept the request and this error
}

export interface AllHole {
  id: string;
  kind: "circle" | "traced";
  area_mm2: number;
  centre_mm: [number, number];
  doubted: boolean;
}

/** reconstruction.json: the Studio's candidates, on success and on refusals alike. */
export interface ReconstructionDoc extends Reconstruction {
  refused: string | null;
  all_holes: AllHole[];
}

export interface FeedbackEntry {
  created_at: string;
  verdict: "ok" | "wrong";
  note: string;
}

export interface JobStatus {
  job_id: string;
  state: "queued" | "running" | "done" | "failed" | "interrupted";
  request: JobRequest;
  stages: StageState[];
  elapsed_s: number | null;
  result?: { report: Report; files: Files };
  files?: Files;
  reconstruction?: ReconstructionDoc;
  feedback?: FeedbackEntry[];
  error?: ApiErrorBody;
}

export interface Health {
  ok: boolean;
  meta_key_configured: boolean;
  segmentation_model: string;
  reasoning_model: string;
  busy: boolean;
  ai_budget?: { cap_usd: number; spent_today_usd: number };
}

export interface GuideOptions {
  axis?: string;
  fracture?: string[];
  /** Designed-asymmetry spans: kept as photographed, their mirror never counts. */
  exclude?: string[];
  damage?: string[];
  /** Exactly these holes get built; undefined (or empty) = automatic. */
  sources?: string[];
  assert_angle?: number;
  assert_x_mm?: number;
  assert_y_mm?: number;
  family_override?: boolean;
  note?: string;
}

export interface JobOptions {
  thickness_mm: number;
  bar_x_mm?: number;
  bar_y_mm?: number;
  known_length_mm?: number;
  deskew_px_per_mm?: number;
  segmenter: "sam" | "classical";
  interpreter: "spark" | "geometric";
  prompt: string;
  guide?: GuideOptions;
}

export interface DeskewResult {
  png_b64: string;
  px_per_mm: number;
  length_mm: number;
  width_mm: number;
  margin_px: [number, number];
  corners_used: [number, number][];
}
