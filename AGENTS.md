# Anima 数据集处理

## 范围

本项目只在 Windows 上处理和打包 Anima style LoRA 数据集，不负责模型训练。

- 项目脚本放在 `anima-train`
- 项目命令通过 `uv` 运行，并由用户执行
- 新增或移除 Python package 时，同时更新 `pyproject.toml` 和 `uv.lock`

## 目录

- 原图：`raws` 本身或其下用户指定的一个或多个一级、二级目录
- 训练集：`train/anima/data`
- 报告：`train/anima/reports`
- 打包文件：`anima-train/atomsphere_anima_train_package.zip`

## 流程

1. `1_convert_image.py`：非递归读取 `--source` 指定的目录，按 source basename 转换图片。
2. `1_image_split.py`：检查 `train/anima/data` 中长边大于 2048 的图片，框选并保存 WebP 切图。
3. `2_tag_with_joytag.py`：为 training data 中缺少 caption basename 的图片生成 `.txt`。
4. `3_caption_review_gui.py`：人工审核并修改 caption。
5. `4_package_dataset.py`：核对 training data 中全部图片与 caption basename 后打包数据集和 `dataset_config.toml`。

## 规则

- `--source` 可重复使用；指定目录必须是 `raws` 本身，或位于 `raws` 下且深度为一级或二级。
- 只读取指定目录中的直接文件，不 recursive。
- 图片转换保留尺寸和构图，应用 EXIF orientation；默认输出 WebP quality 98，输出文件名使用 source basename。
- 切图保存在 training data 中，命名为 `<原图名称>_slice_<number>.webp`。
- `_sliced` 和 `_slice_<number>` 都是状态 suffix，不属于 original name；标记为已切图时同步重命名 image 和 caption。
- 不使用 sourcemap；文件对应关系只通过 basename 判断，比较时忽略 `_sliced` 和 `_slice_<number>`。
- JoyTag 和打包脚本处理 training data 中的全部图片，包括切图。
- JoyTag caption 以固定 trigger `atomsphere_style` 开头；除非使用 `--force`，否则同 basename 已有 caption 或同 basename 图片已排队时跳过。
- 打包只检查 training data 中每张 image 是否存在同 basename `.txt`。
- 打包时才对 zip 内 image/caption 文件名做 ASCII-safe 重命名，本地 training data 文件名不因此改变。
- 打包文件包含 image、caption、dataset config、training script 和 AutoDL notes，不包含报告。
