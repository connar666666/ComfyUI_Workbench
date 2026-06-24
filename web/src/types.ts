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
  started_at?: string | null;
  completed_at?: string | null;
  error_message?: string | null;
  error_code?: string | null;
  created_by_username?: string;
  created_by?: number;
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
