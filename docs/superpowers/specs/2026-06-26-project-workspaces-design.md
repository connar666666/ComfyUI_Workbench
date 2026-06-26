# Project Workspaces Design

## Summary

Add project workspaces as the primary production boundary in ComfyUI Workbench. A project owns its asset library, workflow panel, members, permissions, and merged task history. Global remote workflows remain a shared catalog; each project selects workflows from that catalog and stores project-level defaults and ordering.

This design follows a conservative path: scope existing assets and generation jobs to projects, add a local run-history model for remote workflow runs, and keep the current global pages as transitional admin or legacy views.

## Goals

- Users can create projects with a name, description, and member permissions.
- Each project has private assets that do not appear in other projects.
- Each project has its own workflow panel made from selected global remote workflows.
- Each project can store workflow-specific default input values.
- Project history merges local generation jobs and remote workflow runs into one timeline.
- Remote workflow results are automatically saved into the project's asset library when possible, with manual save available as a fallback.
- Project permissions use `owner`, `editor`, and `viewer` roles.
- Existing data remains visible by migrating unscoped assets and jobs into a default legacy project.

## Non-Goals

- Do not copy full remote workflow JSON into each project.
- Do not build a full client review or delivery system in this phase.
- Do not replace `generation_jobs` with a fully generic task table yet.
- Do not make project assets globally visible by default.

## Product Model

A project is an isolated collaborative production workspace.

Each project page has three main tabs:

- **Workflows**: shows remote workflows selected from the global catalog. Owners can add, remove, reorder, enable, disable, and set project defaults. Editors can run enabled workflows. Viewers can inspect workflow details and past runs.
- **Assets**: shows only assets belonging to the current project. Uploading inside a project always writes `project_id`. Remote workflow outputs are saved here when possible.
- **History**: shows local generation jobs and remote workflow runs in a single chronological timeline. Each row includes type, workflow or prompt summary, status, actor, timestamps, input values, referenced assets, saved results, remote links, and errors.

Global pages can remain during migration:

- Global remote workflows remains the catalog/source list.
- Global assets and jobs can become admin or legacy views.
- New create/upload/run flows should prefer project-scoped routes.

## Permissions

Project roles:

- `owner`: can update project details, manage members, archive projects, and manage workflow favorites and defaults.
- `editor`: can upload assets, run workflows, create local generation jobs, and view project history.
- `viewer`: can read project details, assets, workflow panel, history, and results.

System admins keep a global override for operational recovery. Non-admin users must be project members to access project data.

Permission gates:

- Read project: `viewer`, `editor`, `owner`, or system admin.
- Upload asset: `editor`, `owner`, or system admin.
- Run workflow/local job: `editor`, `owner`, or system admin.
- Manage workflow favorites/defaults: `owner` or system admin.
- Manage members/project settings/archive: `owner` or system admin.

The system should prevent removing or demoting the last `owner` of a project.

## Data Model

### New Tables

`projects`

- `id integer primary key autoincrement`
- `name text not null`
- `description text not null default ''`
- `created_by integer not null references users(id)`
- `archived_at text`
- `created_at text not null`
- `updated_at text not null`

`project_members`

- `project_id integer not null references projects(id) on delete cascade`
- `user_id integer not null references users(id) on delete cascade`
- `role text not null check (role in ('owner', 'editor', 'viewer'))`
- `created_at text not null`
- `updated_at text not null`
- primary key: `(project_id, user_id)`

`project_workflows`

- `id integer primary key autoincrement`
- `project_id integer not null references projects(id) on delete cascade`
- `workflow_id text not null`
- `display_name text`
- `sort_order integer not null default 0`
- `defaults_json text not null default '{}'`
- `enabled integer not null default 1`
- `created_by integer references users(id)`
- `created_at text not null`
- `updated_at text not null`
- unique: `(project_id, workflow_id)`

`remote_workflow_runs`

- `id integer primary key autoincrement`
- `project_id integer not null references projects(id)`
- `project_workflow_id integer references project_workflows(id)`
- `workflow_id text not null`
- `prompt_id text unique`
- `status text not null check (status in ('queued', 'running', 'succeeded', 'failed', 'canceled'))`
- `input_values_json text not null default '{}'`
- `results_json text not null default '[]'`
- `saved_asset_ids_json text not null default '[]'`
- `error_message text`
- `created_by integer references users(id)`
- `created_at text not null`
- `updated_at text not null`
- `completed_at text`

### Existing Table Changes

`assets`

