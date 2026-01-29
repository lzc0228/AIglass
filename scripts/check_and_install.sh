#!/bin/bash
# check_and_install.sh
# 检查环境并安装依赖

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== 环境检查与依赖安装 ===${NC}"

# 1. 检查 Python 环境
echo -e "\n${YELLOW}[1/5] 检查 Python 环境...${NC}"
PYTHON_PATH="/data0/home/scli/conda/envs/openai_glasses/bin/python"
if [ -f "$PYTHON_PATH" ]; then
    PYTHON_VERSION=$($PYTHON_PATH --version)
    echo -e "${GREEN}✓ Python 环境: $PYTHON_VERSION${NC}"
    echo "  路径: $PYTHON_PATH"
else
    echo -e "${RED}✗ Python 环境不存在: $PYTHON_PATH${NC}"
    exit 1
fi

# 2. 检查已安装的 Python 包
echo -e "\n${YELLOW}[2/5] 检查已安装的 Python 包...${NC}"
PACKAGES=("fastapi" "uvicorn" "torch" "ultralytics" "opencv-python" "dashscope" "openai" "pydub" "pygame")
for pkg in "${PACKAGES[@]}"; do
    if $PYTHON_PATH -c "import $pkg" 2>/dev/null; then
        VERSION=$($PYTHON_PATH -c "import $pkg; print(getattr($pkg, '__version__', 'OK'))" 2>/dev/null || echo "OK")
        echo -e "  ${GREEN}✓${NC} $pkg ($VERSION)"
    else
        echo -e "  ${RED}✗${NC} $pkg (未安装)"
    fi
done

# 3. 检查可选包（蓝牙、TTS）
echo -e "\n${YELLOW}[3/5] 检查可选包（蓝牙、TTS）...${NC}"
OPTIONAL_PACKAGES=("pybluez" "pulsectl" "piper_tts" "onnxruntime" "huggingface_hub")
for pkg in "${OPTIONAL_PACKAGES[@]}"; do
    if $PYTHON_PATH -c "import $pkg" 2>/dev/null; then
        VERSION=$($PYTHON_PATH -c "import $pkg; print(getattr($pkg, '__version__', 'OK'))" 2>/dev/null || echo "OK")
        echo -e "  ${GREEN}✓${NC} $pkg ($VERSION)"
    else
        echo -e "  ${YELLOW}○${NC} $pkg (未安装，可选)"
    fi
done

# 4. 检查系统命令（蓝牙、音频）
echo -e "\n${YELLOW}[4/5] 检查系统命令...${NC}"
SYSTEM_CMDS=("bluetoothctl" "pactl" "pulseaudio" "piper")
for cmd in "${SYSTEM_CMDS[@]}"; do
    if command -v $cmd &>/dev/null; then
        echo -e "  ${GREEN}✓${NC} $cmd"
    else
        echo -e "  ${YELLOW}○${NC} $cmd (未安装，服务器环境可忽略)"
    fi
done

# 5. 检查模型文件
echo -e "\n${YELLOW}[5/5] 检查模型文件...${NC}"
MODEL_FILES=(
    "model/yolo-seg.pt"
    "model/yoloe-11l-seg.pt"
    "model/shoppingbest5.pt"
    "model/trafficlight.pt"
    "model/hand_landmarker.task"
    "model/piper/zh_CN-huayan-medium.onnx"
)
for model in "${MODEL_FILES[@]}"; do
    if [ -f "$model" ]; then
        SIZE=$(du -h "$model" | cut -f1)
        echo -e "  ${GREEN}✓${NC} $model ($SIZE)"
    else
        echo -e "  ${RED}✗${NC} $model (缺失)"
    fi
done

# 6. 安装建议
echo -e "\n${BLUE}=== 安装建议 ===${NC}"

echo -e "${YELLOW}安装可选 Python 包:${NC}"
echo "  $PYTHON_PATH -m pip install pybluez pulsectl onnxruntime huggingface_hub"
echo "  $PYTHON_PATH -m pip install piper-tts  # 或使用预编译二进制"

echo -e "\n${YELLOW}安装系统包（Jetson Nano 上）:${NC}"
echo "  sudo apt-get install bluez bluez-tools pulseaudio pulseaudio-module-bluetooth"

echo -e "\n${YELLOW}下载 Piper-TTS 模型:${NC}"
echo "  python scripts/download_piper_model.py"
echo "  或 bash scripts/download_piper_model.sh"

echo -e "\n${YELLOW}配置 .env 文件:${NC}"
echo "  cp .env.example .env"
echo "  # 编辑 .env 填入配置"
echo "  AIGLASS_TTS_ENABLED=1"
echo "  AIGLASS_TTS_MODEL=model/piper/zh_CN-huayan-medium.onnx"

echo -e "\n${GREEN}=== 检查完成 ===${NC}"
