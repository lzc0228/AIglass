#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
download_piper_model.py
下载 Piper-TTS 中文语音模型
使用 HuggingFace 镜像加速下载
"""

import os
import sys
from pathlib import Path

# 配置 HuggingFace 镜像
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'


def download_piper_model():
    """下载 Piper-TTS 中文模型（使用花燕中文语音）"""
    model_name = "zh_CN-huayan-medium"
    model_dir = Path("model/piper")
    model_dir.mkdir(parents=True, exist_ok=True)

    onnx_path = model_dir / f"{model_name}.onnx"
    json_path = model_dir / f"{model_name}.onnx.json"

    # 检查是否已下载
    if onnx_path.exists() and json_path.exists():
        print(f"✓ 模型已存在: {onnx_path}")
        print(f"  大小: {onnx_path.stat().st_size / 1024 / 1024:.1f} MB")
        return str(onnx_path)

    # 方法1: 使用 huggingface_hub
    try:
        from huggingface_hub import hf_hub_download

        # zh_CN-huayan-medium 来自不同仓库
        repo_id = "Lin-HuaZhi/piper-voice-zh-huayan-medium"

        print(f"[1/2] 下载 {model_name}.onnx...")
        hf_hub_download(
            repo_id=repo_id,
            filename=f"{model_name}.onnx",
            local_dir=model_dir,
            local_dir_use_symlinks=False
        )

        print(f"[2/2] 下载 {model_name}.onnx.json...")
        hf_hub_download(
            repo_id=repo_id,
            filename=f"{model_name}.onnx.json",
            local_dir=model_dir,
            local_dir_use_symlinks=False
        )

        print("✓ 下载完成!")
        print(f"  模型路径: {onnx_path}")
        print(f"  大小: {onnx_path.stat().st_size / 1024 / 1024:.1f} MB")

        print("\n在 .env 中配置:")
        print(f"  AIGLASS_TTS_ENABLED=1")
        print(f"  AIGLASS_TTS_MODEL={onnx_path}")

        return str(onnx_path)

    except ImportError:
        print("! huggingface_hub 未安装，使用 urllib 下载...")

        # 方法2: 使用 wget (备用)
        import subprocess
        import shutil

        # 检查是否有 wget
        if shutil.which("wget"):
            base_url = "https://hf-mirror.com/Lin-HuaZhi/piper-voice-zh-huayan-medium/resolve/main"
            print(f"[1/2] 下载 {model_name}.onnx...")
            subprocess.run([
                "wget", "-O", str(onnx_path),
                f"{base_url}/{model_name}.onnx"
            ], check=True)

            print(f"[2/2] 下载 {model_name}.onnx.json...")
            subprocess.run([
                "wget", "-O", str(json_path),
                f"{base_url}/{model_name}.onnx.json"
            ], check=True)
        else:
            raise RuntimeError("请先安装 huggingface_hub: pip install huggingface_hub")

        print("✓ 下载完成!")
        return str(onnx_path)

    except Exception as e:
        print(f"✗ 下载失败: {e}")
        print("\n请尝试:")
        print("  pip install huggingface_hub")
        print("  或者手动下载:")
        print(f"  wget https://hf-mirror.com/Lin-HuaZhi/piper-voice-zh-huayan-medium/resolve/main/{model_name}.onnx -P model/piper/")
        return None


if __name__ == "__main__":
    download_piper_model()
