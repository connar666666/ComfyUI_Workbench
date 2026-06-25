# Collaborative Canvas Liveblocks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Liveblocks + React Flow collaborative canvas that wraps the existing ComfyUI job creation flow without breaking the current form, queue, asset library, or video library.

**Architecture:** The frontend adds a `/canvas` route under `web/src/features/canvas`, using Liveblocks for shared nodes/edges/presence and existing API clients for assets/jobs. The FastAPI backend adds Liveblocks auth, optional canvas fields on jobs, a `node_versions` table, and worker-side version creation after successful canvas jobs.

**Tech Stack:** FastAPI, SQLite, React 18, TypeScript, Vite, Vitest, `@xyflow/react`, `@liveblocks/client`, `@liveblocks/react`, `@liveblocks/react-ui`, `@liveblocks/react-flow`.

---

## File Structure

- Modify `web/package.json` and `web/package-lock.json`: add React Flow and Liveblocks dependencies.
- Modify `workbench/config.py`: add `liveblocks_secret_key`.
- Modify `workbench/schema.sql`: add `node_versions` table; document canvas job columns.
- Modify `workbench/db.py`: extend existing `_run_migrations()` for new `generation_jobs` columns and `node_versions`.
- Modify `workbench/api.py`: extend `CreateJobRequest`; add Liveblocks auth, user resolve, and canvas version routes.
- Modify `workbench/repositories.py`: persist canvas job fields and node versions.
- Modify `workbench/services/jobs.py`: validate/pass canvas fields.
- Modify `workbench/worker.py`: create node version after successful canvas job.
- Modify `web/src/types.ts`: add canvas job fields and `NodeVersion`.
- Modify `web/src/api/client.ts`: add canvas API helpers and extend job payload type.
- Modify `web/src/App.tsx`: add `/canvas` route and sidebar nav item.
- Create `web/src/features/canvas/canvasTypes.ts`: shared canvas node/edge types.
- Create `web/src/features/canvas/utils/resolveNodeInputs.ts`: derive prompt/assets from connected upstream nodes.
- Create `web/src/features/canvas/utils/buildGenerationPayload.ts`: build existing `/api/jobs` payload.
- Create `web/src/features/canvas/api/canvasApi.ts`: canvas-specific API wrappers.
- Create `web/src/features/canvas/components/CanvasPage.tsx`.
- Create `web/src/features/canvas/components/CanvasRoom.tsx`.
- Create `web/src/features/canvas/components/CollaborativeCanvas.tsx`.
- Create `web/src/features/canvas/components/CanvasToolbar.tsx`.
- Create `web/src/features/canvas/components/CanvasSidebar.tsx`.
- Create `web/src/features/canvas/components/CanvasRightPanel.tsx`.
- Create `web/src/features/canvas/hooks/useCanvasAssets.ts`.
- Create `web/src/features/canvas/hooks/useCanvasGeneration.ts`.
- Create `web/src/features/canvas/hooks/useCanvasJobEvents.ts`.
- Create `web/src/features/canvas/nodes/PromptNode.tsx`.
- Create `web/src/features/canvas/nodes/AssetNode.tsx`.
- Create `web/src/features/canvas/nodes/VideoGenerationNode.tsx`.
- Create `web/src/features/canvas/nodes/nodeTypes.ts`.
- Create `web/src/features/canvas/utils/resolveNodeInputs.test.ts`.
- Create `web/src/features/canvas/utils/buildGenerationPayload.test.ts`.

---

### Task 1: Install Canvas Dependencies

**Files:**
- Modify: `web/package.json`
- Modify: `web/package-lock.json`

- [ ] **Step 1: Install dependencies**

Run:

```bash
cd web
npm install @xyflow/react @liveblocks/client @liveblocks/react @liveblocks/react-ui @liveblocks/react-flow
```

Expected: `package.json` and `package-lock.json` include the five new packages.

- [ ] **Step 2: Verify existing frontend still builds**

