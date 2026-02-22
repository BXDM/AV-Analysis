# -*- coding: utf-8 -*-
"""
方案二：基于文件名的标签云与数据可视化。
用正则提取关键词（番号、分辨率等），统计频次并绘制饼图/柱状图。
"""

import os
import re
from pathlib import Path
from collections import Counter

from config import is_video


# 常用正则：分辨率、常见番号模式等（可按需扩展）
PATTERNS = [
    (r"\b(4K|2160p|1080p|720p|480p|360p)\b", "resolution"),
    (r"\b([A-Z]{2,5}-?\d{2,6})\b", "code"),   # 番号类
    (r"\[([^\]]+)\]", "bracket"),             # [xxx]
    (r"\b(HEVC|H\.?264|AVC|x264|x265)\b", "codec"),
]


def extract_keywords(filename: str) -> list[tuple[str, str]]:
    """从文件名提取 (关键词, 类型)。"""
    stem = Path(filename).stem
    out = []
    for pattern, kind in PATTERNS:
        for m in re.finditer(pattern, stem, re.IGNORECASE):
            out.append((m.group(1).strip(), kind))
    return out


def scan_directory(root: str) -> tuple[list[dict], Counter]:
    """
    遍历 root，收集每个视频的路径、文件名、提取的关键词。
    返回 (records, 全局关键词计数)。
    """
    root = Path(root)
    records = []
    all_keywords = Counter()

    for dirpath, _dirs, files in os.walk(str(root)):
        for f in files:
            if not is_video(f):
                continue
            full_path = Path(dirpath) / f
            keywords = extract_keywords(f)
            for kw, _ in keywords:
                all_keywords[kw] += 1
            records.append({
                "path": str(full_path),
                "name": f,
                "keywords": keywords,
            })
    return records, all_keywords


