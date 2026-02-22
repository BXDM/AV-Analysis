# -*- coding: utf-8 -*-
"""从 DuckDB 生成 HTML 索引页（缩略图在输出目录内）。"""

from pathlib import Path

from config import OUTPUT_INDEX_HTML


def path_to_file_url(path: str) -> str:
    return Path(path).resolve().as_uri()


def _fallback_html(items: list, title: str) -> str:
    import html
    rows = []
    for it in items:
        raw_name = it.get("name") or ""
        name_escaped = html.escape(raw_name)
        dur = (it.get("duration_display") or "").replace('"', "&quot;")
        date = (it.get("date_display") or "").replace('"', "&quot;")
        quality = (it.get("quality_display") or "").replace('"', "&quot;")
        search_text = f"{raw_name} {dur} {date} {quality}".lower().replace("&", "&amp;").replace('"', "&quot;")
        if it.get("thumb_rel"):
            thumb = f'<span class="thumb-wrap"><img src="{it["thumb_rel"]}" alt="" class="thumb"/>'
            if it.get("is_4k"):
                thumb += '<img src="4k-uhd.png" alt="4K" class="thumb-4k"/>'
            if dur:
                thumb += f'<span class="duration-badge">{dur}</span>'
            thumb += "</span>"
        else:
            thumb = '<span class="no-thumb">无缩略图</span>'
        meta = " · ".join(x for x in [date, quality] if x)
        rows.append(
            f'<li data-search="{search_text}">'
            f'<a href="{it["file_url"]}" target="_blank">{thumb}'
            f'<span class="name">{name_escaped}</span>'
            f'<span class="meta">{meta}</span></a></li>'
        )
    total = len(items)
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"/><title>{title}</title>
<style>body{{font-family:sans-serif;margin:20px;background:#1a1a1a;color:#eee}}.search-wrap{{margin-bottom:16px}}.search-wrap input{{padding:8px 12px;width:100%;max-width:400px;background:#2a2a2a;border:1px solid #444;border-radius:6px;color:#eee}}.count{{color:#888;font-size:14px;margin-bottom:16px}}ul{{list-style:none;display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:16px;padding:0}}li a{{display:flex;flex-direction:column;text-decoration:none;color:#ccc;border:1px solid #333;border-radius:8px;overflow:hidden}}.thumb-wrap{{position:relative;width:100%}}.thumb{{width:100%;height:auto;min-height:120px;object-fit:cover;display:block}}.thumb-4k{{position:absolute;top:6px;left:6px;width:40px;height:auto;z-index:1}}.duration-badge{{position:absolute;bottom:6px;right:6px;background:rgba(0,0,0,.8);color:#fff;padding:2px 6px;font-size:11px;border-radius:4px;z-index:1}}.no-thumb{{padding:40px;text-align:center;background:#2a2a2a}}.name{{padding:8px 8px 2px;font-size:12px}}.meta{{padding:2px 8px 8px;font-size:11px;color:#888}}</style></head>
<body><h1>{title}</h1><div class="search-wrap"><input type="text" id="q" placeholder="搜索文件名、时长、日期、画质…" autocomplete="off"/></div><p class="count" id="count">共 {total} 个 · 点击用默认播放器打开（将 PotPlayer 设为默认即可）</p><ul id="list">{chr(10).join(rows)}</ul>
<script>var total={total};var list=document.getElementById("list");var countEl=document.getElementById("count");document.getElementById("q").oninput=function(){{var q=this.value.toLowerCase().trim();var vis=0;for(var i=0;i<list.children.length;i++){{var el=list.children[i];var show=!q||el.getAttribute("data-search").indexOf(q)!==-1;el.style.display=show?"":"none";if(show)vis++}}countEl.textContent="显示 "+vis+" / 共 "+total+" 个 · 点击用默认播放器打开（将 PotPlayer 设为默认即可）"}};</script></body></html>"""


def _is_4k(width, height) -> bool:
    if width is None and height is None:
        return False
    return (width is not None and width >= 3840) or (height is not None and height >= 2160)


def _format_duration(sec) -> str:
    if sec is None or sec < 0:
        return ""
    s = int(sec)
    if s < 3600:
        return f"{s // 60}:{(s % 60):02d}"
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{(s % 60):02d}"


def _format_date(file_mtime: str) -> str:
    if not file_mtime or len(file_mtime) < 10:
        return ""
    return file_mtime[:10]  # YYYY-MM-DD


def _format_quality(width, height) -> str:
    if width is None or height is None:
        return ""
    if _is_4k(width, height):
        return "4K"
    return f"{width}×{height}"


def build_index_from_db(db_path: str, output_dir: str, scan_id: int, title: str = "视频索引"):
    import shutil
    import duckdb
    con = duckdb.connect(str(db_path))
    rows = con.execute(
        "SELECT path, rel_path, name, thumbnail_file, width, height, duration_sec, file_mtime FROM videos WHERE scan_id = ? ORDER BY path",
        [scan_id],
    ).fetchall()
    con.close()
    items = []
    for r in rows:
        w, h, dur, mtime = r[4], r[5], r[6], r[7]
        items.append({
            "path": r[0],
            "rel_path": r[1],
            "name": r[2],
            "thumb_rel": r[3],
            "is_4k": _is_4k(w, h),
            "duration_display": _format_duration(dur),
            "date_display": _format_date(mtime),
            "quality_display": _format_quality(w, h),
        })
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
