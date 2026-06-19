# Anima 数据集处理

## 目录

- 原图：`raws` 下指定的一个或多个一级、二级目录
- 训练集：`train/anima/data`
- Source map：`train/anima/data/sourmap.json`
- 报告：`train/anima/reports`
- 打包文件：`anima-train/atomsphere_anima_train_package.zip`

## 1. 转换图片

`1_convert_image.py` 非递归读取指定原图目录，将图片转换为训练集文件，并通过 `sourmap.json` 记录增量处理结果。

- 默认输入：`--source` 指定的 `raws` 下一级或二级目录
- 默认输出：图片与 `sourmap.json` 写入 `train/anima/data`，报告写入 `train/anima/reports`

```powershell
# 指定目录
uv run python anima-train/1_convert_image.py --source raws/default
uv run python anima-train/1_convert_image.py --source raws/default --source raws/方块田
uv run python anima-train/1_convert_image.py --source raws/collection/selected
uv run python anima-train/1_convert_image.py --source raws/default --source raws/方块田 --target-dir train/anima

# 指定图片质量与格式
uv run python anima-train/1_convert_image.py --source raws/default --webp-quality 98
uv run python anima-train/1_convert_image.py --source raws/default --webp-lossless
uv run python anima-train/1_convert_image.py --source raws/default --format png

# 强制重新处理
uv run python anima-train/1_convert_image.py --source raws/default --force
```

## 2. 生成标签

`2_tag_with_joytag.py` 根据 Source map 查找训练图片，使用 JoyTag 为缺少 caption 的图片生成同名 `.txt` 文件。

- 默认输入：`--source` 指定的原图目录及 `train/anima/data/sourmap.json`
- 默认输出：caption 写入 `train/anima/data`，报告写入 `train/anima/reports`

```powershell
# 指定目录
uv run python anima-train/2_tag_with_joytag.py --source raws/default
uv run python anima-train/2_tag_with_joytag.py --source raws/default --source raws/方块田
uv run python anima-train/2_tag_with_joytag.py --source raws/collection/selected
uv run python anima-train/2_tag_with_joytag.py --source raws/default --source raws/方块田 --target-dir train/anima

# 指定打标参数
uv run python anima-train/2_tag_with_joytag.py --source raws/default --trigger atomsphere_style --threshold 0.4 --device cuda

# 强制重新打标
uv run python anima-train/2_tag_with_joytag.py --source raws/default --force
```

## 3. 审核标签

`3_caption_review_gui.py` 打开训练图片及其 caption，供人工检查和修改。

- 默认输入：`train/anima/data` 中的图片与同名 `.txt`
- 默认输出：修改后的 `.txt` 原位置保存

```powershell
# 使用默认目录
uv run python anima-train/3_caption_review_gui.py

# 指定训练集目录
uv run python anima-train/3_caption_review_gui.py --data-dir train/anima/data
```

## 4. 打包数据集

`4_package_dataset.py` 核对每条 Source map 对应的图片和 `.txt`，完整后打包训练数据与 dataset config。

- 默认输入：`--source` 指定的原图目录、`train/anima/data` 和 `anima-train/dataset_config.toml`
- 默认输出：`anima-train/atomsphere_anima_train_package.zip`

```powershell
# 指定目录
uv run python anima-train/4_package_dataset.py --source raws/default
uv run python anima-train/4_package_dataset.py --source raws/default --source raws/方块田
uv run python anima-train/4_package_dataset.py --source raws/collection/selected
uv run python anima-train/4_package_dataset.py --source raws/default --source raws/方块田 --target-dir train/anima

# 指定配置与输出文件
uv run python anima-train/4_package_dataset.py --source raws/default --dataset-config anima-train/dataset_config.toml --output anima-train/atomsphere_anima_train_package.zip
```