Run:

```bash
cd web
npm run build
```

Expected: TypeScript and Vite build complete without errors.

- [ ] **Step 3: Commit**

```bash
git add web/package.json web/package-lock.json
git commit -m "chore: add collaborative canvas dependencies"
```

---

### Task 2: Add Backend Canvas Persistence

**Files:**
- Modify: `workbench/schema.sql`
- Modify: `workbench/db.py`
- Modify: `workbench/repositories.py`

- [ ] **Step 1: Add schema table**

Append this table to `workbench/schema.sql`:

```sql
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
```

- [ ] **Step 2: Extend existing migrations**

In `workbench/db.py`, keep the existing `_run_migrations(conn)` structure and add a small column helper plus canvas migrations inside that function:

```python
def _column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(f"pragma table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


for column, sql in [
    ("canvas_id", "alter table generation_jobs add column canvas_id text"),
    ("canvas_node_id", "alter table generation_jobs add column canvas_node_id text"),
    ("canvas_version_id", "alter table generation_jobs add column canvas_version_id integer"),
]:
    if "generation_jobs" in existing and not _column_exists(conn, "generation_jobs", column):
        conn.execute(sql)

if "node_versions" not in existing:
    conn.execute("""
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
        )
    """)
```

`initialize_db()` already calls `_run_migrations(conn)`, so no new top-level migration function is needed.

- [ ] **Step 3: Extend repository create_job**

Update `WorkbenchRepository.create_job()` to accept and insert:

```python
canvas_id: str | None = None,
canvas_node_id: str | None = None,
canvas_version_id: int | None = None,
```

The insert must write these columns into `generation_jobs`.

- [ ] **Step 4: Add version repository methods**

Add:

```python
def next_node_version_number(self, canvas_id: str, node_id: str) -> int:
    with connect_db(self.db_path) as conn:
        row = conn.execute(
            "select coalesce(max(version_number), 0) + 1 as next_version "
            "from node_versions where canvas_id = ? and node_id = ?",
            (canvas_id, node_id),
        ).fetchone()
    return int(row["next_version"])

def create_node_version(self, *, canvas_id: str, node_id: str, generation_job_id: int,
                        output_video_id: int | None, prompt: str, input_asset_ids: list[int],
                        params: dict[str, Any], snapshot: dict[str, Any],
                        status: str, created_by: int) -> dict[str, Any]:
    now = utc_now()
    version_number = self.next_node_version_number(canvas_id, node_id)
    with connect_db(self.db_path) as conn:
        cur = conn.execute(
            """
            insert into node_versions(
              canvas_id, node_id, generation_job_id, output_video_id, version_number,
              prompt, input_asset_ids_json, params_json, snapshot_json,
              status, created_by, created_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                canvas_id,
                node_id,
                generation_job_id,
                output_video_id,
                version_number,
                prompt,
                json.dumps(input_asset_ids, ensure_ascii=False),
                json.dumps(params, ensure_ascii=False),
                json.dumps(snapshot, ensure_ascii=False),
                status,
                created_by,
                now,
            ),
        )
        conn.commit()
        row = conn.execute("select * from node_versions where id = ?", (cur.lastrowid,)).fetchone()
    return dict(row)

def list_node_versions(self, canvas_id: str, node_id: str | None = None) -> list[dict[str, Any]]:
    sql = "select * from node_versions where canvas_id = ?"
    params: list[Any] = [canvas_id]
    if node_id is not None:
        sql += " and node_id = ?"
        params.append(node_id)
    sql += " order by created_at desc, id desc"
    with connect_db(self.db_path) as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
```

Ensure `json` and `Any` are imported in `workbench/repositories.py`; they already are in the current file.

- [ ] **Step 5: Run backend import check**

Run:

```bash
uv run python -m compileall workbench
```

Expected: compile succeeds.

- [ ] **Step 6: Commit**

