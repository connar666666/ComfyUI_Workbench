import { Layers, Terminal } from "lucide-react";

const ENGINE_VERSION = "v1.4.0-alpha";
const ACTIVE_JOBS = 3;
const NODE_HEALTH = 98;
const QUEUE_DEPTH = 12;
const RENDER_PROGRESS = 65;

export function CanvasTaskbar() {
  return (
    <footer className="canvas-taskbar" role="contentinfo">
      <div className="canvas-taskbar-left">
        <span className="canvas-taskbar-engine">
          星枢渲染引擎 <strong>{ENGINE_VERSION}</strong>
        </span>
        <span className="canvas-taskbar-divider" />
        <span className="canvas-taskbar-active">
          <span className="canvas-taskbar-pulse" />
          <strong>{ACTIVE_JOBS}</strong> 个任务进行中
        </span>
        <span className="canvas-taskbar-divider" />
        <span className="canvas-taskbar-stat">
          节点状态: <strong className="ok">{NODE_HEALTH}%</strong>
        </span>
        <span className="canvas-taskbar-stat">
          队列: <strong className="ok">{QUEUE_DEPTH}</strong>
        </span>
      </div>

      <div className="canvas-taskbar-right">
        <div className="canvas-taskbar-progress">
          <div
            className="canvas-taskbar-progress-thumb"
            style={{
              background:
                "linear-gradient(135deg, rgba(208, 188, 255, 0.45) 0%, rgba(78, 222, 163, 0.45) 100%)",
            }}
            aria-hidden
          />
          <div className="canvas-taskbar-progress-track">
            <div
              className="canvas-taskbar-progress-fill"
              style={{ width: `${RENDER_PROGRESS}%` }}
            />
          </div>
          <span className="canvas-taskbar-progress-text">{RENDER_PROGRESS}%</span>
        </div>

        <button type="button" className="canvas-taskbar-icon" title="终端控制台">
          <Terminal size={15} />
        </button>
        <button type="button" className="canvas-taskbar-icon" title="图层管理">
          <Layers size={15} />
        </button>
      </div>

      <div className="canvas-taskbar-global-progress" aria-hidden>
        <div style={{ width: `${RENDER_PROGRESS / 2}%` }} />
      </div>
    </footer>
  );
}