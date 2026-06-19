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
2. `1_image_split.py`：检查 `train/anima/data` 中长边大于 2048 的图片，框选并保存 WebP 切图。
3. `2_tag_with_joytag.py`：为 training data 中缺少 caption 的全部图片生成同名 `.txt`。
4. `3_caption_review_gui.py`：人工审核并修改 caption。
5. `4_package_dataset.py`：核对 training data 中全部图片与 `.txt` 后打包数据集和 `dataset_config.toml`。

## 规则

- `--source` 可重复使用；指定目录必须位于 `raws` 下，深度为一级或二级。
- 只读取指定目录中的直接文件，不 recursive。
- 图片转换保留尺寸和构图，应用 EXIF orientation；默认输出 WebP quality 98。
- 切图保存在 training data 中，命名为 `<原图名称>_slice_<number>.webp`。
- `_sliced` 和 `_slice_<number>` 都是状态 suffix，不属于 original name；标记为已切图时同步重命名 image、caption 和 Source map output path。
- `sourmap.json` 用于核对转换得到的原图；切图不写入 Source map。
- JoyTag 和打包脚本处理 training data 中的全部图片，包括切图。
- JoyTag caption 以固定 trigger `atomsphere_style` 开头；除非使用 `--force`，否则跳过已有 caption。
- 打包文件包含 image、caption 和 `anima-train/dataset_config.toml`，不包含 `sourmap.json` 与报告。