```bash
git add workbench/schema.sql workbench/db.py workbench/repositories.py
git commit -m "feat: add canvas job and node version persistence"
```

---

### Task 3: Extend Jobs API and Worker

**Files:**
- Modify: `workbench/api.py`
- Modify: `workbench/services/jobs.py`
- Modify: `workbench/worker.py`

- [ ] **Step 1: Extend request model**

In `workbench/api.py`, extend `CreateJobRequest`:

```python
canvas_id: str | None = None
canvas_node_id: str | None = None
canvas_version_id: int | None = None
```

- [ ] **Step 2: Pass fields through JobService**

Update `JobService.create_job()` signature and `self.repo.create_job()` call with the same three fields.

- [ ] **Step 3: Create node version after success**

In `WorkbenchWorker.run_once()`, after `mark_job_succeeded()` and `final_job = self.repo.get_job(job["id"])`, add:

```python
if final_job.get("canvas_id") and final_job.get("canvas_node_id"):
    input_asset_ids = [
        asset_id for asset_id in [
            final_job.get("reference_image_asset_id"),
            final_job.get("reference_audio_asset_id"),
            final_job.get("replace_audio_asset_id"),
        ] if asset_id is not None
    ]
    version = self.repo.create_node_version(
        canvas_id=final_job["canvas_id"],
        node_id=final_job["canvas_node_id"],
        generation_job_id=final_job["id"],
        output_video_id=final_job.get("output_video_id"),
        prompt=final_job["prompt"],
        input_asset_ids=input_asset_ids,
        params={
            "duration_sec": final_job["duration_sec"],
            "resolution": final_job["resolution"],
            "audio_start_sec": final_job["audio_start_sec"],
        },
        snapshot={"job": final_job},
        status=final_job["status"],
        created_by=final_job["created_by"],
    )
    self.repo.set_job_canvas_version(final_job["id"], version["id"])
    final_job = self.repo.get_job(job["id"])
```

Also add `set_job_canvas_version()` in the repository.

- [ ] **Step 4: Verify Python compile**

Run:

```bash
uv run python -m compileall workbench
```

Expected: compile succeeds.

- [ ] **Step 5: Commit**

```bash
git add workbench/api.py workbench/services/jobs.py workbench/worker.py workbench/repositories.py
git commit -m "feat: connect canvas jobs to node versions"
```

---

### Task 4: Add Liveblocks Backend Routes

**Files:**
- Modify: `workbench/config.py`
- Modify: `workbench/api.py`

- [ ] **Step 1: Add config**

Add to `WorkbenchSettings`:

```python
liveblocks_secret_key: str | None
```

Set it in `load_settings()`:

```python
liveblocks_secret_key=os.environ.get("LIVEBLOCKS_SECRET_KEY")
```

- [ ] **Step 2: Add auth route**

Add `POST /api/liveblocks-auth` in `create_app()`. It must:

```python
class LiveblocksAuthRequest(BaseModel):
    room: str

@app.post("/api/liveblocks-auth")
def liveblocks_auth(payload: LiveblocksAuthRequest, user: CurrentUser = Depends(get_current_user)):
    if not payload.room.startswith("canvas:"):
        raise PermissionDeniedError("invalid Liveblocks room")
    if not settings.liveblocks_secret_key:
        raise ValidationError("LIVEBLOCKS_SECRET_KEY is not configured")
    # Use the official Liveblocks auth mechanism for Python if available.
    # If the SDK is unavailable, call the Liveblocks REST authorize endpoint with
    # settings.liveblocks_secret_key and return the provider-compatible JSON.
```

Implement the Liveblocks session call using the supported SDK or REST API. Return the exact JSON Liveblocks expects.

- [ ] **Step 3: Add resolve users route**

Add:

