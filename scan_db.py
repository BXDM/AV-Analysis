# -*- coding: utf-8 -*-
"""
扫描视频目录，将结果写入 DuckDB；缩略图与报告写入单独输出目录，不修改原目录结构。
"""

import hashlib
import json
import os
from pathlib import Path
from datetime import datetime

from config import (
    is_video,
    OUTPUT_DB_NAME,
    OUTPUT_THUMBNAILS_SUBDIR,
    OUTPUT_REPORT_TXT,
    OUTPUT_CHART,
    OUTPUT_INDEX_HTML,
    THUMBNAIL_FRAME_COUNT,
    THUMBNAIL_MAX_WIDTH,
    SKIP_EXISTING_THUMBNAILS,
    QUICK_SCAN_MODE,
    FILE_HASH_ALGO,
    FILE_HASH_CHUNK_SIZE,
    FILE_HASH_SAMPLE,
    FILE_HASH_SAMPLE_SIZE,
    SCAN_WORKERS,
)


def compute_file_hash(file_path: str | Path) -> str | None:
    """
    计算文件内容哈希。返回 hex 字符串，失败返回 None。
    - 采样模式（FILE_HASH_SAMPLE=True）：只读头/中/尾各一段，大文件快，用于查重足够。
    - 全量模式：整文件逐块 SHA，精确但大文件耗时长。
    """
    path = Path(file_path)
    if not path.is_file():
        return None
    try:
        size = path.stat().st_size
        h = hashlib.new(FILE_HASH_ALGO)
        if FILE_HASH_SAMPLE and size > FILE_HASH_SAMPLE_SIZE * 2:
            # 头、中、尾各一段
            n = FILE_HASH_SAMPLE_SIZE
            with open(path, "rb") as f:
                h.update(f.read(n))
                f.seek(max(0, size // 2 - n // 2))
                h.update(f.read(n))
                f.seek(max(0, size - n))
                h.update(f.read(n))
        else:
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(FILE_HASH_CHUNK_SIZE)
                    if not chunk:
                        break
                    h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def thumb_filename_for_path(video_path: str) -> str:
    """根据视频绝对路径生成唯一缩略图文件名（避免重名）。"""
    h = hashlib.sha256(video_path.encode("utf-8")).hexdigest()[:16]
    return f"{h}.jpg"


def init_db(db_path: str) -> None:
    import duckdb
    con = duckdb.connect(db_path)
    con.execute("""
        CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY,
            root_path VARCHAR,
            output_dir VARCHAR,
            scanned_at TIMESTAMP
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            scan_id INTEGER NOT NULL,
            path VARCHAR NOT NULL,
            rel_path VARCHAR,
            name VARCHAR,
            thumbnail_file VARCHAR,
            file_size BIGINT,
            duration_sec DOUBLE,
            keywords_json VARCHAR,
            file_hash VARCHAR,
            file_mtime VARCHAR,
            width INTEGER,
            height INTEGER,
            PRIMARY KEY (scan_id, path)
        )
    """)
    # 兼容已有库：按需添加新列
    for col, typ in [("file_hash", "VARCHAR"), ("file_mtime", "VARCHAR"), ("width", "INTEGER"), ("height", "INTEGER")]:
        try:
            con.execute(f"SELECT {col} FROM videos LIMIT 0")
        except Exception:
            try:
                con.execute(f"ALTER TABLE videos ADD COLUMN {col} {typ}")
            except Exception:
                pass
    con.close()


def _worker_process_one(args: tuple) -> dict:
    """
    多进程 worker：处理单个视频（哈希、元数据、缩略图），返回一行数据。供 ProcessPoolExecutor 调用。
    args: (path, name, rel_path, thumb_dir_str, thumb_file, thumb_rel, num_frames, max_width, skip_existing)
    """
    (path, name, rel_path, thumb_dir_str, thumb_file, thumb_rel, num_frames, max_width, skip_existing) = args
    out = {
        "path": path,
        "rel_path": rel_path,
        "name": name,
        "thumbnail_file": None,
        "file_size": None,
        "duration_sec": None,
        "width": None,
        "height": None,
        "keywords_json": "[]",
        "file_hash": None,
        "file_mtime": None,
        "status": "fail",
    }
    try:
        from filename_analysis import extract_keywords
        out["keywords_json"] = json.dumps([list(k) for k in extract_keywords(name)], ensure_ascii=False)
    except Exception:
        pass
    p = Path(path)
    try:
        out["file_size"] = p.stat().st_size
        out["file_mtime"] = datetime.fromtimestamp(p.stat().st_mtime).isoformat()
    except OSError:
        pass
    out["file_hash"] = compute_file_hash(path)
    thumb_full = Path(thumb_dir_str) / thumb_file
    from config import USE_FFMPEG_GPU
    meta = None
    if USE_FFMPEG_GPU:
        try:
            from ffmpeg_frames import get_video_metadata_ffprobe
            meta = get_video_metadata_ffprobe(path)
        except Exception:
            pass
    if not meta:
        meta = get_video_metadata(path)
    if meta:
        out["duration_sec"] = meta["duration_sec"]
        out["width"] = meta["width"]
        out["height"] = meta["height"]
    # 缩略图已存在则跳过抽帧（仍已用 ffprobe 填好 width/height，角标可显示 360P/1080P/4K）
    if skip_existing and thumb_full.exists():
        out["thumbnail_file"] = thumb_rel
        out["status"] = "skip"
        return out
    duration_sec = out.get("duration_sec")
    # 优先：FFmpeg Tile 一次性出图（-ss 快寻道 + 无临时 PNG），失败再回退
    if duration_sec and duration_sec > 0:
        from config import USE_FFMPEG_GPU, FFMPEG_HWACCEL
        if USE_FFMPEG_GPU:
            try:
                from ffmpeg_frames import extract_and_save_sprite_ffmpeg
                if extract_and_save_sprite_ffmpeg(p, thumb_full, num_frames, max_width, duration_sec, FFMPEG_HWACCEL):
                    out["thumbnail_file"] = thumb_rel
                    out["status"] = "ok"
                    return out
            except Exception:
                pass
    from video_thumbnails import extract_frames, stitch_frames
    duration_for_frames = duration_sec if duration_sec and duration_sec > 0 else None
    frames = extract_frames(p, num_frames, max_width, duration_sec=duration_for_frames)
    if not frames:
        return out
    img = stitch_frames(frames)
    if img is None:
        return out
    try:
        img.save(str(thumb_full), "JPEG", quality=85)
        out["thumbnail_file"] = thumb_rel
        out["status"] = "ok"
    except Exception:
        pass
    return out


def get_video_metadata(path):
    """供 worker 内调用，避免在 scan_to_output 里重复 import。"""
    from video_thumbnails import get_video_metadata as _g
    return _g(path)


def _insert_row(con, scan_id: int, row_dict: dict, stats: dict) -> None:
    """将 worker 返回的一行数据写入 DuckDB 并更新 stats。"""
    row = [
        scan_id,
        row_dict["path"],
        row_dict["rel_path"],
        row_dict["name"],
        row_dict["thumbnail_file"],
        row_dict["file_size"],
        row_dict["duration_sec"],
        row_dict["keywords_json"],
        row_dict["file_hash"],
        row_dict["file_mtime"],
        row_dict["width"],
        row_dict["height"],
    ]
    con.execute("""
        INSERT INTO videos (scan_id, path, rel_path, name, thumbnail_file, file_size, duration_sec, keywords_json, file_hash, file_mtime, width, height)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, row)
    status = row_dict.get("status", "fail")
    if status == "ok":
        stats["ok"] += 1
    elif status == "skip":
        stats["skip"] += 1
    else:
        stats["fail"] += 1


def get_or_create_scan_id(con, root_path: str, output_dir: str) -> int:
    """同一 (root_path, output_dir) 复用同一 scan_id，便于重扫时先删后插、已删视频从库移除。"""
    root_s = str(Path(root_path).resolve())
    out_s = str(Path(output_dir).resolve())
    row = con.execute(
        "SELECT id FROM scans WHERE root_path = ? AND output_dir = ? ORDER BY id DESC LIMIT 1",
        [root_s, out_s],
    ).fetchone()
    if row:
        scan_id = row[0]
        con.execute("UPDATE scans SET scanned_at = ? WHERE id = ?", [datetime.now().isoformat(), scan_id])
        return scan_id
    cur = con.execute("SELECT max(id) FROM scans").fetchone()
    next_id = 1 if (cur[0] is None) else cur[0] + 1
    con.execute(
        "INSERT INTO scans (id, root_path, output_dir, scanned_at) VALUES (?, ?, ?, ?)",
        [next_id, root_s, out_s, datetime.now().isoformat()],
    )
    return next_id


def scan_to_output(
    root_path: str,
    output_dir: str,
    num_frames: int = THUMBNAIL_FRAME_COUNT,
    max_width: int = THUMBNAIL_MAX_WIDTH,
    skip_existing: bool = SKIP_EXISTING_THUMBNAILS,
    workers: int | None = None,
    progress_callback=None,
) -> dict:
    """
    扫描 root_path 下所有视频，缩略图与报告写入 output_dir，不修改原目录。
    - output_dir/thumbnails/<hash>.jpg
    - output_dir/report.duckdb
    - output_dir/video_report.txt, keyword_summary.png, index.html
    返回统计 { ok, skip, fail }。
    """
    root = Path(root_path).resolve()
    out = Path(output_dir).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"目录不存在: {root}")

    out.mkdir(parents=True, exist_ok=True)
    thumb_dir = out / OUTPUT_THUMBNAILS_SUBDIR
    thumb_dir.mkdir(parents=True, exist_ok=True)
    db_path = out / OUTPUT_DB_NAME

    if progress_callback:
        progress_callback(0, 0, None)  # 枚举阶段提示

    import duckdb
    init_db(str(db_path))
    con = duckdb.connect(str(db_path))
    scan_id = get_or_create_scan_id(con, str(root), str(out))
    con.execute("DELETE FROM videos WHERE scan_id = ?", [scan_id])  # 重扫时先删，已删视频从库移除

    from filename_analysis import scan_directory

    records, keyword_counter = scan_directory(str(root))
    stats = {"ok": 0, "skip": 0, "fail": 0}

    # 构建每个视频的 worker 参数（QUICK_SCAN_MODE 时 3 帧，抽帧密度减半）
    nf = 3 if QUICK_SCAN_MODE else num_frames
    arg_list = []
    for r in records:
        path = r["path"]
        name = r["name"]
        try:
            rel = str(Path(path).resolve().relative_to(root))
        except ValueError:
            rel = name
        thumb_file = thumb_filename_for_path(path)
        thumb_rel = f"{OUTPUT_THUMBNAILS_SUBDIR}/{thumb_file}"
        arg_list.append((path, name, rel, str(thumb_dir), thumb_file, thumb_rel, nf, max_width, skip_existing))

    workers = workers if workers is not None else (SCAN_WORKERS if SCAN_WORKERS > 0 else (os.cpu_count() or 4))
    workers = min(max(1, workers), len(arg_list), 32)
    total = len(arg_list)
    if progress_callback:
        progress_callback(0, total, None)
    if not progress_callback:
        print(f"扫描 {total} 个视频，使用 {workers} 个进程并行")

    if workers <= 1:
        for idx, args in enumerate(arg_list):
            row_dict = _worker_process_one(args)
            _insert_row(con, scan_id, row_dict, stats)
            if progress_callback:
                progress_callback(idx + 1, total, row_dict)
    else:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for idx, row_dict in enumerate(ex.map(_worker_process_one, arg_list, chunksize=1)):
                _insert_row(con, scan_id, row_dict, stats)
                if progress_callback:
                    progress_callback(idx + 1, total, row_dict)

    rows_for_report = con.execute(
        "SELECT path, file_size, thumbnail_file FROM videos WHERE scan_id = ?", [scan_id]
    ).fetchall()
    con.close()

    # 报告与图表写到 output_dir：单份 txt（Summary + 按目录分组的文件列表）、treemap 图
    from config import OUTPUT_TREEMAP
    from filename_analysis import write_single_report, plot_summary, report_tree_and_treemap
    write_single_report(
        str(db_path),
        scan_id,
        str(root),
        str(out),
        str(out / OUTPUT_REPORT_TXT),
        rows_for_report,
        keyword_counter,
    )
    plot_summary(keyword_counter, output_path=str(out / OUTPUT_CHART))
    report_tree_and_treemap(str(root), rows_for_report, str(out / OUTPUT_TREEMAP))

    # HTML 从 DB 读，缩略图在 output_dir 下；传 root_path 时用相对链接，thumb_frames 供前端雪碧图拨动
    from html_index import build_index_from_db
    build_index_from_db(str(db_path), str(out), scan_id=scan_id, root_path=str(root), thumb_frames=nf)

    return stats
