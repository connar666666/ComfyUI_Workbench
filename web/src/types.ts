export type User = {
  id: number;
  username: string;
  display_name: string;
  role: "admin" | "member";
};

export type Asset = {
  id: number;
  kind: "image" | "audio" | "video" | "document";
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  created_at: string;
  uploaded_by_username?: string;
};

export type Job = {
  id: number;
  status: "queued" | "running" | "succeeded" | "failed" | "canceled";
  prompt: string;
  duration_sec: number;
  resolution: string;
  created_at: string;
  canvas_id?: string | null;
  canvas_node_id?: string | null;
  canvas_version_id?: number | null;
  output_video_id?: number | null;
  started_at?: string | null;
  completed_at?: string | null;
  error_message?: string | null;
  error_code?: string | null;
  created_by_username?: string;
  created_by?: number;
};

export type NodeVersion = {
  id: number;
  canvas_id: string;
  node_id: string;
  generation_job_id: number;
  output_video_id?: number | null;
  version_number: number;
  prompt: string;
  status: Job["status"];
  created_by: number;
  created_at: string;
};

export type Video = {
  id: number;
  source_job_id: number;
  created_by: number;
  created_by_username?: string;
  title: string;
  storage_key: string;
  thumbnail_storage_key?: string | null;
  mime_type: string;
  size_bytes: number;
  duration_sec?: number | null;
  width?: number | null;
  height?: number | null;
  prompt: string;
  created_at: string;
};

export type QueueStatus = {
  running: Array<{
    prompt_id: string;
    queue_position: number;
    raw: unknown;
  }>;
  pending: Array<{
    prompt_id: string;
    queue_position: number;
    raw: unknown;
  }>;
};

export type SSEEvent = {
  type: string;
  data: Record<string, unknown>;
  timestamp: string;
};
