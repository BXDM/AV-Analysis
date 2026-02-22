# -*- coding: utf-8 -*-
"""
方案一：视频缩略图阵列。
遍历子文件夹，为每个视频在等分时间点截帧并拼成一张索引图。
- 使用 OpenCV 读视频、取帧，Pillow 拼接。
- UTF-8 路径，跳过已存在缩略图（可配置）。
"""

import os
import sys
from pathlib import Path

from config import (
    VIDEO_EXTENSIONS,
    THUMBNAIL_FRAME_COUNT,
    THUMBNAIL_MAX_WIDTH,
    THUMBNAILS_DIR,
    SKIP_EXISTING_THUMBNAILS,
    USE_FFMPEG_GPU,
    FFMPEG_HWACCEL,
    is_video,
)


def _safe_path(s: str) -> Path:
    """使用 pathlib 与 str 保证 Windows/中文/日文路径正常。"""
    return Path(s)


def get_video_duration_frames(cap) -> int:
    """总帧数。"""
    return int(cap.get(0x00000007))  # cv2.CAP_PROP_FRAME_COUNT


# OpenCV 属性常量（避免依赖 cv2 仅为此处）
_CAP_PROP_FRAME_WIDTH = 3
_CAP_PROP_FRAME_HEIGHT = 4
_CAP_PROP_FPS = 5


def get_video_metadata(video_path: str | Path) -> dict | None:
    """
    读取视频元数据（不解码帧）。返回 dict: duration_sec, width, height, resolution。
    resolution 为 "宽x高" 如 "1920x1080"，失败返回 None。
    """
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
        frame_count = int(cap.get(0x00000007) or 0)
        fps = float(cap.get(_CAP_PROP_FPS) or 0)
        duration_sec = (frame_count / fps) if fps > 0 else None
        resolution = f"{w}x{h}" if (w and h) else None
        return {
            "duration_sec": round(duration_sec, 2) if duration_sec is not None else None,
            "width": w or None,
            "height": h or None,
            "resolution": resolution,
        }
    finally:
        cap.release()


_cv2_import_warned = False


def _extract_frames_opencv(video_path: Path, num_frames: int, max_width: int):
    """OpenCV CPU 解码抽帧。返回 list of RGB 数组，失败返回空列表。"""
    global _cv2_import_warned
    try:
        import cv2
    except ImportError:
        if not _cv2_import_warned:
            _cv2_import_warned = True
            print("请安装 opencv-python: pip install opencv-python", file=sys.stderr)
        return []

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return []

    total = get_video_duration_frames(cap)
    if total <= 0:
        cap.release()
        return []

    indices = []
    for i in range(num_frames):
        pos = int((i + 1) * total / (num_frames + 1))
        indices.append(min(pos, total - 1) if total > 1 else 0)

    frames = []
    for idx in indices:
        cap.set(0x00000001, idx)
        ret, frame = cap.read()
        if not ret or frame is None:
            continue
        h, w = frame.shape[:2]
        if w > max_width:
            scale = max_width / w
            new_w = max_width
            new_h = int(h * scale)
            frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
        frame_rgb = frame[:, :, ::-1]
        frames.append(frame_rgb)

    cap.release()
    return frames


def extract_frames(video_path: Path, num_frames: int, max_width: int):
    """
    从视频中均匀截取 num_frames 帧。优先 FFmpeg+GPU，失败则回退 OpenCV。
    返回 list of RGB 数组 (H, W, 3)，失败返回空列表。
    """
    if USE_FFMPEG_GPU:
        try:
            from ffmpeg_frames import extract_frames_ffmpeg
            frames = extract_frames_ffmpeg(video_path, num_frames, max_width, FFMPEG_HWACCEL)
            if frames:
                return frames
        except Exception:
            pass
    return _extract_frames_opencv(video_path, num_frames, max_width)


def stitch_frames(frames, gap: int = 4):
    """将多帧横向拼接成一张图，gap 为间距（像素）。"""
    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        print("请安装 Pillow: pip install Pillow", file=sys.stderr)
        return None

    if not frames:
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


def thumbnail_path_for_video(video_path: Path, thumb_dir: Path) -> Path:
    """与视频同名的缩略图路径（放在 thumb_dir 下，扩展名 .jpg）。"""
    name = video_path.stem + "_thumb.jpg"
    return thumb_dir / name


def process_one_video(video_path: Path, output_dir: Path, num_frames: int, max_width: int, skip_existing: bool) -> bool:
    """处理单个视频，生成缩略图。返回是否成功。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = thumbnail_path_for_video(video_path, output_dir)

    if skip_existing and out_path.exists():
        return True  # 视为“已处理”

    frames = extract_frames(video_path, num_frames, max_width)
    if not frames:
        return False
    img = stitch_frames(frames)
    if img is None:
        return False
    try:
        img.save(str(out_path), "JPEG", quality=85)
        return True
    except Exception:
        return False


def walk_and_thumbnail(
    root: str,
    num_frames: int = THUMBNAIL_FRAME_COUNT,
    max_width: int = THUMBNAIL_MAX_WIDTH,
    thumb_subdir: str = THUMBNAILS_DIR,
    skip_existing: bool = SKIP_EXISTING_THUMBNAILS,
):
    """
    遍历 root 下所有子目录，对每个视频生成缩略图。
    缩略图保存在 视频所在目录 / thumb_subdir / 视频名_thumb.jpg
    """
    root = _safe_path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"目录不存在: {root}")

    results = {"ok": 0, "skip": 0, "fail": 0}
    for dirpath, _dirs, files in os.walk(str(root)):
        dirpath = Path(dirpath)
        thumb_dir = dirpath / thumb_subdir
        for f in files:
            if not is_video(f):
                continue
            video_path = dirpath / f
            out_path = thumbnail_path_for_video(video_path, thumb_dir)
            if skip_existing and out_path.exists():
                results["skip"] += 1
                continue
            if process_one_video(video_path, thumb_dir, num_frames, max_width, skip_existing=False):
                results["ok"] += 1
            else:
                results["fail"] += 1
    return results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python video_thumbnails.py <资源目录>")
        sys.exit(1)
    root = sys.argv[1]
    r = walk_and_thumbnail(root)
    print(f"缩略图: 新生成 {r['ok']}, 已跳过 {r['skip']}, 失败 {r['fail']}")
