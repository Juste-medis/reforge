import type { ApiErrorBody, DeskewResult, Health, JobOptions, JobStatus, Sample } from "./types";

export class ApiError extends Error {
  constructor(public body: ApiErrorBody, public status = 0) {
    super(`${body.code}: ${body.message}`);
  }
}

async function parseError(response: Response): Promise<ApiError> {
  try {
    const data = await response.json();
    if (data?.error?.code) {
      return new ApiError({ ...(data.error as ApiErrorBody), job_id: data.job_id ?? undefined }, response.status);
    }
    if (Array.isArray(data?.detail)) {
      const message = data.detail
        .map((d: { loc?: string[]; msg?: string }) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`)
        .join("; ");
      return new ApiError({ code: "REQUEST_INVALID", message, hint: "Check the values you entered." }, response.status);
    }
  } catch {
    // fall through to the generic error below
  }
  return new ApiError(
    { code: `HTTP_${response.status}`, message: response.statusText || "Request failed", hint: null },
    response.status,
  );
}

async function getJson<T>(url: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, { headers: { Accept: "application/json" } });
  } catch {
    throw new ApiError({ code: "NETWORK", message: "The Re-Forge server can't be reached.", hint: null });
  }
  if (!response.ok) throw await parseError(response);
  return response.json() as Promise<T>;
}

export const getHealth = () => getJson<Health>("/api/health");
export const getSamples = () => getJson<Sample[]>("/api/samples");
export const getJob = (id: string) => getJson<JobStatus>(`/api/jobs/${encodeURIComponent(id)}`);

export type JobSource = { photo: File } | { sample: string } | { fromJob: string };

/** Starts a background job and returns its id; progress then comes from `getJob`. */
export async function startJob(source: JobSource, options: JobOptions): Promise<string> {
  const form = new FormData();
  if ("photo" in source) form.append("photo", source.photo);
  if ("sample" in source) form.append("sample", source.sample);
  if ("fromJob" in source) form.append("from_job", source.fromJob);
  form.append("thickness_mm", String(options.thickness_mm));
  if (options.bar_x_mm !== undefined) form.append("bar_x_mm", String(options.bar_x_mm));
  if (options.bar_y_mm !== undefined) form.append("bar_y_mm", String(options.bar_y_mm));
  if (options.known_length_mm !== undefined) form.append("known_length_mm", String(options.known_length_mm));
  if (options.deskew_px_per_mm !== undefined) form.append("deskew_px_per_mm", String(options.deskew_px_per_mm));
  const guide = options.guide;
  if (guide?.axis) form.append("guide_axis", guide.axis);
  if (guide?.fracture?.length) form.append("guide_fracture", guide.fracture.join(" "));
  if (guide?.exclude?.length) form.append("guide_exclude", guide.exclude.join(" "));
  if (guide?.damage?.length) form.append("guide_damage", guide.damage.join(" "));
  if (guide?.sources?.length) form.append("guide_sources", guide.sources.join(" "));
  if (guide?.assert_angle !== undefined) form.append("guide_assert_angle", String(guide.assert_angle));
  if (guide?.assert_x_mm !== undefined) form.append("guide_assert_x_mm", String(guide.assert_x_mm));
  if (guide?.assert_y_mm !== undefined) form.append("guide_assert_y_mm", String(guide.assert_y_mm));
  if (guide?.family_override) form.append("guide_family_override", "true");
  if (guide?.note?.trim()) form.append("guide_note", guide.note.trim().slice(0, 500));
  form.append("segmenter", options.segmenter);
  form.append("interpreter", options.interpreter);
  form.append("prompt", options.prompt);
  form.append("wait", "false");
  let response: Response;
  try {
    response = await fetch("/api/jobs", { method: "POST", body: form });
  } catch {
    throw new ApiError({ code: "NETWORK", message: "The Re-Forge server can't be reached.", hint: null });
  }
  if (!response.ok) throw await parseError(response);
  const body = (await response.json()) as { job_id: string };
  return body.job_id;
}

/** The Studio's "flatten" step: a perspective photo of a rectangular part back to top-down. */
export async function postDeskew(photo: File, corners: [number, number][], length_mm: number,
                                 width_mm: number): Promise<DeskewResult> {
  const form = new FormData();
  form.append("photo", photo);
  form.append("corners", JSON.stringify(corners));
  form.append("length_mm", String(length_mm));
  form.append("width_mm", String(width_mm));
  let response: Response;
  try {
    response = await fetch("/api/deskew", { method: "POST", body: form });
  } catch {
    throw new ApiError({ code: "NETWORK", message: "The Re-Forge server can't be reached.", hint: null });
  }
  if (!response.ok) throw await parseError(response);
  return response.json() as Promise<DeskewResult>;
}

/** Human-in-the-loop: was this result right? Stored on the job. */
export async function postReshape(jobId: string, outlinePx: number[][], baselinePx: number[][]): Promise<{ job_id: string; status_url: string }> {
  let response: Response;
  try {
    response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/reshape`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ outline_px: outlinePx, baseline_px: baselinePx }),
    });
  } catch {
    throw new ApiError({ code: "NETWORK", message: "The Re-Forge server can't be reached.", hint: null });
  }
  if (!response.ok) throw await parseError(response);
  return response.json() as Promise<{ job_id: string; status_url: string }>;
}

export async function postFeedback(jobId: string, verdict: "ok" | "wrong", note: string): Promise<{ ok: boolean; count: number }> {
  const form = new FormData();
  form.append("verdict", verdict);
  form.append("note", note);
  let response: Response;
  try {
    response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/feedback`, { method: "POST", body: form });
  } catch {
    throw new ApiError({ code: "NETWORK", message: "The Re-Forge server can't be reached.", hint: null });
  }
  if (!response.ok) throw await parseError(response);
  return response.json() as Promise<{ ok: boolean; count: number }>;
}

/** A model file, optionally rebuilt by the server with a printer compensation (the spec is re-validated). */
export function modelUrl(base: string, holeOffset: number): string {
  if (!holeOffset) return base;
  return `${base}?hole_offset_mm=${holeOffset.toFixed(2)}`;
}
