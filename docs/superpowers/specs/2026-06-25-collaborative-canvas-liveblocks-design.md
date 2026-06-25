# ComfyUI Workbench Collaborative Canvas Liveblocks Spec v0.1

> 目标：在现有 ComfyUI Workbench 上新增多人协作创作画布，把当前“创建任务”表单封装为可连接、可复用、可追踪版本的画布节点。画布状态由 Liveblocks + React Flow 负责协作同步；素材、任务、视频、权限和业务版本仍由现有 FastAPI + SQLite 后端负责。

---

## 1. 当前代码逻辑梳理

### 1.1 现有技术栈

- 后端：FastAPI，入口在 `workbench/api.py` 和 `workbench/main.py`。
- 数据库：SQLite，schema 在 `workbench/schema.sql`。
- 数据访问：`workbench/repositories.py`。
- 业务服务：`workbench/services/assets.py`、`workbench/services/jobs.py`。
- 认证：JWT + 邀请链接，实现在 `workbench/auth.py`、`workbench/routes_auth.py`。
- 实时事件：SSE，实现在 `workbench/sse.py`，前端 hook 为 `web/src/hooks/useSSE.ts`。
- 前端：React + TypeScript + Vite + React Router，入口在 `web/src/App.tsx`。
- 现有 UI：CSS class + 少量 lucide-react 图标，无 Zustand、无 React Flow、无 Liveblocks。

### 1.2 现有页面与 API

- 素材库：`web/src/pages/AssetsPage.tsx`
  - 调用 `listAssets(kind)` 和 `uploadAsset(kind, file)`。
  - 后端接口为 `GET /api/assets`、`POST /api/assets`、`GET /files/assets/{asset_id}`。
  - 上传后通过 SSE `asset_uploaded` 广播。
- 创建任务：`web/src/pages/NewJobPage.tsx`
  - 表单字段：`prompt`、`duration_sec`、`resolution`、`audio_start_sec`、`reference_image_asset_id`、`reference_audio_asset_id`。
  - 调用 `createJob()`，后端接口为 `POST /api/jobs`。
- 任务队列：`web/src/pages/JobsPage.tsx`
  - 调用 `listJobs()` 和 `cancelJob(jobId)`。
  - 监听 SSE `job_created`、`job_status_changed`。
- 视频库：`web/src/pages/VideosPage.tsx`
  - 调用 `GET /api/videos`、`GET /files/videos/{video_id}`。

### 1.3 现有生成链路

```txt
NewJobPage form submit
  ↓
web/src/api/client.ts createJob()
  ↓
POST /api/jobs
  ↓
workbench/api.py CreateJobRequest
  ↓
workbench/services/jobs.py JobService.create_job()
  ↓
workbench/repositories.py create_job()
  ↓
SQLite generation_jobs + job_inputs
  ↓
workbench/main.py background worker loop
  ↓
workbench/worker.py claim_next_job()
  ↓
WorkbenchComfyUIAdapter.submit()
  ↓
ComfyUI
  ↓
WorkbenchComfyUIAdapter.await_result()
  ↓
storage.archive_video()
  ↓
repositories.create_video()
  ↓
repositories.mark_job_succeeded()
  ↓
SSE job_status_changed
  ↓
JobsPage updates
```

### 1.4 当前约束

- 当前没有 `projects`、`canvas_projects` 或每项目成员表，只有 workspace 级 `users` 和角色 `admin | member`。
- 当前成员权限是粗粒度的：`admin` 可看全部素材/任务；`member` 的素材和任务列表按创建者过滤。
- 当前任务模型只支持一张参考图片、一条参考音频和可选替换音频，不支持参考视频。
- 当前 `videos` 表保存生成结果；`generation_jobs.output_video_id` 指向结果视频。
- 当前 SSE 是进程内事件总线，不是持久队列；重启后事件不会补发。
- 当前前端无集中状态管理，新增画布应先使用局部 React state 和 Liveblocks hooks，避免额外引入 Zustand。

---

## 2. 产品目标

### 2.1 Phase 1 MVP 目标

1. 新增“创作画布”页面，路由为 `/canvas`。
2. 支持 React Flow 画布上的 PromptNode、AssetNode、VideoGenerationNode。
3. 使用 Liveblocks room 同步节点、边、在线用户、光标、undo/redo。
4. VideoGenerationNode 覆盖现有创建任务表单字段，并调用现有 `/api/jobs`。
5. 允许从素材库选择图片/音频并创建 AssetNode，禁止把二进制文件写入 Liveblocks。
6. 点击 Generate 后创建后端任务，并把 `jobId`、`status`、轻量错误信息写回节点。
7. 任务通过现有 SSE 更新后，画布节点能跟随更新状态。
8. 任务成功后写入 node version，版本记录绑定 `canvas_id`、`node_id`、`generation_job_id`、`output_video_id`。
9. 保留现有素材库、创建任务、任务队列、ComfyUI 队列、视频库页面，不破坏旧流程。

