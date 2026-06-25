pragma foreign_keys = on;

create table if not exists users (
  id integer primary key autoincrement,
  username text not null unique,
  display_name text not null,
  role text not null check (role in ('member', 'admin')),
  password_hash text,
  last_seen_at text,
  created_at text not null,
  updated_at text not null
);

create table if not exists invite_tokens (
  id integer primary key autoincrement,
  token_hash text not null unique,
  created_by integer not null references users(id),
  role text not null check (role in ('member', 'admin')),
  max_uses integer,
  use_count integer not null default 0,
  expires_at text,
  created_at text not null,
  is_revoked integer not null default 0
);

create table if not exists folders (
  id integer primary key autoincrement,
  parent_id integer references folders(id),
  scope text not null check (scope in ('assets', 'videos')),
  name text not null,
  created_by integer references users(id),
  created_at text not null,
  updated_at text not null,
  unique(parent_id, scope, name)
);

create table if not exists tags (
  id integer primary key autoincrement,
  name text not null unique,
  color text not null default '#6b7280',
  created_by integer references users(id),
  created_at text not null
);

create table if not exists assets (
  id integer primary key autoincrement,
  folder_id integer references folders(id),
  kind text not null check (kind in ('image', 'audio', 'video', 'document')),
  original_filename text not null,
  storage_key text not null unique,
  mime_type text not null,
  size_bytes integer not null,
  sha256 text not null,
  uploaded_by integer references users(id),
  created_at text not null,
  updated_at text not null,
  deleted_at text
);

create table if not exists asset_tags (
  asset_id integer not null references assets(id) on delete cascade,
  tag_id integer not null references tags(id) on delete cascade,
  created_by integer references users(id),
  created_at text not null,
  primary key(asset_id, tag_id)
);

create table if not exists generation_jobs (
  id integer primary key autoincrement,
  created_by integer references users(id),
  status text not null check (status in ('queued', 'running', 'succeeded', 'failed', 'canceled')),
  prompt text not null,
  duration_sec integer not null,
  resolution text not null,
  audio_start_sec real not null default 0,
  reference_image_asset_id integer references assets(id),
  reference_audio_asset_id integer references assets(id),
  replace_audio_asset_id integer references assets(id),
  output_video_id integer references videos(id),
  canvas_id text,
  canvas_node_id text,
  canvas_version_id integer,
  error_code text,
  error_message text,
  created_at text not null,
  started_at text,
  completed_at text,
  updated_at text not null
);

create table if not exists job_inputs (
  job_id integer not null references generation_jobs(id) on delete cascade,
  asset_id integer not null references assets(id),
  role text not null check (role in ('reference_image', 'reference_audio', 'replace_audio')),
  created_at text not null,
  primary key(job_id, asset_id, role)
);

create table if not exists comfyui_tasks (
  id integer primary key autoincrement,
  job_id integer references generation_jobs(id),
  prompt_id text not null unique,
  comfyui_url text not null,
  native_status text not null check (native_status in ('pending', 'running', 'history', 'missing', 'unknown')),
  queue_position integer,
  raw_summary_json text not null default '{}',
  created_at text not null,
  updated_at text not null
);

create table if not exists videos (
  id integer primary key autoincrement,
  folder_id integer references folders(id),
  source_job_id integer references generation_jobs(id),
  created_by integer references users(id),
  title text not null,
  storage_key text not null unique,
  thumbnail_storage_key text,
  mime_type text not null,
  size_bytes integer not null,
  duration_sec real,
  width integer,
  height integer,
  prompt text not null,
  created_at text not null,
  updated_at text not null,
  deleted_at text
);

create table if not exists node_versions (
  id integer primary key autoincrement,
  canvas_id text not null,
  node_id text not null,
  generation_job_id integer not null references generation_jobs(id),
  output_video_id integer references videos(id),
  version_number integer not null,
  parent_version_id integer references node_versions(id),
  prompt text not null,
  negative_prompt text,
  input_asset_ids_json text not null default '[]',
  params_json text not null default '{}',
  snapshot_json text not null default '{}',
  status text not null check (status in ('queued', 'running', 'succeeded', 'failed', 'canceled')),
  created_by integer references users(id),
  created_at text not null,
  unique(canvas_id, node_id, version_number)
);

create table if not exists video_tags (
  video_id integer not null references videos(id) on delete cascade,
  tag_id integer not null references tags(id) on delete cascade,
  created_by integer references users(id),
  created_at text not null,
  primary key(video_id, tag_id)
);

create table if not exists audit_events (
  id integer primary key autoincrement,
  actor_id integer references users(id),
  action text not null,
  entity_type text not null,
  entity_id integer,
  details_json text not null default '{}',
  created_at text not null
);
