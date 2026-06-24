# ComfyUI Workbench

独立的 ComfyUI 视频生成工作台，无需依赖 openclaw-platform-core。

## 项目结构

```
ComfyUI_Workbench/
├── comfyui/                 # ComfyUI 后端核心
│   ├── backend.py           # ComfyUIBackend (LTX 2.3 IA2V)
│   ├── workflow.json        # ComfyUI workflow 模板
│   └── static/              # 占位资源 (placeholder.jpg/wav)
├── workbench/               # 工作台 API 后端
│   ├── main.py              # FastAPI 入口 (uvicorn)
│   ├── api.py               # API 路由定义
│   ├── config.py            # 配置 (环境变量)
│   ├── db.py                # SQLite 数据库初始化
│   ├── schema.sql           # 数据库 schema
│   ├── repositories.py      # 数据访问层
│   ├── storage.py           # 本地文件存储
│   ├── auth.py              # 认证 (header-based)
│   ├── worker.py            # 任务 worker (claim + execute)
│   ├── comfyui_adapter.py   # ComfyUI 适配器
│   ├── comfyui_queue.py     # ComfyUI 队列客户端
│   ├── scripts/             # 工具脚本
│   └── services/            # 业务逻辑层
├── web/                     # React 前端
│   ├── src/
│   │   ├── api/client.ts    # API 客户端
│   │   ├── pages/           # 页面组件
│   │   └── components/      # 共享组件
│   └── vite.config.ts       # Vite 配置 (proxy → backend)
├── start.sh                 # 一键启动脚本
├── pyproject.toml           # Python 依赖
└── README.md
```

## 快速开始

### 前置条件

- Python >= 3.12 + [uv](https://docs.astral.sh/uv/)
- Node.js >= 18
- ComfyUI 实例 (LTX 2.3 workflow) 已运行

### 一键启动（推荐）

```bash
cd ComfyUI_Workbench
./start.sh
```

自动完成依赖安装、数据库初始化、后端 + 前端启动。`Ctrl+C` 停止所有服务。

```bash
# 自定义配置
COMFYUI_URL="http://127.0.0.1:8188" WORKBENCH_PORT=8090 FRONTEND_PORT=5174 ./start.sh
```

### 手动启动

#### 1. 安装依赖

```bash
uv sync                  # Python
cd web && npm install    # 前端
```

#### 2. 启动后端

```bash
uv run python -m workbench.main
# API: http://0.0.0.0:8090
# 首次启动自动创建 SQLite 数据库和存储目录
```

#### 3. 启动前端

```bash
cd web && npm run dev
# 前端: http://0.0.0.0:5174
# Vite proxy 自动转发 /api, /files → 后端
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `COMFYUI_URL` | `http://192.168.7.75:8188` | ComfyUI 实例地址 |
| `WORKBENCH_ROOT` | `~/.openclaw/shared-workbench` | 文件存储根目录 |
| `WORKBENCH_DB` | `<root>/workbench.sqlite` | SQLite 数据库路径 |
| `WORKBENCH_DEFAULT_USER` | `local-user` | 默认用户名 |
| `WORKBENCH_DEFAULT_ROLE` | `admin` | 默认用户角色 |
| `WORKBENCH_HOST` | `0.0.0.0` | 后端监听地址 |
| `WORKBENCH_PORT` | `8090` | 后端监听端口 |
| `FRONTEND_HOST` | `0.0.0.0` | 前端监听地址 |
| `FRONTEND_PORT` | `5174` | 前端监听端口 |

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/assets` | 列出素材 |
| POST | `/api/assets` | 上传素材 |
| GET | `/files/assets/{id}` | 下载素材文件 |
| GET | `/api/jobs` | 列出任务 |
| POST | `/api/jobs` | 创建生成任务 |
