# -*- coding: utf-8 -*-
"""CLI 命令：scan / clean / query / duplicates / check-gpu。"""

import os
import shutil
import sys
from pathlib import Path

from config import (
    OUTPUT_DB_NAME,
    THUMBNAILS_DIR,
    SCAN_OUTPUT_INSIDE_SOURCE,
    SCAN_OUTPUT_DIR,
    SCAN_SOURCE_DIR,
    QUICK_SCAN_MODE,
    THUMBNAIL_FRAME_COUNT,
)


def default_output_dir(root: str, inside_source: bool = True) -> str:
    """inside_source=True 时优先用 扫描源/AV-Summary，summary 随目录迁移。"""
    if inside_source and (SCAN_OUTPUT_INSIDE_SOURCE or "").strip():
        return str(Path(root).resolve() / (SCAN_OUTPUT_INSIDE_SOURCE or "").strip())
    import hashlib
    base = Path(__file__).resolve().parent / "output"
    h = hashlib.sha256(root.encode("utf-8")).hexdigest()[:12]
    return str(base / h)


def get_scan_source_and_output():
    """
    统一解析扫描源与输出目录：优先 config.SCAN_SOURCE_DIR，否则读 target_dir.txt 第一行。
    返回 (source_path: Path, output_path: Path) 或 (None, None)。output 使用 SCAN_OUTPUT_DIR 或 源/AV-Summary。
    """
    source = (SCAN_SOURCE_DIR or "").strip()
    if not source:
        cfg = Path(__file__).resolve().parent / "target_dir.txt"
        if cfg.exists():
            line = cfg.read_text(encoding="utf-8").strip().splitlines()
            if line:
                source = line[0].strip()
    if not source:
        return None, None
    source_path = Path(source).resolve()
    if not source_path.is_dir():
        return None, None
    if (SCAN_OUTPUT_DIR or "").strip():
        output_path = Path((SCAN_OUTPUT_DIR or "").strip()).resolve()
    else:
        output_path = source_path / ((SCAN_OUTPUT_INSIDE_SOURCE or "AV-Summary").strip() or "AV-Summary")
        output_path = output_path.resolve()
    return source_path, output_path


def safe_print_path(p: str) -> None:
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        print("  ", p)
    except UnicodeEncodeError:
        print("  ", p.encode(enc, errors="replace").decode(enc))


def resolve_db_path(path: str) -> Path:
    p = Path(path).resolve()
    return p / OUTPUT_DB_NAME if p.is_dir() else p


def cmd_scan(root: str, output_dir: str | None, workers: int | None = None) -> None:
    from scan_db import scan_to_output
    out = output_dir or default_output_dir(root)
    r = scan_to_output(root, out, workers=workers)
    print(f"缩略图: 新生成 {r['ok']}, 已跳过 {r['skip']}, 失败 {r['fail']}")
    print("结果目录:", out)


def cmd_clean(root: str) -> None:
    """删除 root 下所有 _thumbnails 目录（一次性/按需）。"""
    root = Path(root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"目录不存在: {root}")
    deleted = []
    for dirpath, dirnames, _ in os.walk(str(root), topdown=True):
        to_remove = [d for d in dirnames if d == THUMBNAILS_DIR]
        for d in to_remove:
            try:
                shutil.rmtree(Path(dirpath) / d)
                deleted.append(str(Path(dirpath) / d))
            except OSError:
                pass
        for d in to_remove:
            dirnames.remove(d)
    print(f"已删除 {len(deleted)} 个 _thumbnails 目录")
    for p in deleted:
        safe_print_path(p)


def cmd_query(db_or_output: str, sql: str | None, out_file: str | None) -> None:
    import duckdb
    db_path = resolve_db_path(db_or_output)
    if not db_path.is_file():
        print("错误：未找到 DuckDB 文件", db_path, file=sys.stderr)
        sys.exit(1)
    con = duckdb.connect(str(db_path))
    q = sql or """
        SELECT path, name, file_mtime, duration_sec, width, height, file_size
        FROM videos ORDER BY file_mtime DESC NULLS LAST LIMIT 500
    """
    result = con.execute(q)
    rows = result.fetchall()
    cols = [d[0] for d in result.description] if result.description else []
    con.close()
    if not rows:
        print("(无记录)")
        return
    lines = ["\t".join(str(c) for c in cols)] if cols else []
    for r in rows:
        parts = ["" if x is None else str(round(x, 2) if isinstance(x, float) else x) for x in r]
        lines.append("\t".join(parts))
    text = "\n".join(lines)
    if out_file:
        Path(out_file).write_text(text, encoding="utf-8")
        print("已写入:", out_file)
    else:
        print(text)


def cmd_duplicates(db_or_output: str, out_file: str | None) -> None:
    import duckdb
    db_path = resolve_db_path(db_or_output)
    if not db_path.is_file():
        print("错误：未找到 DuckDB 文件", db_path, file=sys.stderr)
        sys.exit(1)
    con = duckdb.connect(str(db_path))
    rows = con.execute("""
        SELECT file_hash, list(path), count(*) FROM videos
        WHERE file_hash IS NOT NULL GROUP BY file_hash HAVING count(*) > 1 ORDER BY count(*) DESC
    """).fetchall()
    con.close()
    lines = [f"# 相同文件（共 {len(rows)} 组）", ""]
    for i, (fh, paths, cnt) in enumerate(rows, 1):
        lines.append(f"## 组 {i}  hash={fh}  共 {cnt} 个")
        for path in paths:
            lines.append(f"  {path}")
        lines.append("")
    text = "\n".join(lines)
    if out_file:
        Path(out_file).write_text(text, encoding="utf-8")
        print("已写入:", out_file)
    else:
        print(text)


def cmd_check_gpu(video_path: str | None) -> None:
    from ffmpeg_frames import run_gpu_check
    run_gpu_check(video_path)


def cmd_index(output_dir: str) -> None:
    """仅根据已有 report.duckdb 重新生成 index.html（不重新扫描）。用于模板/样式更新后刷新索引页。"""
    import duckdb
    from html_index import build_index_from_db
    out = Path(output_dir).resolve()
    db_path = out / OUTPUT_DB_NAME
    if not db_path.is_file():
        print("错误：未找到", OUTPUT_DB_NAME, "于", out, file=sys.stderr)
        sys.exit(1)
    con = duckdb.connect(str(db_path))
    row = con.execute(
        "SELECT id, root_path FROM scans WHERE output_dir = ? ORDER BY id DESC LIMIT 1",
        [str(out)],
    ).fetchone()
    con.close()
    if not row:
        print("错误：该目录下无扫描记录", file=sys.stderr)
        sys.exit(1)
    scan_id, root_path = row[0], row[1]
    nf = 3 if QUICK_SCAN_MODE else THUMBNAIL_FRAME_COUNT
    build_index_from_db(str(db_path), str(out), scan_id=scan_id, title="视频索引", root_path=root_path, thumb_frames=nf)
    print("已重新生成索引页:", out / "index.html")
