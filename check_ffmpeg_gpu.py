# -*- coding: utf-8 -*-
"""
检测 FFmpeg 与 GPU 硬解是否可用、是否生效。可直接运行或通过 main.py check-gpu 调用。
"""

import subprocess
import sys
from pathlib import Path


def _run(cmd: list, timeout: int = 15) -> tuple[int, str, str]:
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        return r.returncode, (r.stdout or ""), (r.stderr or "")
    except FileNotFoundError:
        return -1, "", "命令未找到"
    except subprocess.TimeoutExpired:
        return -1, "", "超时"
    except Exception as e:
        return -1, "", str(e)


def check_ffmpeg_path() -> tuple[bool, str]:
    import shutil
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg:
        return False, "ffmpeg 未找到（请安装并加入 PATH）"
    if not ffprobe:
        return False, "ffprobe 未找到（通常与 ffmpeg 同目录，请一并加入 PATH）"
    return True, f"ffmpeg: {ffmpeg}\nffprobe: {ffprobe}"


def check_hwaccels() -> str:
    import shutil
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return "（无法检测：未找到 ffmpeg）"
    code, out, err = _run([ffmpeg, "-hwaccels"])
    if code != 0:
        return f"（运行 ffmpeg -hwaccels 失败）\n{err.strip()}"
    return out.strip() or err.strip()


def check_hwaccel_works(hwaccel: str) -> tuple[bool, str]:
    """尝试用指定 hwaccel 解码一帧（用 lavfi 生成 1 帧测试输入），看是否报错。"""
    import shutil
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False, "未找到 ffmpeg"
    # 用 lavfi 生成 1 秒测试视频，用 GPU 解码再立即结束（-frames:v 1）
    # -f lavfi -i testsrc=duration=1 生成 1 秒；-hwaccel cuda 会用于解码（若输入是 raw 则可能不经过 GPU）
    # 更可靠：用 -hwaccel cuda -i 一个真实文件 -frames:v 1 -f null -；没有文件就只报“是否支持”
    # 我们改为：仅检测该 hwaccel 是否被 ffmpeg 接受（不报 Unknown decoder）
    code, out, err = _run([
        ffmpeg, "-y", "-hwaccel", hwaccel,
        "-f", "lavfi", "-i", "testsrc=duration=0.1:size=320x240:rate=1",
        "-frames:v", "1", "-f", "null", "-"
    ], timeout=10)
    if code == 0:
        return True, "可用"
    err_lower = err.lower()
    if "unknown" in err_lower and "hwaccel" in err_lower or "not found" in err_lower:
        return False, "不支持或驱动未安装"
    # 其他错误（如 lavfi 不可用）也视为该 hwaccel 可能不可用
    return False, err.strip()[:200]


def run(video_path: str | None = None) -> None:
    from config import USE_FFMPEG_GPU, FFMPEG_HWACCEL

    print("========== FFmpeg + GPU 检测 ==========\n")
    print("[配置]")
    print(f"  USE_FFMPEG_GPU = {USE_FFMPEG_GPU}")
    print(f"  FFMPEG_HWACCEL = {FFMPEG_HWACCEL!r}\n")

    print("[1] FFmpeg / ffprobe 路径")
    ok, msg = check_ffmpeg_path()
    if not ok:
        print(f"  未通过: {msg}")
        print("\n结论: 请安装 FFmpeg 并将 ffmpeg、ffprobe 加入 PATH 后重试。")
        return
    print(f"  通过\n{msg}\n")

    print("[2] 当前 FFmpeg 支持的硬件加速 (ffmpeg -hwaccels)")
    hwaccels_out = check_hwaccels()
    print(hwaccels_out)
    print()

    if USE_FFMPEG_GPU and FFMPEG_HWACCEL:
        try_order = ["cuda", "d3d11va", "dxva2"] if FFMPEG_HWACCEL == "auto" else [FFMPEG_HWACCEL]
        print("[3] 各 hwaccel 实际可用性（解码测试）")
        for accel in try_order:
            if not accel:
                print("  (无/CPU): 跳过测试")
                continue
            works, detail = check_hwaccel_works(accel)
            status = "可用" if works else "不可用"
            print(f"  {accel}: {status}  {detail if not works and detail else ''}")
        print()

    if video_path:
        path = Path(video_path).resolve()
        if not path.is_file():
            print(f"[4] 抽帧测试: 文件不存在 {path}")
            return
        print("[4] 使用 FFmpeg 抽帧测试（实际抽 1 帧）")
        try:
            from ffmpeg_frames import extract_frames_ffmpeg
            from config import FFMPEG_HWACCEL, THUMBNAIL_FRAME_COUNT, THUMBNAIL_MAX_WIDTH
            frames = extract_frames_ffmpeg(path, 1, THUMBNAIL_MAX_WIDTH, FFMPEG_HWACCEL)
            if frames:
                print(f"  成功: 抽得 {len(frames)} 帧, 形状 {frames[0].shape}")
            else:
                print("  失败: 未得到帧（将回退到 OpenCV）")
        except Exception as e:
            print(f"  异常: {e}")
    else:
        print("[4] 抽帧测试: 未指定视频文件。可用: python main.py check-gpu <视频路径>")

    print("\n========== 检测结束 ==========")


if __name__ == "__main__":
    video = sys.argv[1] if len(sys.argv) > 1 else None
    run(video)
