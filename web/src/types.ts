export type Asset = {
  id: number;
  kind: "image" | "audio" | "video" | "document";
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  created_at: string;
};

export type Job = {
  id: number;
  status: "queued" | "running" | "succeeded" | "failed" | "canceled";
  prompt: string;
  duration_sec: number;
  resolution: string;
  created_at: string;
  error_message?: string | null;
};
