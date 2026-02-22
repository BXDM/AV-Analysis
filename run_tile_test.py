# -*- coding: utf-8 -*-
"""
验证当前优化方案（FFmpeg Tile 一路出图 + 快寻道）是否可运行。
用 ffmpeg 生成一段约 5 秒的测试视频，再调用 extract_and_save_sprite_ffmpeg，检查输出 JPG。
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

def main():
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("FAIL: ffmpeg 未找到")
        return 1
    with tempfile.TemporaryDirectory(prefix="av_tile_test_") as tmp:
        tmp = Path(tmp)
        video = tmp / "test.mp4"
        jpg = tmp / "sprite.jpg"
        # 生成约 5 秒 640x360 测试视频
        r = subprocess.run(
            [ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc=duration=5:size=640x360:rate=30", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)],
            capture_output=True,
            timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        if r.returncode != 0 or not video.is_file():
            print("FAIL: 生成测试视频失败", r.stderr.decode("utf-8", errors="replace")[:500])
            return 1
        print("OK: 测试视频已生成", video.stat().st_size, "bytes")

        from ffmpeg_frames import get_video_metadata_ffprobe, extract_and_save_sprite_ffmpeg
        from config import FFMPEG_HWACCEL, THUMBNAIL_MAX_WIDTH

        meta = get_video_metadata_ffprobe(video)
        if not meta or not meta.get("duration_sec"):
            print("FAIL: ffprobe 未取得 duration")
            return 1
        duration = meta["duration_sec"]
        print("OK: duration_sec =", duration)

        ok = extract_and_save_sprite_ffmpeg(
            video, jpg, num_frames=3, max_width=THUMBNAIL_MAX_WIDTH, duration_sec=duration, hwaccel=FFMPEG_HWACCEL, timeout=60
        )
        if not ok or not jpg.is_file():
            print("FAIL: extract_and_save_sprite_ffmpeg 未生成 JPG")
            return 1
        print("OK: Tile 雪碧图已生成", jpg.stat().st_size, "bytes")
    print("\n===== 当前优化方案（FFmpeg Tile + 快寻道）运行正常 =====")
    return 0

if __name__ == "__main__":
    sys.exit(main())
