# -*- coding: utf-8 -*-
"""
方案三：HTML 交互式索引页。
扫描视频路径，结合方案一生成的缩略图，生成本地 HTML，点击可在本地播放器打开。
"""

import os
from pathlib import Path

from config import is_video, THUMBNAILS_DIR
from video_thumbnails import thumbnail_path_for_video


def scan_for_index(root: str) -> list[dict]:
    """
    遍历 root，收集每个视频的绝对路径、相对路径、缩略图路径（若存在）。
    返回列表，每项: path, rel_path, thumb_path, name
    """
    root = Path(root).resolve()
    items = []
    for dirpath, _dirs, files in os.walk(str(root)):
        dirpath = Path(dirpath)
        thumb_dir = dirpath / THUMBNAILS_DIR
        for f in files:
            if not is_video(f):
                continue
            video_path = dirpath / f
            thumb_path = thumbnail_path_for_video(video_path, thumb_dir)
            try:
                rel_path = video_path.resolve().relative_to(root)
            except ValueError:
                rel_path = video_path
            items.append({
                "path": str(video_path.resolve()),
                "rel_path": str(rel_path),
                "name": f,
                "thumb_path": str(thumb_path) if thumb_path.exists() else None,
            })
    return items


def path_to_file_url(path: str) -> str:
    """本地路径转 file:// URL，便于在浏览器中点击用本地程序打开。"""
    return Path(path).resolve().as_uri()


def render_html(items: list[dict], output_path: str, root_dir: str, title: str = "视频索引"):
    """用 Jinja2 渲染 HTML；若未安装 Jinja2 则用简单字符串模板。"""
    root = Path(root_dir).resolve()
    # 缩略图在 HTML 中使用相对路径（相对于输出的 HTML 所在目录）
    output_dir = Path(output_path).resolve().parent
    for it in items:
        if it.get("thumb_path"):
            tp = Path(it["thumb_path"]).resolve()
            try:
                it["thumb_rel"] = str(tp.relative_to(output_dir))
            except ValueError:
                it["thumb_rel"] = it["thumb_path"]
        else:
            it["thumb_rel"] = None
        it["file_url"] = path_to_file_url(it["path"])

    try:
        from jinja2 import Template
        with open(Path(__file__).parent / "index_template.html", "r", encoding="utf-8") as f:
            tpl = Template(f.read())
        html = tpl.render(items=items, title=title, total=len(items))
    except Exception:
        html = _fallback_html(items, title)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print("已生成索引页:", output_path)


def _fallback_html(items: list[dict], title: str) -> str:
    """无 Jinja2 时的简单 HTML。"""
    rows = []
    for it in items:
        thumb = f'<img src="{it.get("thumb_rel") or ""}" alt="" class="thumb"/>' if it.get("thumb_rel") else "<span class=\"no-thumb\">无缩略图</span>"
        rows.append(
            f'<li><a href="{it["file_url"]}" target="_blank">{thumb}<span>{it["name"]}</span></a></li>'
        )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<title>{title}</title>
<style>
  body {{ font-family: sans-serif; margin: 20px; background: #1a1a1a; color: #eee; }}
  h1 {{ margin-bottom: 20px; }}
  ul {{ list-style: none; display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px; padding: 0; }}
  li a {{ display: flex; flex-direction: column; text-decoration: none; color: #ccc; border: 1px solid #333; border-radius: 8px; overflow: hidden; }}
  li a:hover {{ border-color: #666; color: #fff; }}
  .thumb {{ width: 100%; height: auto; min-height: 120px; object-fit: cover; }}
  .no-thumb {{ padding: 40px; text-align: center; background: #2a2a2a; }}
  span {{ padding: 8px; font-size: 12px; }}
</style>
</head>
<body>
<h1>{title}（共 {len(items)} 个）</h1>
<ul>
{chr(10).join(rows)}
</ul>
</body>
</html>"""


def build_index(root: str, output_html: str = None, title: str = "视频索引"):
    """入口：扫描 root，生成 output_html。建议将 output_html 放在资源根目录，缩略图相对路径才正确。"""
    root_p = Path(root).resolve()
    if output_html is None:
        output_html = str(root_p / "index.html")
    items = scan_for_index(root)
    if not items:
        print("未发现视频文件")
        return
    render_html(items, output_html, root, title=title)


def build_index_from_db(db_path: str, output_dir: str, scan_id: int, title: str = "视频索引"):
    """从 DuckDB 读取视频列表，在 output_dir 下生成 index.html（缩略图路径相对 output_dir）。"""
    from config import OUTPUT_INDEX_HTML
    import duckdb
    con = duckdb.connect(str(db_path))
    rows = con.execute("""
        SELECT path, rel_path, name, thumbnail_file FROM videos WHERE scan_id = ? ORDER BY path
    """, [scan_id]).fetchall()
    con.close()
    items = [
        {"path": r[0], "rel_path": r[1], "name": r[2], "thumb_rel": r[3]}
        for r in rows
    ]
    out_path = Path(output_dir).resolve() / OUTPUT_INDEX_HTML
    for it in items:
        it["file_url"] = path_to_file_url(it["path"])
    try:
        from jinja2 import Template
        with open(Path(__file__).parent / "index_template.html", "r", encoding="utf-8") as f:
            tpl = Template(f.read())
        html = tpl.render(items=items, title=title, total=len(items))
    except Exception:
        html = _fallback_html(items, title)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print("已生成索引页:", out_path)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python html_index.py <资源目录> [输出 index.html]")
        sys.exit(1)
    root = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "index.html"
    build_index(root, out)