def plot_summary(keyword_counter: Counter, top_n: int = 20, output_path: str = "keyword_summary.png"):
    """绘制关键词频次柱状图与饼图（前 top_n）。"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("请安装 matplotlib: pip install matplotlib")
        return

    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    most = keyword_counter.most_common(top_n)
    if not most:
        print("没有提取到关键词，跳过绘图")
        return

    labels = [x[0] for x in most]
    counts = [x[1] for x in most]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 10))

    # 柱状图
    ax1.barh(range(len(labels)), counts, color="steelblue", alpha=0.8)
    ax1.set_yticks(range(len(labels)))
    ax1.set_yticklabels(labels, fontsize=9)
    ax1.invert_yaxis()
    ax1.set_xlabel("出现次数")
    ax1.set_title("文件名关键词频次（Top %d）" % top_n)

    # 饼图（前 10）
    n_pie = min(10, len(most))
    pie_labels = [x[0] for x in most[:n_pie]]
    pie_counts = [x[1] for x in most[:n_pie]]
    other = sum(x[1] for x in most[n_pie:])
    if other > 0:
        pie_labels.append("其他")
        pie_counts.append(other)
    ax2.pie(pie_counts, labels=pie_labels, autopct="%1.1f%%", startangle=90)
    ax2.set_title("关键词分布（前 %d）" % n_pie)

    plt.tight_layout()
    try:
        plt.savefig(output_path, dpi=120, bbox_inches="tight")
        print("已保存图表:", output_path)
    except (UnicodeDecodeError, UnicodeEncodeError) as e:
        print("保存图表时编码异常（如文件名含特殊字符），已跳过:", e)
    finally:
        plt.close()


def _format_size(size_bytes: int) -> str:
    if size_bytes is None or size_bytes < 0:
        return "0 B"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def _build_dir_stats(root_path: Path, rows: list) -> dict:
    """rows: [(path, file_size, thumbnail_file), ...]。返回 rel_dir -> (file_count, thumb_count, total_size)。"""
    root = root_path.resolve()
    stats = {}
    for path, file_size, thumb in rows:
        try:
            rel = Path(path).resolve().relative_to(root)
        except ValueError:
            rel = Path(path).name
        rel_dir = (str(rel.parent) if rel.parent != Path(".") else "").replace("\\", "/")
        size = file_size or 0
        if rel_dir not in stats:
            stats[rel_dir] = [0, 0, 0]
        stats[rel_dir][0] += 1
        if thumb:
            stats[rel_dir][1] += 1
        stats[rel_dir][2] += size
    return stats


def _tree_lines(dir_stats: dict, prefix: str = "", root_label: str = "根") -> list[str]:
    """生成树状文本行。dir_stats 的 key 为相对路径，空串表示根。"""
    lines = []
    root_count, root_thumbs, root_size = dir_stats.get("", (0, 0, 0))
    lines.append(f"{root_label}  ({root_count} 个文件, {root_thumbs} 张缩略图, {_format_size(root_size)})")
    keys = sorted(k for k in dir_stats if k != "")
    if not keys:
        return lines
    # 按层级组织：直接子目录 = 父为 "" 的为 "x"，父为 "a" 的为 "a/x"
    def children_of(parent: str):
        if not parent:
            return [k for k in keys if "/" not in k]
        pre = parent + "/"
        return [k for k in keys if k.startswith(pre) and "/" not in k[len(pre):]]

    def walk(parent: str, indent: str, is_last_sibling: bool):
        ch = children_of(parent)
        for i, k in enumerate(ch):
            is_last = i == len(ch) - 1
            count, thumbs, size = dir_stats[k]
            name = k.split("/")[-1] if "/" in k else k
            branch = "└── " if is_last else "├── "
            lines.append(f"{indent}{branch}{name}  ({count} 个文件, {thumbs} 张缩略图, {_format_size(size)})")
            add = "    " if is_last else "│   "
            walk(k, indent + add, is_last)

    walk("", "", True)
    return lines


def report_tree_and_treemap(
    root_path: str,
    db_rows: list,
    treemap_path: str,
):
    """
    根据 DB 行（path, file_size, thumbnail_file）按目录大小生成 treemap 图。目录树已并入 write_single_report。
    """
    root = Path(root_path).resolve()
    if not db_rows:
        return
    dir_stats = _build_dir_stats(root, db_rows)

    # Treemap：按目录大小
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import squarify
    except ImportError:
        print("treemap 需安装 squarify: pip install squarify，已跳过")
        return
    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    # 按大小排序，取前若干项，其余合并为「其他」
    items = [(k, dir_stats[k][2]) for k in dir_stats if dir_stats[k][2] > 0]
    items.sort(key=lambda x: -x[1])
    max_blocks = 32
    if len(items) <= max_blocks:
        labels = [("根" if k == "" else k.split("/")[-1]) for k, _ in items]
        sizes = [s for _, s in items]
    else:
        top = items[: max_blocks - 1]
        other_size = sum(s for _, s in items[max_blocks - 1 :])
        labels = [("根" if k == "" else k.split("/")[-1]) for k, _ in top] + ["其他"]
        sizes = [s for _, s in top] + [other_size]

    fig, ax = plt.subplots(figsize=(12, 8))
    colors = plt.cm.Set3(range(len(sizes)))
    squarify.plot(sizes=sizes, label=labels, color=colors, alpha=0.8, ax=ax, text_kw={"fontsize": 8})
    ax.set_title("按目录占用大小（Treemap）")
    ax.axis("off")
    try:
        plt.savefig(treemap_path, dpi=120, bbox_inches="tight")
        print("已保存 Treemap:", treemap_path)
    except Exception as e:
        print("保存 Treemap 时异常，已跳过:", e)
    finally:
        plt.close()


def _group_paths_by_dir(rows_for_report: list) -> list[tuple[str, list[str]]]:
    """rows: [(path, ...), ...]。返回 [(目录路径, [文件名, ...]), ...]，按目录排序。"""
    by_dir = {}
    for row in rows_for_report:
        path = row[0] if isinstance(row, (list, tuple)) else row.get("path", "")
        if not path:
            continue
        p = Path(path)
        dir_str = str(p.parent)
        name = p.name
        if dir_str not in by_dir:
            by_dir[dir_str] = []
        by_dir[dir_str].append(name)
    for names in by_dir.values():
        names.sort()
    return sorted(by_dir.items(), key=lambda x: x[0])


def write_single_report(
    db_path: str,
    scan_id: int,
    root_path: str,
    output_dir: str,
    report_path: str,
    rows_for_report: list,
    keyword_counter: Counter,
):
    """
    生成单份 txt 报告：前为 Summary（扫描信息、汇总、目录树、关键词），后为按目录分组的详细文件列表。
    """
    import duckdb
    from datetime import datetime

    con = duckdb.connect(db_path)
    try:
        scanned = con.execute("SELECT scanned_at FROM scans WHERE id = ?", [scan_id]).fetchone()
        scan_time = scanned[0] if scanned and scanned[0] else datetime.now().isoformat()
    except Exception:
        scan_time = datetime.now().isoformat()
    total = con.execute("SELECT count(*) FROM videos WHERE scan_id = ?", [scan_id]).fetchone()[0]
    ok_count = con.execute(
        "SELECT count(*) FROM videos WHERE scan_id = ? AND thumbnail_file IS NOT NULL AND thumbnail_file != ''",
        [scan_id],
    ).fetchone()[0]
    fail_count = con.execute(
        "SELECT count(*) FROM videos WHERE scan_id = ? AND (thumbnail_file IS NULL OR thumbnail_file = '')",
        [scan_id],
    ).fetchone()[0]
    dup_rows = con.execute(
        "SELECT file_hash, count(*) AS c FROM videos WHERE scan_id = ? AND file_hash IS NOT NULL GROUP BY file_hash HAVING count(*) > 1",
        [scan_id],
    ).fetchall()
    dup_groups = len(dup_rows)
    dup_files = sum(c for _, c in dup_rows)
    con.close()

    root = Path(root_path).resolve()
    dir_stats = _build_dir_stats(root, rows_for_report) if rows_for_report else {}
    tree_lines = _tree_lines(dir_stats) if dir_stats else []
    dir_file_list = _group_paths_by_dir(rows_for_report)

    lines = []
    lines.append("Summary")
    lines.append("-" * 40)
    lines.append("扫描时间  %s" % scan_time)
    lines.append("扫描源    %s" % root_path)
    lines.append("输出目录  %s" % output_dir)
    lines.append("")
    lines.append("汇总：  总视频数 %d  正常(有缩略图) %d  损坏/失败 %d  重复组 %d 组  涉及重复文件 %d 个" % (total, ok_count, fail_count, dup_groups, dup_files))
    lines.append("")
    lines.append("目录树（文件数 / 缩略图数 / 大小）")
    for t in tree_lines:
        lines.append("  " + t)
    lines.append("")
    lines.append("关键词 Top 20")
    for kw, cnt in (keyword_counter.most_common(20) if keyword_counter else []):
        lines.append("  %s  %d" % (kw, cnt))
    lines.append("")
    lines.append("=" * 40)
    lines.append("详细文件列表（按目录）")
    lines.append("")
    for dir_path, names in dir_file_list:
        lines.append("[%s]" % dir_path)
        for name in names:
            lines.append("  " + name)
        lines.append("")

    try:
        Path(report_path).write_text("\n".join(lines), encoding="utf-8")
        print("已保存报告:", report_path)
    except (UnicodeEncodeError, OSError) as e:
        print("保存报告时异常，已跳过:", e)


def text_report(records: list[dict], keyword_counter: Counter, output_path: str = "video_report.txt"):
    """纯文字列表报告：文件列表 + 关键词统计。"""
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("=== 视频文件列表 ===\n\n")
            for r in records:
                f.write(r["path"] + "\n")
            f.write("\n=== 关键词统计（Top 50）===\n\n")
            for kw, cnt in keyword_counter.most_common(50):
                f.write(f"  {kw}: {cnt}\n")
        print("已保存文字报告:", output_path)
    except (UnicodeDecodeError, UnicodeEncodeError) as e:
        print("保存文字报告时编码异常，已跳过:", e)


def run_analysis(root: str, top_n: int = 20, report_txt: str = "video_report.txt", chart_path: str = "keyword_summary.png"):
    """扫描目录并生成文字报告 + 图表。"""
    records, counter = scan_directory(root)
    if not records:
        print("未发现视频文件")
        return
    text_report(records, counter, report_txt)
    plot_summary(counter, top_n=top_n, output_path=chart_path)
    return records, counter
