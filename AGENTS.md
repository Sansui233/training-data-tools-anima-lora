# Anima 数据集处理

## 范围

本项目只在 Windows 上处理和打包 Anima style LoRA 数据集，不负责模型训练。

- 项目脚本放在 `anima-train`
- 项目命令通过 `uv` 运行，并由用户执行
- 新增或移除 Python package 时，同时更新 `pyproject.toml` 和 `uv.lock`

## 目录

- 原图：`raws` 下用户指定的一个或多个一级、二级目录
- 训练集：`train/anima/data`
- Source map：`train/anima/data/sourmap.json`
- 报告：`train/anima/reports`
- 打包文件：`anima-train/atomsphere_anima_train_package.zip`

## 流程

1. `1_convert_image.py`：非递归读取 `--source` 指定的目录，转换图片并更新 `sourmap.json`。
2. `2_tag_with_joytag.py`：根据 Source map 为缺少 caption 的图片生成同名 `.txt`。
3. `3_caption_review_gui.py`：人工审核并修改 caption。
4. `4_package_dataset.py`：核对全部图片与 `.txt` 后打包数据集和 `dataset_config.toml`。

## 规则

- `--source` 可重复使用；指定目录必须位于 `raws` 下，深度为一级或二级。
- 只读取指定目录中的直接文件，不 recursive。
- 图片转换保留尺寸和构图，应用 EXIF orientation；默认输出 WebP quality 98。
- `sourmap.json` 中的 mapping 只有在 target image 和同名 `.txt` 都存在时才完整。
- JoyTag caption 以固定 trigger `atomsphere_style` 开头；除非使用 `--force`，否则跳过已有 caption。
- 打包文件包含 image、caption 和 `anima-train/dataset_config.toml`，不包含 `sourmap.json` 与报告。
