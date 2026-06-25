# Canvas v2 — 统一节点架构 · 版本管理 · AI 对话 · 聚合导出

> 设计文档 | 2026-06-25 | fc 分支

## 1. 问题陈述

当前画布系统 (canvas v1) 的局限：

| 问题 | 现状 |
|------|------|
| 画布状态仅存 Liveblocks | 无后端持久化，无法导出/导入 JSON |
| 版本管理仅限生成后 | node_versions 仅 worker 成功后创建，参数变更不保存 |
| 无 AI 集成 | 节点无对话能力，无法通过 AI 优化参数 |
| 无聚合节点 | 多片段无法组织为长视频 pipeline |
| 节点数据模型不统一 | 每种节点独立定义，新增类型需大量重复代码 |

## 2. 目标架构

```
┌─ 浏览器 (前端) ──────────────────────────────────────┐
│                                                       │
│  Liveblocks Storage (实时协作态)                       │
│  ┌─────────────────────────────────────────────────┐  │
│  │ workbenchFlow: { nodes: [...], edges: [...] }   │  │
│  │ 每个节点: { data: {...}, versions: [...],       │  │
│  │            aiConfig: {...}, aiConversations:[] } │  │
│  └─────────────────────────────────────────────────┘  │
│                                                       │
│  ┌──────────┐ ┌──────────┐ ┌───────────────────┐     │
│  │PromptNode│ │AssetNode │ │VideoGenerationNode│     │
│  │ · prompt │ │ · assetId│ │ · duration/res    │     │
│  │ · AI 💬  │ │ · AI 💬  │ │ · AI 💬           │     │
│  │ · 版本📋 │ │ · 版本📋 │ │ · 版本📋          │     │
│  └────┬─────┘ └────┬─────┘ └────────┬──────────┘     │
│       └─────────────┼───────────────┘                 │
│                     │ edges                           │
│                     ▼                                 │
│            ┌──────────────────┐                      │
│            │ AggregatorNode   │                      │
│            │ · segments[]     │                      │
│            │ · 版本📋 · AI 💬 │                      │
│            │ [导出 JSON]      │                      │
│            └──────────────────┘                      │
└──────────────────────────────────────────────────────┘
         ↕ REST + SSE
┌─ 后端 FastAPI ────────────────────────────────────────┐
│                                                       │
│  /api/canvas/                                         │
│    GET  /{id}/export          → 画布完整 JSON         │
│    POST /{id}/import          → 从 JSON 恢复画布      │
│    GET  /{id}/nodes/{nid}/versions                    │
│    POST /{id}/nodes/{nid}/versions                    │
│    POST /{id}/nodes/{nid}/versions/{vid}/restore      │
│    POST /{id}/nodes/{nid}/ai/chat    → SSE stream     │
│    POST /{id}/nodes/{nid}/ai/apply                    │
│    GET  /{id}/nodes/{nid}/ai/conversations            │
│                                                       │
│  SQLite 新增表:                                       │
│    canvas_snapshots   — 画布级完整快照                │
│    ai_conversations   — 节点 AI 对话记录              │
│                                                       │
│  SQLite 修改表:                                       │
│    node_versions      — 扩展为通用节点版本            │
│                                                       │
└───────────────────────────────────────────────────────┘
```

## 3. 统一节点数据模型

所有节点共享基类 `WorkbenchNodeData`，类型特定字段通过 `&` 扩展：