```python
class ResolveUsersRequest(BaseModel):
    userIds: list[str]

@app.post("/api/liveblocks/resolve-users")
def resolve_liveblocks_users(payload: ResolveUsersRequest, user: CurrentUser = Depends(get_current_user)):
    users = repo.list_users()
    by_id = {str(u["id"]): u for u in users}
    return [
        {
            "id": user_id,
            "name": by_id.get(user_id, {}).get("display_name") or by_id.get(user_id, {}).get("username") or f"user#{user_id}",
            "color": f"hsl({(int(user_id) * 47) % 360} 70% 45%)" if user_id.isdigit() else "hsl(210 70% 45%)",
        }
        for user_id in payload.userIds
    ]
```

- [ ] **Step 4: Add versions routes**

Add:

```python
@app.get("/api/canvas/{canvas_id}/versions")
def list_canvas_versions(canvas_id: str, user: CurrentUser = Depends(get_current_user)):
    return repo.list_node_versions(canvas_id)

@app.get("/api/canvas/{canvas_id}/nodes/{node_id}/versions")
def list_canvas_node_versions(canvas_id: str, node_id: str, user: CurrentUser = Depends(get_current_user)):
    return repo.list_node_versions(canvas_id, node_id)
```

- [ ] **Step 5: Verify backend compile**

Run:

```bash
uv run python -m compileall workbench
```

Expected: compile succeeds.

- [ ] **Step 6: Commit**

```bash
git add workbench/config.py workbench/api.py
git commit -m "feat: add liveblocks and canvas version api routes"
```

---

### Task 5: Add Canvas Types and Pure Utilities

**Files:**
- Modify: `web/src/types.ts`
- Create: `web/src/features/canvas/canvasTypes.ts`
- Create: `web/src/features/canvas/utils/resolveNodeInputs.ts`
- Create: `web/src/features/canvas/utils/buildGenerationPayload.ts`
- Create: `web/src/features/canvas/utils/resolveNodeInputs.test.ts`
- Create: `web/src/features/canvas/utils/buildGenerationPayload.test.ts`

- [ ] **Step 1: Add shared types**

Add `NodeVersion` and optional canvas fields to `Job` in `web/src/types.ts`:

```ts
canvas_id?: string | null;
canvas_node_id?: string | null;
canvas_version_id?: number | null;
output_video_id?: number | null;
```

Add:

```ts
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
```

- [ ] **Step 2: Create canvasTypes.ts**

Define `WorkbenchNode`, `WorkbenchEdge`, `PromptNodeData`, `AssetNodeData`, and `VideoGenerationNodeData` exactly as specified in `docs/superpowers/specs/2026-06-25-collaborative-canvas-liveblocks-design.md`.

- [ ] **Step 3: Write failing utility tests**

`resolveNodeInputs.test.ts` must cover:

```ts
it("uses connected prompt and asset nodes as generation inputs", () => {
  const nodes: WorkbenchNode[] = [
    { id: "prompt-1", type: "prompt", position: { x: 0, y: 0 }, data: { title: "Prompt", prompt: "rainy city" } },
    { id: "image-1", type: "asset", position: { x: 0, y: 120 }, data: { title: "Image", assetId: 10, assetKind: "image" } },
    { id: "audio-1", type: "asset", position: { x: 0, y: 240 }, data: { title: "Audio", assetId: 20, assetKind: "audio" } },
    { id: "vg-1", type: "videoGeneration", position: { x: 320, y: 0 }, data: { title: "Generate", duration_sec: 5, resolution: "720x1280", audio_start_sec: 0 } },
  ];
  const edges: WorkbenchEdge[] = [
    { id: "e1", source: "prompt-1", target: "vg-1" },
    { id: "e2", source: "image-1", target: "vg-1" },
    { id: "e3", source: "audio-1", target: "vg-1" },
  ];
  const result = resolveNodeInputs(nodes, edges, "vg-1");
  expect(result.prompt).toBe("rainy city");
  expect(result.reference_image_asset_id).toBe(10);
  expect(result.reference_audio_asset_id).toBe(20);
});
```

`buildGenerationPayload.test.ts` must cover:

