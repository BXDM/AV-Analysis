# -*- coding: utf-8 -*-
"""
主入口：扫描结果写入 DuckDB，缩略图/报告写入单独目录，不破坏原目录结构。
用法:
  python main.py scan <资源目录> [输出目录]   # 推荐：扫描到 DuckDB + 单独输出目录
  python main.py clean <资源目录>             # 删除该目录下所有 _thumbnails（恢复原结构）
  python main.py report <资源目录>            # 仅生成纯文字报告（写到指定路径或输出目录）
  python main.py chart <资源目录>             # 仅生成关键词图表
  python main.py analysis <资源目录>          # 报告 + 图表
  python main.py html <资源目录> [输出路径]   # 生成 HTML 索引
  python main.py duplicates <输出目录或report.duckdb路径> [--out 文件]  # 按 file_hash 列出相同文件
  python main.py query <输出目录或db路径> [--sql "SQL"] [--out 文件]   # 查历史：写入时间、清晰度、大小、时长等
  python main.py thumbnails <资源目录>        # 旧方案：缩略图写回各视频目录（不推荐）
  python main.py all <资源目录>               # 旧方案一站式（不推荐，请用 scan）
"""

import argparse
import hashlib
import sys
from pathlib import Path

from config import OUTPUT_DB_NAME


def _default_output_dir(root: str) -> str:
    """未指定时，输出目录 = 项目目录/output/<根路径的短哈希>。"""
    base = Path(__file__).resolve().parent / "output"
    h = hashlib.sha256(root.encode("utf-8")).hexdigest()[:12]
    return str(base / h)


def cmd_scan(root: str, output_dir: str | None, workers: int | None = None) -> None:
    """扫描到 DuckDB，缩略图与报告写入 output_dir，不写回视频目录。"""
    from scan_db import scan_to_output
    out = output_dir or _default_output_dir(root)
    r = scan_to_output(root, out, workers=workers)
    print(f"缩略图: 新生成 {r['ok']}, 已跳过 {r['skip']}, 失败 {r['fail']}")
    print("结果目录:", out)


def _safe_print_path(p: str) -> None:
    """避免 Windows 控制台 GBK 无法编码时报错。"""
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        print("  ", p)
    except UnicodeEncodeError:
        print("  ", p.encode(enc, errors="replace").decode(enc))


def cmd_clean(root: str) -> None:
    """删除 root 下所有 _thumbnails 目录，恢复原有文件结构。"""
    from clean_thumbnails import clean_under
    r = clean_under(root)
    print(f"已删除 {r['deleted']} 个 _thumbnails 目录")
    for p in r["paths"]:
        _safe_print_path(p)


def _resolve_db_path(path: str) -> Path:
    """若 path 是目录则返回 path/report.duckdb，否则视为 db 文件路径。"""
    p = Path(path).resolve()
    if p.is_dir():
        return p / OUTPUT_DB_NAME
    return p


def cmd_query(db_or_output: str, sql: str | None, out_file: str | None) -> None:
    """查询 DuckDB：默认列出 path, name, file_mtime, duration_sec, width, height, file_size；或执行 --sql。"""
    import duckdb
    db_path = _resolve_db_path(db_or_output)
    if not db_path.is_file():
        print("错误：未找到 DuckDB 文件", db_path, file=sys.stderr)
        sys.exit(1)
    con = duckdb.connect(str(db_path))
    if sql:
        q = sql
    else:
        q = """
        SELECT path, name, file_mtime, duration_sec, width, height, file_size
        FROM videos
        ORDER BY file_mtime DESC NULLS LAST
        LIMIT 500
        """
    result = con.execute(q)
    rows = result.fetchall()
    try:
        cols = [d[0] for d in result.description]
    except Exception:
        cols = ["path", "name", "file_mtime", "duration_sec", "width", "height", "file_size"][: len(rows[0])] if rows else []
    con.close()
    if not rows:
        print("(无记录)")
        return
    lines = ["\t".join(str(c) for c in cols)] if cols else []
    for r in rows:
        parts = []
        for x in r:
            if x is None:
                parts.append("")
            elif isinstance(x, float):
                parts.append(str(round(x, 2)))
            else:
                parts.append(str(x))
        lines.append("\t".join(parts))
    text = "\n".join(lines)
    if out_file:
        Path(out_file).write_text(text, encoding="utf-8")
        print("已写入:", out_file)
    else:
        print(text)


def cmd_duplicates(db_or_output: str, out_file: str | None) -> None:
    """按 file_hash 检索相同文件，列出所有重复组。"""
    import duckdb
    db_path = _resolve_db_path(db_or_output)
    if not db_path.is_file():
        print("错误：未找到 DuckDB 文件", db_path, file=sys.stderr)
        sys.exit(1)
    con = duckdb.connect(str(db_path))
    # 按 file_hash 分组，只保留出现多于 1 次的
    rows = con.execute("""
        SELECT file_hash, list(path) AS paths, count(*) AS cnt
        FROM videos
        WHERE file_hash IS NOT NULL
        GROUP BY file_hash
        HAVING count(*) > 1
        ORDER BY count(*) DESC
    """).fetchall()
    con.close()
    lines = []
    lines.append(f"# 相同文件（按 file_hash 重复，共 {len(rows)} 组）")
    lines.append("")
    for i, (fh, paths, cnt) in enumerate(rows, 1):
        lines.append(f"## 组 {i}  hash={fh}  共 {cnt} 个相同文件")
        for path in paths:
            lines.append(f"  {path}")
        lines.append("")
    text = "\n".join(lines)
    if out_file:
        Path(out_file).write_text(text, encoding="utf-8")
        print("已写入:", out_file)
    else:
        print(text)


