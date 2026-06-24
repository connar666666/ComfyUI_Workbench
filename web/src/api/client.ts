import type { Asset, Job } from "../types";

export async function listAssets(): Promise<Asset[]> {
  const response = await fetch("/api/assets");
  if (!response.ok) throw new Error("Failed to load assets");
  return response.json();
}

export async function listJobs(): Promise<Job[]> {
  const response = await fetch("/api/jobs");
  if (!response.ok) throw new Error("Failed to load jobs");
  return response.json();
}

export async function createJob(payload: {
  prompt: string;
  duration_sec: number;
  resolution: string;
  audio_start_sec: number;
  reference_image_asset_id?: number | null;
  reference_audio_asset_id?: number | null;
}): Promise<Job> {
  const response = await fetch("/api/jobs", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-workbench-user": "local-user",
      "x-workbench-user-id": "1",
      "x-workbench-role": "admin"
    },
    body: JSON.stringify(payload)
  });
  if (!response.ok) throw new Error("Failed to create job");
  return response.json();
}
