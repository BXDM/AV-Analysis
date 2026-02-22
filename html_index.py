# -*- coding: utf-8 -*-
"""从 DuckDB 生成 HTML 索引页（缩略图在输出目录内）。"""

from pathlib import Path

from config import OUTPUT_INDEX_HTML


def path_to_file_url(path: str) -> str:
    return Path(path).resolve().as_uri()


def _fallback_html(items: list, title: str, thumb_frames: int = 6) -> str:
    import html
    rows = []
    for it in items:
        raw_name = it.get("name") or ""
        name_escaped = html.escape(raw_name)
        dur = (it.get("duration_display") or "").replace('"', "&quot;")
        date = (it.get("date_display") or "").replace('"', "&quot;")
        quality = (it.get("quality_display") or "").replace('"', "&quot;")
        size_d = (it.get("size_display") or "").replace('"', "&quot;")
        search_text = f"{raw_name} {dur} {date} {quality} {size_d}".lower().replace("&", "&amp;").replace('"', "&quot;")
        sort_size = it.get("file_size") is not None and str(it["file_size"]) or "0"
        sort_dur = it.get("duration_sec") is not None and str(int(it["duration_sec"])) or "0"
        sort_w = it.get("width") is not None and str(it["width"]) or "0"
        sort_h = it.get("height") is not None and str(it["height"]) or "0"
        sort_res = str((it.get("width") or 0) * (it.get("height") or 0))
        sort_date = (it.get("file_mtime") or "")[:10].replace("-", "") or "0"
        if it.get("thumb_rel"):
            tr = it["thumb_rel"]
            thumb = f'<span class="thumb-wrap" data-frames="{thumb_frames}"><img src="{tr}" alt="" class="thumb"/>'
            if it.get("is_4k"):
                thumb += '<img src="4k-uhd.png" alt="4K" class="thumb-4k"/>'
            if dur:
                thumb += f'<span class="duration-badge">{dur}</span>'
            thumb += "</span>"
        else:
            thumb = '<span class="no-thumb">无缩略图</span>'
        meta_parts = [x for x in [dur, quality, size_d, date] if x]
        meta = " · ".join(meta_parts)
        rows.append(
            f'<li data-search="{search_text}" data-sort-size="{sort_size}" data-sort-duration="{sort_dur}" data-sort-resolution="{sort_res}" data-sort-width="{sort_w}" data-sort-height="{sort_h}" data-sort-date="{sort_date}" data-sort-name="{html.escape(raw_name.lower())}">'
            f'<a href="{it["file_url"]}" target="_blank">{thumb}'
            f'<span class="name">{name_escaped}</span>'
            f'<span class="meta">{meta}</span></a></li>'
        )
    total = len(items)
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"/><title>{title}</title>
<style>body{{font-family:sans-serif;margin:20px;background:#1a1a1a;color:#eee}}.search-wrap{{margin-bottom:16px}}.search-wrap input{{padding:8px 12px;width:100%;max-width:400px;background:#2a2a2a;border:1px solid #444;border-radius:6px;color:#eee}}.count{{color:#888;font-size:14px;margin-bottom:16px}}ul{{list-style:none;display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:16px;padding:0}}li a{{display:flex;flex-direction:column;text-decoration:none;color:#ccc;border:1px solid #333;border-radius:8px;overflow:hidden}}body{{--thumb-frames:{thumb_frames}}}.thumb-wrap{{position:relative;width:100%;overflow:hidden}}.thumb-wrap .thumb{{width:calc(var(--thumb-frames,6) * 100%);height:auto;min-height:120px;display:block;object-fit:none;object-position:0 0}}.thumb-4k{{position:absolute;top:6px;left:6px;width:40px;height:auto;z-index:1}}.duration-badge{{position:absolute;bottom:6px;right:6px;background:rgba(0,0,0,.8);color:#fff;padding:2px 6px;font-size:11px;border-radius:4px;z-index:1}}.no-thumb{{padding:40px;text-align:center;background:#2a2a2a}}.name{{padding:8px 8px 2px;font-size:12px}}.meta{{padding:2px 8px 8px;font-size:11px;color:#888}}</style></head>
<body style="--thumb-frames:{thumb_frames}"><h1>{title}</h1><div class="search-wrap"><input type="text" id="q" placeholder="搜索文件名、时长、日期、画质…" autocomplete="off"/></div><p class="count" id="count">共 {total} 个 · 点击用默认播放器打开（将 PotPlayer 设为默认即可）</p><ul id="list">{chr(10).join(rows)}</ul>
<script>var total={total};var list=document.getElementById("list");var countEl=document.getElementById("count");document.getElementById("q").oninput=function(){{var q=this.value.toLowerCase().trim();var vis=0;for(var i=0;i<list.children.length;i++){{var el=list.children[i];var show=!q||el.getAttribute("data-search").indexOf(q)!==-1;el.style.display=show?"":"none";if(show)vis++}}countEl.textContent="显示 "+vis+" / 共 "+total+" 个 · 点击用默认播放器打开（将 PotPlayer 设为默认即可）"}};list.querySelectorAll(".thumb-wrap[data-frames]").forEach(function(wrap){{var img=wrap.querySelector(".thumb");if(!img)return;var n=parseInt(wrap.getAttribute("data-frames")||"6",10)||6;wrap.addEventListener("mousemove",function(e){{var w=wrap.offsetWidth;if(!w)return;var i=Math.min(n-1,Math.max(0,Math.floor((e.offsetX/w)*n)));img.style.transform="translateX(-"+(i/n*100)+"%)"}});wrap.addEventListener("mouseleave",function(){{img.style.transform="translateX(0)"}})}});</script></body></html>"""


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


def _format_size(size) -> str:
    if size is None or size < 0:
        return ""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    if size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{size / (1024 * 1024 * 1024):.1f} GB"


def build_index_from_db(db_path: str, output_dir: str, scan_id: int, title: str = "视频索引", root_path: str | None = None, thumb_frames: int = 6):
    import shutil
    import duckdb
    con = duckdb.connect(str(db_path))
    rows = con.execute(
        "SELECT path, rel_path, name, thumbnail_file, file_size, width, height, duration_sec, file_mtime FROM videos WHERE scan_id = ? ORDER BY path",
        [scan_id],
    ).fetchall()
    con.close()
    items = []
    for r in rows:
        size, w, h, dur, mtime = r[4], r[5], r[6], r[7], r[8]
        thumb_rel = r[3]
        items.append({
            "path": r[0],
            "rel_path": r[1],
            "name": r[2],
            "thumb_rel": thumb_rel,
            "file_size": size,
            "width": w,
            "height": h,
            "duration_sec": dur,
            "file_mtime": mtime,
            "is_4k": _is_4k(w, h),
            "duration_display": _format_duration(dur),
            "date_display": _format_date(mtime),
            "quality_display": _format_quality(w, h),
            "size_display": _format_size(size),
        })
    out_dir = Path(output_dir).resolve()
    logo_src = Path(__file__).parent / "4k-uhd.png"
    if logo_src.exists():
        shutil.copy2(logo_src, out_dir / "4k-uhd.png")
    out_path = out_dir / OUTPUT_INDEX_HTML
    use_relative = root_path and str(Path(output_dir).resolve().parent) == str(Path(root_path).resolve())
    for it in items:
        if use_relative and it.get("rel_path"):
            it["file_url"] = "../" + it["rel_path"].replace("\\", "/")
        else:
            it["file_url"] = path_to_file_url(it["path"])
    try:
        from jinja2 import Template
        with open(Path(__file__).parent / "index_template.html", "r", encoding="utf-8") as f:
            html = Template(f.read()).render(items=items, title=title, total=len(items), thumb_frames=thumb_frames)
    except Exception:
        html = _fallback_html(items, title, thumb_frames=thumb_frames)
    out_path.write_text(html, encoding="utf-8")
    print("已生成索引页:", out_path)
