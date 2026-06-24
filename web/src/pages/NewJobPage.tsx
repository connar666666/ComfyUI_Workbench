import { useEffect, useState } from "react";
import { createJob, listAssets, assetUrl } from "../api/client";
import type { Asset } from "../types";

export function NewJobPage() {
  const [prompt, setPrompt] = useState("");
  const [durationSec, setDurationSec] = useState(5);
  const [resolution, setResolution] = useState("720x1280");
  const [audioStartSec, setAudioStartSec] = useState(0);
  const [refImageId, setRefImageId] = useState<number | null>(null);
  const [refAudioId, setRefAudioId] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [imageAssets, setImageAssets] = useState<Asset[]>([]);
  const [audioAssets, setAudioAssets] = useState<Asset[]>([]);

  useEffect(() => {
    listAssets("image").then(setImageAssets).catch(() => {});
    listAssets("audio").then(setAudioAssets).catch(() => {});
  }, []);

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
        reference_image_asset_id: refImageId,
        reference_audio_asset_id: refAudioId,
      });
      setResult(`任务已创建 (ID: ${job.id})`);
      setPrompt("");
      setRefImageId(null);
      setRefAudioId(null);
    } catch (err: any) {
      setResult(`创建失败: ${err.message}`);
    } finally { setSubmitting(false); }
  };

  return (
    <div className="page">
      <h1>创建任务</h1>
      <form className="job-form" onSubmit={handleSubmit} style={{ maxWidth: 640 }}>
        {result && <p className={result.includes("失败") ? "auth-error" : "auth-success"}>{result}</p>}

        <div className="form-group">
          <label>提示词</label>
          <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={3} placeholder="描述你想生成的视频内容..." required />
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>时长（秒）</label>
            <input type="number" value={durationSec} onChange={(e) => setDurationSec(Number(e.target.value))} min={1} max={60} required />
          </div>
          <div className="form-group">
            <label>分辨率</label>
            <select value={resolution} onChange={(e) => setResolution(e.target.value)}>
              <option value="720x1280">720x1280 (竖屏)</option>
              <option value="1280x720">1280x720 (横屏)</option>
              <option value="1024x1024">1024x1024 (方形)</option>
            </select>
          </div>
          <div className="form-group">
            <label>音频偏移（秒）</label>
            <input type="number" value={audioStartSec} onChange={(e) => setAudioStartSec(Number(e.target.value))} min={0} step={0.1} />
          </div>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>参考图片（可选）</label>
            <select value={refImageId ?? ""} onChange={(e) => setRefImageId(e.target.value ? Number(e.target.value) : null)}>
              <option value="">无</option>
              {imageAssets.map((a) => <option key={a.id} value={a.id}>[{a.id}] {a.original_filename}</option>)}
            </select>
            {refImageId && <img src={assetUrl(refImageId)} alt="Preview" className="asset-preview" style={{ marginTop: 8, maxWidth: 120, maxHeight: 120, borderRadius: 6 }} />}
          </div>
          <div className="form-group">
            <label>参考音频（可选）</label>
            <select value={refAudioId ?? ""} onChange={(e) => setRefAudioId(e.target.value ? Number(e.target.value) : null)}>
              <option value="">无</option>
              {audioAssets.map((a) => <option key={a.id} value={a.id}>[{a.id}] {a.original_filename}</option>)}
            </select>
          </div>
        </div>

        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? "提交中..." : "创建任务"}
        </button>
      </form>
    </div>
  );
}
