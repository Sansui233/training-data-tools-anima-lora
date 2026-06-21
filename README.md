# Anima 数据集处理

个人的 Anima 图像数据处理工作流程与工具，用于训练 Lora。集格式转换、切图 GUI、打标、标签审核 GUI，打包训练数据、训练脚本为一体。

## 准备

安装依赖，同时需要克隆 [Joytag](https://github.com/fpgaminer/joytag) 打标工具到工作目录下。

```
uv sync
git clone --depth=1 https://github.com/fpgaminer/joytag
```

## 目录

- 原图：`raws` 下指定的一个或多个一级、二级目录
- 训练集：`train/anima/data`
- Source map：`train/anima/data/sourmap.json`
- 报告：`train/anima/reports`
- 打包文件：`anima-train/atomsphere_anima_train_package.zip`

## 1. 转换图片

`1_convert_image.py` 读取指定原图目录（非递归），将图片转换为训练集文件，并通过 `sourmap.json` 记录增量处理结果。

- 默认输入：`--source` 指定的 `raws` 下一级或二级目录
- 默认输出：图片与 `sourmap.json` 写入 `train/anima/data`，报告写入 `train/anima/reports`。sourmap 用于避免重复处理，主要是因为有的图像会改名。考虑以后改为打包时改名，避免额外依赖 index。

```powershell
# 指定目录
uv run python anima-train/1_convert_image.py --source raws/default
uv run python anima-train/1_convert_image.py --source raws/default --source raws/感觉至上
uv run python anima-train/1_convert_image.py --source raws/default --source raws/感觉至上 --target-dir train/anima

# 指定图片质量与格式
uv run python anima-train/1_convert_image.py --source raws/default --webp-quality 98
uv run python anima-train/1_convert_image.py --source raws/default --webp-lossless
uv run python anima-train/1_convert_image.py --source raws/default --format png

# 强制重新处理
uv run python anima-train/1_convert_image.py --source raws/default --force
```

## 2. 人工切分大图

`1_image_split.py` 检测 training data 中长边超过阈值且名称不是 `_slice_<number>` 的图片。框选后使用 `Ctrl+S` 保存、`Space` 预览、`Esc` 取消，使用 `←/→` 切换图片。右侧可将原图标记为 `_sliced`，缩略图可单击放大查看。

- 默认输入：`train/anima/data`
- 默认输出：切图写回原目录，命名为 `<原图名称>_slice_<number>.webp`；启动日志写入 `train/anima/reports/image_split.log`

```powershell
# 使用默认目录
uv run python anima-train/1_image_split.py

# 指定训练集目录
uv run python anima-train/1_image_split.py --data-dir train/anima/data

# 指定检测阈值与图片质量
uv run python anima-train/1_image_split.py --max-side 2048 --webp-quality 98

# 显示详细性能日志
uv run python anima-train/1_image_split.py --log-level DEBUG
```

## 3. 生成标签

`2_tag_with_joytag.py` 读取 training data 中的全部图片，并使用 JoyTag 为缺少 caption 的图片生成同名 `.txt` 文件。

- 默认输入：`train/anima/data` 中的全部图片及 `sourmap.json`
- 默认输出：caption 写入 `train/anima/data`，报告写入 `train/anima/reports`

```powershell
# 使用默认目录
uv run python anima-train/2_tag_with_joytag.py

# 指定训练集目录
uv run python anima-train/2_tag_with_joytag.py --target-dir train/anima
uv run python anima-train/2_tag_with_joytag.py --data-dir train/anima/data --report-dir train/anima/reports

# 指定打标参数
uv run python anima-train/2_tag_with_joytag.py --trigger atomsphere_style --threshold 0.4 --device cuda

# 强制重新打标
uv run python anima-train/2_tag_with_joytag.py --force
```

## 4. 人工审核标签

`3_caption_review_gui.py` 打开训练图片及其 caption，供人工检查和修改。颜色词按对应颜色高亮，`eye`、`hair`、`body`、`necklace` 等词使用浅灰背景；停止输入 500ms 后自动重新渲染。

- 默认输入：`train/anima/data` 中的图片与同名 `.txt`
- 默认输出：修改后的 `.txt` 原位置保存

```powershell
# 使用默认目录
uv run python anima-train/3_caption_review_gui.py

# 指定训练集目录
uv run python anima-train/3_caption_review_gui.py --data-dir train/anima/data
```

## 5. 打包数据集

`4_package_dataset.py` 核对 training data 中全部图片和 `.txt` 的对应关系，确认数据完整后，打包训练数据与 dataset config。

- 默认输入：`train/anima/data`、dataset config、training script 和 AutoDL notes
- 默认输出：`anima-train/atomsphere_anima_train_package.zip`

```powershell
# 使用默认目录
uv run python anima-train/4_package_dataset.py

# 指定训练集目录
uv run python anima-train/4_package_dataset.py --target-dir train/anima

# 指定配置与输出文件
uv run python anima-train/4_package_dataset.py --dataset-config anima-train/dataset_config.toml --output anima-train/atomsphere_anima_train_package.zip
```

# 上传到 AutoDL 并训练

## 6. 上传并解压

将 `atomsphere_anima_train_package.zip` 上传到 AutoDL，然后在 `/root/autodl-tmp` 解压。

```bash
cd /root/autodl-tmp
unzip -o /path/to/atomsphere_anima_train_package.zip
```

```text
/root/autodl-tmp/anima-train/data
/root/autodl-tmp/anima-train/dataset_config.toml
/root/autodl-tmp/anima-train/train_anima_lora_4090.sh
```

## 7. 安装 sd-scripts

```bash
cd /root/autodl-tmp
git clone https://github.com/kohya-ss/sd-scripts.git
cd sd-scripts
python -m venv venv
source venv/bin/activate
python -m pip install -U pip setuptools wheel
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
pip install -U -r requirements.txt
pip install bitsandbytes
accelerate config
```

## 8. 放置模型文件

```text
/root/autodl-tmp/anima-base-v1.0.safetensors
/root/autodl-tmp/qwen_3_06b_base.safetensors
/root/autodl-tmp/qwen_image_vae.safetensors
```

## 9. 启动训练

在 sd-scripts 下启动。

```bash
cd /root/autodl-tmp/sd-scripts
source venv/bin/activate
bash /root/autodl-tmp/anima-train/train_anima_lora_4090.sh
```

## 10. 查看 checkpoint

```text
/root/autodl-tmp/anima-train/output
```

默认 training script 使用 Anima LoRA rank/alpha 32、learning rate `2e-5`、batch size 2、gradient accumulation 4、bf16、20 epochs，并每 2 epochs 保存 checkpoint。

100张图 4 小时关机