```ts
it("builds a /api/jobs-compatible payload with canvas ids", () => {
  const node: WorkbenchNode = {
    id: "vg-1",
    type: "videoGeneration",
    position: { x: 0, y: 0 },
    data: {
      title: "Generate",
      prompt: "rainy city",
      duration_sec: 5,
      resolution: "720x1280",
      audio_start_sec: 0,
    },
  };
  const payload = buildGenerationPayload({
    canvasId: "default",
    node,
    resolvedInputs: {},
  });
  expect(payload).toMatchObject({
    canvas_id: "default",
    canvas_node_id: "vg-1",
    prompt: "rainy city",
    duration_sec: 5,
    resolution: "720x1280",
    audio_start_sec: 0,
  });
});
```

- [ ] **Step 4: Run tests to verify failure**

Run:

```bash
cd web
npm test -- web/src/features/canvas/utils
```

Expected: tests fail because utilities are not implemented.

- [ ] **Step 5: Implement utilities**

`resolveNodeInputs()` must:

- Find incoming edges for the target generation node.
- Read connected PromptNode prompt when target prompt is empty.
- Read first connected image AssetNode as `reference_image_asset_id`.
- Read first connected audio AssetNode as `reference_audio_asset_id`.

`buildGenerationPayload()` must:

- Trim prompt.
- Throw `Error("prompt is required")` if no prompt exists.
- Return existing `/api/jobs` field names plus `canvas_id` and `canvas_node_id`.

- [ ] **Step 6: Verify tests pass**

Run:

```bash
cd web
npm test -- web/src/features/canvas/utils
```

Expected: tests pass.

- [ ] **Step 7: Commit**

```bash
git add web/src/types.ts web/src/features/canvas
git commit -m "feat: add canvas types and generation payload utilities"
```

---

### Task 6: Add Frontend Canvas API Helpers

**Files:**
- Modify: `web/src/api/client.ts`
- Create: `web/src/features/canvas/api/canvasApi.ts`

- [ ] **Step 1: Extend createJob payload type**

In `createJob()`, add optional:

```ts
canvas_id?: string | null;
canvas_node_id?: string | null;
canvas_version_id?: number | null;
```

- [ ] **Step 2: Add version API helpers**

Add:

```ts
export async function listNodeVersions(canvasId: string, nodeId?: string): Promise<NodeVersion[]> {
  const suffix = nodeId ? `/nodes/${encodeURIComponent(nodeId)}/versions` : "/versions";
  const res = await fetch(`/api/canvas/${encodeURIComponent(canvasId)}${suffix}`, { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to load node versions");
  return res.json();
}
```

- [ ] **Step 3: Add Liveblocks user resolve helper**

Add:

```ts
export async function resolveLiveblocksUsers(userIds: string[]) {
  const res = await fetch("/api/liveblocks/resolve-users", {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ userIds }),
  });
  if (!res.ok) throw new Error("Failed to resolve users");
  return res.json();
}
```

- [ ] **Step 4: Create canvasApi.ts wrappers**

Export `createCanvasJob`, `listCanvasNodeVersions`, and `resolveCanvasUsers` as thin wrappers over `web/src/api/client.ts`.

- [ ] **Step 5: Typecheck**

Run:

```bash
cd web
npm run build
```

Expected: build succeeds.

- [ ] **Step 6: Commit**

```bash
git add web/src/api/client.ts web/src/features/canvas/api/canvasApi.ts
git commit -m "feat: add canvas frontend api helpers"
```

---

### Task 7: Build Canvas Route and Room

**Files:**
- Modify: `web/src/App.tsx`
- Create: `web/src/features/canvas/components/CanvasPage.tsx`
- Create: `web/src/features/canvas/components/CanvasRoom.tsx`
- Modify: `web/src/styles.css`

- [ ] **Step 1: Add route and nav**

In `App.tsx`, import a canvas icon from lucide-react and `CanvasPage`. Add sidebar link:

