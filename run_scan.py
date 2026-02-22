# -*- coding: utf-8 -*-
"""
一键扫描入口：从 config 读取目录，仅更新数据库与缩略图（不全盘清空），终端用 rich 显示进度。
在 config.py 中设置 SCAN_SOURCE_DIR（必填）、SCAN_OUTPUT_DIR（可选，留空则自动生成）。
"""
import sys
from pathlib import Path

# 项目根
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import SCAN_SOURCE_DIR, SCAN_OUTPUT_DIR
from commands import default_output_dir
from scan_db import scan_to_output


def main():
    source = (SCAN_SOURCE_DIR or "").strip()
    if not source:
        # 兼容：若未配置则读 target_dir.txt
        cfg = ROOT / "target_dir.txt"
        if cfg.exists():
            source = cfg.read_text(encoding="utf-8").strip().splitlines()[0].strip()
        if not source:
            print("未配置扫描目录。请在 config.py 中设置 SCAN_SOURCE_DIR，或创建 target_dir.txt 写入资源根路径。", file=sys.stderr)
            sys.exit(1)
    source_path = Path(source).resolve()
    if not source_path.is_dir():
        print(f"目录不存在: {source_path}", file=sys.stderr)
        sys.exit(1)

    if (SCAN_OUTPUT_DIR or "").strip():
        output = (SCAN_OUTPUT_DIR or "").strip()
    else:
        output = default_output_dir(source)
    output_path = Path(output).resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    try:
        from rich.console import Console
        from rich.progress import Progress, BarColumn, TextColumn, TaskProgressColumn, TimeElapsedColumn, TimeRemainingColumn
    except ImportError:
        # 无 rich 时直接调用，使用 scan_db 内置的 print
        scan_to_output(source, output)
        return

    console = Console()
    console.print(f"[bold]扫描源:[/bold] {source_path}")
    console.print(f"[bold]输出目录:[/bold] {output_path}")
    console.print("[dim]仅更新数据库与缩略图，已存在的缩略图会跳过。[/dim]\n")

    def on_progress(completed: int, total: int, row_dict: dict):
        progress.update(task_id, completed=completed, total=max(total, 1))
        if row_dict:
            name = (row_dict.get("name") or "")[:32]
            status = row_dict.get("status", "")
            n_total = f" {completed}/{total}"
            if status == "ok":
                desc = f"[green]✓[/green] {name}{n_total}"
            elif status == "skip":
                desc = f"[yellow]跳过[/yellow] {name}{n_total}"
            else:
                desc = f"[red]失败[/red] {name}{n_total}"
            progress.update(task_id, description=desc)
        elif total and completed == 0:
            progress.update(task_id, description=f"正在处理… 共 {total} 个")
        else:
            progress.update(task_id, description="正在枚举文件…")

    with Progress(
        TextColumn("[bold blue]{task.description}[/bold blue]", justify="left"),
        BarColumn(bar_width=40),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        refresh_per_second=4,
    ) as progress:
        task_id = progress.add_task("准备中…", total=None, completed=0)
        scan_to_output(source, output, progress_callback=on_progress)

    console.print("\n[green]扫描完成。[/green] 结果目录: " + str(output_path))


if __name__ == "__main__":
    main()
