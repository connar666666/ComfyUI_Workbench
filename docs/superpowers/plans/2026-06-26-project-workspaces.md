# Project Workspaces Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a first usable version of project workspaces with private assets, selected remote workflows, project remote-run history, merged history, and project routes.

**Architecture:** Add project tables and repository/service methods behind FastAPI project-scoped endpoints. Reuse existing asset storage and remote workflow client, adding project IDs and local remote-run records. Add React project pages that adapt the current assets and remote workflow UX into a project detail workspace.

**Tech Stack:** FastAPI, SQLite, unittest/TestClient, React, Vite, TypeScript, Vitest.

---

### Task 1: Backend Project Model and Permissions

**Files:**
- Modify: `workbench/schema.sql`
- Modify: `workbench/db.py`
- Modify: `workbench/models.py`
- Modify: `workbench/permissions.py`
- Modify: `workbench/repositories.py`
- Create: `workbench/services/projects.py`
- Test: `tests/test_projects_api.py`

- [x] Write failing tests for creating projects, adding members, role checks, and project-private asset listing.
- [x] Run `uv run python -m unittest tests.test_projects_api -v` and verify failures are due to missing endpoints/tables.
- [x] Add schema, migrations, repository methods, project permission helpers, and `ProjectService`.
- [x] Run `uv run python -m unittest tests.test_projects_api -v` and verify pass.

### Task 2: Project APIs, Workflows, Runs, and History

**Files:**
- Modify: `workbench/api.py`
- Modify: `workbench/repositories.py`
- Modify: `workbench/services/assets.py`
- Modify: `workbench/services/jobs.py`
- Create: `workbench/services/project_workflows.py`
- Test: `tests/test_projects_api.py`

- [x] Write failing tests for project workflow selection, project remote run creation, result refresh, and unified history.
- [x] Run `uv run python -m unittest tests.test_projects_api -v` and verify failures are due to missing behavior.
- [x] Add project-scoped endpoints under `/api/projects`.
- [x] Add remote run persistence and result refresh.
- [x] Run `uv run python -m unittest tests.test_projects_api tests.test_remote_workflows_api tests.test_api_queue -v` and verify pass.

### Task 3: Frontend Project Workspace

**Files:**
- Modify: `web/src/types.ts`
- Modify: `web/src/api/client.ts`
- Modify: `web/src/App.tsx`
- Create: `web/src/pages/ProjectsPage.tsx`
- Create: `web/src/pages/ProjectDetailPage.tsx`
- Test: `web/src/pages/ProjectsPage.test.tsx`
- Test: `web/src/pages/ProjectDetailPage.test.tsx`

- [x] Write failing frontend tests for project list and project detail workflow/assets/history tabs.
- [x] Run `cd web && npm test -- --run src/pages/ProjectsPage.test.tsx src/pages/ProjectDetailPage.test.tsx` and verify failures are due to missing pages.
- [x] Add client helpers, types, routes, navigation, and project pages.
- [x] Run `cd web && npm test -- --run src/pages/ProjectsPage.test.tsx src/pages/ProjectDetailPage.test.tsx`.
- [x] Run backend and frontend relevant test suites.

### Task 4: Final Verification and Commit

**Files:**
- All modified implementation and test files.

- [x] Run backend unit tests relevant to projects and remote workflows.
- [x] Run frontend project page tests.
- [x] Run typecheck/build if available.
- [x] Commit implementation changes.
