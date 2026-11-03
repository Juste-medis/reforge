import type { ApiErrorBody, Health, JobOptions, JobStatus, Sample } from "./types";

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

/** A model file, optionally rebuilt by the server with a printer compensation (the spec is re-validated). */
export function modelUrl(base: string, holeOffset: number): string {
  if (!holeOffset) return base;
  return `${base}?hole_offset_mm=${holeOffset.toFixed(2)}`;
}
