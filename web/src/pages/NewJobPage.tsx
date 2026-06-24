import { useState } from "react";
import { createJob } from "../api/client";

export function NewJobPage() {
  const [prompt, setPrompt] = useState("");
  const [durationSec, setDurationSec] = useState(5);
  const [resolution, setResolution] = useState("720x1280");
  const [audioStartSec, setAudioStartSec] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setResult(null);
    try {
      const job = await createJob({
        prompt,
        duration_sec: durationSec,
        resolution,
        audio_start_sec: audioStartSec,
      });
      setResult(`任务已创建 (ID: ${job.id})`);
      setPrompt("");
    } catch (err: any) {
      setResult(`创建失败: ${err.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="page">
      <h1>创建任务</h1>
      <form className="job-form" onSubmit={handleSubmit}>
        <label>
          提示词
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={3}
            placeholder="描述你想生成的视频内容..."
            required
          />
        </label>
        <label>
          时长（秒）
          <input
            type="number"
            value={durationSec}
            onChange={(e) => setDurationSec(Number(e.target.value))}
            min={1}
            max={60}
            required
          />
        </label>
        <label>
          分辨率
          <select value={resolution} onChange={(e) => setResolution(e.target.value)}>
            <option value="720x1280">720x1280 (竖屏)</option>
            <option value="1280x720">1280x720 (横屏)</option>
            <option value="1024x1024">1024x1024 (方形)</option>
          </select>
        </label>
        <label>
          音频起始偏移（秒）
          <input
            type="number"
            value={audioStartSec}
            onChange={(e) => setAudioStartSec(Number(e.target.value))}
            min={0}
            step={0.1}
          />
        </label>
        <button type="submit" disabled={submitting}>
          {submitting ? "提交中..." : "创建任务"}
        </button>
      </form>
      {result && <p className="result-message">{result}</p>}
    </div>
  );
}
