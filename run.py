# -*- coding: utf-8 -*-
"""
唯一入口。无参数 = 扫描并刷新索引；加 --index = 只刷新索引。
目录：先读 config，没有则用上次用的（target_dir.txt），再没有就提示输入并保存。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TARGET_FILE = ROOT / "target_dir.txt"


def _get_source_and_output():
    """(源目录, 输出目录)。无则 (None, None)。"""
    from commands import get_scan_source_and_output
    return get_scan_source_and_output()


def _prompt_and_save_source():
    """提示输入目录，写入 target_dir.txt，返回 Path。"""
    try:
        p = input("请输入扫描源目录路径（将保存，下次直接用）: ").strip().strip('"').strip("'")
    except EOFError:
        print("未输入。", file=sys.stderr)
        sys.exit(1)
    if not p:
        print("未输入路径。", file=sys.stderr)
        sys.exit(1)
    path = Path(p).resolve()
    if not path.is_dir():
        print("目录不存在:", path, file=sys.stderr)
        sys.exit(1)
    TARGET_FILE.write_text(str(path), encoding="utf-8")
    return path


def _resolve_source_output(only_index: bool):
    """解析源与输出；无则提示并保存。only_index 时输出目录必须有 report.duckdb。"""
    from commands import default_output_dir
    from config import SCAN_OUTPUT_DIR, SCAN_OUTPUT_INSIDE_SOURCE

    source_path, output_path = _get_source_and_output()
    if source_path is None or output_path is None:
        source_path = _prompt_and_save_source()
        if (SCAN_OUTPUT_DIR or "").strip():
            output_path = Path((SCAN_OUTPUT_DIR or "").strip()).resolve()
        else:
            sub = (SCAN_OUTPUT_INSIDE_SOURCE or "AV-Summary").strip() or "AV-Summary"
            output_path = source_path / sub
            output_path = output_path.resolve()

    if only_index and not (output_path / "report.duckdb").is_file():
        print("未找到 report.duckdb，请先直接运行一次扫描（不加 --index）。路径:", output_path, file=sys.stderr)
        sys.exit(1)
    return source_path, output_path


def _do_scan(source_path: Path, output_path: Path):
    from scan_db import scan_to_output
    from commands import cmd_index

    try:
        from rich.console import Console
        from rich.progress import Progress, BarColumn, TextColumn, TaskProgressColumn, TimeElapsedColumn, TimeRemainingColumn
    except ImportError:
        try:
            scan_to_output(str(source_path), str(output_path))
        except KeyboardInterrupt:
            print("已中断。", file=sys.stderr)
            sys.exit(130)
        try:
            cmd_index(str(output_path))
        except Exception:
            pass
        return

    console = Console()
    console.print(f"[bold]扫描源:[/bold] {source_path}")
    console.print(f"[bold]输出:[/bold] {output_path}\n")

    NAME_WIDTH = 40
    def on_progress(completed: int, total: int, row_dict: dict):
        progress.update(task_id, completed=completed, total=max(total, 1))
        if row_dict:
            raw = (row_dict.get("name") or "")
            name = raw[: NAME_WIDTH - 1] + "…" if len(raw) > NAME_WIDTH else raw.ljust(NAME_WIDTH)
            st = row_dict.get("status", "")
            if st == "ok":
                desc = f"[green]✓[/green] {name} {completed}/{total}"
            elif st == "skip":
                desc = f"[yellow]跳过[/yellow] {name} {completed}/{total}"
            else:
                desc = f"[red]失败[/red] {name} {completed}/{total}"
            progress.update(task_id, description=desc)
        elif total and completed == 0:
            progress.update(task_id, description=f"共 {total} 个…")
        else:
            progress.update(task_id, description="枚举中…")

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
        try:
            scan_to_output(str(source_path), str(output_path), progress_callback=on_progress)
        except KeyboardInterrupt:
            console.print("\n[yellow]已中断。[/yellow] 已处理数据已写入，下次继续运行即可。")
            sys.exit(130)

    try:
        cmd_index(str(output_path))
    except Exception as e:
        console.print("[yellow]索引未刷新:[/yellow]", str(e))
    console.print("\n[green]完成。[/green] 结果: " + str(output_path))


def main():
    only_index = "--index" in sys.argv or "-i" in sys.argv
    source_path, output_path = _resolve_source_output(only_index)
    output_path.mkdir(parents=True, exist_ok=True)

    if only_index:
        from commands import cmd_index
        cmd_index(str(output_path))
        print("已刷新索引:", output_path / "index.html")
    else:
        _do_scan(source_path, output_path)


if __name__ == "__main__":
    main()