def cmd_thumbnails(root: str) -> None:
    from video_thumbnails import walk_and_thumbnail
    r = walk_and_thumbnail(root)
    print(f"缩略图: 新生成 {r['ok']}, 已跳过 {r['skip']}, 失败 {r['fail']}")


def cmd_report(root: str) -> None:
    from filename_analysis import scan_directory, text_report
    records, counter = scan_directory(root)
    out = Path(root) / "video_report.txt"
    text_report(records, counter, str(out))
    print("已保存文字报告:", out)


def cmd_chart(root: str) -> None:
    from filename_analysis import scan_directory, plot_summary
    _, counter = scan_directory(root)
    plot_summary(counter, output_path=str(Path(root) / "keyword_summary.png"))


def cmd_analysis(root: str) -> None:
    from filename_analysis import run_analysis
    run_analysis(
        root,
        report_txt=str(Path(root) / "video_report.txt"),
        chart_path=str(Path(root) / "keyword_summary.png"),
    )


def cmd_html(root: str, output: str | None) -> None:
    from html_index import build_index
    build_index(root, output_html=output)


def cmd_all(root: str) -> None:
    root = str(Path(root).resolve())
    print("1/3 生成缩略图...")
    cmd_thumbnails(root)
    print("2/3 生成报告与图表...")
    cmd_analysis(root)
    print("3/3 生成 HTML 索引...")
    cmd_html(root, str(Path(root) / "index.html"))
    print("全部完成。可在资源根目录打开 index.html 查看。")


def main():
    parser = argparse.ArgumentParser(description="视频资源梗概：缩略图、文件名分析、HTML 索引")
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="扫描到 DuckDB，缩略图/报告写入单独目录（推荐）")
    p_scan.add_argument("root", help="资源根目录")
    p_scan.add_argument("output", nargs="?", default=None, help="输出目录（默认：项目/output/<哈希>）")
    p_scan.add_argument("--workers", "-j", type=int, default=None, metavar="N", help="并行进程数，默认自动(CPU 核心数)")

    p_clean = sub.add_parser("clean", help="删除资源目录下所有 _thumbnails，恢复原结构")
    p_clean.add_argument("root", help="资源根目录")

    p_dup = sub.add_parser("duplicates", help="按 file_hash 列出相同文件（需先 scan）")
    p_dup.add_argument("db_or_output", help="输出目录或 report.duckdb 路径")
    p_dup.add_argument("--out", "-o", default=None, help="写入该文件，不指定则打印到终端")

    p_query = sub.add_parser("query", help="查询历史：写入时间、清晰度、大小、时长等（默认按 file_mtime 倒序）")
    p_query.add_argument("db_or_output", help="输出目录或 report.duckdb 路径")
    p_query.add_argument("--sql", default=None, help="自定义 SQL，不指定则输出 path,name,file_mtime,duration_sec,width,height,file_size")
    p_query.add_argument("--out", "-o", default=None, help="写入该文件")

    p_check = sub.add_parser("check-gpu", help="检测 FFmpeg 与 GPU 硬解是否可用、是否生效")
    p_check.add_argument("video", nargs="?", default=None, help="可选：指定一个视频文件做抽帧测试")

    for name in ("thumbnails", "report", "chart", "analysis", "all"):
        p = sub.add_parser(name, help={"thumbnails": "旧方案：缩略图写回各视频目录", "report": "仅生成纯文字报告", "chart": "仅生成关键词图表", "analysis": "报告+图表", "all": "旧方案一站式"}[name])
        p.add_argument("root", help="资源根目录")

    p_html = sub.add_parser("html", help="生成 HTML 交互式索引页")
    p_html.add_argument("root", help="资源根目录")
    p_html.add_argument("output", nargs="?", default=None, help="输出的 HTML 路径（默认：资源根/index.html）")

    args = parser.parse_args()
    if args.command == "duplicates":
        cmd_duplicates(args.db_or_output, getattr(args, "out", None))
        return
    if args.command == "query":
        cmd_query(args.db_or_output, getattr(args, "sql", None), getattr(args, "out", None))
        return
    if args.command == "check-gpu":
        from check_ffmpeg_gpu import run as check_gpu_run
        check_gpu_run(getattr(args, "video", None))
        return
    root = getattr(args, "root", None)
    if not root:
        parser.error("需要指定资源目录")
    root = str(Path(root).resolve())
    if not Path(root).is_dir():
        print("错误：目录不存在", root, file=sys.stderr)
        sys.exit(1)

    if args.command == "scan":
        cmd_scan(root, getattr(args, "output", None), getattr(args, "workers", None))
    elif args.command == "clean":
        cmd_clean(root)
    elif args.command == "thumbnails":
        cmd_thumbnails(root)
    elif args.command == "report":
        cmd_report(root)
    elif args.command == "chart":
        cmd_chart(root)
    elif args.command == "analysis":
        cmd_analysis(root)
    elif args.command == "html":
        cmd_html(root, getattr(args, "output", None))
    elif args.command == "all":
        cmd_all(root)


if __name__ == "__main__":
    main()
