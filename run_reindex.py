# -*- coding: utf-8 -*-
"""
根据 target_dir.txt 或 config 中的扫描源，找到输出目录（源目录/AV-Summary）并重新生成 index.html。
缩略图已存在时，只需刷新索引页即可看到分辨率角标和正确帧数。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import SCAN_OUTPUT_INSIDE_SOURCE, SCAN_SOURCE_DIR


def main():
    # 1) 优先 config 中的扫描源
    source = (SCAN_SOURCE_DIR or "").strip()
    if not source:
        # 2) 否则读 target_dir.txt 第一行
        cfg = ROOT / "target_dir.txt"
        if cfg.exists():
            source = cfg.read_text(encoding="utf-8").strip().splitlines()[0].strip()
    if not source:
        print("未配置扫描源。请在 config.py 中设置 SCAN_SOURCE_DIR，或编辑 target_dir.txt 第一行为资源根路径。", file=sys.stderr)
        sys.exit(1)

    source_path = Path(source).resolve()
    if not source_path.is_dir():
        print("扫描源目录不存在:", source_path, file=sys.stderr)
        sys.exit(1)

    # 输出目录 = 源目录/AV-Summary（与 scan 时“放在文件目录下”一致）
    sub = (SCAN_OUTPUT_INSIDE_SOURCE or "AV-Summary").strip() or "AV-Summary"
    output_dir = source_path / sub
    db_path = output_dir / "report.duckdb"

    if not db_path.is_file():
        print("未找到 report.duckdb，路径:", db_path, file=sys.stderr)
        print("若缩略图在其它目录，请直接运行: python main.py index <含 report.duckdb 的目录>", file=sys.stderr)
        sys.exit(1)

    from commands import cmd_index
    cmd_index(str(output_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
