# 项目迁移方案：OpenAIglasses_for_Navigation

## 迁移背景

将 AI 导航眼镜项目从本地服务器迁移到 AutoDL 云服务器。该项目是一个基于计算���视觉和深度学习的视障辅助导航系统，需要完整的 Python 环境、大模型文件和音频资源。

## 目标服务器信息

- **地址**: `ssh -p 13862 root@connect.bjb2.seetacloud.com`
- **目标目录**: `/root/autodl-tmp/IROS`
- **密码**: `lJTlSosqoUj4`

---

## 一、迁移内容清单

### 1.1 项目文件结构

```
OpenAIglasses_for_Navigation-main/
├── app_main.py              # 主程序入口 (FastAPI)
├── requirements.txt         # 依赖列表
├── Dockerfile               # Docker配置
├── docker-compose.yml       # Docker编排
├── .env                     # 环境变量（需复制并修改）
├── .env.example             # 环境变量模板
├── model/                   # ML模型目录 (1.4GB)
├── voice/                   # 语音资产 (222MB)
├── recordings/              # 录音文件 (33MB，可忽略)
├── static/                  # 静态资源
├── templates/               # HTML模板
├── context/                 # 配置文件
└── third_party/             # 第三方库
```

### 1.2 大文件清单

| 文件/目录 | 大小 | 描述 |
|-----------|------|------|
| model/ 目录 | 1.4GB | 所有模型文件 |
| model/trafficlight.pt | 175MB | 交通灯检测模型 |
| model/shoppingbest5.pt | 144MB | 购物物品识别 |
| model/yolo-seg.pt | 144MB | 盲道分割模型 |
| model/3dmodel.obj | 126MB | 3D模型文件 |
| model/yoloe-11l-seg.pt | 71MB | 障碍物检测 |
| model/yolo11l-seg.pt | 56MB | YOLO-L分割 |
| model/piper/zh_CN-huayan-medium.onnx | 63MB | TTS语音合成 |
| voice/ | 222MB | 预录语音提示 |
| recordings/ | 33MB | 运行时录音（可选迁移） |

### 1.3 Conda虚拟环境

**环境名称**: `openai_glasses`
**环境路径**: `/data0/home/scli/conda/envs/openai_glasses`
**环境大小**: 6.5GB
**Python版本**: 3.12.7

**核心依赖**:
- opencv-python==4.13.0.90
- numpy==2.4.2
- onnxruntime==1.23.2
- openai==2.15.0
- piper-tts==1.3.0
- matplotlib==3.9.2

**注意**: 项目使用的是 `openai_glasses` conda环境，但 `requirements.txt` 中的核心依赖（torch, ultralytics, fastapi等）未在该环境中完全安装。需要确认实际运行环境。

---

## 二、迁移步骤

### 步骤1：导出依赖清单

```bash
# 激活环境
conda activate openai_glasses

# 导出pip依赖（核心依赖）
pip freeze > requirements_full.txt

# 导出conda环境配置
conda env export > environment.yml

# 生成精简的依赖列表（仅项目需要的）
cat > requirements_core.txt << 'EOF'
fastapi==0.104.1
uvicorn[standard]==0.24.0
websockets==12.0
python-multipart==0.0.6
opencv-python==4.8.1.78
numpy>=1.26.0
Pillow==10.1.0
ultralytics==8.3.200
torch>=2.2.0
torchvision
mediapipe==0.10.8
pyaudio==0.2.14
pydub==0.25.1
pygame==2.5.2
python-dotenv==1.0.0
opencv-contrib-python==4.8.1.78
openai>=1.3.5
piper-tts>=1.2.0
onnxruntime>=1.16.0
EOF
```

### 步骤2：压缩项目代码

```bash
# 打包项目（包含recordings，排除不需要的文件）
tar -czf openai_glasses_project.tar.gz \
  --exclude='.git' \
  --exclude='voice/generated/*' \
  --exclude='context/faces/images/*' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.specstory' \
  --exclude='CLIP-main.zip' \
  OpenAIglasses_for_Navigation-main/
```

### 步骤3：传输到目标服务器

```bash
# 上传项目文件
scp -P 13862 openai_glasses_project.tar.gz root@connect.bjb2.seetacloud.com:/root/autodl-tmp/IROS/

# 上传依赖清单
scp -P 13862 requirements_full.txt requirements_core.txt environment.yml root@connect.bjb2.seetacloud.com:/root/autodl-tmp/IROS/
```

### 步骤4：在目标服务器解压和配置

```bash
# SSH登录
ssh -p 13862 root@connect.bjb2.seetacloud.com

# 创建目录
cd /root/autodl-tmp/IROS
mkdir -p openai_glasses

# 解压项目
tar -xzf openai_glasses_project.tar.gz -C openai_glasses/
cd openai_glasses/OpenAIglasses_for_Navigation-main
```

