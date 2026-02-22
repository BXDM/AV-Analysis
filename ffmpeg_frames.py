# -*- coding: utf-8 -*-
"""
使用 FFmpeg + GPU 硬解抽帧（可选）。需系统已安装 ffmpeg；GPU 加速需对应驱动（如 NVIDIA 驱动 + cuda）。
"""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def _ffmpeg_bin() -> str | None:
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    return None


def _ffprobe_bin() -> str | None:
    if shutil.which("ffprobe"):
        return "ffprobe"
    return None


def _parse_r_frame_rate(r_frame_rate: str) -> float:
    """解析 ffprobe 的 r_frame_rate，如 '30/1' -> 30.0, '30000/1001' -> 29.97"""
    try:
        if "/" in r_frame_rate:
            a, b = r_frame_rate.strip().split("/", 1)
            return float(a) / float(b)
        return float(r_frame_rate)
    except Exception:
        return 0.0


def get_video_metadata_ffprobe(video_path: str | Path) -> dict | None:
    """
    用 ffprobe 读取视频元数据（不解码）。返回 duration_sec, width, height, resolution。
    失败或未安装 ffprobe 返回 None。
    """
    ffprobe = _ffprobe_bin()
    if not ffprobe:
        return None
    path = Path(video_path).resolve()
    if not path.is_file():
        return None
    try:
        out = subprocess.run(
            [
                ffprobe,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=duration,width,height,r_frame_rate",
                "-of", "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        if out.returncode != 0 or not out.stdout:
            return None
        data = json.loads(out.stdout)
        streams = data.get("streams") or []
        if not streams:
            return None
        s = streams[0]
        duration = s.get("duration")
        if duration is not None:
            duration = float(duration)
        else:
            duration = None
        w = s.get("width")
        h = s.get("height")
        if w is not None:
            w = int(w)
        if h is not None:
            h = int(h)
        resolution = f"{w}x{h}" if (w and h) else None
        return {
            "duration_sec": round(duration, 2) if duration is not None else None,
            "width": w or None,
            "height": h or None,
            "resolution": resolution,
        }
    except (json.JSONDecodeError, subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def _resolve_hwaccel(hwaccel: str) -> list[str]:
    """返回 FFmpeg 硬件加速参数。hwaccel=auto 时依次尝试 cuda -> d3d11va -> 无。"""
    if hwaccel == "auto":
        # 不在此处探测，返回空；调用方可多次尝试
        return []
    if not hwaccel or hwaccel.lower() == "none":
        return []
    return ["-hwaccel", hwaccel.strip().lower()]


def extract_frames_ffmpeg(
    video_path: str | Path,
    num_frames: int,
    max_width: int,
    hwaccel: str = "cuda",
) -> list:
    """
    用 FFmpeg（可选 GPU）从视频均匀截取 num_frames 帧，缩放到 max_width 宽。
    返回 list of RGB numpy 数组 (H,W,3)，失败返回空列表。
    hwaccel: "cuda", "d3d11va", "dxva2", "" 或 "auto"（内部会尝试 cuda -> d3d11va -> 无）
    """
    ffmpeg = _ffmpeg_bin()
    if not ffmpeg:
        return []
    path = Path(video_path).resolve()
    if not path.is_file():
        return []

    ffprobe = _ffprobe_bin()
    duration_sec = None
    fps = 30.0
    if ffprobe:
        try:
            out = subprocess.run(
                [
                    ffprobe,
                    "-v", "error",
                    "-select_streams", "v:0",
                    "-show_entries", "stream=duration,r_frame_rate",
                    "-of", "json",
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            if out.returncode == 0 and out.stdout:
                data = json.loads(out.stdout)
                s = (data.get("streams") or [{}])[0]
                if s.get("duration"):
                    duration_sec = float(s["duration"])
                if s.get("r_frame_rate"):
                    fps = _parse_r_frame_rate(s["r_frame_rate"]) or 30.0
        except Exception:
            pass

    if duration_sec is None or duration_sec <= 0:
        duration_sec = 10.0
    total_frames = int(duration_sec * fps) or 1
    indices = []
    for i in range(num_frames):
        pos = int((i + 1) * total_frames / (num_frames + 1))
        indices.append(min(pos, total_frames - 1) if total_frames > 1 else 0)

    # 尝试的 hwaccel 顺序
    if hwaccel == "auto":
        try_order = ["cuda", "d3d11va", ""]
    else:
        try_order = [hwaccel] if hwaccel else [""]

    for accel in try_order:
        hw_args = _resolve_hwaccel(accel) if accel else []
        tmpdir = tempfile.mkdtemp(prefix="av_thumb_")
        try:
            # select 表达式: eq(n,N1)+eq(n,N2)+...
            select_parts = "+".join(f"eq(n,{idx})" for idx in indices)
            scale = f"scale={max_width}:-2"
            vf = f"select='{select_parts}',{scale}"
            cmd = (
                [ffmpeg, "-y"]
                + hw_args
                + ["-i", str(path), "-vf", vf, "-vsync", "0", "-frames:v", str(num_frames), "-pix_fmt", "rgb24"]
                + [str(Path(tmpdir) / "f%02d.png")]
            )
            run = subprocess.run(
                cmd,
                capture_output=True,
                timeout=60,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            if run.returncode != 0:
                continue
            import numpy as np
            from PIL import Image
            frames = []
            for p in sorted(Path(tmpdir).glob("f*.png")):
                img = Image.open(p).convert("RGB")
                frames.append(np.asarray(img))
            if len(frames) >= 1:
                return frames
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        finally:
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass
    return []
