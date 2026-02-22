# 视频资源梗概（AV-Analysis）

本地、离线：扫描视频目录 → **DuckDB** + 缩略图/报告/HTML 写入**单独输出目录**，不修改原目录。FFmpeg+GPU 抽帧、多进程并行。

---

## 命令（5 个）

| 命令 | 说明 |
|------|------|
| **scan** | 扫描 → DuckDB（哈希/写入时间/分辨率/时长）+ 缩略图/报告/index.html 到输出目录 |
| **clean** | 删除资源目录下所有 `_thumbnails`（按需，补救用） |
| **query** | 查 DuckDB：写入时间、清晰度、大小、时长（可 --sql、--out） |
| **duplicates** | 按 file_hash 列出相同文件（可 --out） |
| **check-gpu** | 检测 FFmpeg 与 GPU 是否可用（可选传视频路径做抽帧测试） |

---

## 项目结构（8 个 Py + 1 模板）

| 文件 | 职责 |
|------|------|
| `main.py` | 入口，解析参数并分发 |
| `commands.py` | 5 个命令实现 + clean 逻辑内联 |
| `config.py` | 扩展名、输出路径、并行度、FFmpeg/GPU |
| `scan_db.py` | 扫描、DuckDB、多进程 worker |
| `video_thumbnails.py` | 抽帧（FFmpeg→OpenCV）、拼图、元数据 |
| `ffmpeg_frames.py` | FFmpeg/ffprobe 抽帧与元数据、run_gpu_check |
| `filename_analysis.py` | 文件名关键词、报告与图表（scan 内用） |
| `html_index.py` | 从 DuckDB 生成 index.html |
| `index_template.html` | HTML 模板 |
| `run_scan.py` | **一键扫描**：从 config 读目录，rich 进度条，仅更新 DB 与缩略图 |
| `run_analysis_target.py` | 按 target_dir.txt 执行 scan（可选 --clean） |

---

## 安装与使用

```bash
pip install -r requirements.txt
# 或 venv: python -m venv venv && venv\Scripts\pip install -r requirements.txt
```

- **扫描**：`python main.py scan <资源目录>`  
  结果在 `output/<路径哈希>/`：`report.duckdb`、`thumbnails/`、`video_report.txt`、`keyword_summary.png`、`index.html`。
- **查历史**：`python main.py query <输出目录>`
- **查重**：`python main.py duplicates <输出目录>`
- **检测 GPU**：`python main.py check-gpu [视频路径]`
- **一键扫描（推荐）**：在 `config.py` 中设置 `SCAN_SOURCE_DIR`（必填）、`SCAN_OUTPUT_DIR`（可选），然后运行 `python run_scan.py`。仅更新数据库与缩略图（已存在会跳过），终端用 rich 显示进度。
- **按 target_dir.txt**：编辑 `target_dir.txt` 第一行为资源路径，然后 `python run_analysis_target.py`（加 `--clean` 可先删 _thumbnails）。

---

## 配置（config.py）

- **扫描入口**：`SCAN_SOURCE_DIR` 资源根目录（run_scan.py 必填）；`SCAN_OUTPUT_DIR` 输出目录（留空则按源路径哈希自动生成）
- `VIDEO_EXTENSIONS`、`THUMBNAIL_FRAME_COUNT`、`THUMBNAIL_MAX_WIDTH`
- `SCAN_WORKERS`：0=自动核心数，1=单进程，N=固定进程数
- `USE_FFMPEG_GPU`、`FFMPEG_HWACCEL`（cuda / d3d11va / auto）
- `SKIP_EXISTING_THUMBNAILS`：输出目录内跳过已有缩略图
- `THUMBNAILS_DIR`：clean 要删除的目录名（默认 _thumbnails）
- `FILE_HASH_SAMPLE`：True=采样哈希（头/中/尾各一段，大文件快）；False=全量哈希（精确但慢）

---

## 安全与注意

- 全部本地处理，不联网。
- 勿将仓库上传公开；输出文件自行保管。
- 中文/日文路径使用 UTF-8；Windows 控制台乱码时可用 `run_analysis_target.py` + target_dir.txt。
