# -*- coding: utf-8 -*-
"""主入口：scan / clean / query / duplicates / check-gpu。"""
import argparse
import sys
from pathlib import Path

import commands


def main():
    p = argparse.ArgumentParser(description="视频资源梗概：扫描→DuckDB+输出目录，不写回原目录")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("scan", help="扫描到 DuckDB，缩略图/报告/HTML 写入单独目录")
    sp.add_argument("root", help="资源根目录")
    sp.add_argument("output", nargs="?", default=None, help="输出目录（默认 output/<哈希>）")
    sp.add_argument("--workers", "-j", type=int, default=None, help="并行进程数")

    sp = sub.add_parser("clean", help="删除资源目录下所有 _thumbnails（按需）")
    sp.add_argument("root", help="资源根目录")

    sp = sub.add_parser("query", help="查询 DuckDB：写入时间、清晰度、大小、时长")
    sp.add_argument("db_or_output", help="输出目录或 report.duckdb")
    sp.add_argument("--sql", default=None, help="自定义 SQL")
    sp.add_argument("--out", "-o", default=None, help="写入文件")

    sp = sub.add_parser("duplicates", help="按 file_hash 列出相同文件")
    sp.add_argument("db_or_output", help="输出目录或 report.duckdb")
    sp.add_argument("--out", "-o", default=None, help="写入文件")

    sp = sub.add_parser("check-gpu", help="检测 FFmpeg 与 GPU 是否可用")
    sp.add_argument("video", nargs="?", default=None, help="可选：视频路径做抽帧测试")

    args = p.parse_args()

    if args.command == "duplicates":
        commands.cmd_duplicates(args.db_or_output, getattr(args, "out", None))
        return
    if args.command == "query":
        commands.cmd_query(args.db_or_output, getattr(args, "sql", None), getattr(args, "out", None))
        return
    if args.command == "check-gpu":
        commands.cmd_check_gpu(getattr(args, "video", None))
        return

    root = getattr(args, "root", None)
    if not root:
        p.error("需要指定资源目录")
    root = str(Path(root).resolve())
    if not Path(root).is_dir():
        print("错误：目录不存在", root, file=sys.stderr)
        sys.exit(1)

    if args.command == "scan":
        commands.cmd_scan(root, getattr(args, "output", None), getattr(args, "workers", None))
    elif args.command == "clean":
        commands.cmd_clean(root)


if __name__ == "__main__":
    main()