```typescript
// ── 基类 ────────────────────────────────────────────

type WorkbenchNodeData = {
  title: string;
  createdBy?: number;
  updatedBy?: number;

  // 版本管理（所有节点共享）
  currentVersionId?: number;
  versions: NodeVersion[];

  // AI 配置（每个节点独立，协作者各自配置）
  aiConfig?: NodeAIConfig;
};

type NodeAIConfig = {
  provider: 'openai' | 'anthropic' | 'custom';
  apiKey: string;
  apiUrl?: string;
  model: string;
  systemPrompt?: string;
};

// ── 通用版本 ────────────────────────────────────────

type NodeVersion = {
  id: number;
  versionNumber: number;
  snapshot: Record<string, unknown>;   // 节点完整 data 深拷贝
  status: 'draft' | 'published' | 'generated';
  parentVersionId?: number;
  aiConversationId?: number;
  changeSummary?: string;
  generationJobId?: number;
  outputVideoId?: number;
  createdAt: string;
  createdBy: number;
};

// ── 具体节点类型 ────────────────────────────────────

type PromptNodeData = WorkbenchNodeData & {
  prompt: string;
  negativePrompt?: string;
};

type AssetNodeData = WorkbenchNodeData & {
  assetId: number;
  assetKind: 'image' | 'audio' | 'video' | 'document';
  fileName?: string;
  mimeType?: string;
};

type VideoGenerationNodeData = WorkbenchNodeData & {
  prompt?: string;
  negativePrompt?: string;
  durationSec: number;
  resolution: '720x1280' | '1280x720' | '1024x1024';
  audioStartSec: number;
  referenceImageAssetId?: number | null;
  referenceAudioAssetId?: number | null;
  status?: WorkbenchStatus;
  currentJobId?: number;
  thumbnailUrl?: string;
  errorMessage?: string;
};

type AggregatorNodeData = WorkbenchNodeData & {
  segments: AggregatorSegment[];
  transitionMode: 'concat' | 'crossfade';
  crossfadeDurationSec?: number;
  estimatedTotalDuration: number;
};

type AggregatorSegment = {
  order: number;
  sourceNodeId: string;
  sourceVersionId?: number;
  sourceVideoUrl?: string;
  durationSec: number;
  trimStart?: number;
  trimEnd?: number;
};
```

## 4. 数据库 Schema 变更

### 4.1 新增 `canvas_snapshots` 表

```sql
create table if not exists canvas_snapshots (
  id integer primary key autoincrement,
  canvas_id text not null,
  snapshot_json text not null,         -- 完整画布 JSON
  exported_by integer references users(id),
  created_at text not null,
  unique(canvas_id, created_at)
);
```

### 4.2 新增 `ai_conversations` 表

```sql
create table if not exists ai_conversations (
  id integer primary key autoincrement,
  canvas_id text not null,
  node_id text not null,
  messages_json text not null,          -- [{role, content, timestamp}, ...]
  provider text not null,
  model text not null,
  created_by integer references users(id),
  created_at text not null,
  updated_at text not null
);
```

### 4.3 修改 `node_versions` 表

```sql
-- 变更:
--   generation_job_id → 可选 (无生成场景的版本不关联 job)
--   新增 ai_conversation_id
--   新增 change_summary
--   snapshot_json 已存在，改为存储完整节点 data 快照

-- 迁移 SQL:
alter table node_versions add column ai_conversation_id integer
  references ai_conversations(id);
alter table node_versions add column change_summary text;
-- generation_job_id 通过重建表变为可选 (见 db.py 迁移逻辑)
```

## 5. 版本管理系统

### 5.1 触发规则

- 任何节点参数变更 → 300ms debounce → 自动 POST 创建新版本
- 每个版本存储节点完整 `data` 对象快照 (深拷贝)
- 版本号自动递增 (per node)

### 5.2 API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/canvas/{id}/nodes/{nid}/versions` | 列出某节点所有版本 |
| `POST` | `/api/canvas/{id}/nodes/{nid}/versions` | 创建新版本快照 |
| `POST` | `/api/canvas/{id}/nodes/{nid}/versions/{vid}/restore` | 恢复到指定版本（创建新版本，不覆盖历史） |

### 5.3 前端 UI

- 右侧面板版本列表: 版本号、变更摘要、时间、状态徽标
- 点击版本 → 预览快照 diff（旧值 vs 新值）
- 「恢复此版本」按钮 → 确认后应用
- Liveblocks 同步版本元数据 (versionNumber + 最新摘要)

