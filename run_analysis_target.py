# -*- coding: utf-8 -*-
"""通过 target_dir.txt 指定目录并执行扫描，避免命令行中文路径问题。先清理 _thumbnails，再扫描到 DuckDB + 单独输出目录。"""
import sys
from pathlib import Path

# 优先从同目录下的 target_dir.txt 读取路径（第一行）
CONFIG = Path(__file__).parent / "target_dir.txt"
DEFAULT_ROOT = r"F:\迅雷下载\二十大报告\中国近代史纲要"


def main():
    if CONFIG.exists():
        root = CONFIG.read_text(encoding="utf-8").strip().splitlines()[0].strip()
    else:
        root = DEFAULT_ROOT
    if not root or not Path(root).is_dir():
        print("错误：目录不存在或未配置。请编辑 target_dir.txt 写入资源根目录路径（UTF-8），或修改本脚本中的 DEFAULT_ROOT。", file=sys.stderr)
        sys.exit(1)
    # 先清理曾写入视频目录的 _thumbnails
    from main import cmd_clean, cmd_scan
    print("清理已有 _thumbnails...")
    cmd_clean(root)
    # 再扫描到单独输出目录（DuckDB + 缩略图 + 报告 + HTML）
    print("扫描到输出目录...")
    cmd_scan(root, None)


if __name__ == "__main__":
    main()
