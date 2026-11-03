import { startJob, type JobSource } from "../api";
import type { Health, JobOptions } from "../types";
import { remember } from "./history";
import { go } from "./route";

// Object URLs of photos chosen in this tab, so the progress view can show the photo while it is analysed.
const previews = new Map<string, string>();
export const previewFor = (jobId: string): string | undefined => previews.get(jobId);

export function defaultAi(health: Health | null | undefined): Pick<JobOptions, "segmenter" | "interpreter"> {
  const ai = !!health?.meta_key_configured;
  return { segmenter: ai ? "sam" : "classical", interpreter: ai ? "spark" : "geometric" };
}

export async function launch(source: JobSource, options: JobOptions, title: string, preview?: string): Promise<string> {
  const id = await startJob(source, options);
  if (preview) previews.set(id, preview);
  remember({ id, createdAt: new Date().toISOString(), title, sample: "sample" in source ? source.sample : undefined, state: "running" });
  go({ name: "job", id });
  return id;
}