### 步骤5：创建和配置Conda环境

```bash
# 创建新的conda环境（与本地版本匹配）
conda create -n openai_glasses python=3.12.7 -y
conda activate openai_glasses

# 安装系统依赖（AutoDL通常已预装）
# sudo apt-get update
# sudo apt-get install -y portaudio19-dev libgl1-mesa-glx

# 安装核心依赖（先安装PyTorch，根据服务器CUDA版本调整）
pip install torch>=2.2.0 torchvision --index-url https://download.pytorch.org/whl/cu118

# 安装其他依赖
pip install -r requirements_core.txt

# 如果有缺失的包，使用完整清单安装
pip install -r requirements_full.txt
```

### 步骤6：配置环境变量

```bash
# 复制并编辑环境变量
cd openai_glasses/OpenAIglasses_for_Navigation-main
cp .env.example .env
nano .env  # 配置API密钥和其他参数
```

### 步骤7：测试运行

```bash
# 检查GPU
nvidia-smi

# 测试导入
python -c "import torch; import cv2; import fastapi; print('All OK')"

# 启动服务
python app_main.py
```

---

## 三、迁移日志

### 日志文件位置

- **本地日志**: `/data0/home/scli/migration_export_log.txt`
- **服务器日志**: `/root/autodl-tmp/IROS/migration_deploy_log.txt`

### 导出阶段（本地执行）

```bash
# 创建导出日志
cat > /data0/home/scli/migration_export_log.txt << 'EOF'
=== OpenAI Glasses 项目迁移导出日志 ===
开始时间: $(date)
服务器: ssh -p 13862 root@connect.bjb2.seetacloud.com
目标目录: /root/autodl-tmp/IROS

--- 准备阶段 ---
EOF
```

### 部署阶段（服务器执行）

```bash
# 创建部署日志
cat > /root/autodl-tmp/IROS/migration_deploy_log.txt << 'EOF'
=== OpenAI Glasses 项目迁移部署日志 ===
开始时间: $(date)
EOF
```

### 迁移进度跟踪表

| 阶段 | 任务 | 状态 | 时间 | 备注 |
|------|------|------|------|------|
| 准备 | 导出依赖清单 | □ 待完成 | | |
| 准备 | 创建requirements_core.txt | □ 待完成 | | |
| 准备 | 压缩项目文件 | □ 待完成 | | |
| 准备 | 验证压缩包完整性 | □ 待完成 | | |
| 传输 | 上传项目文件(约2GB) | □ 待完成 | | |
| 传输 | 上传依赖清单 | □ 待完成 | | |
| 传输 | 验证传输完整性 | □ 待完成 | | |
| 部署 | 解压项目文件 | □ 待完成 | | |
| 部署 | 创建conda环境 | □ 待完成 | | |
| 部署 | 安装PyTorch | □ 待完成 | | |
| 部署 | 安装核心依赖 | □ 待完成 | | |
| 部署 | 配置环境变量 | □ 待完成 | | |
| 测试 | Python导入测试 | □ 待完成 | | |
| 测试 | GPU可用性测试 | □ 待完成 | | |
| 测试 | 启动服务测试 | □ 待完成 | | |

---

## 五、注意事项

### 5.1 不需要迁移的内容

- `voice/generated/` - TTS生成的语音
- `context/faces/images/` - 人脸识别数据
- `.git/` - Git历史（除非需要）
- `__pycache__/` - Python缓存
- `CLIP-main.zip` - 压缩包（已解压）

**注意**: `recordings/` 目录（33MB）将包含在迁移中

### 5.2 系统依赖

目标服务器需要安装：
- CUDA Toolkit 11.8+
- cuDNN 8.6+
- PortAudio (for PyAudio): `apt-get install portaudio19-dev`
- PulseAudio

### 5.3 网络配置

- Web API端口: 8081
- IMU UDP端口: 12345
- 确保防火墙允许这些端口

### 5.4 API密钥

需要配置 `DASHSCOPE_API_KEY` 在 `.env` 文件中。

---

## 六、验证清单

- [ ] 项目文件完整传输
- [ ] Conda环境正确解压
- [ ] Python版本匹配 (3.12.7)
- [ ] 核心依赖安装成功
- [ ] 模型文件可访问
- [ ] 语音文件可访问
- [ ] GPU可用
- [ ] 环境变量配置正确
- [ ] 服务可启动
- [ ] API端点可访问

---

## 七、回滚方案

如果迁移失败：
1. 保留本地完整备份
2. 使用git恢复代码版本
3. 使用environment.yml重新创建环境
