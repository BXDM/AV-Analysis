# -*- coding: utf-8 -*-
"""
通过 target_dir.txt 指定目录并执行扫描，避免命令行中文路径问题。
默认只执行 scan；若曾用旧方案在视频目录下生成过 _thumbnails，可加 --clean 先清理再扫描。
"""
import argparse
import sys
from pathlib import Path

CONFIG = Path(__file__).parent / "target_dir.txt"
DEFAULT_ROOT = r"F:\迅雷下载\二十大报告\中国近代史纲要"


def main():
    parser = argparse.ArgumentParser(description="按 target_dir.txt 或默认目录执行扫描")
    parser.add_argument("--clean", action="store_true", help="扫描前先删除该目录下所有 _thumbnails（一次性补救用）")
    args = parser.parse_args()

    if CONFIG.exists():
        root = CONFIG.read_text(encoding="utf-8").strip().splitlines()[0].strip()
    else:
        root = DEFAULT_ROOT
    if not root or not Path(root).is_dir():
        print("错误：目录不存在或未配置。请编辑 target_dir.txt 写入资源根目录路径（UTF-8），或修改本脚本中的 DEFAULT_ROOT。", file=sys.stderr)
        sys.exit(1)

    import commands
    if args.clean:
        print("清理已有 _thumbnails...")
        commands.cmd_clean(root)
    print("扫描到输出目录...")
    commands.cmd_scan(root, None)


if __name__ == "__main__":
    main()