## 6. 节点内嵌 AI 对话框

### 6.1 布局

选中节点 → 右侧属性面板底部 → 可折叠的 AI 对话区域:

```
┌─ 右侧面板 ───────────────────┐
│ 属性                          │
│ ┌──────────────────────────┐  │
│ │ 标题: [____________]     │  │
│ │ ...节点特定字段...       │  │
│ └──────────────────────────┘  │
│ ──────────────────────────── │
│ AI 助手 ▾                     │
│ ┌──────────────────────────┐  │
│ │ Provider: [Anthropic ▾]  │  │
│ │ API Key:  [••••••••]     │  │
│ │ Model:    [claude-sonnet]│  │
│ │ System:   [___________]  │  │
│ │ ──────────────────────── │  │
│ │ [AI] 建议将 prompt 改为:  │  │
│ │ "一只猫在草地上奔跑,      │  │
│ │  4K画质, 电影感光影"      │  │
│ │ [✓ 应用] [✎ 微调]        │  │
│ │ ──────────────────────── │  │
│ │ [输入框______________]→  │  │
│ └──────────────────────────┘  │
│ ──────────────────────────── │
│ 版本历史                      │
│ v3 · AI 辅助 · 刚刚           │
│ v2 · 手动 · 2分钟前           │
└──────────────────────────────┘
```

### 6.2 对话流程

```
用户输入消息
  → POST /api/canvas/{id}/nodes/{nid}/ai/chat
  → 后端代理调用 AI API (使用节点 aiConfig)
  → SSE stream 返回 token
  → AI 可在响应中包含 proposedChanges
  → 前端展示 diff 预览
  → 用户确认 / 微调后确认
  → POST /api/canvas/{id}/nodes/{nid}/ai/apply
  → 更新节点 data + 自动创建新版本 (标记 aiConversationId)
```

### 6.3 API

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/canvas/{id}/nodes/{nid}/ai/chat` | 发送消息，SSE stream 返回 |
| `POST` | `/api/canvas/{id}/nodes/{nid}/ai/apply` | 应用 AI 建议的修改 |
| `GET` | `/api/canvas/{id}/nodes/{nid}/ai/conversations` | 获取对话历史 |

### 6.4 安全

- API Key 存储在节点 data 的 `aiConfig.apiKey` 字段
- Liveblocks Storage 同步时，apiKey 对其他协作者过滤为 `"***"`（前端过滤）
- 后端仅作为代理转发，不存储 API Key
- 对话记录 (messages_json) 存储时不包含 apiKey

## 7. AggregatorNode 聚合节点

### 7.1 职责

- 组织 VideoGenerationNode 片段的拼接顺序
- 导出完整 Task JSON 参数集
- 可选的简单代码拼接 (ffmpeg concat)

### 7.2 连线规则

- 仅 VideoGenerationNode → AggregatorNode（target handle 接受 videoGeneration 类型）
- 连线顺序决定拼接顺序（可拖拽调整）
- PromptNode / AssetNode 不直接连 AggregatorNode

### 7.3 UI

```
┌─ AggregatorNode ──────────────────────────┐
│ 📼 视频聚合                               │
│ ───────────────────────────────────────── │
│ 片段列表:                                  │
│ ┌──────────────────────────────────────┐  │
│ │ 1. 猫场景 (5s)  ✅ succeeded  [×][↑↓]│  │
│ │ 2. 狗场景 (8s)  ⏳ running    [×][↑↓]│  │
│ │ 3. 鸟场景 (3s)  ⬜ idle      [×][↑↓]│  │
│ └──────────────────────────────────────┘  │
│ 总时长: 16s · 过渡: [concat ▾]           │
│ [📋 导出 Task JSON]  [🔗 简单拼接(可选)]  │
└──────────────────────────────────────────┘
```

### 7.4 导出 Task JSON 格式

```json
{
  "version": "1.0",
  "exported_at": "2026-06-25T12:00:00Z",
  "canvas": {
    "id": "default",
    "name": "我的创作项目",
    "nodes": [
      {
        "id": "prompt-abc",
        "type": "prompt",
        "position": { "x": 120, "y": 120 },
        "data": {
          "title": "猫场景",
          "prompt": "一只猫在草地上奔跑，4K画质",
          "negativePrompt": "模糊"
        },
        "versions": [...]
      },
      {
        "id": "generation-def",
        "type": "videoGeneration",
        "position": { "x": 480, "y": 180 },
        "data": {
          "title": "猫场景生成",
          "durationSec": 5,
          "resolution": "720x1280",
          "audioStartSec": 0
        },
        "versions": [...]
      }
    ],
    "edges": [
      { "source": "prompt-abc", "target": "generation-def" },
      { "source": "asset-ghi", "target": "generation-def" }
    ],
    "pipeline": [
      {
        "segment_order": 1,
        "node_id": "generation-def",
        "version_id": 42,
        "params": {
          "prompt": "一只猫在草地上奔跑，4K画质",
          "duration_sec": 5,
          "resolution": "720x1280",
          "reference_image_asset_id": 15
        }
      }
    ],
    "aggregator": {
      "transition_mode": "concat",
      "total_duration": 16
    }
  }
}
```

## 8. 画布级 JSON 导出/导入

### 8.1 API

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/canvas/{id}/export` | 导出画布完整 JSON（含所有节点、版本、AI 对话） |
| `POST` | `/api/canvas/{id}/import` | 从 JSON 恢复画布 |
| `GET` | `/api/canvas/{id}/snapshots` | 列出历史快照 |