- Add `project_id integer references projects(id)`.
- New uploads must provide `project_id`.
- After migration, all non-deleted assets should have a project.

`generation_jobs`

- Add `project_id integer references projects(id)`.
- New jobs created from project pages must provide `project_id`.
- Existing jobs migrate into the default legacy project.

`folders`

- Existing folders are scoped only by `scope`. For project-private assets, either add `project_id` to folders or postpone folder support in project assets. The lower-risk first phase is to keep project assets flat plus filters, then add project-scoped folders later.

## Migration Strategy

1. Create a default project named `Legacy Workspace`.
2. Add all existing users who can currently see legacy data as members. A simple first migration can make the first admin or first user the owner, with admins retaining global override.
3. Set `assets.project_id` for existing assets to the legacy project.
4. Set `generation_jobs.project_id` for existing jobs to the legacy project.
5. Keep global list endpoints working during migration, but prefer project-scoped endpoints for new UI flows.

The schema should allow nullable `project_id` briefly during migration if needed, but services should require it for new writes.

## API Design

### Projects

- `GET /api/projects`: list projects visible to the current user.
- `POST /api/projects`: create a project with name, description, and initial members. Creator becomes `owner`.
- `GET /api/projects/{project_id}`: get project detail, membership, and current user's project role.
- `PATCH /api/projects/{project_id}`: update name or description.
- `POST /api/projects/{project_id}/archive`: archive a project.
- `GET /api/projects/{project_id}/members`: list members.
- `PUT /api/projects/{project_id}/members/{user_id}`: add or update a member role.
- `DELETE /api/projects/{project_id}/members/{user_id}`: remove a member, unless it removes the last owner.

### Project Assets

- `GET /api/projects/{project_id}/assets?kind=image`: list current project assets.
- `POST /api/projects/{project_id}/assets`: upload a project-private asset.
- `GET /files/assets/{asset_id}`: require that current user can read the asset's project.

The existing `/api/assets` endpoint can remain as a legacy/admin view. For non-admin users, it should eventually either require `project_id` or return assets from visible projects only.

### Project Workflows

- `GET /api/projects/{project_id}/workflows`: list selected workflows with project defaults and remote summary metadata.
- `POST /api/projects/{project_id}/workflows`: add a global remote workflow to the project.
- `PATCH /api/projects/{project_id}/workflows/{project_workflow_id}`: update display name, ordering, enabled flag, or defaults.
- `DELETE /api/projects/{project_id}/workflows/{project_workflow_id}`: remove from project panel.
- `GET /api/projects/{project_id}/workflows/catalog`: list global remote workflows with a flag showing which are already selected.
- `GET /api/projects/{project_id}/workflows/{project_workflow_id}/detail`: get remote workflow detail plus project defaults.

### Remote Workflow Runs

- `POST /api/projects/{project_id}/workflows/{project_workflow_id}/runs`: create a local run record, call the remote workflow API, store `prompt_id`, and return the run.
- `GET /api/projects/{project_id}/remote-runs/{run_id}`: get run status/results.
- `POST /api/projects/{project_id}/remote-runs/{run_id}/refresh`: poll remote result, update status/results, and save outputs when possible.
- `POST /api/projects/{project_id}/remote-runs/{run_id}/save-results`: manually save remote results that were not auto-saved.

Polling can start in the browser for the first phase. A background worker can later own refresh and result archiving.

### Unified History

- `GET /api/projects/{project_id}/history`: return a merged list from `generation_jobs` and `remote_workflow_runs`.

Each item should normalize to:

- `id`
- `type`: `local_generation` or `remote_workflow`
- `status`
- `title`
- `created_by`
- `created_by_username`
- `created_at`
- `updated_at`
- `completed_at`
- `input_summary`
- `asset_ids`
- `result_asset_ids`
- `remote_results`
- `error_message`

## Remote Workflow Result Saving

When a remote run returns results:

1. Store the raw normalized result payload in `remote_workflow_runs.results_json`.
2. For each result with a downloadable image, audio, video, or document URL, attempt to download and store it through `LocalStorage`.
3. Create an `assets` row with the current `project_id`.
4. Store created asset ids in `saved_asset_ids_json`.
5. If a result cannot be downloaded or typed safely, keep its remote link in `results_json` and expose a manual save action.

Auto-save failures should not mark the remote workflow run as failed if generation succeeded. The run can include a non-fatal result-save warning.

## Frontend Design

### Navigation

Add a Projects entry to the main navigation. The preferred user path is:

`Projects -> Project Detail -> Workflows / Assets / History`

