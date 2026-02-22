# -*- coding: utf-8 -*-
"""抽帧（FFmpeg+GPU 优先，回退 OpenCV）+ 拼图。"""

import sys
from pathlib import Path

from config import USE_FFMPEG_GPU, FFMPEG_HWACCEL

_CAP_PROP_FRAME_WIDTH = 3
_CAP_PROP_FRAME_HEIGHT = 4
_CAP_PROP_FPS = 5
_cv2_warned = False


def get_video_metadata(video_path: str | Path) -> dict | None:
    """读取视频元数据。返回 duration_sec, width, height, resolution。"""
    try:
        import cv2
    except ImportError:
        return None
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None
    try:
        w = int(cap.get(_CAP_PROP_FRAME_WIDTH) or 0)
        h = int(cap.get(_CAP_PROP_FRAME_HEIGHT) or 0)
        n = int(cap.get(7) or 0)
        fps = float(cap.get(_CAP_PROP_FPS) or 0)
        dur = round((n / fps), 2) if fps > 0 else None
        return {"duration_sec": dur, "width": w or None, "height": h or None, "resolution": f"{w}x{h}" if (w and h) else None}
    finally:
        cap.release()


def _extract_opencv(video_path: Path, num_frames: int, max_width: int):
    try:
        import cv2
    except ImportError:
        global _cv2_warned
        if not _cv2_warned:
            _cv2_warned = True
            print("请安装 opencv-python", file=sys.stderr)
        return []
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return []
    total = int(cap.get(7) or 0)
    if total <= 0:
        cap.release()
        return []
    indices = [min(int((i + 1) * total / (num_frames + 1)), total - 1) if total > 1 else 0 for i in range(num_frames)]
    frames = []
    for idx in indices:
        cap.set(1, idx)
        ret, frame = cap.read()
        if not ret or frame is None:
            continue
        h, w = frame.shape[:2]
        if w > max_width:
            frame = cv2.resize(frame, (max_width, int(h * max_width / w)), interpolation=cv2.INTER_AREA)
        frames.append(frame[:, :, ::-1])
    cap.release()
    return frames


def extract_frames(video_path: Path, num_frames: int, max_width: int, duration_sec: float | None = None):
    """均匀截取 num_frames 帧。优先 FFmpeg+GPU，回退 OpenCV。duration_sec 已有时可传入以省一次 ffprobe。"""
    if USE_FFMPEG_GPU:
        try:
            from ffmpeg_frames import extract_frames_ffmpeg
            f = extract_frames_ffmpeg(video_path, num_frames, max_width, FFMPEG_HWACCEL, duration_sec=duration_sec)
            if f:
                return f
        except Exception:
            pass
    return _extract_opencv(video_path, num_frames, max_width)


def save_animated_gif(frames, path: str | Path, duration_ms: int = 280) -> None:
    """将多帧保存为循环 GIF，用于悬停预览。"""
    if not frames:
        return
    try:
        from PIL import Image
    except ImportError:
        return
    path = Path(path)
    images = [Image.fromarray(f) for f in frames]
    try:
        images[0].save(
            str(path),
            save_all=True,
            append_images=images[1:],
            duration=duration_ms,
            loop=0,
        )
    except Exception:
        pass


def stitch_frames(frames, gap: int = 4):
    """多帧横向拼接成一张图。"""
    if not frames:
        return None
    try:
        from PIL import Image
    except ImportError:
        print("请安装 Pillow", file=sys.stderr)
        return None
    images = [Image.fromarray(f) for f in frames]
    w = sum(im.width for im in images) + gap * (len(images) - 1)
    h = max(im.height for im in images)
    out = Image.new("RGB", (w, h), (30, 30, 30))
    x = 0
    for im in images:
        out.paste(im, (x, 0))
        x += im.width + gap
    return out
