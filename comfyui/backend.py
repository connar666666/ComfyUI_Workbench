"""
ComfyUIBackend — 调用本地 ComfyUI LAN 实例 (LTX 2.3 IA2V workflow) 生成视频。

独立模块，不依赖 openclaw-platform-core。支持 prompt + (optional) image + (optional) audio 三种输入。
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import secrets
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError

# ---------------------------------------------------------------------------
# VideoGenResult — standalone (no ABC dependency)
# ---------------------------------------------------------------------------


@dataclass
class VideoGenResult:
    """视频生成结果。"""

    status: str  # "done" | "failed" | "timeout"
    video_url: str
    task_id: str
    elapsed_sec: float
    error: str = ""
    last_frame_url: str = ""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "ltx-2.3-22b-distilled"
DEFAULT_RESOLUTION = "720x1280"  # 默认 9:16 竖屏
DEFAULT_RATIO = "9:16"
DEFAULT_MAX_DURATION = 10

_POLL_INTERVAL_SEC = 3.0
_POLL_TIMEOUT_SEC = 21600.0  # 6 hours, 给批量任务排队留余量

STATIC_DIR = Path(__file__).parent / "static"
PLACEHOLDER_JPG = STATIC_DIR / "placeholder.jpg"
PLACEHOLDER_WAV = STATIC_DIR / "placeholder.wav"


# ---------------------------------------------------------------------------
# Submission dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ComfyUISubmission:
    prompt_id: str
    started_at: float
    replace_audio_url: str | None = None
    audio_start_sec: float = 0


# ---------------------------------------------------------------------------
# ComfyUIBackend
# ---------------------------------------------------------------------------


class ComfyUIBackend:
    """ComfyUI LAN backend (LTX 2.3 IA2V workflow).

    工作流：把 workflow.json 加载到内存，提交时深拷贝、注入 prompt/image/audio
    三个动态参数，POST 到 ``/prompt``，轮询 ``/history/<prompt_id>`` 拿到
    SaveVideo 节点输出的文件路径，然后 curl 下载到本地。
    """

    name = "comfyui"
    label = "ComfyUI (LTX 2.3)"
    model_name = "LTX 2.3"
    max_duration = 60  # LTX 2.3 一次最长 60s
    min_duration = 1

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        resolution: str = DEFAULT_RESOLUTION,
        ratio: str = DEFAULT_RATIO,
        max_duration: int = DEFAULT_MAX_DURATION,
        comfyui_url: str | None = None,
    ):
        self._model = model
        self._resolution = resolution
        self._ratio = ratio
        self._max_duration = max_duration

        # 优先用参数 → 环境变量 → 默认
        self._comfyui_url = (
            comfyui_url
            or os.environ.get("COMFYUI_URL", "")
            or "http://192.168.7.75:8188"
        ).rstrip("/")

        # 加载 workflow 模板
        workflow_path = Path(__file__).parent / "workflow.json"
        with open(workflow_path, encoding="utf-8") as f:
            self._workflow_template = json.load(f)

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    async def generate(
        self,
        prompt: str,
        duration: int,
        reference_image_url: str | None = None,
        reference_audio_url: str | None = None,
        return_last_frame: bool = False,
        replace_audio_url: str | None = None,
        audio_start_sec: float = 0,
    ) -> VideoGenResult:
        """提交一次 ComfyUI 任务，轮询直到 done/error。"""
        if not self._comfyui_url:
            return VideoGenResult(
                status="failed", video_url="", task_id="", elapsed_sec=0.0,
                error="comfyui_url 未配置 (设置环境变量 COMFYUI_URL 或传参数)",
            )

        if return_last_frame:
            print(
                f"[comfyui] WARNING: return_last_frame 暂未实现，将忽略",
                file=__import__("sys").stderr,
            )

        try:
            submission = await self.submit_generation_request(
                prompt=prompt,
                duration=duration,
                reference_image_url=reference_image_url,
                reference_audio_url=reference_audio_url,
                replace_audio_url=replace_audio_url,
                audio_start_sec=audio_start_sec,
            )
        except Exception as exc:
            return VideoGenResult(status="failed", video_url="", task_id="", elapsed_sec=0.0, error=str(exc))
        return await self.await_generation_result(submission)

    async def submit_generation_request(
        self,
        prompt: str,
        duration: int,
        reference_image_url: str | None = None,
        reference_audio_url: str | None = None,
        replace_audio_url: str | None = None,
        audio_start_sec: float = 0,
    ) -> ComfyUISubmission:
        if not self._comfyui_url:
            raise RuntimeError("comfyui_url 未配置 (设置环境变量 COMFYUI_URL 或传参数)")

        clamped = self._resolve_duration(duration, replace_audio_url, audio_start_sec)
        width, height = self._resolve_dimensions()
        image_filename = await self._stage_input(reference_image_url, kind="image")
        if reference_audio_url is None:
            audio_for_upload = self._near_silent_audio(clamped)
        else:
            audio_for_upload = reference_audio_url
        if reference_audio_url and audio_start_sec > 0:
            trimmed = self._trim_audio(reference_audio_url, audio_start_sec, clamped)
            if trimmed:
                audio_for_upload = trimmed
        audio_filename = await self._stage_input(audio_for_upload, kind="audio")
        workflow = self._build_workflow(
            prompt=prompt,
            width=width,
            height=height,
            duration=clamped,
            image_filename=image_filename,
            audio_filename=audio_filename,
            keep_audio=True,
            keep_image=bool(reference_image_url),
            use_empty_audio_latent=reference_audio_url is None,
        )
        started_at = time.time()
        prompt_id = self._submit_prompt(workflow)
        if not prompt_id:
            raise RuntimeError("提交 ComfyUI /prompt 失败")
        return ComfyUISubmission(
            prompt_id=prompt_id,
            started_at=started_at,
            replace_audio_url=replace_audio_url,
            audio_start_sec=audio_start_sec,
        )

    async def await_generation_result(self, submission: ComfyUISubmission) -> VideoGenResult:
        history = await self._poll_history(submission.prompt_id, submission.started_at)
        if history is None:
            return VideoGenResult(
                status="failed", video_url="", task_id=submission.prompt_id,
                elapsed_sec=time.time() - submission.started_at,
                error="ComfyUI 任务轮询超时或失败",
            )
        video_path = self._extract_output(history, submission.prompt_id)
        if not video_path:
            return VideoGenResult(
                status="failed", video_url="", task_id=submission.prompt_id,
                elapsed_sec=time.time() - submission.started_at,
                error="ComfyUI 完成但未产出视频（SaveVideo 节点）",
            )
        video_url = self._to_view_url(video_path)
        local_path = ""
        if submission.replace_audio_url and os.path.exists(submission.replace_audio_url):
            dest = Path("/tmp") / f"comfyui_out_{submission.prompt_id}.mp4"
            if self.download(video_url, dest) and self._replace_audio(dest, submission.replace_audio_url, submission.audio_start_sec):
                local_path = str(dest.resolve())
        return VideoGenResult(
            status="done",
            video_url=local_path or video_url,
            task_id=submission.prompt_id,
            elapsed_sec=round(time.time() - submission.started_at, 1),
        )

    # ------------------------------------------------------------------
    # 时长 / 分辨率辅助
    # ------------------------------------------------------------------

    def _resolve_duration(self, duration: int, replace_audio_url: str | None, audio_start_sec: float) -> int:
        if duration == 0 and replace_audio_url and os.path.exists(replace_audio_url):
            try:
                r = subprocess.run(
                    ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", replace_audio_url],
                    capture_output=True, text=True, timeout=10,
                )
                if r.returncode == 0:
                    info = json.loads(r.stdout)
                    total = float(info["format"]["duration"])
                    auto_dur = int(total - audio_start_sec)
                    return max(self.min_duration, min(auto_dur, self.max_duration))
            except Exception:
                pass
        return max(self.min_duration, min(int(duration), self.max_duration))

    def _resolve_dimensions(self) -> tuple[int, int]:
        try:
            w_str, h_str = self._resolution.split("x")
            return int(w_str), int(h_str)
        except (ValueError, AttributeError):
            return 720, 1280

    # ------------------------------------------------------------------
    # 分段生成 (Long Video)
    # ------------------------------------------------------------------

    async def generate_long_video(
        self,
        prompt: str,
        duration: int,
        reference_image_url: str | None = None,
        reference_audio_url: str | None = None,
        replace_audio_url: str | None = None,
        audio_start_sec: float = 0,
        segment_duration: int | None = None,
    ) -> VideoGenResult:
        """分段生成长视频，将总时长按 segment_duration 切分，
        每段独立生成，上一段的最后一帧作为下一段的首帧，最后拼接。
        """
        if segment_duration is None:
            segment_duration = self._max_duration

        if duration <= segment_duration:
            return await self.generate(
                prompt=prompt, duration=duration,
                reference_image_url=reference_image_url,
                reference_audio_url=reference_audio_url,
                replace_audio_url=replace_audio_url,
                audio_start_sec=audio_start_sec,
            )

        num_segments = (duration + segment_duration - 1) // segment_duration
        print(
            f"[comfyui] 分段生成: 总时长 {duration}s → {num_segments} 段, "
            f"每段 ≤{segment_duration}s"
        )

        segment_files: list[str] = []
        last_frame_path: str | None = reference_image_url
        t0 = time.time()

        for i in range(num_segments):
            seg_start = i * segment_duration
            seg_duration = min(segment_duration, duration - seg_start)
            seg_audio_start = audio_start_sec + seg_start

            print(
                f"[comfyui] 第 {i+1}/{num_segments} 段 "
                f"(start={seg_start}s, dur={seg_duration}s, audio_offset={seg_audio_start}s)"
            )

            result = await self.generate(
                prompt=prompt,
                duration=seg_duration,
                reference_image_url=last_frame_path,
                reference_audio_url=reference_audio_url,
                replace_audio_url=None,
                audio_start_sec=seg_audio_start,
            )

            if result.status != "done":
                self._cleanup_segments(segment_files)
                return VideoGenResult(
                    status="failed", video_url="", task_id="",
                    elapsed_sec=round(time.time() - t0, 1),
                    error=f"第 {i+1}/{num_segments} 段生成失败: {result.error}",
                )

            seg_path = f"/tmp/comfyui_segment_{i}_{int(time.time()*1000)}.mp4"
            if not self.download(result.video_url, Path(seg_path)):
                self._cleanup_segments(segment_files)
                return VideoGenResult(
                    status="failed", video_url="", task_id="",
                    elapsed_sec=round(time.time() - t0, 1),
                    error=f"下载第 {i+1}/{num_segments} 段视频失败",
                )
            segment_files.append(seg_path)

            if i < num_segments - 1:
                last_frame_path = self._extract_last_frame(seg_path)
                if not last_frame_path:
                    self._cleanup_segments(segment_files)
                    return VideoGenResult(
                        status="failed", video_url="", task_id="",
                        elapsed_sec=round(time.time() - t0, 1),
                        error=f"提取第 {i+1}/{num_segments} 段最后一帧失败",
                    )

        final_path = self._concat_segments(segment_files)
        self._cleanup_segments(segment_files)

        if not final_path:
            return VideoGenResult(
                status="failed", video_url="", task_id="",
                elapsed_sec=round(time.time() - t0, 1),
                error="视频拼接失败",
            )

        if replace_audio_url and os.path.exists(replace_audio_url):
            final_dest = Path(final_path)
            if self._replace_audio(final_dest, replace_audio_url, audio_start_sec):
                print(f"[comfyui] 拼接后整体替换音轨 -> {replace_audio_url}")

        return VideoGenResult(
            status="done", video_url=final_path, task_id="long_video",
            elapsed_sec=round(time.time() - t0, 1),
        )

    # ------------------------------------------------------------------
    # 分段生成辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_last_frame(video_path: str) -> str | None:
        out_path = f"/tmp/comfyui_last_frame_{int(time.time()*1000)}.png"
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-sseof", "-1", "-i", video_path,
                 "-update", "1", "-q:v", "1", out_path],
                check=True, capture_output=True, timeout=30,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
            print(f"[comfyui] 提取最后一帧失败: {exc}", file=__import__("sys").stderr)
            return None
        if Path(out_path).exists() and Path(out_path).stat().st_size > 0:
            return out_path
        return None

    @staticmethod
    def _concat_segments(segment_files: list[str]) -> str | None:
        if not segment_files:
            return None
        if len(segment_files) == 1:
            return segment_files[0]

        ts = int(time.time() * 1000)
        list_path = f"/tmp/comfyui_concat_list_{ts}.txt"
        with open(list_path, "w") as f:
            for seg in segment_files:
                f.write(f"file '{seg}'\n")

        out_path = f"/tmp/comfyui_concat_{ts}.mp4"
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path,
                 "-c", "copy", out_path],
                check=True, capture_output=True, timeout=300,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
            print(f"[comfyui] 视频拼接失败: {exc}", file=__import__("sys").stderr)
            return None
        finally:
            Path(list_path).unlink(missing_ok=True)

        if Path(out_path).exists() and Path(out_path).stat().st_size > 0:
            return out_path
        return None

    @staticmethod
    def _cleanup_segments(segment_files: list[str]) -> None:
        for f in segment_files:
            try:
                Path(f).unlink(missing_ok=True)
            except OSError:
                pass

    def download(self, url: str, dest: Path) -> bool:
        """把 ComfyUI /view URL 或本地路径 下载到本地 dest."""
        dest.parent.mkdir(parents=True, exist_ok=True)

        if url.startswith("http://") or url.startswith("https://"):
            try:
                subprocess.run(
                    ["curl", "-L", "-o", str(dest), "-f", "-s", "--retry", "3",
                     "--connect-timeout", "30", "--max-time", "600", url],
                    check=True, capture_output=True, timeout=610,
                )
                return dest.exists() and dest.stat().st_size > 0
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
                return False
        elif url.startswith("file://") or os.path.exists(url):
            src = url[len("file://"):] if url.startswith("file://") else url
            try:
                shutil.copy2(src, dest)
                return dest.exists() and dest.stat().st_size > 0
            except OSError:
                return False
        else:
            return False

    @staticmethod
    def _trim_audio(audio_path: str, start_sec: float, duration_sec: float) -> str | None:
        if not os.path.exists(audio_path):
            return None
        suffix = Path(audio_path).suffix or ".mp3"
        out = Path("/tmp") / f"comfyui_audio_trim_{int(time.time()*1000)}{suffix}"
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-ss", str(start_sec), "-i", audio_path,
                 "-t", str(duration_sec), "-c", "copy", str(out)],
                check=True, capture_output=True, timeout=60,
            )
            if out.exists() and out.stat().st_size > 0:
                return str(out)
            return None
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
            print(f"[comfyui] 音频截取失败: {exc}", file=__import__("sys").stderr)
            return None

    @staticmethod
    def _near_silent_audio(duration_sec: int) -> str:
        out = Path("/tmp") / f"comfyui_near_silent_{int(time.time()*1000)}.wav"
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi",
                 "-i", f"sine=frequency=20:duration={duration_sec}:sample_rate=48000",
                 "-af", "volume=0.0001", str(out)],
                check=True, capture_output=True, timeout=30,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
            print(f"[comfyui] 生成近零能量音频失败: {exc}，回退到占位 wav", file=__import__("sys").stderr)
            return str(PLACEHOLDER_WAV)
        if out.exists() and out.stat().st_size > 0:
            return str(out)
        return str(PLACEHOLDER_WAV)

    @staticmethod
    def _replace_audio(
        video_path: Path,
        audio_path: str,
        audio_start_sec: float = 0,
        target_duration: float | None = None,
    ) -> bool:
        if not os.path.exists(audio_path):
            print(f"[comfyui] 音频文件不存在: {audio_path}", file=__import__("sys").stderr)
            return False

        tmp_path = video_path.parent / f"_replaced_{video_path.name}"
        try:
            cmd = [
                "ffmpeg", "-y",
                "-i", str(video_path),
                "-ss", str(audio_start_sec),
            ]
            if target_duration is not None:
                cmd += ["-t", str(target_duration)]
            cmd += [
                "-i", audio_path,
                "-c:v", "copy",
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-shortest",
                str(tmp_path),
            ]
            subprocess.run(cmd, check=True, capture_output=True, timeout=300)
            if tmp_path.exists() and tmp_path.stat().st_size > 0:
                tmp_path.replace(video_path)
                return True
            return False
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
            print(f"[comfyui] 音频替换失败: {exc}", file=__import__("sys").stderr)
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            return False

    # ------------------------------------------------------------------
    # Workflow 注入
    # ------------------------------------------------------------------

    def _build_workflow(
        self,
        prompt: str,
        width: int,
        height: int,
        duration: int,
        image_filename: str,
        audio_filename: str,
        keep_audio: bool = True,
        keep_image: bool = True,
        use_empty_audio_latent: bool = False,
    ) -> dict:
        """深拷贝 workflow 模板并注入动态参数。"""
        wf = copy.deepcopy(self._workflow_template)

        if "340:319" in wf:
            wf["340:319"]["inputs"]["value"] = prompt
        if "340:330" in wf:
            wf["340:330"]["inputs"]["value"] = width
        if "340:324" in wf:
            wf["340:324"]["inputs"]["value"] = height
        if "340:331" in wf:
            wf["340:331"]["inputs"]["value"] = duration
        if "340:323" in wf:
            wf["340:323"]["inputs"]["value"] = 24
        if "269" in wf:
            wf["269"]["inputs"]["image"] = image_filename
        if "276" in wf:
            wf["276"]["inputs"]["audio"] = audio_filename
        if "340:305" in wf:
            wf["340:305"]["inputs"]["value"] = not keep_image
        if "340:349" in wf:
            wf["340:349"]["inputs"]["value"] = False

        if not keep_audio:
            self._strip_audio_chain(wf)
        if not keep_image:
            self._strip_image_chain(wf)

        self._randomize_noise_seeds(wf)

        if use_empty_audio_latent:
            if "340:430" in wf:
                wf["340:430"]["inputs"]["frames_number"] = duration * 24
                wf["340:430"]["inputs"]["frame_rate"] = 24
            if "340:326" in wf and "340:430" in wf:
                wf["340:326"]["inputs"]["audio_latent"] = ["340:430", 0]
            if "340:431" in wf:
                wf["340:431"]["inputs"]["select"] = True
            print(f"[comfyui] 音频起点切换到 EmptyLatentAudio（纯噪声，模型自由生成）")

        return wf

    @staticmethod
    def _randomize_noise_seeds(wf: dict) -> None:
        max_seed = 2**63 - 1
        for nid in ("340:285", "340:286"):
            node = wf.get(nid)
            if not node:
                continue
            inputs = node.get("inputs", {})
            if "noise_seed" in inputs:
                inputs["noise_seed"] = secrets.randbelow(max_seed)

    def _strip_audio_chain(self, wf: dict) -> None:
        to_remove = {"276", "340:332", "340:328", "340:327"}
        for nid in to_remove:
            wf.pop(nid, None)
        for nid, node in list(wf.items()):
            if nid in to_remove:
                continue
            inputs = node.get("inputs", {})
            for k in list(inputs.keys()):
                v = inputs[k]
                if isinstance(v, list) and len(v) >= 2 and v[0] in to_remove:
                    inputs[k] = None
        if "340:326" in wf:
            wf["340:326"]["inputs"]["audio_latent"] = {}

    def _strip_image_chain(self, wf: dict) -> None:
        to_remove = {"269", "340:334", "340:294", "340:297"}
        for nid in to_remove:
            wf.pop(nid, None)
        for nid, node in list(wf.items()):
            if nid in to_remove:
                continue
            inputs = node.get("inputs", {})
            for k in list(inputs.keys()):
                v = inputs[k]
                if isinstance(v, list) and len(v) >= 2 and v[0] in to_remove:
                    inputs[k] = None

    # ------------------------------------------------------------------
    # 资源 staging
    # ------------------------------------------------------------------

    async def _stage_input(self, url: str | None, kind: str) -> str:
        if not url:
            local_path = PLACEHOLDER_JPG if kind == "image" else PLACEHOLDER_WAV
        elif url.startswith("file://"):
            local_path = url[len("file://"):]
        elif url.startswith("/"):
            local_path = url
        else:
            try:
                local_path = self._download_to_tmp(url)
            except Exception as e:
                print(f"[comfyui] download input failed: {e}, using placeholder", file=__import__("sys").stderr)
                local_path = str(PLACEHOLDER_JPG if kind == "image" else PLACEHOLDER_WAV)

        if not os.path.exists(local_path):
            print(f"[comfyui] input file missing: {local_path}, using placeholder", file=__import__("sys").stderr)
            local_path = str(PLACEHOLDER_JPG if kind == "image" else PLACEHOLDER_WAV)

        return self._upload_to_comfyui(local_path, kind=kind)

    def _upload_to_comfyui(self, local_path: str, kind: str) -> str:
        try:
            import requests
        except ImportError:
            return self._upload_to_comfyui_urllib(local_path, kind)

        try:
            endpoint = f"{self._comfyui_url}/upload/image"
            with open(local_path, "rb") as f:
                files = {"image": (os.path.basename(local_path), f, "application/octet-stream")}
                resp = requests.post(endpoint, files=files, timeout=30)
            if resp.status_code != 200:
                print(
                    f"[comfyui] upload failed: HTTP {resp.status_code}: {resp.text[:200]}",
                    file=__import__("sys").stderr,
                )
                return os.path.basename(local_path)
            result = resp.json()
            return result.get("name", os.path.basename(local_path))
        except Exception as exc:
            print(f"[comfyui] upload exception: {exc}", file=__import__("sys").stderr)
            return os.path.basename(local_path)

    def _upload_to_comfyui_urllib(self, local_path: str, kind: str) -> str:
        import http.client
        import mimetypes

        boundary = "----comfyui_upload_boundary_x7y9z"
        filename = os.path.basename(local_path)
        file_bytes = Path(local_path).read_bytes()
        ctype, _ = mimetypes.guess_type(filename)
        ctype = ctype or "application/octet-stream"

        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'
            f"Content-Type: {ctype}\r\n"
            f"\r\n"
        ).encode() + file_bytes + f"\r\n--{boundary}--\r\n".encode()

        parsed = urllib.parse.urlparse(self._comfyui_url)
        conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=30)
        try:
            conn.request("POST", "/upload/image", body=body, headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(body)),
            })
            resp = conn.getresponse()
            data = resp.read()
            if resp.status != 200:
                return filename
            return json.loads(data).get("name", filename)
        finally:
            conn.close()

    def _download_to_tmp(self, url: str) -> str:
        suffix = Path(urllib.parse.urlparse(url).path).suffix or ".bin"
        out = Path("/tmp") / f"comfyui_in_{int(time.time()*1000)}{suffix}"
        subprocess.run(
            ["curl", "-L", "-o", str(out), "-f", "-s", "--retry", "3",
             "--connect-timeout", "30", "--max-time", "300", url],
            check=True, capture_output=True, timeout=310,
        )
        return str(out)

    # ------------------------------------------------------------------
    # 提交 & 轮询
    # ------------------------------------------------------------------

    def _submit_prompt(self, workflow: dict) -> str | None:
        try:
            body = json.dumps({"prompt": workflow}).encode("utf-8")
            req = urllib.request.Request(
                f"{self._comfyui_url}/prompt",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            if "error" in data:
                print(f"[comfyui] submit error: {data['error']}", file=__import__("sys").stderr)
                return None
            return data.get("prompt_id")
        except (URLError, json.JSONDecodeError) as exc:
            print(f"[comfyui] submit failed: {exc}", file=__import__("sys").stderr)
            return None

    async def _poll_history(self, prompt_id: str, t0: float) -> dict | None:
        deadline = t0 + _POLL_TIMEOUT_SEC
        while time.time() < deadline:
            try:
                req = urllib.request.urlopen(
                    f"{self._comfyui_url}/history/{prompt_id}", timeout=5,
                )
                history = json.loads(req.read())
            except (URLError, json.JSONDecodeError):
                await asyncio.sleep(_POLL_INTERVAL_SEC)
                continue

            if prompt_id in history:
                entry = history[prompt_id]
                status = entry.get("status", {})
                completed = status.get("completed", False)
                if completed:
                    return history
                if status.get("error"):
                    print(f"[comfyui] task error: {status['error']}", file=__import__("sys").stderr)
                    return None

            await asyncio.sleep(_POLL_INTERVAL_SEC)
        return None

    def _extract_output(self, history: dict, prompt_id: str) -> str | None:
        entry = history.get(prompt_id, {})
        outputs = entry.get("outputs", {})

        for nid, out in outputs.items():
            for key in ("videos", "images"):
                items = out.get(key, [])
                if items:
                    item = items[0]
                    filename = item.get("filename")
                    if filename:
                        subfolder = item.get("subfolder", "")
                        if subfolder:
                            return f"{subfolder}/{filename}"
                        return filename
        return None

    def _to_view_url(self, server_path: str) -> str:
        if "/" in server_path:
            subfolder, filename = server_path.split("/", 1)
        else:
            subfolder, filename = "", server_path
        return f"{self._comfyui_url}/view?filename={urllib.parse.quote(filename)}&subfolder={urllib.parse.quote(subfolder)}&type=output"