### 8.2 导出内容

- 所有节点（含完整 data、版本历史、AI 对话记录）
- 所有连线
- AggregatorNode 的 pipeline 配置
- 导出元数据（版本号、时间戳、导出者）

### 8.3 导入行为

- 清空当前 Liveblocks Storage 中的 workbenchFlow
- 从 JSON 恢复 nodes + edges
- 后端创建 canvas_snapshot 记录
- 素材 (assets) 不随 JSON 导出（仅引用 assetId，需确保素材库中存在）

## 9. 新增 API 汇总

| 分类 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 画布 | `POST` | `/api/canvas/{id}/export` | 导出完整 JSON |
| 画布 | `POST` | `/api/canvas/{id}/import` | 从 JSON 恢复 |
| 画布 | `GET` | `/api/canvas/{id}/snapshots` | 历史快照列表 |
| 版本 | `POST` | `/api/canvas/{id}/nodes/{nid}/versions` | 创建版本 |
| 版本 | `POST` | `/api/canvas/{id}/nodes/{nid}/versions/{vid}/restore` | 恢复版本 |
| AI | `POST` | `/api/canvas/{id}/nodes/{nid}/ai/chat` | AI 对话 (SSE) |
| AI | `POST` | `/api/canvas/{id}/nodes/{nid}/ai/apply` | 应用 AI 建议 |
| AI | `GET` | `/api/canvas/{id}/nodes/{nid}/ai/conversations` | 对话历史 |

## 10. 实施阶段

| 阶段 | 内容 | 预估改动 |
|------|------|---------|
| **阶段 1** | 统一节点数据模型 + 通用版本管理 | 后端 schema 迁移、新增 API、前端类型重构、版本 UI |
| **阶段 2** | 节点内嵌 AI 对话框 | 后端 AI 代理 + SSE、前端聊天 UI、diff 预览 |
| **阶段 3** | AggregatorNode + 导出 Task JSON | 新节点类型、连线规则、导出 API、前端 UI |
| **阶段 4** | 画布级 JSON 导出/导入 + 简单拼接 | canvas_snapshots、导入恢复、ffmpeg concat (可选) |
