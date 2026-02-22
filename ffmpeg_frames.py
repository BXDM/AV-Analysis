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
            timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        if out.returncode != 0 or not out.stdout:
            return None
        data = json.loads(out.stdout.decode("utf-8", errors="replace"))
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
    duration_sec: float | None = None,
    fps: float | None = None,
) -> list:
    """
    用 FFmpeg（可选 GPU）从视频均匀截取 num_frames 帧，缩放到 max_width 宽。
    返回 list of RGB numpy 数组 (H,W,3)，失败返回空列表。
    duration_sec/fps 若已由外部传入则跳过 ffprobe，减少一次子进程。
    """
    ffmpeg = _ffmpeg_bin()
    if not ffmpeg:
        return []
    path = Path(video_path).resolve()
    if not path.is_file():
        return []

    # 未传入有效 duration 时才调 ffprobe，避免与 worker 内 get_video_metadata_ffprobe 重复
    if duration_sec is None or duration_sec <= 0:
        ffprobe_bin = _ffprobe_bin()
        if ffprobe_bin:
            try:
                out = subprocess.run(
                    [
                        ffprobe_bin,
                        "-v", "error",
                        "-select_streams", "v:0",
                        "-show_entries", "stream=duration,r_frame_rate",
                        "-of", "json",
                        str(path),
                    ],
                    capture_output=True,
                    timeout=15,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
                )
                if out.returncode == 0 and out.stdout:
                    data = json.loads(out.stdout.decode("utf-8", errors="replace"))
                    s = (data.get("streams") or [{}])[0]
                    if s.get("duration"):
                        duration_sec = float(s["duration"])
                    if s.get("r_frame_rate"):
                        fps = _parse_r_frame_rate(s["r_frame_rate"]) or 30.0
            except Exception:
                pass
        if duration_sec is None or duration_sec <= 0:
            duration_sec = 10.0
    if fps is None or fps <= 0:
        fps = 30.0
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


def extract_and_save_sprite_ffmpeg(
    video_path: str | Path,
    output_jpg_path: str | Path,
    num_frames: int,
    max_width: int,
    duration_sec: float,
    hwaccel: str = "auto",
    timeout: int = 60,
) -> bool:
    """
    用 FFmpeg 一次性生成雪碧图 JPG：-ss 在 -i 前（快寻道）+ tile 滤镜，无临时 PNG。
    成功返回 True，失败返回 False（调用方回退到 extract_frames + stitch）。
    """
    ffmpeg = _ffmpeg_bin()
    if not ffmpeg:
        return False
    path = Path(video_path).resolve()
    out_path = Path(output_jpg_path).resolve()
    if not path.is_file() or duration_sec <= 0:
        return False
    # 均匀时间点（秒），-ss 快寻道
    timestamps = [(i + 1) * duration_sec / (num_frames + 1) for i in range(num_frames)]
    try_order = ["cuda", "d3d11va", ""] if hwaccel == "auto" else [hwaccel] if hwaccel else [""]
    for accel in try_order:
        hw_args = _resolve_hwaccel(accel) if accel else []
        # 每个时间点一组 -ss -i，实现快寻道
        args = [ffmpeg, "-y"] + hw_args
        for t in timestamps:
            args.extend(["-ss", str(round(t, 2)), "-i", str(path)])
        # [0:v][1:v]... scale -> [v0][v1]... -> hstack 水平拼接（tile 在新版 FFmpeg 仅单路输入）
        scale_vf = f"scale={max_width}:-2"
        scale_parts = [f"[{i}:v]{scale_vf}[v{i}]" for i in range(num_frames)]
        stack_inputs = "".join(f"[v{i}]" for i in range(num_frames))
        filter_complex = ";".join(scale_parts) + f";{stack_inputs}hstack=inputs={num_frames}[out]"
        args.extend(["-filter_complex", filter_complex, "-map", "[out]", "-frames:v", "1", "-q:v", "3", str(out_path)])
        try:
            r = subprocess.run(
                args,
                capture_output=True,
                timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            if r.returncode == 0 and out_path.is_file():
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
    return False


def _run_cmd(cmd: list, timeout: int = 15) -> tuple[int, str, str]:
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        stdout = (r.stdout or b"").decode("utf-8", errors="replace")
        stderr = (r.stderr or b"").decode("utf-8", errors="replace")
        return r.returncode, stdout, stderr
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return -1, "", str(e)
    except Exception as e:
        return -1, "", str(e)


def run_gpu_check(video_path: str | None = None) -> None:
    """检测 FFmpeg 与 GPU 硬解是否可用。"""
    from config import USE_FFMPEG_GPU, FFMPEG_HWACCEL, THUMBNAIL_MAX_WIDTH
    print("========== FFmpeg + GPU 检测 ==========\n")
    print("[配置] USE_FFMPEG_GPU =", USE_FFMPEG_GPU, " FFMPEG_HWACCEL =", repr(FFMPEG_HWACCEL), "\n")

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg:
        print("[1] ffmpeg 未找到，请安装并加入 PATH")
        return
    if not ffprobe:
        print("[1] ffprobe 未找到")
        return
    print("[1] FFmpeg 路径:", ffmpeg, "\n")

    code, out, _ = _run_cmd([ffmpeg, "-hwaccels"])
    print("[2] 硬件加速 (ffmpeg -hwaccels)\n", out.strip() if code == 0 else "（失败）", "\n")

    if USE_FFMPEG_GPU and FFMPEG_HWACCEL:
        try_order = ["cuda", "d3d11va", "dxva2"] if FFMPEG_HWACCEL == "auto" else [FFMPEG_HWACCEL]
        print("[3] 解码测试")
        for accel in try_order:
            if not accel:
                continue
            code, _, err = _run_cmd([
                ffmpeg, "-y", "-hwaccel", accel,
                "-f", "lavfi", "-i", "testsrc=duration=0.1:size=320x240:rate=1",
                "-frames:v", "1", "-f", "null", "-"
            ], timeout=10)
            print(f"  {accel}: {'可用' if code == 0 else '不可用'}")
        print()

    if video_path and Path(video_path).is_file():
        print("[4] 抽帧测试")
        try:
            frames = extract_frames_ffmpeg(video_path, 1, THUMBNAIL_MAX_WIDTH, FFMPEG_HWACCEL)
            print(f"  成功: {len(frames)} 帧" if frames else "  失败")
        except Exception as e:
            print("  异常:", e)
    else:
        print("[4] 抽帧测试: 可指定视频路径，如 python main.py check-gpu <视频>")
    print("\n========== 检测结束 ==========")
