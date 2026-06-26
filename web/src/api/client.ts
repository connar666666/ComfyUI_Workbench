import type {
  Asset,
  Job,
  NodeVersion,
  QueueStatus,
  RemoteWorkflowDetail,
  RemoteWorkflowResult,
  RemoteWorkflowRun,
  RemoteWorkflowSummary,
  RemoteWorkflowUpload,
  User,
  Video,
} from "../types";

// ── Auth token helpers ──────────────────────────────────────────────────

function storage(): Storage | null {
  return typeof globalThis !== "undefined" && "localStorage" in globalThis ? globalThis.localStorage : null;
}

let _token: string | null = storage()?.getItem("workbench_token") ?? null;

export function setAuthToken(token: string | null) {
  _token = token;
  const store = storage();
  if (token) {
    store?.setItem("workbench_token", token);
  } else {
    store?.removeItem("workbench_token");
  }
}

export function getAuthToken(): string | null {
  return _token;
}

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (_token) {
    headers["Authorization"] = `Bearer ${_token}`;
  }
  return headers;
}

export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

function defaultAuthErrorMessage(status: number, fallback: string): string {
  if (status === 403) return "Invalid username or password";
  if (status === 409) return "Username is already taken";
  return fallback;
}

export async function readApiError(
  res: Response,
  fallbackMessage: string,
  useAuthDefaults: boolean = false
): Promise<ApiError> {
  let payload: Record<string, unknown> | null = null;
  let text = "";

  const contentType = res.headers.get("Content-Type") || "";
  if (contentType.includes("application/json")) {
    payload = await res.json().catch(() => null);
  } else {
    text = await res.text().catch(() => "");
    if (text) {
      try {
        payload = JSON.parse(text) as Record<string, unknown>;
      } catch {
        payload = null;
      }
    }
  }

  const messageFromPayload =
    typeof payload?.message === "string"
      ? payload.message
      : typeof payload?.detail === "string"
      ? payload.detail
      : text.trim();

  const message = messageFromPayload || (useAuthDefaults ? defaultAuthErrorMessage(res.status, fallbackMessage) : fallbackMessage);
  const code = typeof payload?.error === "string" ? payload.error : undefined;
  return new ApiError(message, res.status, code);
}

async function throwApiError(res: Response, fallbackMessage: string, useAuthDefaults: boolean = false): Promise<never> {
  throw await readApiError(res, fallbackMessage, useAuthDefaults);
}

// ── Auth ────────────────────────────────────────────────────────────────

export async function joinWithInvite(
  token: string,
  username: string,
  displayName?: string
): Promise<{ access_token: string; refresh_token: string; user: User }> {
  const res = await fetch("/api/auth/join", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, username, display_name: displayName }),
  });
  if (!res.ok) {
    await throwApiError(res, "Invalid invite link");
  }
  return res.json();
}

export async function register(
  username: string,
  password: string,
  displayName?: string
): Promise<{ access_token: string; refresh_token: string; user: User }> {
  const res = await fetch("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password, display_name: displayName }),
  });
  if (!res.ok) {
    await throwApiError(res, "Registration failed", true);
  }
  return res.json();
}

export async function login(
  username: string,
  password: string
): Promise<{ access_token: string; refresh_token: string; user: User }> {
  const res = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    await throwApiError(res, "Login failed", true);
  }
  return res.json();
}

export async function refreshToken(
  refreshTokenStr: string
): Promise<{ access_token: string; refresh_token: string; user: User }> {
  const res = await fetch("/api/auth/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshTokenStr }),
  });
  if (!res.ok) throw new Error("Session expired");
  return res.json();
}

export async function getMe(): Promise<User> {
  const res = await fetch("/api/auth/me", { headers: authHeaders() });
  if (!res.ok) throw new Error("Not authenticated");
  return res.json();
}

export async function createInvite(
  role: string = "member",
  maxUses?: number | null,
  expiresInDays: number = 7
): Promise<{ invite_link: string; token: string }> {
  const res = await fetch("/api/auth/invites", {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ role, max_uses: maxUses, expires_in_days: expiresInDays }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.message || "Failed to create invite");
  }
  return res.json();
}

// ── Assets ──────────────────────────────────────────────────────────────