### 2.2 非目标

Phase 1 不做：

- 完整 ComfyUI workflow 可视化编辑器。
- 视频时间线剪辑器。
- 项目级权限系统。
- 参考视频生成输入。
- Liveblocks Comments 和 Notifications。
- Figma 级评论、标注、审阅状态。
- 大媒体文件、base64、任务日志或完整 workflow JSON 写入 Liveblocks Storage。

---

## 3. 推荐架构

### 3.1 前端依赖

新增依赖：

```txt
@xyflow/react
@liveblocks/client
@liveblocks/react
@liveblocks/react-ui
@liveblocks/react-flow
```

继续复用：

```txt
react
react-router-dom
lucide-react
现有 web/src/styles.css
现有 web/src/api/client.ts
现有 web/src/contexts/AuthContext.tsx
现有 web/src/hooks/useSSE.ts
```

不在 Phase 1 引入 Zustand。画布 UI 本地态使用组件 state；多人共享态使用 Liveblocks Storage/Presence。

### 3.2 后端新增能力

新增：

- `POST /api/liveblocks-auth`
- `POST /api/liveblocks/resolve-users`
- `GET /api/canvas/{canvas_id}/versions`
- `POST /api/canvas/{canvas_id}/nodes/{node_id}/versions`

扩展：

- `POST /api/jobs` 支持可选字段 `canvas_id`、`canvas_node_id`、`canvas_version_id`。
- `generation_jobs` 表增加上述可选字段。
- 新增 `node_versions` 表。
- worker 在任务成功后，如果 job 有 `canvas_id` 和 `canvas_node_id`，自动创建或更新对应 node version。

### 3.3 事实来源

```txt
Liveblocks Storage
  - nodes
  - edges
  - 节点位置
  - 节点轻量 data
  - 当前 job/version 指针

Workbench SQLite
  - users
  - assets
  - generation_jobs
  - videos
  - node_versions

SSE
  - job_created
  - job_status_changed
  - job_progress
  - asset_uploaded
```

Liveblocks 是画布布局与协作状态的事实来源。后端是素材、任务、视频、权限和版本历史的事实来源。

---

## 4. Room 与权限设计

### 4.1 Room ID

当前代码没有项目模型，Phase 1 使用 workspace 默认画布：

```ts
const canvasId = "default";
const roomId = `canvas:${canvasId}`;
```

以后增加项目模型时迁移为：

```ts
const roomId = `canvas:${projectId}:${canvasId}`;
```

### 4.2 角色映射

当前用户角色：

```txt
admin
member
```

Phase 1 权限：

| 能力 | admin | member |
|---|---:|---:|
| 进入画布 | 是 | 是 |
| 移动/编辑节点 | 是 | 是 |
| 上传素材 | 是 | 是 |
| 发起生成 | 是 | 是 |
| 创建邀请 | 是 | 否 |
| 删除版本 | 是 | 否 |

未来项目级角色：

```txt
owner -> admin 或项目 owner
editor -> member with edit permission
viewer -> read-only Liveblocks session
```

### 4.3 Liveblocks Auth

新增 FastAPI route：

```txt
POST /api/liveblocks-auth
```

请求必须带当前 JWT。后端读取 `Authorization: Bearer <token>`，校验用户存在后授权 room。

环境变量：

```txt
LIVEBLOCKS_SECRET_KEY=<your-liveblocks-secret-key>
```

后端职责：

1. 校验 JWT。
2. 校验 room id 格式必须是 `canvas:<canvas_id>`。
3. 当前版本允许所有 authenticated users 进入 `canvas:default`。
4. 通过 Liveblocks Python/REST session 返回授权结果。
5. `userInfo` 返回 `id`、`name`、`avatar` 可为空、`color` 可由 user id 稳定生成。

---

## 5. 前端模块设计

### 5.1 目录结构

```txt
web/src/features/canvas/
  api/
    canvasApi.ts
  components/
    CanvasPage.tsx
    CanvasRoom.tsx
    CollaborativeCanvas.tsx
    CanvasToolbar.tsx
    CanvasSidebar.tsx
    CanvasRightPanel.tsx
  hooks/
    useCanvasAssets.ts
    useCanvasGeneration.ts
    useCanvasJobEvents.ts
  nodes/
    PromptNode.tsx
    AssetNode.tsx
    VideoGenerationNode.tsx
    nodeTypes.ts
  utils/
    buildGenerationPayload.ts
    resolveNodeInputs.ts
  canvasTypes.ts
```

