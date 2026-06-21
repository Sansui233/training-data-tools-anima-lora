# AutoDL Training Notes

## 1. Unpack Dataset

Upload `atomsphere_anima_train_package.zip` to the AutoDL machine, then unpack it:

```bash
cd /root/autodl-tmp
unzip /path/to/atomsphere_anima_train_package.zip
```

After unpacking, the dataset should look like:

```text
/root/autodl-tmp/anima-train/data/*.{webp,png,jpg,jpeg,bmp}
/root/autodl-tmp/anima-train/data/*.txt
/root/autodl-tmp/anima-train/dataset_config.toml
/root/autodl-tmp/anima-train/train_anima_lora_4090.sh
/root/autodl-tmp/anima-train/AUTODL_TRAINING.md
```

## 2. Prepare sd-scripts

Clone and install `sd-scripts` on the AutoDL machine:

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
```

Then configure accelerate:

```bash
accelerate config
```

For a single RTX 4090, choose a single-machine, single-GPU setup, with bf16 mixed precision if prompted.

## 3. Prepare Model Files

Place these model assets on the AutoDL machine:

```text
Anima DiT model weights at `/root/autodl-tmp/anima-base-v1.0.safetensors`
Qwen3-0.6B text encoder at `/root/autodl-tmp/qwen_3_06b_base.safetensors`
Qwen-Image VAE weights at `/root/autodl-tmp/qwen_image_vae.safetensors`
```

Suggested layout:

```text
/root/autodl-tmp/anima-base-v1.0.safetensors
/root/autodl-tmp/qwen_3_06b_base.safetensors
/root/autodl-tmp/qwen_image_vae.safetensors
```

## 4. Edit Dataset Config

Edit:

```bash
nano /root/autodl-tmp/anima-train/dataset_config.toml
```

Set:

```toml
image_dir = "/root/autodl-tmp/anima-train/data"
```

## 5. Edit Training Script

Edit:

```bash
nano /root/autodl-tmp/anima-train/train_anima_lora_4090.sh
```

Set the model paths:

```bash
ANIMA_DIT="/root/autodl-tmp/anima-base-v1.0.safetensors"
QWEN3="/root/autodl-tmp/qwen_3_06b_base.safetensors"
QWEN_IMAGE_VAE="/root/autodl-tmp/qwen_image_vae.safetensors"
DATASET_CONFIG="/root/autodl-tmp/anima-train/dataset_config.toml"
OUTPUT_DIR="/root/autodl-tmp/anima-train/output"
```

## 6. Start Training

From the `sd-scripts` directory with the venv activated:

```bash
cd /root/autodl-tmp/sd-scripts
source venv/bin/activate
bash /root/autodl-tmp/anima-train/train_anima_lora_4090.sh
```

Checkpoints will be written to:

```text
/root/autodl-tmp/anima-train/output
```

## Notes

The first run trains only the Anima DiT LoRA, not the Qwen3 text encoder LoRA. This is intentional because the script uses `--cache_text_encoder_outputs` and `--network_train_unet_only` for a conservative first style LoRA run.

The first-run settings are tuned for one RTX 4090: dataset batch size 2, gradient accumulation 4, LoRA rank/alpha 32, learning rate 2e-5, cosine scheduler, bf16 precision, 20 epochs, and checkpoints every 2 epochs.