Project detail route:

- `/projects/{projectId}`
- `/projects/{projectId}/workflows`
- `/projects/{projectId}/assets`
- `/projects/{projectId}/history`
- `/projects/{projectId}/settings`

### Project List

The project list should be dense and operational:

- Project name and description.
- Current user's role.
- Member count.
- Counts for assets, active/running tasks, and selected workflows if cheap to compute.
- Last activity timestamp.
- Create project action.

### Project Workflows Tab

Use the existing remote workflow page as the foundation, but scope it to selected project workflows:

- Left column: selected project workflows, search, enabled/disabled state, add workflow action.
- Center: generated form from remote workflow detail, prefilled with project defaults.
- Right column: current run/result preview and recent runs for this workflow.

Owners see settings for defaults, ordering, and removal. Editors see run controls. Viewers see read-only forms and history.

### Project Assets Tab

Adapt the current assets table:

- Filter by kind.
- Upload action for editors/owners.
- Preview thumbnails for images and media controls for audio/video.
- Show source: uploaded manually, local generation output, remote workflow output.
- Link each generated asset back to the history item that produced it when available.

### Project History Tab

Use a single table or list:

- Type badge.
- Status badge.
- Title: prompt snippet or workflow display name.
- Actor.
- Created/completed timestamps.
- Result indicators: saved assets count, remote result links, warnings.
- Expandable detail with input values, referenced assets, raw remote prompt id, error details.

## Backend Service Design

Add a `ProjectService` for project creation, membership, role checks, and member mutations.

Add project-aware methods to `AssetService` and `JobService` instead of duplicating logic:

- `AssetService.upload_asset(..., project_id)`
- `AssetService.list_assets(..., project_id)`
- `JobService.create_job(..., project_id)`
- `JobService.list_jobs(..., project_id)`

Add a `ProjectWorkflowService` for selected workflow management and remote run orchestration:

- Add/remove/list project workflows.
- Merge remote workflow details with project defaults.
- Create remote run records.
- Poll and persist remote results.
- Save result files into project assets.

Repository methods should keep SQL ownership centralized in `WorkbenchRepository`, matching the current codebase pattern.

## Error Handling

- Missing project: return 404.
- User is not a member: return permission denied.
- Viewer attempts mutation: return permission denied.
- Workflow is not selected for project: return validation error or 404 from the project-scoped endpoint.
- Remote workflow API unavailable: keep local run as `failed` with error message if prompt creation fails.
- Remote result polling unavailable: keep run `running` or mark `failed` only when the remote API confirms failure or an unrecoverable validation error occurs.
- Auto-save output failure: keep run `succeeded`, record warning, and allow manual save.

## Testing Strategy

Backend tests:

- Project creation adds creator as owner.
- Project member roles enforce read/write/manage permissions.
- Project assets list excludes assets from other projects.
- Project uploads write `project_id`.
- Project workflows can be added from a mocked global remote catalog.
- Remote workflow run creates local history, calls remote client, stores `prompt_id`, polls results, and records saved result assets.
- Unified history returns local jobs and remote runs in chronological order.
- Existing unscoped data migrates to `Legacy Workspace`.

Frontend tests:

- Project list renders visible projects and roles.
- Project workflows tab lists selected workflows and runs a workflow with project defaults.
- Viewer cannot see mutation controls.
- Project assets tab uploads and filters project-private assets.
- Project history displays mixed local and remote items.

Manual verification:

- Create project with members.
- Add a remote workflow from catalog.
- Upload a project asset.
- Run workflow.
- Confirm result appears in history and asset library.
- Confirm another project cannot see the asset or run.

## Implementation Sequence

1. Add schema and repository support for projects, members, project workflows, remote workflow runs, and `project_id` columns.
2. Add project permission helpers and backend services.
3. Add project APIs and tests.
4. Scope asset APIs and job APIs to projects while preserving legacy endpoints.
5. Add remote workflow run persistence and result saving.
6. Add frontend project list/detail routes.
7. Adapt remote workflow, assets, and jobs UI into project tabs.
8. Add unified history UI and tests.
9. Run migration verification and end-to-end manual checks.

## Open Decisions For Implementation

- Whether project asset folders ship in the first implementation or stay flat for the first pass.
- Whether remote result polling remains browser-driven initially or moves immediately to a backend worker.
- Whether global asset/job pages remain visible to all members or become admin-only after project pages are complete.

The recommended first implementation is flat project assets, browser-driven remote polling with persisted run records, and global pages retained as transitional views.