### 5.2 路由和导航

修改 `web/src/App.tsx`：

- 侧边栏新增 `创作画布`。
- 新增 protected route：`/canvas`。
- 保留 `/jobs/new`，但导航文案可保持“创建任务”作为旧入口。

### 5.3 CanvasRoom

职责：

- 配置 `LiveblocksProvider`。
- 使用 `authEndpoint="/api/liveblocks-auth"`。
- 使用 `resolveUsers` 调 `/api/liveblocks/resolve-users`。
- 包裹 `RoomProvider id="canvas:default"`。

### 5.4 CollaborativeCanvas

职责：

- 使用 `useLiveblocksFlow` 同步 nodes/edges。
- 注册 `nodeTypes`。
- 处理新增节点、连接、删除、选中节点。
- 渲染 `Background`、`Controls`、`MiniMap`、`Cursors`。
- 把选中节点传给右侧面板。

Liveblocks Storage 同步白名单：

```ts
type SyncedNodeData = {
  title: string;
  status?: "idle" | "queued" | "running" | "succeeded" | "failed" | "canceled";
  currentJobId?: number;
  currentVersionId?: number;
  thumbnailUrl?: string;
  errorMessage?: string;
  prompt?: string;
  negativePrompt?: string;
  duration_sec?: number;
  resolution?: "720x1280" | "1280x720" | "1024x1024";
  audio_start_sec?: number;
  assetId?: number;
  assetKind?: "image" | "audio" | "video" | "document";
  reference_image_asset_id?: number | null;
  reference_audio_asset_id?: number | null;
};
```

禁止同步：

```txt
File
Blob
base64
local object URL
upload progress
完整任务日志
完整 ComfyUI workflow JSON
长视频 URL token
```

---

## 6. 节点类型

### 6.1 通用类型

```ts
import type { Edge, Node } from "@xyflow/react";

export type WorkbenchNodeType = "prompt" | "asset" | "videoGeneration";

export type WorkbenchStatus =
  | "idle"
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "canceled";

export type WorkbenchNodeData = {
  title: string;
  createdBy?: number;
  updatedBy?: number;
  status?: WorkbenchStatus;
  currentJobId?: number;
  currentVersionId?: number;
  thumbnailUrl?: string;
  errorMessage?: string;
};

export type PromptNodeData = WorkbenchNodeData & {
  prompt: string;
  negativePrompt?: string;
};

export type AssetNodeData = WorkbenchNodeData & {
  assetId: number;
  assetKind: "image" | "audio" | "video" | "document";
  fileName?: string;
  mimeType?: string;
};

export type VideoGenerationNodeData = WorkbenchNodeData & {
  prompt?: string;
  negativePrompt?: string;
  duration_sec: number;
  resolution: "720x1280" | "1280x720" | "1024x1024";
  audio_start_sec: number;
  reference_image_asset_id?: number | null;
  reference_audio_asset_id?: number | null;
};

export type WorkbenchNode =
  | Node<PromptNodeData, "prompt">
  | Node<AssetNodeData, "asset">
  | Node<VideoGenerationNodeData, "videoGeneration">;

export type WorkbenchEdge = Edge<{
  inputType?: "prompt" | "image" | "audio" | "reference";
}>;
```

### 6.2 PromptNode

用途：

- 保存可复用提示词。
- 可连接到 VideoGenerationNode。
- 当 VideoGenerationNode 自身 prompt 为空时，可从上游 PromptNode 取值。

### 6.3 AssetNode

用途：

- 引用已有后端 asset。
- 图片显示缩略图：`assetUrl(asset.id)`。
- 音频/视频 Phase 1 用图标和文件名展示。
- 可连接到 VideoGenerationNode，图片作为 `reference_image_asset_id`，音频作为 `reference_audio_asset_id`。

### 6.4 VideoGenerationNode

用途：

- 画布版创建任务表单。
- 节点上展示核心字段和 Generate 按钮。
- 右侧面板展示完整字段。
- Generate 时从自身 data 和上游节点解析 payload。

字段对应现有 API：

| 节点字段 | 现有 API 字段 |
|---|---|
| `prompt` | `prompt` |
| `duration_sec` | `duration_sec` |
| `resolution` | `resolution` |
| `audio_start_sec` | `audio_start_sec` |
| `reference_image_asset_id` | `reference_image_asset_id` |
| `reference_audio_asset_id` | `reference_audio_asset_id` |

