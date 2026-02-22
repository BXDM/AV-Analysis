# 视频资源梗概（AV-Analysis）

本地、离线：扫描视频目录 → **DuckDB** + 缩略图/报告/HTML 写入**源目录/AV-Summary**，不修改原目录。FFmpeg+GPU 抽帧、多进程并行。

---

## 用法（一个入口）

```bash
pip install -r requirements.txt
python run.py
```

- **第一次**：若未在 config 里设 `SCAN_SOURCE_DIR` 且没有 `target_dir.txt`，会提示「请输入扫描源目录路径」，输入后自动保存到 `target_dir.txt`，下次直接用。
- **之后**：直接 `python run.py` = 用上次目录扫描并刷新索引。
- **只刷新索引**（改过模板/样式时）：`python run.py --index` 或 `python run.py -i`。

结果在 **扫描源/AV-Summary**：`report.duckdb`、`thumbnails/`、`index.html` 等。打开 `index.html` 即可浏览。

---

## 配置（config.py，可选）

- **SCAN_SOURCE_DIR**：设了则不再读 target_dir.txt、不提示输入。
- **SCAN_OUTPUT_DIR**：设了则不用「源/AV-Summary」。
- 其它：`THUMBNAIL_FRAME_COUNT`、`QUICK_SCAN_MODE`、`SCAN_WORKERS`（HDD 建议 2–4）、`USE_FFMPEG_GPU` 等，见文件内注释。

---

## 高级（main.py，按需）

查库、查重、清 _thumbnails、测 GPU 等：

```bash
python main.py query <输出目录>
python main.py duplicates <输出目录>
python main.py clean <资源根目录>
python main.py check-gpu
```

---

## 其它

- 索引页为雪碧图，悬停拨动帧；分辨率角标 360P/1080P/2K/4K。
- 全部本地，不联网；中文路径 UTF-8。
