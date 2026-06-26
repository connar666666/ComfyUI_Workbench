export type User = {
  id: number;
  username: string;
  display_name: string;
  role: "admin" | "member";
};

export type Asset = {
  id: number;
  project_id?: number | null;
  folder_id?: number | null;
  kind: "image" | "audio" | "video" | "document";
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  created_at: string;
  uploaded_by_username?: string;
};

export type AssetFolder = {
  id: number;
  name: string;
  parent_id: number | null;
  scope: "assets" | "videos";
  asset_count: number;
  created_by?: number | null;
  created_at: string;
  updated_at?: string;
};

export type ProjectRole = "owner" | "editor" | "viewer";

export type ProjectMember = {
  project_id: number;
  user_id: number;
  role: ProjectRole;
  username: string;
  display_name: string;
};

export type Project = {
  id: number;
  name: string;
  description: string;
  current_user_role?: ProjectRole;
  member_count?: number;
  members?: ProjectMember[];
  created_at?: string;
  updated_at?: string;
};

export type ProjectWorkflow = {
  id: number;
  project_id: number;
  workflow_id: string;
  display_name?: string | null;
  defaults: Record<string, unknown>;
  enabled: boolean;
};

export type ProjectRemoteRun = {
  id: number;
  project_id: number;
  workflow_id: string;
  prompt_id?: string | null;
  status: Job["status"];
  saved_asset_ids: number[];
  results?: RemoteWorkflowResultItem[];
};

export type ProjectHistoryItem = {
  id: number;
  type: "local_generation" | "remote_workflow";
  status: Job["status"];
  title: string;
  created_at: string;
  updated_at?: string;
  completed_at?: string | null;
  created_by_username?: string;
  result_asset_ids?: number[];
  remote_results?: RemoteWorkflowResultItem[];
  error_message?: string | null;
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

export type RemoteWorkflowSummary = {
  id: string;
  name: string;
  mtime?: string;
  run_count?: number;
  last_run_at?: string;
  last_prompt_id?: string;
};

export type RemoteWorkflowTemplate = Record<
  string,
  {
    class_type?: string;
    inputs?: Record<string, unknown>;
  }
>;

export type RemoteWorkflowApiConfig = {
  enabledParams?: Record<string, boolean>;
  formValues?: Record<string, unknown>;
  customLabels?: Record<string, string>;
};

export type RemoteWorkflowDetail = {
  workflow_id: string;
  workflow_template: RemoteWorkflowTemplate;
  api_config: RemoteWorkflowApiConfig;
};

export type RemoteWorkflowRun = {
  prompt_id: string;
};

export type RemoteWorkflowResultItem = {
  type?: string;
  url?: string;
  download_url?: string;
  filename?: string;
  text?: string;
};

export type RemoteWorkflowResult = {
  prompt_id: string;
  pending: boolean;
  results: RemoteWorkflowResultItem[];
};

export type RemoteWorkflowUpload = {
  name: string;
  subfolder?: string;
  type?: string;
};

export type SSEEvent = {
  type: string;
  data: Record<string, unknown>;
  timestamp: string;
};