---

## 7. 生成任务和版本历史

### 7.1 Generate 流程

```txt
User clicks Generate on VideoGenerationNode
  ↓
resolveNodeInputs(nodes, edges, nodeId)
  ↓
buildGenerationPayload()
  ↓
POST /api/jobs with canvas_id + canvas_node_id
  ↓
Backend creates generation_jobs row
  ↓
Frontend writes node.data.currentJobId + status=queued
  ↓
SSE job_status_changed
  ↓
useCanvasJobEvents updates matching node status
  ↓
Worker succeeds and creates video
  ↓
Backend creates node_versions row
  ↓
SSE job_status_changed includes output_video_id
  ↓
Frontend refreshes versions and writes currentVersionId
```

### 7.2 扩展 CreateJobRequest

```py
class CreateJobRequest(BaseModel):
    prompt: str
    duration_sec: int
    resolution: str = "720x1280"
    audio_start_sec: float = 0
    reference_image_asset_id: int | None = None
    reference_audio_asset_id: int | None = None
    replace_audio_asset_id: int | None = None
    canvas_id: str | None = None
    canvas_node_id: str | None = None
    canvas_version_id: int | None = None
```

### 7.3 generation_jobs schema 扩展

```sql
alter table generation_jobs add column canvas_id text;
alter table generation_jobs add column canvas_node_id text;
alter table generation_jobs add column canvas_version_id integer;
```

`initialize_db()` 当前使用 `create table if not exists`。实现时需要增加轻量 migration helper，检测列是否存在后再 `alter table`。

### 7.4 node_versions 表

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

### 7.5 version snapshot

```json
{
  "canvasId": "default",
  "nodeId": "vg_123",
  "node": {
    "type": "videoGeneration",
    "data": {
      "prompt": "cinematic rain city",
      "duration_sec": 5,
      "resolution": "720x1280",
      "audio_start_sec": 0
    }
  },
  "inputs": {
    "promptNodeIds": ["prompt_1"],
    "referenceImageAssetIds": [12],
    "referenceAudioAssetIds": [18]
  },
  "requestPayload": {
    "prompt": "cinematic rain city",
    "duration_sec": 5,
    "resolution": "720x1280",
    "audio_start_sec": 0,
    "reference_image_asset_id": 12,
    "reference_audio_asset_id": 18
  }
}
```

---

## 8. UI 设计

### 8.1 页面布局

```txt
┌─────────────────────────────────────────────────────────────┐
│ CanvasToolbar: title, online users, undo, redo, fit view     │
├──────────────┬─────────────────────────────┬────────────────┤
│ CanvasSidebar│ CollaborativeCanvas          │ CanvasRightPanel│
│              │ React Flow                   │ selected node   │
│ 节点库        │ nodes / edges / cursors       │ fields          │
│ 素材选择      │ controls / minimap            │ versions        │
└──────────────┴─────────────────────────────┴────────────────┘
```

### 8.2 CanvasSidebar

包含：

- 添加 PromptNode。
- 添加 VideoGenerationNode。
- 素材类型筛选。
- 从现有素材创建 AssetNode。
- 上传素材后创建 AssetNode。

### 8.3 CanvasRightPanel

根据选中节点类型展示：

- PromptNode：prompt、negative prompt。
- AssetNode：文件名、类型、下载/预览入口。
- VideoGenerationNode：prompt、duration、resolution、audio offset、参考图片、参考音频、Generate、任务状态、版本列表。

### 8.4 状态反馈

VideoGenerationNode 展示：

- `idle`：可生成。
- `queued`：显示任务 id 和排队状态。
- `running`：显示运行状态。
- `succeeded`：显示结果视频入口和最新版本。
- `failed`：显示 `errorMessage`。
- `canceled`：显示已取消。

---

## 9. API 设计

### 9.1 前端 API client

在 `web/src/api/client.ts` 增加：

```ts
export async function createCanvasJob(payload: CreateCanvasJobPayload): Promise<Job>;
export async function listNodeVersions(canvasId: string, nodeId?: string): Promise<NodeVersion[]>;
export async function createNodeVersion(canvasId: string, nodeId: string, payload: CreateNodeVersionPayload): Promise<NodeVersion>;
export async function resolveLiveblocksUsers(userIds: string[]): Promise<LiveblocksUserInfo[]>;
```

`createCanvasJob` 可以复用 `/api/jobs`，只是 payload 多带 `canvas_id` 和 `canvas_node_id`。

### 9.2 后端版本 API

```txt
GET /api/canvas/{canvas_id}/versions
GET /api/canvas/{canvas_id}/nodes/{node_id}/versions
POST /api/canvas/{canvas_id}/nodes/{node_id}/versions
```

