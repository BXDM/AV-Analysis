# 视频资源梗概工具（AV-Analysis）

在**不逐个打开视频**的前提下，对本地大量视频做安全、离线的“梗概”：缩略图阵列、文件名关键词统计、本地 HTML 索引页。全部在本地运行，**不联网、不上传**。

**推荐用法**：扫描结果写入 **DuckDB**，缩略图与报告写入**单独输出目录**，**不修改**原视频目录结构。

---

## 功能概览

| 命令 | 说明 |
|------|------|
| **scan** | 扫描资源目录 → 写入 DuckDB（含 file_hash、写入时间、清晰度、大小、时长等），缩略图/报告/HTML 存到单独输出目录 |
| **clean** | 删除资源目录下所有 `_thumbnails` 文件夹，恢复原有结构 |
| **duplicates** | 按 file_hash 检索相同文件，列出所有重复组（需先 scan） |
| **query** | 查询历史：按写入时间、清晰度、大小、时长等查 DuckDB（默认按 file_mtime 倒序） |
| report / chart / analysis | 仅生成纯文字报告或图表 |
| html | 生成 HTML 索引页 |
| thumbnails / all | 旧方案：缩略图写回各视频目录（不推荐，可用 clean 清理） |

---

## 安装

**推荐：使用虚拟环境**

```bash
cd AV-Analysis
python -m venv venv
# Windows PowerShell 激活：
venv\Scripts\Activate.ps1
# Windows CMD 或直接使用 venv 的 Python：
venv\Scripts\pip install -r requirements.txt
```

**或全局安装：**

```bash
cd AV-Analysis
pip install -r requirements.txt
```

- 仅做缩略图：`opencv-python` + `Pillow` 即可。
- 做图表：需要 `matplotlib`。
- HTML 用 Jinja2 模板：需要 `Jinja2`（未安装则用内置简单 HTML）。

---

## 使用

- **推荐：扫描到单独目录（不破坏原结构）**  
  `python main.py scan <资源目录> [输出目录]`  
  - 扫描所有视频，结果写入 **DuckDB**（`report.duckdb`）  
  - 缩略图 → `输出目录/thumbnails/`  
  - 报告、图表、`index.html` → 输出目录  
  - 不指定输出目录时，默认使用 `项目目录/output/<路径哈希>/`

- **清理曾写入视频目录的缩略图**  
  `python main.py clean <资源目录>`  
  会删除该目录及子目录下所有名为 `_thumbnails` 的文件夹。

- **只想要纯文字列表**：  
  `python main.py report <资源目录>`

- **从已有输出目录打开索引页**：  
  用浏览器打开 `输出目录/index.html` 即可（scan 完成后会生成）。

- **按哈希检索相同文件**：  
  `python main.py duplicates <输出目录或report.duckdb路径>`  
  会列出所有内容完全相同的文件组（基于 SHA-256）。可加 `--out 文件名` 将结果写入文件。

- **查历史：写入时间、清晰度、大小、时长**：  
  `python main.py query <输出目录或report.duckdb路径>`  
  默认输出 path, name, file_mtime（文件写入时间）, duration_sec（视频时长）, width, height（分辨率）, file_size（字节），按 file_mtime 倒序，最多 500 条。  
  自定义 SQL：`python main.py query <db或目录> --sql "SELECT name, width, height, duration_sec FROM videos WHERE height >= 1080"`，可加 `--out 文件` 导出。

---

## 配置（可选）

在 `config.py` 中可修改：

- `VIDEO_EXTENSIONS`：识别的视频后缀（默认含 .mp4, .mkv, .avi 等）。
- `THUMBNAIL_FRAME_COUNT`：每个视频截取的帧数（默认 6）。
- `OUTPUT_*`：输出目录内的文件名（DuckDB、缩略图子目录、报告、图表、HTML）。
- `FILE_HASH_ALGO` / `FILE_HASH_CHUNK_SIZE`：文件内容哈希算法（默认 sha256）与逐块读取的块大小，用于**相同文件检索**。

**DuckDB `videos` 表字段**：path, rel_path, name, thumbnail_file, file_size（字节）, duration_sec（时长秒）, keywords_json, file_hash, **file_mtime**（文件写入时间 ISO）, **width, height**（分辨率），便于按历史、清晰度、大小、时长查询。

---

## 为什么扫描慢？如何加速？

**主要耗时**：每个视频都要做「读元数据 + 计算文件哈希 + 解码多帧并生成缩略图」，其中**视频解码和缩略图生成**占绝大部分时间，且是 CPU 密集。

**已支持：多进程并行**

- 默认按 **CPU 核心数** 开多个进程同时处理多个视频，可明显缩短总时间。
- 在 `config.py` 中设置 `SCAN_WORKERS = 4`（或其它数字）可固定进程数；设为 `1` 则退化为单进程。
- 命令行覆盖：`python main.py scan <目录> --workers 8`（或 `-j 8`）。

**FFmpeg + GPU 解码（已内置）**

- 在 `config.py` 中 `USE_FFMPEG_GPU = True` 时，会优先用 **FFmpeg** 抽帧；若系统已安装 ffmpeg 且支持 GPU，会依次尝试 **cuda**（NVIDIA）、**d3d11va**（Windows）再回退到 CPU。
- 需本机已安装 [FFmpeg](https://ffmpeg.org/) 并加入 PATH；NVIDIA GPU 需安装对应驱动（无需单独装 CUDA  toolkit，驱动自带 NVDEC 即可）。
- 若未装 FFmpeg 或 GPU 不可用，会自动回退到 **OpenCV（CPU）** 解码。
- **检测是否生效**：`python main.py check-gpu` 可查看 FFmpeg/ffprobe 路径、支持的 hwaccel 及实际解码测试；加一个视频路径可做抽帧测试：`python main.py check-gpu <视频文件>`。
- `THUMBNAILS_DIR`：仅用于 **clean** 命令要删除的目录名（默认 `_thumbnails`）。
- `USE_FFMPEG_GPU`：为 `True` 时优先用 FFmpeg+GPU 抽帧（需安装 ffmpeg）。
- `FFMPEG_HWACCEL`：`"cuda"`（NVIDIA）、`"d3d11va"`（Windows）、`"auto"`（依次尝试 cuda→d3d11va→CPU）、`""` 仅 CPU。
- `SKIP_EXISTING_THUMBNAILS`：为 `True` 时在输出目录内跳过已存在的缩略图，减轻 CPU 压力。

---

## 安全与隐私

- 所有处理均在本地完成，**不调用任何联网 API**。
- 建议**不要**将本仓库上传到公开 GitHub 等公开仓库。
- 文件名可能包含敏感信息，生成的报告与 HTML 请自行妥善保管。

---

## 避坑说明

1. **路径与编码**：代码使用 `pathlib` 与 UTF-8，便于处理中文、日文等文件名；若遇编码问题，请确保终端与系统区域为 UTF-8。
2. **性能**：视频数量很大时，优先使用“仅处理新文件”（`SKIP_EXISTING_THUMBNAILS = True`），避免重复截帧。
3. **推荐用 scan**：使用 `scan` 时，`index.html` 与缩略图都在同一输出目录下，相对路径自动正确。

---

## 许可

仅供个人本地使用，请勿用于传播或未授权内容。