```tsx
<NavLink to="/canvas"><Workflow size={18} />创作画布</NavLink>
```

Add route:

```tsx
<Route path="/canvas" element={isAuthenticated ? <CanvasPage /> : <Navigate to="/login" />} />
```

- [ ] **Step 2: Create CanvasPage**

`CanvasPage` renders:

```tsx
export function CanvasPage() {
  return (
    <CanvasRoom canvasId="default">
      <div className="canvas-page">
        <CollaborativeCanvas canvasId="default" />
      </div>
    </CanvasRoom>
  );
}
```

- [ ] **Step 3: Create CanvasRoom**

Use:

```tsx
<LiveblocksProvider
  authEndpoint="/api/liveblocks-auth"
  resolveUsers={async ({ userIds }) => resolveCanvasUsers(userIds)}
>
  <RoomProvider id={`canvas:${canvasId}`}>
    <ClientSideSuspense fallback={<div className="empty-state">加载画布...</div>}>
      {children}
    </ClientSideSuspense>
  </RoomProvider>
</LiveblocksProvider>
```

- [ ] **Step 4: Add base CSS**

Add stable full-height layout classes:

```css
.canvas-page { height: calc(100vh - 0px); min-height: 640px; overflow: hidden; }
.canvas-workspace { display: grid; grid-template-columns: 240px minmax(0, 1fr) 320px; height: 100%; }
.canvas-surface { min-width: 0; height: 100%; }
```

- [ ] **Step 5: Build**

Run:

```bash
cd web
npm run build
```

Expected: build succeeds.

- [ ] **Step 6: Commit**

```bash
git add web/src/App.tsx web/src/styles.css web/src/features/canvas/components/CanvasPage.tsx web/src/features/canvas/components/CanvasRoom.tsx
git commit -m "feat: add collaborative canvas route"
```

---

### Task 8: Implement React Flow Nodes and Canvas Shell

**Files:**
- Create: `web/src/features/canvas/components/CollaborativeCanvas.tsx`
- Create: `web/src/features/canvas/components/CanvasToolbar.tsx`
- Create: `web/src/features/canvas/components/CanvasSidebar.tsx`
- Create: `web/src/features/canvas/components/CanvasRightPanel.tsx`
- Create: `web/src/features/canvas/nodes/PromptNode.tsx`
- Create: `web/src/features/canvas/nodes/AssetNode.tsx`
- Create: `web/src/features/canvas/nodes/VideoGenerationNode.tsx`
- Create: `web/src/features/canvas/nodes/nodeTypes.ts`
- Modify: `web/src/styles.css`

- [ ] **Step 1: Implement node components**

Each node must render handles from `@xyflow/react`:

```tsx
<Handle type="target" position={Position.Left} />
<div className="canvas-node-title">{data.title}</div>
<Handle type="source" position={Position.Right} />
```

VideoGenerationNode must show status, prompt preview, duration, resolution, and Generate button.

- [ ] **Step 2: Register nodeTypes**

Create:

```ts
export const nodeTypes = {
  prompt: PromptNode,
  asset: AssetNode,
  videoGeneration: VideoGenerationNode,
};
```

- [ ] **Step 3: Implement CollaborativeCanvas**

Use `useLiveblocksFlow<WorkbenchNode, WorkbenchEdge>()`, render:

```tsx
<ReactFlow
  nodes={nodes}
  edges={edges}
  nodeTypes={nodeTypes}
  onNodesChange={onNodesChange}
  onEdgesChange={onEdgesChange}
  onConnect={onConnect}
  fitView
>
  <Background />
  <Controls />
  <MiniMap />
  <Cursors />
</ReactFlow>
```

- [ ] **Step 4: Implement sidebar add actions**

Add buttons for:

- PromptNode
- VideoGenerationNode
- AssetNode from selected existing asset

Use deterministic IDs with `crypto.randomUUID()`.

- [ ] **Step 5: Implement right panel**

