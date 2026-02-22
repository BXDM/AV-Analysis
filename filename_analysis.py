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
