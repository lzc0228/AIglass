#!/bin/bash
# 使用清华源创建 openai_glasses conda 环境

set -e

echo "=== 设置清华源 ==="
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/free/
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main/
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge/
conda config --set show_channel_urls yes
conda config --remove channels defaults 2>/dev/null || true
conda config --remove channels https://repo.anaconda.com/pkgs/main 2>/dev/null || true
conda config --remove channels https://repo.anaconda.com/pkgs/r 2>/dev/null || true

echo "=== 创建 Python 3.10 环境 ==="
conda create -n openai_glasses python=3.10 -y

echo "=== 激活环境并安装依赖 ==="
source $(conda info --base)/etc/profile.d/conda.sh
conda activate openai_glasses

# 使用清华 PyTorch 源
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 安装 PyTorch (CUDA 12.1)
pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu121

# 安装其他依赖
pip install -r requirements.txt

echo "=== 安装完成 ==="
conda list | head -20