Show editable fields for selected node. Updating fields must use React Flow node updates so Liveblocks syncs the node data.

- [ ] **Step 6: Build**

Run:

```bash
cd web
npm run build
```

Expected: build succeeds.

- [ ] **Step 7: Commit**

```bash
git add web/src/features/canvas web/src/styles.css
git commit -m "feat: implement collaborative canvas nodes"
```

---

### Task 9: Connect Generation and SSE Status Updates

**Files:**
- Create: `web/src/features/canvas/hooks/useCanvasGeneration.ts`
- Create: `web/src/features/canvas/hooks/useCanvasJobEvents.ts`
- Modify: `web/src/features/canvas/components/CollaborativeCanvas.tsx`
- Modify: `web/src/features/canvas/nodes/VideoGenerationNode.tsx`
- Modify: `web/src/features/canvas/components/CanvasRightPanel.tsx`

- [ ] **Step 1: Implement useCanvasGeneration**

The hook must:

- Resolve upstream inputs.
- Build payload with `canvas_id="default"` and target node id.
- Call `createCanvasJob`.
- Set node data `status="queued"` and `currentJobId=job.id`.
- Set `errorMessage` on failure.

- [ ] **Step 2: Implement useCanvasJobEvents**

Use existing `useSSE()` and update nodes when:

```ts
event.type === "job_created" || event.type === "job_status_changed"
```

Only update nodes where:

```ts
job.canvas_id === canvasId && job.canvas_node_id === node.id
```

- [ ] **Step 3: Disable duplicate Generate**

Disable Generate button when status is `queued` or `running`.

- [ ] **Step 4: Load versions in right panel**

When selected node is `videoGeneration`, call `listCanvasNodeVersions(canvasId, node.id)` and show version number, status, prompt, and output video id.

- [ ] **Step 5: Run tests and build**

Run:

```bash
cd web
npm test -- web/src/features/canvas/utils
npm run build
```

Expected: tests and build succeed.

- [ ] **Step 6: Commit**

```bash
git add web/src/features/canvas
git commit -m "feat: connect canvas generation to existing jobs"
```

---

### Task 10: End-to-End Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add README instructions**

Document:

```txt
LIVEBLOCKS_SECRET_KEY=<your-liveblocks-secret-key>
cd web && npm install
./start.sh
open http://127.0.0.1:8088/canvas
```

- [ ] **Step 2: Run backend compile**

Run:

```bash
uv run python -m compileall workbench
```

Expected: compile succeeds.

- [ ] **Step 3: Run frontend tests**

Run:

```bash
cd web
npm test -- web/src/features/canvas/utils
```

Expected: tests pass.

- [ ] **Step 4: Run frontend build**

Run:

```bash
cd web
npm run build
```

Expected: build succeeds.

- [ ] **Step 5: Manual browser verification**

Start the app:

```bash
./start.sh
```

Verify:

- Login works.
- `/assets`, `/jobs/new`, `/jobs`, `/videos` still load.
- `/canvas` loads.
- PromptNode, AssetNode, and VideoGenerationNode can be created.
- Nodes can move and connect.
- Generate creates a job visible in `/jobs`.
- Canvas node status changes from queued/running to succeeded/failed through SSE.
- Two browser windows connected to `/canvas` show shared node movement and cursors.

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "docs: document collaborative canvas setup"
```

---

## Self-Review

- Spec coverage: tasks cover dependencies, backend persistence, Liveblocks auth, canvas route, node types, generation integration, version history, SSE updates, and verification.
- Placeholder scan: no `TBD`, `TODO`, or unspecified implementation steps remain.
- Type consistency: plan uses current backend field names `duration_sec`, `audio_start_sec`, `reference_image_asset_id`, `reference_audio_asset_id`, and current roles `admin | member`.
- Scope check: plan implements Phase 1 only and leaves project permissions, comments, notifications, reference video, and advanced version operations for later phases.
