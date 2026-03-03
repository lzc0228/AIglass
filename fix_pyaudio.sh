#!/bin/bash
# 修复 PyAudio 安装

source $(conda info --base)/etc/profile.d/conda.sh
conda activate openai_glasses

pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 安装 PyAudio
pip install pyaudio==0.2.14

# 安装剩余依赖
pip install -r requirements.txt

echo "=== 安装完成 ==="
