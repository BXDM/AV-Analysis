# -*- coding: utf-8 -*-
"""配置：扩展名、缩略图数量、编码等。"""

import os

# 支持的视频扩展名（小写）
VIDEO_EXTENSIONS = (".mp4", ".mkv", ".avi", ".wmv", ".flv", ".webm", ".mov")

# 每个视频截取的帧数（均匀分布在时长上）
THUMBNAIL_FRAME_COUNT = 6

# 缩略图单帧最大宽度（保持比例）
THUMBNAIL_MAX_WIDTH = 320

# 旧方案：曾放在每个视频目录下的缩略图子目录名（仅用于 clean 清理）
THUMBNAILS_DIR = "_thumbnails"

# 新方案：统一输出目录。扫描结果、缩略图、报告、DuckDB 均放在此处，不写回视频目录
OUTPUT_DB_NAME = "report.duckdb"
OUTPUT_THUMBNAILS_SUBDIR = "thumbnails"
OUTPUT_REPORT_TXT = "video_report.txt"
OUTPUT_CHART = "keyword_summary.png"
OUTPUT_INDEX_HTML = "index.html"

# 文件名编码（处理日语等）
FILE_ENCODING = "utf-8"

# 仅处理尚未生成缩略图的文件（在统一输出目录内生效）
SKIP_EXISTING_THUMBNAILS = True

# 文件哈希：用于检索相同文件
FILE_HASH_ALGO = "sha256"
# 全量哈希时逐块读取的块大小（字节）
FILE_HASH_CHUNK_SIZE = 1024 * 1024  # 1MB
# True=采样哈希（头/中/尾各一段，大文件快）；False=全量哈希（精确但大文件慢）
FILE_HASH_SAMPLE = True
# 采样哈希时每段字节数（头、中、尾各读一段，共约 3*此值）
FILE_HASH_SAMPLE_SIZE = 128 * 1024  # 128KB

# 扫描并行度：0=自动(CPU 核心数)，1=单进程(原逻辑)，N=多进程数。多进程可显著加速缩略图生成。
SCAN_WORKERS = 0

# 抽帧优先使用 FFmpeg + GPU 解码（需系统已安装 ffmpeg）。GPU 解码通常比 OpenCV CPU 更快。
USE_FFMPEG_GPU = True
# FFmpeg 硬件加速：cuda(NVIDIA), d3d11va(Windows), dxva2(Windows), "" 仅 CPU。auto=依次尝试 cuda -> d3d11va -> ""
FFMPEG_HWACCEL = "auto"

# 一键扫描入口（run_scan.py）使用的目录：仅更新数据库与缩略图，不全盘清空
# 扫描源目录（必填，运行 run_scan.py 时从此处读）
SCAN_SOURCE_DIR = r""
# 输出目录（留空时见下）
SCAN_OUTPUT_DIR = ""
# 当 SCAN_OUTPUT_DIR 留空时：写到此子目录名下，summary 随视频目录迁移（推荐）
# 设为空字符串则用项目 output/<路径哈希>，不随目录迁移
SCAN_OUTPUT_INSIDE_SOURCE = "AV-Summary"


def is_video(filename: str) -> bool:
    return os.path.splitext(filename)[1].lower() in VIDEO_EXTENSIONS
