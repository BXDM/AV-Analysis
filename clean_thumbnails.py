# -*- coding: utf-8 -*-
"""
清理曾写入视频目录的 _thumbnails 文件夹，恢复原有目录结构。
只删除名为 _thumbnails 的目录及其内容，不触碰其他文件。
"""

import os
import shutil
from pathlib import Path

from config import THUMBNAILS_DIR


def clean_under(root: str) -> dict:
    """
    遍历 root 下所有子目录，删除名为 THUMBNAILS_DIR 的文件夹及其内容。
    返回 { "deleted": 删除的目录数, "paths": 被删除的路径列表 }。
    """
    root = Path(root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"目录不存在: {root}")

    deleted_paths = []
    for dirpath, dirnames, _ in os.walk(str(root), topdown=True):
        # 只检查当前层是否有 _thumbnails，有则删除
        to_remove = [d for d in dirnames if d == THUMBNAILS_DIR]
        for d in to_remove:
            full = Path(dirpath) / d
            try:
                shutil.rmtree(full)
                deleted_paths.append(str(full))
            except OSError:
                pass
        # 避免进入已删除的目录
        for d in to_remove:
            dirnames.remove(d)

    return {"deleted": len(deleted_paths), "paths": deleted_paths}


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print(f"用法: python clean_thumbnails.py <资源根目录>")
        print(f"将删除该目录下所有名为 '{THUMBNAILS_DIR}' 的子文件夹。")
        sys.exit(1)
    r = clean_under(sys.argv[1])
    print(f"已删除 {r['deleted']} 个目录:")
    for p in r["paths"]:
        print("  ", p)
