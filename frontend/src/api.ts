import type { ApiErrorBody, Health, JobResponse } from "./types";

export class ApiError extends Error {
  constructor(public body: ApiErrorBody) {
    super(`${body.code}: ${body.message}`);
  }
}

async function parseError(response: Response): Promise<ApiError> {
  try {
    const data = await response.json();
    if (data?.error?.code) return new ApiError(data.error as ApiErrorBody);
    if (Array.isArray(data?.detail)) {
      const message = data.detail.map((d: { loc?: string[]; msg?: string }) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`).join("; ");
      return new ApiError({ code: "REQUEST_INVALID", message, hint: "Check the highlighted inputs." });
    }
  } catch {
    // fall through to the generic error below
  }
  return new ApiError({ code: `HTTP_${response.status}`, message: response.statusText || "Request failed", hint: null });
}

export async function getHealth(): Promise<Health> {
  const response = await fetch("/api/health");
  if (!response.ok) throw await parseError(response);
  return response.json();
}

export async function runJob(form: FormData): Promise<JobResponse> {
  const response = await fetch("/api/jobs", { method: "POST", body: form });
  if (!response.ok) throw await parseError(response);
  return response.json();
}