export async function listAssets(kind?: string): Promise<Asset[]> {
  const params = kind ? `?kind=${encodeURIComponent(kind)}` : "";
  const res = await fetch(`/api/assets${params}`, { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to load assets");
  return res.json();
}

export async function uploadAsset(
  kind: string,
  file: File,
  folderId?: number
): Promise<Asset> {
  const form = new FormData();
  form.append("kind", kind);
  form.append("file", file);
  if (folderId) form.append("folder_id", String(folderId));

  const headers: Record<string, string> = {};
  if (_token) headers["Authorization"] = `Bearer ${_token}`;

  const res = await fetch("/api/assets", {
    method: "POST",
    headers,
    body: form,
  });
  if (!res.ok) throw new Error("Failed to upload asset");
  return res.json();
}

export function assetUrl(assetId: number): string {
  return `/files/assets/${assetId}`;
}

// ── Jobs ────────────────────────────────────────────────────────────────

export async function listJobs(): Promise<Job[]> {
  const res = await fetch("/api/jobs", { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to load jobs");
  return res.json();
}

export async function createJob(payload: {
  prompt: string;
  duration_sec: number;
  resolution: string;
  audio_start_sec: number;
  reference_image_asset_id?: number | null;
  reference_audio_asset_id?: number | null;
  canvas_id?: string | null;
  canvas_node_id?: string | null;
  canvas_version_id?: number | null;
}): Promise<Job> {
  const res = await fetch("/api/jobs", {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.message || "Failed to create job");
  }
  return res.json();
}

export async function cancelJob(jobId: number): Promise<Job> {
  const res = await fetch(`/api/jobs/${jobId}/cancel`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.message || "Failed to cancel job");
  }
  return res.json();
}

// ── Videos ──────────────────────────────────────────────────────────────

export async function listVideos(): Promise<Video[]> {
  const res = await fetch("/api/videos", { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to load videos");
  return res.json();
}

export function videoUrl(videoId: number): string {
  return `/files/videos/${videoId}`;
}

// ── ComfyUI Queue ───────────────────────────────────────────────────────

export async function getQueueStatus(): Promise<QueueStatus> {
  const res = await fetch("/api/comfyui/queue", { headers: authHeaders() });
  if (!res.ok) {
    await throwApiError(res, "Failed to fetch queue status");
  }
  return res.json();
}

// ── Remote Workflows ──────────────────────────────────────────────────────

export async function listRemoteWorkflows(): Promise<RemoteWorkflowSummary[]> {
  const res = await fetch("/api/remote-workflows", { headers: authHeaders() });
  if (!res.ok) {
    await throwApiError(res, "Failed to load remote workflows");
  }
  const payload = await res.json();
  return payload.workflows ?? [];
}

export async function getRemoteWorkflow(workflowId: string): Promise<RemoteWorkflowDetail> {
  const res = await fetch(`/api/remote-workflows/${encodeURIComponent(workflowId)}`, {
    headers: authHeaders(),
  });
  if (!res.ok) {
    await throwApiError(res, "Failed to load remote workflow");
  }
  return res.json();
}

export async function runRemoteWorkflow(
  workflowId: string,
  inputValues: Record<string, unknown>
): Promise<RemoteWorkflowRun> {
  const res = await fetch(`/api/remote-workflows/${encodeURIComponent(workflowId)}/run`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ input_values: inputValues }),
  });
  if (!res.ok) {
    await throwApiError(res, "Failed to run remote workflow");
  }
  return res.json();
}

export async function getRemoteWorkflowResult(promptId: string): Promise<RemoteWorkflowResult> {
  const res = await fetch(`/api/remote-workflows/runs/${encodeURIComponent(promptId)}`, {
    headers: authHeaders(),
  });
  if (!res.ok) {
    await throwApiError(res, "Failed to load remote workflow result");
  }
  return res.json();
}

export async function uploadRemoteWorkflowFile(file: File, overwrite: boolean = true): Promise<RemoteWorkflowUpload> {
  const form = new FormData();
  form.append("file", file);
  form.append("overwrite", String(overwrite));

  const headers: Record<string, string> = {};
  if (_token) headers["Authorization"] = `Bearer ${_token}`;

  const res = await fetch("/api/remote-workflows/uploads", {
    method: "POST",
    headers,
    body: form,
  });
  if (!res.ok) {
    await throwApiError(res, "Failed to upload remote workflow file");
  }
  return res.json();
}

// ── Users ───────────────────────────────────────────────────────────────

export async function listUsers(): Promise<User[]> {
  const res = await fetch("/api/users", { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to list users");
  return res.json();
}

// ── Canvas ───────────────────────────────────────────────────────────────

export async function listNodeVersions(
  canvasId: string,
  nodeId?: string
): Promise<NodeVersion[]> {
  const suffix = nodeId ? `/nodes/${encodeURIComponent(nodeId)}/versions` : "/versions";
  const res = await fetch(`/api/canvas/${encodeURIComponent(canvasId)}${suffix}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to load node versions");
  return res.json();
}

export type LiveblocksUserInfo = {
  id: string;
  name: string;
  color: string;
};

export async function resolveLiveblocksUsers(userIds: string[]): Promise<LiveblocksUserInfo[]> {
  const res = await fetch("/api/liveblocks/resolve-users", {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ userIds }),
  });
  if (!res.ok) throw new Error("Failed to resolve users");
  return res.json();
}