Phase 1 的版本创建主要由 worker 在任务完成时自动写入。`POST` 保留给手动保存版本或失败版本记录。

### 9.3 SSE 与节点状态同步

`useCanvasJobEvents` 监听现有 SSE：

- `job_created`：如果 job 有 `canvas_node_id`，更新节点 status 为 `queued`。
- `job_status_changed`：根据 `canvas_node_id` 更新 status、error、currentVersionId。
- `job_progress`：只更新轻量 stage，不写日志。

后端 job response 需要包含：

```txt
canvas_id
canvas_node_id
canvas_version_id
output_video_id
```

---

## 10. 测试策略

### 10.1 后端测试

使用 Python 单元测试覆盖：

- schema migration 对已有数据库幂等。
- `CreateJobRequest` 接收 canvas 字段。
- `repo.create_job()` 保存 canvas 字段。
- worker 成功后为 canvas job 创建 `node_versions`。
- member/admin 权限保持现有行为。

### 10.2 前端测试

使用 Vitest 覆盖：

- `resolveNodeInputs()` 从 PromptNode/AssetNode/edges 解析输入。
- `buildGenerationPayload()` 生成兼容 `/api/jobs` 的 payload。
- 缺少 prompt 时返回明确错误。
- AssetNode 不把 File/Blob/base64 放入 node data。

### 10.3 手工验收

1. 启动后端和前端。
2. 登录。
3. 打开 `/canvas`。
4. 创建 PromptNode、AssetNode、VideoGenerationNode。
5. 连接 prompt/image/audio 到 generation node。
6. 点击 Generate。
7. 在任务队列看到新任务。
8. 节点状态随 SSE 从 queued/running 到 succeeded/failed。
9. 成功后版本面板出现一条版本。
10. 打开两个浏览器窗口，同一 room 节点拖动和光标可同步。

---

## 11. 风险与决策

### 11.1 Liveblocks SDK 与后端语言

Liveblocks 官方示例常见于 Next.js/Node。当前后端是 FastAPI。实现前需要确认 Liveblocks Python SDK 是否满足授权需求；如果没有合适 SDK，使用 Liveblocks REST auth endpoint 或新增极小 Node auth sidecar 都可以，但优先不引入 sidecar。

### 11.2 SQLite migration

当前 schema 初始化没有正式 migration 系统。新增列和表必须通过幂等 helper 完成，避免破坏已有用户数据库。

### 11.3 权限模型不足

当前没有 project/canvas membership。Phase 1 只能做 workspace 级协作。项目级权限应放到后续 phase，不要在画布 MVP 里一次性重构用户体系。

### 11.4 多人同时 Generate

Phase 1 允许同一节点短时间内创建多个任务，但前端在 `queued/running` 时禁用 Generate。后端不强制锁定同一 `canvas_node_id`。Phase 2 再增加“同一节点最多一个 running job”的约束。

### 11.5 Liveblocks 存储边界

任何媒体二进制、大型 JSON、日志和临时本地 URL 都不能写入 Liveblocks。只保存 asset id、video id、job id、version id 和轻量 UI 状态。

---

## 12. Phase Roadmap

### Phase 1: Canvas MVP

- 安装 React Flow + Liveblocks。
- 新增 `/canvas` 页面。
- 实现 PromptNode、AssetNode、VideoGenerationNode。
- 接入现有素材和任务 API。
- 新增 Liveblocks auth。
- 新增 canvas job 字段和 node_versions。
- 通过 SSE 更新节点状态。

### Phase 2: 版本操作

- 版本回滚。
- 复制版本为新节点。
- 输出视频作为下游 AssetNode。
- 同一节点并发生成保护。

### Phase 3: 素材体验

- 拖拽上传。
- 视频封面。
- 音频波形。
- 素材库拖入画布。

### Phase 4: 评论和通知

- Liveblocks Comments。
- 节点评论。
- 版本评论。
- @成员和 resolved 状态。

### Phase 5: 项目和权限

- `projects`、`project_members`、`canvases`。
- owner/editor/viewer。
- 项目级邀请。
- 画布归档和导出。

---

## 13. 实施结论

采用：

```txt
@xyflow/react + @liveblocks/react-flow + 现有 FastAPI/SQLite/SSE/worker
```

关键原则：

- 画布是现有生成链路的协作上游，不替换现有任务系统。
- Liveblocks 保存协作画布轻量状态。
- SQLite 保存业务版本和生成结果。
- Phase 1 保持 workspace 级权限，不引入项目级重构。
- 旧页面必须继续可用。
