#!/usr/bin/env bash
set -euo pipefail

export OMP_NUM_THREADS=1

ANIMA_DIT="/root/autodl-tmp/anima-base-v1.0.safetensors"
QWEN3="/root/autodl-tmp/qwen_3_06b_base.safetensors"
QWEN_IMAGE_VAE="/root/autodl-tmp/qwen_image_vae.safetensors"
DATASET_CONFIG="/root/autodl-tmp/anima-train/dataset_config.toml"
OUTPUT_DIR="/root/autodl-tmp/anima-train/output"

accelerate launch --num_cpu_threads_per_process 1 anima_train_network.py \
  --pretrained_model_name_or_path="${ANIMA_DIT}" \
  --qwen3="${QWEN3}" \
  --vae="${QWEN_IMAGE_VAE}" \
  --dataset_config="${DATASET_CONFIG}" \
  --output_dir="${OUTPUT_DIR}" \
  --output_name="atomsphere_style_anima_lora_r32" \
  --save_model_as=safetensors \
  --network_module=networks.lora_anima \
  --network_dim=32 \
  --network_alpha=32 \
  --network_train_unet_only \
  --gradient_accumulation_steps=4 \
  --max_data_loader_n_workers=4 \
  --persistent_data_loader_workers \
  --learning_rate=2e-5 \
  --optimizer_type="AdamW8bit" \
  --lr_scheduler="cosine" \
  --lr_warmup_steps=100 \
  --timestep_sampling="sigmoid" \
  --max_train_epochs=20 \
  --save_every_n_epochs=2 \
  --mixed_precision="bf16" \
  --save_precision="bf16" \
  --gradient_checkpointing \
  --cache_latents \
  --cache_text_encoder_outputs \
  --qwen_image_vae_2d \
  --vae_chunk_size=64 \
  --vae_disable_cache \
  --console_log_simple \
  --resize_interpolation lanczos
