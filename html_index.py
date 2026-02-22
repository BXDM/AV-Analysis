# -*- coding: utf-8 -*-
"""从 DuckDB 生成 HTML 索引页（缩略图在输出目录内）。"""

from pathlib import Path

from config import OUTPUT_INDEX_HTML


def path_to_file_url(path: str) -> str:
    return Path(path).resolve().as_uri()


def _fallback_html(items: list, title: str) -> str:
    rows = []
    for it in items:
        if it.get("thumb_rel"):
            thumb = f'<span class="thumb-wrap"><img src="{it["thumb_rel"]}" alt="" class="thumb"/>'
            if it.get("is_4k"):
                thumb += '<img src="4k-uhd.png" alt="4K" class="thumb-4k"/>'
            thumb += "</span>"
        else:
            thumb = '<span class="no-thumb">无缩略图</span>'
        rows.append(f'<li><a href="{it["file_url"]}" target="_blank">{thumb}<span class="name">{it["name"]}</span></a></li>')
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"/><title>{title}</title>
<style>body{{font-family:sans-serif;margin:20px;background:#1a1a1a;color:#eee}}ul{{list-style:none;display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:16px;padding:0}}li a{{display:flex;flex-direction:column;text-decoration:none;color:#ccc;border:1px solid #333;border-radius:8px;overflow:hidden}}.thumb-wrap{{position:relative;width:100%}}.thumb{{width:100%;height:auto;min-height:120px;object-fit:cover;display:block}}.thumb-4k{{position:absolute;top:6px;left:6px;width:40px;height:auto;z-index:1}}.no-thumb{{padding:40px;text-align:center;background:#2a2a2a}}.name{{padding:8px;font-size:12px}}</style></head>
<body><h1>{title}（共 {len(items)} 个）</h1><ul>{chr(10).join(rows)}</ul></body></html>"""


def _is_4k(width, height) -> bool:
    if width is None and height is None:
        return False
    return (width is not None and width >= 3840) or (height is not None and height >= 2160)


def build_index_from_db(db_path: str, output_dir: str, scan_id: int, title: str = "视频索引"):
    import shutil
    import duckdb
    con = duckdb.connect(str(db_path))
    rows = con.execute(
        "SELECT path, rel_path, name, thumbnail_file, width, height FROM videos WHERE scan_id = ? ORDER BY path",
        [scan_id],
    ).fetchall()
    con.close()
    items = [
        {
            "path": r[0],
            "rel_path": r[1],
            "name": r[2],
            "thumb_rel": r[3],
            "is_4k": _is_4k(r[4], r[5]),
        }
        for r in rows
    ]
    out_dir = Path(output_dir).resolve()
    logo_src = Path(__file__).parent / "4k-uhd.png"
    if logo_src.exists():
        shutil.copy2(logo_src, out_dir / "4k-uhd.png")
    out_path = out_dir / OUTPUT_INDEX_HTML
    for it in items:
        it["file_url"] = path_to_file_url(it["path"])
    try:
        from jinja2 import Template
        with open(Path(__file__).parent / "index_template.html", "r", encoding="utf-8") as f:
            html = Template(f.read()).render(items=items, title=title, total=len(items))
    except Exception:
        html = _fallback_html(items, title)
    out_path.write_text(html, encoding="utf-8")
    print("已生成索引页:", out_path)
