#!/bin/bash
# download_piper_model.sh
# 下载 Piper-TTS 中文语音模型
# 使用 HuggingFace 镜像加速下载

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Piper-TTS 中文模型下载脚本 ===${NC}"

# 配置
MODEL_NAME="zh_CN-huayan-medium"
MODEL_DIR="model/piper"
HF_MIRROR="https://hf-mirror.com"

# 创建目录
echo -e "${YELLOW}[1/4] 创建模型目录...${NC}"
mkdir -p "$MODEL_DIR"
cd "$MODEL_DIR"

# 检查是否已下载
if [ -f "${MODEL_NAME}.onnx" ]; then
    echo -e "${GREEN}模型��存在，跳过下载${NC}"
    ls -lh "${MODEL_NAME}.onnx"
    exit 0
fi

# 使用 HuggingFace 镜像下载
echo -e "${YELLOW}[2/4] 从 HuggingFace 镜像下载模型...${NC}"

# 注意：zh_CN-huayan-medium 来自不同仓库
HUAYAN_REPO="Lin-HuaZhi/piper-voice-zh-huayan-medium"

# 方法1: 使用 wget
echo "下载 ${MODEL_NAME}.onnx..."
wget -c "${HF_MIRROR}/${HUAYAN_REPO}/resolve/main/${MODEL_NAME}.onnx" \
    -O "${MODEL_NAME}.onnx" || {
    echo -e "${RED}wget 下载失败，尝试使用 huggingface-cli...${NC}"
    # 方法2: 使用 huggingface-cli
    huggingface-cli download ${HUAYAN_REPO} ${MODEL_NAME}.onnx \
        --repo-type model --local-dir . --local-dir-use-symlinks False || {
        echo -e "${RED}huggingface-cli 下载失败，尝试使用原始地址...${NC}"
        # 方法3: 原始地址（最慢）
        wget -c "https://huggingface.co/${HUAYAN_REPO}/resolve/main/${MODEL_NAME}.onnx" \
            -O "${MODEL_NAME}.onnx"
    }
}

echo "下载 ${MODEL_NAME}.onnx.json..."
wget -c "${HF_MIRROR}/${HUAYAN_REPO}/resolve/main/${MODEL_NAME}.onnx.json" \
    -O "${MODEL_NAME}.onnx.json" || {
    huggingface-cli download ${HUAYAN_REPO} ${MODEL_NAME}.onnx.json \
        --repo-type model --local-dir . --local-dir-use-symlinks False || {
        wget -c "https://huggingface.co/${HUAYAN_REPO}/resolve/main/${MODEL_NAME}.onnx.json" \
            -O "${MODEL_NAME}.onnx.json"
    }
}

# 验证文件
echo -e "${YELLOW}[3/4] 验证下载文件...${NC}"
if [ -f "${MODEL_NAME}.onnx" ] && [ -f "${MODEL_NAME}.onnx.json" ]; then
    ONNX_SIZE=$(du -h "${MODEL_NAME}.onnx" | cut -f1)
    echo -e "${GREEN}✓ 模型文件: ${ONNX_SIZE}${NC}"
    echo -e "${GREEN}✓ 配置文件: $(du -h "${MODEL_NAME}.onnx.json" | cut -f1)${NC}"
else
    echo -e "${RED}✗ 文件验证失败${NC}"
    exit 1
fi

# 完成
echo -e "${YELLOW}[4/4] 下载完成！${NC}"
echo ""
echo "模型路径: $(pwd)/${MODEL_NAME}.onnx"
echo ""
echo "在 .env 中配置:"
echo "  AIGLASS_TTS_ENABLED=1"
echo "  AIGLASS_TTS_MODEL=$(pwd)/${MODEL_NAME}.onnx"
echo ""
