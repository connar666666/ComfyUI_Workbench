create extension if not exists pgcrypto;

create table if not exists users (
  id uuid primary key default gen_random_uuid(),
  email varchar unique,
  username varchar not null unique,
  display_name varchar not null,
  avatar_url text,
  role varchar not null default 'member' check (role in ('member', 'admin')),
  status varchar not null default 'ACTIVE' check (status in ('ACTIVE', 'DISABLED', 'DELETED')),
  password_hash text,
  last_seen_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists invite_tokens (
  id uuid primary key default gen_random_uuid(),
  token_hash text not null unique,
  created_by uuid not null references users(id),
  role text not null check (role in ('member', 'admin')),
  max_uses integer,
  use_count integer not null default 0,
  expires_at timestamptz,
  created_at timestamptz not null default now(),
  is_revoked boolean not null default false
);

create table if not exists projects (
  id uuid primary key default gen_random_uuid(),
  name varchar not null,
  description text not null default '',
  owner_user_id uuid references users(id),
  created_by uuid references users(id),
  visibility varchar not null default 'PRIVATE' check (visibility in ('PRIVATE', 'TEAM', 'PUBLIC')),
  status varchar not null default 'ACTIVE' check (status in ('ACTIVE', 'ARCHIVED', 'DELETED')),
  archived_at timestamptz,
  graph_namespace varchar unique,
  main_character_key varchar,
  main_storyline_key varchar,
  current_graph_release_id uuid,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists project_members (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references projects(id) on delete cascade,
  user_id uuid not null references users(id) on delete cascade,
  role varchar not null check (role in ('OWNER', 'ADMIN', 'EDITOR', 'VIEWER', 'owner', 'editor', 'viewer')),
  permissions jsonb not null default '{}'::jsonb,
  joined_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(project_id, user_id)
);

create table if not exists canvases (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references projects(id) on delete cascade,
  name varchar not null,
  description text,
  latest_version_id varchar,
  latest_version_no integer not null default 0,
  metadata jsonb not null default '{}'::jsonb,
  status varchar not null default 'DRAFT' check (status in ('DRAFT', 'ACTIVE', 'ARCHIVED', 'DELETED')),
  created_by uuid references users(id),
  created_at timestamptz not null default now(),
  updated_by uuid references users(id),
  updated_at timestamptz not null default now()
);

create table if not exists canvas_versions (
  id varchar primary key,
  project_id uuid not null references projects(id) on delete cascade,
  canvas_id uuid not null references canvases(id) on delete cascade,
  version_no integer not null,
  parent_version_id varchar references canvas_versions(id),
  change_type varchar not null check (change_type in ('CREATE', 'UPDATE', 'GENERATE', 'ROLLBACK', 'RESTORE', 'AUTO_SAVE')),
  change_summary text,
  is_current boolean not null default false,
  metadata jsonb not null default '{}'::jsonb,
  created_by uuid references users(id),
  created_at timestamptz not null default now(),
  unique(canvas_id, version_no)
);

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'canvases_latest_version_fk') then
    alter table canvases
      add constraint canvases_latest_version_fk
      foreign key (latest_version_id) references canvas_versions(id);
  end if;
end $$;

create table if not exists canvas_version_details (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references projects(id) on delete cascade,
  canvas_id uuid not null references canvases(id) on delete cascade,
  canvas_version_id varchar not null references canvas_versions(id) on delete cascade,
  graph_json jsonb not null,
  nodes_count integer,
  edges_count integer,
  content_hash varchar,
  schema_version integer not null default 1,
  created_at timestamptz not null default now(),
  unique(canvas_version_id)
);

create table if not exists oss_objects (
  id uuid primary key default gen_random_uuid(),
  project_id uuid references projects(id) on delete set null,
  storage_provider varchar not null default 'MINIO' check (storage_provider in ('MINIO', 'S3', 'OSS', 'R2')),
  endpoint varchar,
  bucket varchar not null,
  object_key text not null,
  original_filename varchar,
  mime_type varchar not null,
  object_type varchar not null check (object_type in ('IMAGE', 'AUDIO', 'VIDEO', 'TEXT', 'JSON', 'SUBTITLE', 'OTHER')),
  size_bytes bigint not null,
  sha256 varchar,
  width integer,
  height integer,
  duration_ms integer,
  metadata jsonb not null default '{}'::jsonb,
  status varchar not null default 'READY' check (status in ('UPLOADING', 'READY', 'DELETED', 'FAILED')),
  created_by uuid references users(id),
  created_at timestamptz not null default now(),
  deleted_at timestamptz,
  unique(bucket, object_key)
);

create table if not exists canvas_outputs (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references projects(id) on delete cascade,
  canvas_id uuid not null references canvases(id) on delete cascade,
  canvas_version_id varchar not null references canvas_versions(id) on delete cascade,
  canvas_node_id varchar not null,
  canvas_node_type varchar,
  output_type varchar not null check (output_type in ('IMAGE', 'AUDIO', 'VIDEO', 'TEXT', 'JSON', 'SUBTITLE')),
  oss_object_id uuid not null references oss_objects(id),
  title varchar,
  description text,
  status varchar not null default 'CREATED' check (status in ('CREATED', 'SELECTED', 'REJECTED', 'SAVED_TO_LIBRARY', 'DELETED')),
  metadata jsonb not null default '{}'::jsonb,
  created_by uuid references users(id),
  created_at timestamptz not null default now()
);

create table if not exists project_asset_libraries (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references projects(id) on delete cascade,
  name varchar not null,
  description text,
  is_default boolean not null default true,
  status varchar not null default 'ACTIVE' check (status in ('ACTIVE', 'ARCHIVED', 'DELETED')),
  created_by uuid references users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(project_id, name)
);

create table if not exists asset_folders (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references projects(id) on delete cascade,
  library_id uuid not null references project_asset_libraries(id) on delete cascade,
  parent_folder_id uuid references asset_folders(id),
  name varchar not null,
  path text,
  sort_order integer not null default 0,
  created_by uuid references users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz,
  unique(library_id, parent_folder_id, name)
);

create table if not exists library_assets (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references projects(id) on delete cascade,
  library_id uuid not null references project_asset_libraries(id) on delete cascade,
  folder_id uuid references asset_folders(id),
  asset_type varchar not null check (asset_type in ('IMAGE', 'AUDIO', 'VIDEO', 'TEXT', 'DOCUMENT', 'SUBTITLE', 'OTHER')),
  name varchar not null,
  description text,
  oss_object_id uuid not null references oss_objects(id),
  source_type varchar not null default 'UPLOAD' check (source_type in ('UPLOAD', 'CANVAS_OUTPUT', 'IMPORT', 'MANUAL')),
  source_canvas_id uuid references canvases(id),
  source_canvas_version_id varchar references canvas_versions(id),
  source_canvas_output_id uuid references canvas_outputs(id),
  tags jsonb not null default '[]'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  status varchar not null default 'ACTIVE' check (status in ('ACTIVE', 'ARCHIVED', 'DELETED')),
  created_by uuid references users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz
);

create table if not exists canvas_change_logs (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references projects(id) on delete cascade,
  canvas_id uuid not null references canvases(id) on delete cascade,
  from_version_id varchar references canvas_versions(id),
  to_version_id varchar references canvas_versions(id),
  actor_user_id uuid references users(id),
  action varchar not null check (action in ('ADD_NODE', 'UPDATE_NODE', 'DELETE_NODE', 'ADD_EDGE', 'DELETE_EDGE', 'GENERATE_OUTPUT', 'ROLLBACK')),
  target_type varchar,
  target_id varchar,
  diff_json jsonb,
  created_at timestamptz not null default now()
);

create table if not exists folders (
  id uuid primary key default gen_random_uuid(),
  project_id uuid references projects(id) on delete cascade,
  parent_id uuid references folders(id),
  scope text not null check (scope in ('assets', 'videos')),
  name text not null,
  description text not null default '',
  created_by uuid references users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(parent_id, scope, name)
);

create table if not exists tags (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  color text not null default '#6b7280',
  created_by uuid references users(id),
  created_at timestamptz not null default now()
);

create table if not exists assets (
  id uuid primary key default gen_random_uuid(),
  project_id uuid references projects(id),
  folder_id uuid references folders(id),
  oss_object_id uuid references oss_objects(id),
  kind text not null check (kind in ('image', 'audio', 'video', 'document')),
  original_filename text not null,
  storage_key text not null unique,
  mime_type text not null,
  size_bytes bigint not null,
  sha256 text not null,
  uploaded_by uuid references users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz
);

create table if not exists asset_tags (
  asset_id uuid not null references assets(id) on delete cascade,
  tag_id uuid not null references tags(id) on delete cascade,
  created_by uuid references users(id),
  created_at timestamptz not null default now(),
  primary key(asset_id, tag_id)
);

create table if not exists project_workflows (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references projects(id) on delete cascade,
  workflow_id text not null,
  display_name text,
  sort_order integer not null default 0,
  defaults_json jsonb not null default '{}'::jsonb,
  enabled boolean not null default true,
  created_by uuid references users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(project_id, workflow_id)
);

create table if not exists generation_jobs (
  id uuid primary key default gen_random_uuid(),
  project_id uuid references projects(id),
  created_by uuid references users(id),
  status text not null check (status in ('queued', 'running', 'succeeded', 'failed', 'canceled')),
  prompt text not null,
  duration_sec integer not null,
  resolution text not null,
  audio_start_sec double precision not null default 0,
  reference_image_asset_id uuid references assets(id),
  reference_audio_asset_id uuid references assets(id),
  replace_audio_asset_id uuid references assets(id),
  output_video_id uuid,
  canvas_id text,
  canvas_node_id text,
  canvas_version_id uuid,
  error_code text,
  error_message text,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz,
  updated_at timestamptz not null default now()
);

create table if not exists remote_workflow_runs (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references projects(id),
  project_workflow_id uuid references project_workflows(id),
  workflow_id text not null,
  prompt_id text unique,
  status text not null check (status in ('queued', 'running', 'succeeded', 'failed', 'canceled')),
  input_values_json jsonb not null default '{}'::jsonb,
  results_json jsonb not null default '[]'::jsonb,
  saved_asset_ids_json jsonb not null default '[]'::jsonb,
  error_message text,
  created_by uuid references users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  completed_at timestamptz
);

create table if not exists job_inputs (
  job_id uuid not null references generation_jobs(id) on delete cascade,
  asset_id uuid not null references assets(id),
  role text not null check (role in ('reference_image', 'reference_audio', 'replace_audio')),
  created_at timestamptz not null default now(),
  primary key(job_id, asset_id, role)
);

create table if not exists comfyui_tasks (
  id uuid primary key default gen_random_uuid(),
  job_id uuid references generation_jobs(id),
  prompt_id text not null unique,
  comfyui_url text not null,
  native_status text not null check (native_status in ('pending', 'running', 'history', 'missing', 'unknown')),
  queue_position integer,
  raw_summary_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists videos (
  id uuid primary key default gen_random_uuid(),
  folder_id uuid references folders(id),
  source_job_id uuid references generation_jobs(id),
  oss_object_id uuid references oss_objects(id),
  created_by uuid references users(id),
  title text not null,
  storage_key text not null unique,
  thumbnail_storage_key text,
  mime_type text not null,
  size_bytes bigint not null,
  duration_sec double precision,
  width integer,
  height integer,
  prompt text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz
);

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'generation_jobs_output_video_fk') then
    alter table generation_jobs
      add constraint generation_jobs_output_video_fk
      foreign key (output_video_id) references videos(id);
  end if;
end $$;

create table if not exists node_versions (
  id uuid primary key default gen_random_uuid(),
  canvas_id text not null,
  node_id text not null,
  generation_job_id uuid references generation_jobs(id),
  output_video_id uuid references videos(id),
  version_number integer not null,
  parent_version_id uuid references node_versions(id),
  prompt text not null,
  negative_prompt text,
  input_asset_ids_json jsonb not null default '[]'::jsonb,
  params_json jsonb not null default '{}'::jsonb,
  snapshot_json jsonb not null default '{}'::jsonb,
  status text not null check (status in ('queued', 'running', 'succeeded', 'failed', 'canceled')),
  created_by uuid references users(id),
  created_at timestamptz not null default now(),
  unique(canvas_id, node_id, version_number)
);

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'generation_jobs_canvas_version_fk') then
    alter table generation_jobs
      add constraint generation_jobs_canvas_version_fk
      foreign key (canvas_version_id) references node_versions(id);
  end if;
end $$;

create table if not exists video_tags (
  video_id uuid not null references videos(id) on delete cascade,
  tag_id uuid not null references tags(id) on delete cascade,
  created_by uuid references users(id),
  created_at timestamptz not null default now(),
  primary key(video_id, tag_id)
);

create table if not exists audit_events (
  id uuid primary key default gen_random_uuid(),
  actor_id uuid references users(id),
  action text not null,
  entity_type text not null,
  entity_id uuid,
  details_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_canvases_project_id on canvases(project_id);
create index if not exists idx_canvas_versions_project_canvas_version on canvas_versions(project_id, canvas_id, version_no);
create index if not exists idx_oss_objects_project_id on oss_objects(project_id);
create index if not exists idx_canvas_outputs_canvas_version on canvas_outputs(canvas_id, canvas_version_id);
create index if not exists idx_canvas_outputs_node on canvas_outputs(canvas_id, canvas_node_id);
create index if not exists idx_library_assets_project_library on library_assets(project_id, library_id);
create index if not exists idx_library_assets_folder on library_assets(folder_id);
create index if not exists idx_canvas_change_logs_canvas_created on canvas_change_logs(canvas_id, created_at);
