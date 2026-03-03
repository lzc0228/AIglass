# OpenAI 智能眼镜导航系统 - 完整项目文档

> **项目概述**: 面向视障人士的智能导航与辅助系统，集成盲道导航、过马路辅助、物品识别、实时语音交互等功能。
>
> **重要声明**: 本项目仅为交流学习使用，请勿直接给视障人群使用。

---

## 目录

1. [项目简介](#1-项目简介)
2. [系统架构](#2-系统架构)
3. [环境配置](#3-环境配置)
4. [目录结构详解](#4-目录结构详解)
5. [核心模块详解](#5-核心模块详解)
6. [状态机与工作流](#6-状态机与工作流)
7. [API接口文档](#7-api接口文档)
8. [前端详解](#8-前端详解)
9. [配置参数说明](#9-配置参数说明)
10. [开发指南](#10-开发指南)
11. [故障排除](#11-故障排除)

---

## 1. 项目简介

### 1.1 项目背景

本项目是一个基于计算机视觉和人工智能的智能导航辅助系统，旨在帮助视障人士进行日常出行。系统通过摄像头获取环境信息，利用深度学习模型进行实时检测和识别，通过语音反馈引导用户安全导航。

### 1.2 核心功能

#### 1.2.1 盲道导航系统
- **实时盲道检测**: 基于 YOLO 分割模型实时识别盲道路径
- **智能语音引导**: 提供精准的方向指引（左转、右转、直行等）
- **障碍物检测与避障**: 自动识别前方障碍物并规划避障路线
- **转弯检测**: 自动识别急转弯并提前提醒
- **光流稳定**: 使用 Lucas-Kanade 光流算法稳定掩码，减少抖动

#### 1.2.2 过马路辅助
- **斑马线识别**: 实时检测斑马线位置和方向
- **红绿灯识别**: 基于颜色和形状的红绿灯状态检测
- **对齐引导**: 引导用户对准斑马线中心
- **安全提醒**: 绿灯时语音提示可以通行

#### 1.2.3 物品识别与查找
- **智能物品搜索**: 语音指令查找物品（如"帮我找一下红牛"）
- **实时目标追踪**: 使用 YOLO-E 开放词汇检测 + ByteTrack 追踪
- **手部引导**: 结合 MediaPipe 手部检测，引导用户手部靠近物品
- **抓取检测**: 检测手部握持动作，确认物品已拿到
- **多模态反馈**: 视觉标注 + 语音引导 + 居中提示

#### 1.2.4 实时语音交互
- **语音识别(ASR)**: 基于阿里云 DashScope Paraformer 实时语音识别
- **多模态对话**: Qwen-Omni-Turbo 支持图像+文本输入，语音输出
- **智能指令解析**: 自动识别导航、查找、对话等不同类型指令
- **上下文感知**: 在不同模式下智能过滤无关指令

#### 1.2.5 视频与音频处理
- **实时视频流**: WebSocket 推流，支持多客户端同时观看
- **音视频同步录制**: 自动保存带时间戳的录像和音频文件
- **IMU 数据融合**: 接收 ESP32 的 IMU 数据，支持姿态估计
- **多路音频混音**: 支持系统语音、AI 回复、环境音同时播放

#### 1.2.6 可视化与交互
- **Web 实时监控**: 浏览器端实时查看处理后的视频流
- **IMU 3D 可视化**: Three.js 实时渲染设备姿态
- **状态面板**: 显示导航状态、检测信息、FPS 等
- **中文友好**: 所有界面和语音使用中文，支持自定义字体

### 1.3 技术栈

| 分类 | 技术 |
|------|------|
| **后端框架** | FastAPI, Uvicorn, asyncio |
| **深度学习** | PyTorch, Ultralytics YOLO/YOLOE, MediaPipe |
| **计算机视觉** | OpenCV, NumPy |
| **语音服务** | 阿里云 DashScope (Paraformer ASR, Qwen-Omni) |
| **前端** | HTML5, JavaScript, Three.js |
| **硬件** | ESP32-CAM, IMU传感器 |
| **音频** | PyAudio, PyGame, pygame.mixer |
| **通信** | WebSocket, UDP |

### 1.4 系统要求

#### 硬件要求
- **开发/服务器端**:
  - CPU: Intel i5 或以上（推荐 i7/i9）
  - GPU: NVIDIA GPU（支持 CUDA 11.8+，推荐 RTX 3060 或以上）
  - 内存: 8GB RAM（推荐 16GB）
  - 存储: 10GB 可用空间

- **客户端设备**（可选）:
  - ESP32-CAM 或其他支持 WebSocket 的摄像头
  - 麦克风（用于语音输入）
  - 扬声器/耳机（用于语音输出）

#### 软件要求
- **操作系统**: Windows 10/11, Linux (Ubuntu 20.04+), macOS 10.15+
- **Python**: 3.9 - 3.11
- **CUDA**: 11.8 或更高版本（GPU 加速必需）
- **浏览器**: Chrome 90+, Firefox 88+, Edge 90+（用于 Web 监控）

#### API 密钥
- **阿里云 DashScope API Key**（必需）:
  - 用于语音识别（ASR）和 Qwen-Omni 对话
  - 申请地址：https://dashscope.console.aliyun.com/

---

## 2. 系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        客户端层                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  ESP32-CAM   │  │   浏览器      │  │   移动端      │          │
│  │  (视频/音频)  │  │  (监控界面)   │  │  (语音控制)   │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
└─────────┼──────────────────┼──────────────────┼──────────────────┘
          │ WebSocket        │ HTTP/WS          │ WebSocket
┌─────────┼──────────────────┼──────────────────┼──────────────────┐
│         │                  │                  │                   │
│    ┌────▼──────────────────▼──────────────────▼────────┐         │
│    │         FastAPI 主服务 (app_main.py)              │         │
│    │  - WebSocket 路由管理                               │         │
│    │  - 音视频流分发                                     │         │
│    │  - 状态管理与协调                                   │         │
│    └────┬────────────────┬────────────────┬─────────────┘      │
│         │                │                │                      │
│  ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐           │
│  │ ASR 模块     │  │ Omni 对话   │  │ 音频播放     │           │
│  │ (asr_core)   │  │(omni_client)│  │(audio_player)│           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│                                                               │
│         应用层                                                │
└───────────────────────────────────────────────────────────────┘
          │                  │                  │
┌─────────▼──────────────────▼──────────────────▼──────────────┐
│                     导航统领层                                │
│    ┌─────────────────────────────────────────────────┐        │
│    │  NavigationMaster (navigation_master.py)         │        │
│    │  - 状态机：IDLE/CHAT/BLINDPATH_NAV/              │        │
│    │            CROSSING/TRAFFIC_LIGHT/ITEM_SEARCH     │        │
│    │  - 模式切换与协调                                  │        │
│    └───┬─────────────────────┬───────────────────┬───┘       │
│        │                     │                   │              │
│   ┌────▼────────┐   ┌────────▼────────┐   ┌─────▼──────┐   │
│   │ 盲道导航     │   │  过马路导航      │   │ 物品查找    │   │
│   │(blindpath)   │   │ (crossstreet)   │   │(yolomedia)  │   │
│   └──────────────┘   └──────────────────┘   └─────────────┘   │
└───────────────────────────────────────────────────────────────┘
          │                  │                  │
┌─────────▼──────────────────▼──────────────────▼──────────────┐
│                       模型推理层                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ YOLO 分割     │  │  YOLO-E 检测 │  │ MediaPipe    │       │
│  │ (盲道/斑马线) │  │ (开放词汇)   │  │  (手部检测)   │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
│  ┌──────────────┐  ┌──────────────┐                          │
│  │ 红绿灯检测    │  │ 光流稳定      │                          │
│  │(HSV+YOLO)     │  │(Lucas-Kanade)│                          │
│  └──────────────┘  └──────────────┘                          │
└───────────────────────────────────────────────────────────────┘
          │
┌─────────▼─────────────────────────────────────────────────────┐
│                    外部服务层                                  │
│  ┌──────────────────────────────────────────────┐             │
│  │  阿里云 DashScope API                         │             │
│  │  - Paraformer ASR (实时语音识别)              │             │
│  │  - Qwen-Omni-Turbo (多模态对话)               │             │
│  │  - Qwen-Turbo (标签提取)                      │             │
│  └──────────────────────────────────────────────┘             │
└───────────────────────────────────────────────────────────────┘
```

### 2.2 数据流

#### 2.2.1 视频流
```
ESP32-CAM
  → [JPEG] WebSocket /ws/camera
  → bridge_io.push_raw_jpeg()
  → yolomedia / navigation_master
  → bridge_io.send_vis_bgr()
  → [JPEG] WebSocket /ws/viewer
  → Browser Canvas
```

#### 2.2.2 音频流（上行）
```
ESP32-MIC
  → [PCM16] WebSocket /ws_audio
  → asr_core
  → DashScope ASR
  → 识别结果
  → start_ai_with_text_custom()
```

#### 2.2.3 音频流（下行）
```
Qwen-Omni / TTS
  → audio_player
  → [PCM16] audio_stream
  → [WAV] HTTP /stream.wav
  → ESP32-Speaker
```

#### 2.2.4 IMU 数据流
```
ESP32-IMU
  → [JSON] UDP 12345
  → process_imu_and_maybe_store()
  → [JSON] WebSocket /ws
  → visualizer.js (Three.js)
```

---

## 3. 环境配置

### 3.1 克隆项目

```bash
git clone <repository_url>
cd OpenAIglasses_for_Navigation-main
```

### 3.2 创建虚拟环境

```bash
# 创建虚拟环境（推荐）
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/macOS
source venv/bin/activate
```

### 3.3 安装依赖

```bash
pip install -r requirements.txt
```

### 3.4 下载模型文件

将以下模型文件放入 `model/` 目录：

| 模型文件 | 用途 | 大小 | 类别 |
|---------|------|------|------|
| `yolo-seg.pt` | 盲道分割 | ~50MB | 盲道(1), 斑马线(0) |
| `yoloe-11l-seg.pt` | 开放词汇检测 | ~80MB | 通用物体检测 |
| `shoppingbest5.pt` | 物品识别 | ~30MB | 饮料/食品类 |
| `trafficlight.pt` | 红绿灯检测 | ~20MB | 红绿灯类别 |
| `hand_landmarker.task` | 手部检测 | ~15MB | MediaPipe 手部 |

### 3.5 配置 API 密钥

创建 `.env` 文件：

```bash
# .env
DASHSCOPE_API_KEY=your_api_key_here
```

或在代码中直接修改（不推荐）：
```python
# app_main.py, line 50
API_KEY = "your_api_key_here"
```

### 3.6 启动系统

```bash
python app_main.py
```

系统将在 `http://0.0.0.0:8081` 启动，打开浏览器访问即可看到实时监控界面。

---

## 4. 目录结构详解

```
OpenAIglasses_for_Navigation-main/
├── 📄 核心应用文件
│   ├── app_main.py                    # [1330行] FastAPI主服务入口
│   ├── navigation_master.py           # [701行] 导航统领器（状态机）
│   ├── workflow_blindpath.py          # 盲道导航工作流（大文件）
│   ├── workflow_crossstreet.py        # [1818行] 过马路导航工作流
│   └── yolomedia.py                   # 物品查找工作流（大文件）
│
├── 🎙️ 语音处理模块
│   ├── asr_core.py                    # [205行] 语音识别核心
│   ├── omni_client.py                 # [76行] Qwen-Omni 客户端
│   ├── qwen_extractor.py              # 标签提取（中文->英文）
│   ├── audio_player.py                # [~600行] 音频播放器
│   ├── audio_stream.py                # 音频流管理
│   └── audio_compressor.py            # 音频压缩
│
├── 🤖 模型相关
│   ├── yoloe_backend.py               # [83行] YOLO-E 后端（开放词汇）
│   ├── trafficlight_detection.py      # [~600行] 红绿灯检测
│   ├── obstacle_detector_client.py    # [176行] 障碍物检测客户端
│   └── models.py                      # 模型定义
│
├── 🎥 视频处理
│   ├── bridge_io.py                   # 线程安全的帧缓冲
│   └── sync_recorder.py               # 音视频同步录制
│
├── 🌐 Web 前端
│   ├── templates/
│   │   └── index.html                 # 主界面 HTML
│   └── static/
│       ├── main.js                    # 主 JS 脚本
│       ├── vision.js                  # 视觉流处理
│       ├── visualizer.js              # IMU 3D 可视化
│       └── vision_renderer.js         # WebGL 渲染器
│
├── 🎵 音频资源
│   ├── music/                         # 系统提示音
│   │   ├── 向上.txt / 向下.txt / 向左.txt / 向右.txt
│   │   ├── 向前.txt / 向后.txt
│   │   ├── 接近斑马线.txt / 远处发现斑马线.txt
│   │   ├── 在画面左侧.txt / 在画面中间.txt / 在画面右侧.txt
│   │   ├── 斑马线到了可以过马路.txt
│   │   ├── 正在靠近斑马线.txt
│   │   ├── 找到啦.txt / 拿到啦.txt / 已对中.txt
│   │   └── ...
│   └── voice/                         # 预录语音
│       ├── map.zh-CN.json             # 语音映射表
│       └── *.wav                      # 语音文件
│
├── 🧠 模型文件
│   └── model/
│       ├── yolo-seg.pt                # 盲道分割模型
│       ├── yoloe-11l-seg.pt           # YOLO-E 开放词汇模型
│       ├── shoppingbest5.pt           # 物品识别模型
│       ├── trafficlight.pt            # 红绿灯检测模型
│       └── hand_landmarker.task       # MediaPipe 手部模型
│
├── 📹 录制文件
│   └── recordings/                    # 自动保存的视频和音频
│       ├── video_*.avi
│       └── audio_*.wav
│
├── 🛠️ ESP32 固件
│   └── compile/
│       ├── compile.ino                # Arduino 主程序
│       └── camera_pins.h              # 摄像头引脚定义
│
├── 🐳 Docker 相关
│   ├── Dockerfile                     # Docker 镜像定义
│   └── docker-compose.yml             # Docker Compose 配置
│
├── ⚙️ 配置文件
│   ├── requirements.txt               # Python 依赖
│   ├── setup.sh                       # Linux/macOS 安装脚本
│   └── setup.bat                      # Windows 安装脚本
│
└── 📚 文档
    ├── README.md                      # 项目主文档
    ├── PROJECT_STRUCTURE.md           # 项目结构说明
    ├── CHANGELOG.md                   # 更新日志
    └── LICENSE                        # MIT 许可证
```

---

## 5. 核心模块详解

### 5.1 app_main.py - 主应用入口

#### 5.1.1 文件概述
- **行数**: 约1330行
- **主要功能**: FastAPI 服务、WebSocket 管理、状态协调
- **关键类/函数**:
  - `load_navigation_models()`: 加载导航模型
  - `start_ai_with_text_custom()`: 扩展版AI启动，支持特殊命令
  - `ws_camera_esp()`: ESP32 相机 WebSocket 处理
  - `ws_audio()`: ESP32 音频 WebSocket 处理
  - `ws_viewer()`: 浏览器视频订阅

#### 5.1.2 全局变量

| 变量名 | 类型 | 用途 |
|--------|------|------|
| `blind_path_navigator` | BlindPathNavigator | 盲道导航器实例 |
| `cross_street_navigator` | CrossStreetNavigator | 过马路导航器实例 |
| `orchestrator` | NavigationMaster | 导航统领器（状态机） |
| `yolo_seg_model` | YOLO | 盲道分割模型 |
| `obstacle_detector` | ObstacleDetectorClient | 障碍物检测器 |
| `camera_viewers` | Set[WebSocket] | 相机视频订阅者集合 |
| `esp32_camera_ws` | WebSocket | ESP32 相机连接 |

#### 5.1.3 物品名称映射

```python
ITEM_TO_CLASS_MAP = {
    "红牛": "Red_Bull",
    "AD钙奶": "AD_milk",
    "ad钙奶": "AD_milk",
    "钙奶": "AD_milk",
}
```

#### 5.1.4 特殊命令处理

| 命令关键词 | 触发操作 |
|-----------|----------|
| "开始导航" / "盲道导航" | 启动盲道导航模式 |
| "停止导航" / "结束导航" | 停止盲道导航 |
| "开始过马路" / "帮我过马路" | 启动过马路模式 |
| "过马路结束" / "结束过马路" | 停止过马路模式 |
| "检测红绿灯" / "看红绿灯" | 启动红绿灯检测 |
| "停止检测" / "停止红绿灯" | 停止红绿灯检测 |
| "帮我找一下 [物品]" | 启动物品搜索 |
| "找到了" / "拿到了" | 确认找到物品 |

### 5.2 navigation_master.py - 导航统领器

#### 5.2.1 文件概述
- **行数**: 约701行
- **主要功能**: 状态机管理、模式切换、语音节流

#### 5.2.2 状态常量

```python
IDLE = "IDLE"                                    # 空闲/未启用
CHAT = "CHAT"                                    # 对话模式
BLINDPATH_NAV = "BLINDPATH_NAV"                  # 正在走盲道
SEEKING_CROSSWALK = "SEEKING_CROSSWALK"          # 盲道阶段发现斑马线
WAIT_TRAFFIC_LIGHT = "WAIT_TRAFFIC_LIGHT"        # 等待交通灯
CROSSING = "CROSSING"                            # 正在过马路
SEEKING_NEXT_BLINDPATH = "SEEKING_NEXT_BLINDPATH" # 寻找下一段盲道
RECOVERY = "RECOVERY"                            # 兜底/恢复
TRAFFIC_LIGHT_DETECTION = "TRAFFIC_LIGHT_DETECTION"  # 红绿灯检测模式
ITEM_SEARCH = "ITEM_SEARCH"                      # 找物品模式
```

#### 5.2.3 状态转换图

```
                    ┌─────────────┐
                    │    IDLE     │
                    └──────┬──────┘
                           │ 启动时自动
                           ▼
                    ┌─────────────┐
                    │    CHAT     │ ◄─────────────────┐
                    └──────┬──────┘                   │
                           │                         │
        ┌──────────────────┼──────────────────┐       │
        │                  │                  │       │
   "开始导航"        "开始过马路"      "检测红绿灯"  │
        │                  │                  │       │
        ▼                  ▼                  ▼       │
┌───────────────┐  ┌──────────────┐  ┌──────────────┐
│ BLINDPATH_NAV │  │   CROSSING   │  │TRAFFIC_LIGHT  │
└───────┬───────┘  └───────┬──────┘  └───────┬──────┘
        │                  │                  │
        │ 发现斑马线        │                  │
        ▼                  │                  │
┌───────────────┐           │                  │
│ SEEKING_      │           │                  │
│ CROSSWALK     │           │                  │
└───────┬───────┘           │                  │
        │ 对准完成           │                  │
        ▼                  │                  │
┌───────────────┐           │                  │
│ WAIT_TRAFFIC  │           │                  │
│    _LIGHT     │           │                  │
└───────┬───────┘           │                  │
        │ 绿灯              │                  │
        ▼                  │                  │
┌───────────────┐           │                  │
│   CROSSING    │◄──────────┘                  │
└───────┬───────┘                              │
        │ 过马路完成                            │
        ▼                                       │
┌───────────────┐                               │
│ SEEKING_       │                               │
│ NEXT_         │                               │
│ BLINDPATH     │                               │
└───────┬───────┘                               │
        │                                        │
        └────────────────────────────────────────┘
```

#### 5.2.4 多数表决过滤器 (MajorityFilter)

用于红绿灯状态稳定：
```python
class MajorityFilter:
    def __init__(self, size: int = 8):
        self.buf: Deque[str] = deque(maxlen=size)

    def push(self, v: str):  # 添加新值
        self.buf.append(v)

    def majority(self) -> str:  # 返回多数值
        # 统计各值出现次数，返回最多的
```

### 5.3 workflow_blindpath.py - 盲道导航工作流

#### 5.3.1 状态常量

```python
STATE_ONBOARDING = "ONBOARDING"           # 上盲道
STATE_NAVIGATING = "NAVIGATING"           # 导航中
STATE_MANEUVERING_TURN = "MANEUVERING_TURN"  # 转弯
STATE_AVOIDING_OBSTACLE = "AVOIDING_OBSTACLE"  # 避障
STATE_LOCKING_ON = "LOCKING_ON"           # 锁定中

# ONBOARDING子步骤
ONBOARDING_STEP_ROTATION = "ROTATION"     # 旋转对准
ONBOARDING_STEP_TRANSLATION = "TRANSLATION"  # 平移居中

# 转向子步骤
MANEUVER_STEP_1_ISSUE_COMMAND = "ISSUE_COMMAND"
MANEUVER_STEP_2_WAIT_FOR_SHIFT = "WAIT_FOR_SHIFT"
MANEUVER_STEP_3_ALIGN_ON_NEW_PATH = "ALIGN_ON_NEW_PATH"
```

#### 5.3.2 核心方法

| 方法 | 功能 |
|------|------|
| `process_frame(image)` | 处理单帧图像，返回导航结果 |
| `_detect_path_and_crosswalk(image)` | 检测盲道和斑马线 |
| `_detect_obstacles(image, path_mask)` | 检测障碍物 |
| `_compute_guidance()` | 计算导航引导指令 |
| `_get_voice_priority(text)` | 获取语音指令优先级 |

#### 5.3.3 导航阈值

```python
# 上盲道阈值
ONBOARDING_ALIGN_THRESHOLD_RATIO = 0.1        # 对准阈值
ONBOARDING_ORIENTATION_THRESHOLD_RAD = np.deg2rad(10)  # 角度阈值

# 导航中阈值
NAV_ORIENTATION_THRESHOLD_RAD = np.deg2rad(10)
NAV_CENTER_OFFSET_THRESHOLD_RATIO = 0.15

# 转弯检测阈值
CURVATURE_PROXY_THRESHOLD = 5e-5

# 斑马线切换阈值
CROSSWALK_SWITCH_AREA_RATIO = 0.22
CROSSWALK_SWITCH_BOTTOM_RATIO = 0.9
CROSSWALK_SWITCH_CONSECUTIVE_FRAMES = 10
```

### 5.4 workflow_crossstreet.py - 过马路导航

#### 5.4.1 状态常量

```python
STATE_SEEKING = "SEEKING_CROSSWALK"       # 寻找并对准远处的斑马线
STATE_WAIT_LIGHT = "WAIT_TRAFFIC_LIGHT"   # 等待红绿灯判定
STATE_CROSSING = "CROSSING"               # 正在过马路
```

#### 5.4.2 配置参数

```python
# 检测间隔
CROSSWALK_DETECTION_INTERVAL = 4  # 每4帧检测一次斑马线
OBSTACLE_DETECTION_INTERVAL = 15  # 每15帧检测一次障碍物

# 阈值
CROSSWALK_MIN_CONF = 0.3          # 斑马线最小置信度
CROSSWALK_MIN_AREA = 5000        # 斑马线最小面积
BLIND_MIN_CONF = 0.34            # 盲道最小置信度

# 对准阈值
ANGLE_THRESH_DEG = 5.0           # 角度阈值
OFFSET_THRESH = 0.08             # 偏移阈值

# 远距离对准阈值（更宽松）
SEEKING_ANGLE_THRESH_DEG = 15.0
SEEKING_OFFSET_THRESH = 0.20

# "很近"判定条件
CROSSWALK_NEAR_AREA_RATIO = 0.30      # 面积占画面30%
CROSSWALK_NEAR_BOTTOM_RATIO = 0.80    # 底部超过画面80%
CROSSWALK_NEAR_MIN_HEIGHT_RATIO = 0.35  # 高度占画面35%
```

#### 5.4.3 核心方法

| 方法 | 功能 |
|------|------|
| `process_frame(bgr_image)` | 处理单帧图像 |
| `_is_crosswalk_near(mask, h, w)` | 判断斑马线是否"很近" |
| `_is_crosswalk_almost_done(mask, h, w)` | 判断斑马线是否"快消失" |
| `_compute_远_distance_alignment(mask, h, w)` | 计算远距离对准 |
| `_estimate_angle_by_stripes(mask, gray)` | 基于条纹估计角度 |
| `_get_crosswalk_guidance_features(mask, shape)` | 计算引导特征 |

### 5.5 yolomedia.py - 物品查找

#### 5.5.1 模式

```python
# 检测模式：使用YOLO检测目标物品
SEGMENT = "SEGMENT"

# 闪烁模式：目标高亮闪烁确认
FLASH = "FLASH"

# 居中引导模式：引导用户将物品居中
CENTER_GUIDE = "CENTER_GUIDE"

# 追踪模式：使用光流追踪目标
TRACK = "TRACK"
```

#### 5.5.2 配置参数

```python
# 模型路径
YOLO_MODEL_PATH = "model/shoppingbest5.pt"
HAND_TASK_PATH = "model/hand_landmarker.task"

# 检测参数
CONF_THRESHOLD = 0.20
MASK_ALPHA = 0.45
STROKE_WIDTH = 5

# 对齐参数
ALIGN_LOOSE_PCT = 0.12  # 归一化距离阈值

# 距离参数（ratio = 物体面积 / 手面积）
RATIO_IDEAL = 1.0       # 理想值
RATIO_TOL = 0.25        # 容许偏离 ±25%

# 光流参数
LK_PARAMS = dict(
    winSize=(21, 21),
    maxLevel=3,
    criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 12, 0.03)
)

# 引导音频间隔
GUIDANCE_INTERVAL_SEC = 1.5
```

### 5.6 trafficlight_detection.py - 红绿灯检测

#### 5.6.1 类别映射

```python
# 红绿灯状态
LIGHT_NAMES = {
    "stop": "红灯",              # 机动车红灯
    "go": "绿灯",                # 机动车绿灯
    "countdown_go": "黄灯",      # 绿灯倒计时
    "countdown_stop": "红灯",    # 红灯倒计时
}

# 过滤的类别
FILTERED_CLASSES = {
    "crossing",          # 斑马线
    "blank",             # 空白
    "countdown_blank"    # 倒计时空白
}
```

#### 5.6.2 核心方法

| 方法 | 功能 |
|------|------|
| `init_model()` | 初始化/预加载模型 |
| `process_single_frame(image, ui_broadcast_callback)` | 处理单帧 |
| `reset_detection_state()` | 重置检测状态 |

#### 5.6.3 多数表决逻辑

```python
# 状态稳定性判断
detection_history = []  # 保存最近N帧
HISTORY_SIZE = 5        # 保存最近5帧
MAJORITY_THRESHOLD = 3  # 5帧中至少3帧相同才认为稳定

# 获取多数表决
def get_majority_light(history):
    counts = {}
    for state in history:
        counts[state] = counts.get(state, 0) + 1
    return max(counts, key=counts.get)
```

### 5.7 asr_core.py - 语音识别核心

#### 5.7.1 热词中断

```python
# 触发全系统复位的热词
INTERRUPT_KEYWORDS = set(
    os.getenv("INTERRUPT_KEYWORDS", "停下,别说了,停止").split(",")
)
```

#### 5.7.2 ASRCallback 类

```python
class ASRCallback:
    """
    设计目标：
    1) 热词出现 → 全清零复位
    2) 不接受打断；AI播报时用户说话只展示，不触发新一轮
    3) partial只用于UI展示；final驱动AI
    """

    def on_result(self, result):  # 处理识别结果
    def on_event(self, event):    # 处理事件
```

#### 5.7.3 全局总闸

```python
_current_recognition: Optional[object] = None
_rec_lock = asyncio.Lock()

async def set_current_recognition(r):
    global _current_recognition
    async with _rec_lock:
        _current_recognition = r

async def stop_current_recognition():
    global _current_recognition
    async with _rec_lock:
        r = _current_recognition
        _current_recognition = None
    if r:
        r.stop()
```

### 5.8 audio_player.py - 音频播放器

#### 5.8.1 功能概述

- 处理预录音频文件的播放
- 通过 ESP32 扬声器输出
- 支持优先级队列
- 音频缓存和压缩

#### 5.8.2 音频映射

```python
# 基础音频映射
AUDIO_MAP = {
    "检测到物体": "music/音频1.wav",
    "向上": "music/音频2.wav",
    "向下": "music/音频3.wav",
    "向左": "music/音频4.wav",
    "向右": "music/音频5.wav",
    "OK": "music/音频6.wav",
    "向前": "music/音频7.wav",
    "后退": "music/音频8.wav",
    "拿到物体": "music/音频9.wav",
}

# voice 目录映射（自动合并）
VOICE_DIR = "voice"
VOICE_MAP_FILE = "voice/map.zh-CN.json"
```

#### 5.8.3 主要函数

| 函数 | 功能 |
|------|------|
| `load_wav_file(filepath)` | 加载WAV文件，转换为8kHz |
| `preload_all_audio()` | 预加载所有音频文件 |
| `play_voice_text(text)` | 根据文本播放音频 |
| `play_audio_threadsafe(data)` | 线程安全播放 |

### 5.9 omni_client.py - Qwen-Omni 客户端

#### 5.9.1 功能概述

- 多模态对话（图像+文本输入，语音输出）
- 流式响应
- OpenAI 兼容模式

#### 5.9.2 核心代码

```python
from openai import OpenAI

oai_client = OpenAI(
    api_key=API_KEY,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

async def stream_chat(content_list, voice="Cherry", audio_format="wav"):
    """流式对话"""
    extra_body = {
        "modalities": ["text", "audio"],
        "audio": {"voice": voice, "format": audio_format}
    }

    completion = oai_client.chat.completions.create(
        model="qwen-omni-turbo",
        messages=[{"role": "user", "content": content_list}],
        stream=True,
        extra_body=extra_body
    )

    for chunk in completion:
        # 处理文本和音频增量
        yield OmniStreamPiece(text_delta=..., audio_b64=...)
```

### 5.10 obstacle_detector_client.py - 障碍物检测

#### 5.10.1 白名单类别

```python
WHITELIST_CLASSES = [
    # 动态类别
    'bicycle', 'car', 'motorcycle', 'bus', 'truck', 'animal', 'scooter', 'stroller', 'dog',

    # 静态障碍物
    'pole', 'post', 'column', 'pillar', 'stanchion', 'bollard', 'utility pole',
    'telegraph pole', 'light pole', 'street pole', 'signpost', 'support post',
    'vertical post', 'bench', 'chair', 'potted plant', 'hydrant', 'cone', 'stone', 'box'
]
```

#### 5.10.2 GPU 配置

```python
DEVICE = os.getenv("AIGLASS_DEVICE", "cuda:0")
AMP_POLICY = os.getenv("AIGLASS_AMP", "bf16").lower()  # bf16/fp16/off
GPU_SLOTS = int(os.getenv("AIGLASS_GPU_SLOTS", "2"))  # 并发限流

@contextmanager
def gpu_infer_slot():
    """统一管理 GPU 并发限流 + inference_mode + AMP autocast"""
    with _gpu_slots:
        if IS_CUDA and AMP_POLICY != "off":
            with torch.inference_mode(), torch.amp.autocast(device_type='cuda', dtype=AMP_DTYPE):
                yield
        else:
            with torch.inference_mode():
                yield
```

### 5.11 crosswalk_awareness.py - 斑马线感知

#### 5.11.1 面积阈值

```python
THRESHOLDS = {
    'discover': 0.01,      # 1% - 发现
    'approaching': 0.08,   # 8% - 靠近
    'near': 0.18,          # 18% - 很近
    'arrival': 0.25,       # 25% - 到达（可以过马路）
}
```

#### 5.11.2 播报间隔

```python
REPEAT_INTERVALS = {
    'approaching': 6.7,   # 靠近阶段：每6.7秒重复
    'near': 3.3,          # 很近阶段：每3.3秒重复
    'arrival': 5.3,       # 到达阶段：每5.3秒重复
}
```

#### 5.11.3 方位描述

```python
def _get_position_description(self, center_x_ratio) -> str:
    """获取方位描述（3分法）"""
    if center_x_ratio < 0.40:
        return "在画面左侧"
    elif center_x_ratio < 0.60:
        return "在画面中间"
    else:
        return "在画面右侧"
```

---

## 6. 状态机与工作流

### 6.1 主状态机 (NavigationMaster)

```
┌─────────────────────────────────────────────────────────────┐
│                        NavigationMaster                      │
├─────────────────────────────────────────────────────────────┤
│  状态                    │  切换条件        │  触发命令      │
├─────────────────────────────────────────────────────────────┤
│  IDLE                    │  启动时自动     │  -             │
│  ↓                       │                 │                │
│  CHAT                    │  默认状态       │  任何对话      │
│  ↓                       │                 │                │
│  BLINDPATH_NAV           │  "开始导航"     │  "停止导航"    │
│  ↓                       │                 │                │
│  SEEKING_CROSSWALK       │  发现斑马线     │  -             │
│  ↓                       │                 │                │
│  WAIT_TRAFFIC_LIGHT      │  对准完成       │  -             │
│  ↓                       │                 │                │
│  CROSSING                │  绿灯稳定       │  -             │
│  ↓                       │                 │                │
│  SEEKING_NEXT_BLINDPATH  │  过马路完成     │  -             │
│  ↓                       │                 │                │
│  BLINDPATH_NAV (循环)     │  检测到盲道     │  -             │
├─────────────────────────────────────────────────────────────┤
│  TRAFFIC_LIGHT_DETECTION  │  "检测红绿灯"   │  "停止检测"    │
├─────────────────────────────────────────────────────────────┤
│  ITEM_SEARCH              │  "帮我找..."   │  "找到了"      │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 盲道导航状态机

```
┌─────────────────────────────────────────────────────────────┐
│                    BlindPathNavigator                       │
├─────────────────────────────────────────────────────────────┤
│  状态                    │  进入条件       │  退出条件      │
├─────────────────────────────────────────────────────────────┤
│  ONBOARDING              │  启动导航       │  对准完成      │
│    ├─ ROTATION          │  -              │  角度对准      │
│    └─ TRANSLATION       │  角度对准       │  位置对准      │
│  ↓                       │                 │                │
│  NAVIGATING              │  位置对准       │  发现转弯/障碍 │
│  ↓                       │                 │                │
│  MANEUVERING_TURN        │  检测到转弯     │  完成转弯      │
│  ↓                       │                 │                │
│  AVOIDING_OBSTACLE       │  检测到障碍     │  绕过障碍      │
│  ↓                       │                 │                │
│  NAVIGATING (循环)        │  -              │  -             │
└─────────────────────────────────────────────────────────────┘
```

### 6.3 过马路状态机

```
┌─────────────────────────────────────────────────────────────┐
│                   CrossStreetNavigator                       │
├─────────────────────────────────────────────────────────────┤
│  状态                    │  进入条件       │  退出条件      │
├─────────────────────────────────────────────────────────────┤
│  SEEKING_CROSSWALK       │  启动过马路     │  斑马线很近    │
│  ↓                       │                 │                │
│  WAIT_TRAFFIC_LIGHT      │  斑马线很近     │  绿灯稳定      │
│  ↓                       │                 │                │
│  CROSSING                │  绿灯稳定       │  斑马线消失    │
│  ↓                       │                 │                │
│  (完成)                  │  -              │  -             │
└─────────────────────────────────────────────────────────────┘
```

### 6.4 物品查找状态机

```
┌─────────────────────────────────────────────────────────────┐
│                      YoloMedia                              │
├─────────────────────────────────────────────────────────────┤
│  模式                    │  进入条件       │  退出条件      │
├─────────────────────────────────────────────────────────────┤
│  SEGMENT                 │  启动查找       │  检测到目标    │
│  ↓                       │                 │                │
│  FLASH                   │  检测到目标     │  用户确认      │
│  ↓                       │                 │                │
│  CENTER_GUIDE            │  闪烁后         │  目标居中      │
│  ↓                       │                 │                │
│  TRACK                   │  居中完成       │  抓取成功      │
│  ↓                       │                 │                │
│  (完成/找到啦)           │  -              │  -             │
└─────────────────────────────────────────────────────────────┘
```

---

## 7. API接口文档

### 7.1 HTTP接口

#### 7.1.1 GET /
- **描述**: 主页
- **返回**: HTMLResponse (index.html)

#### 7.1.2 GET /api/health
- **描述**: 健康检查
- **返回**: PlainTextResponse "OK"

#### 7.1.3 GET /stream.wav
- **描述**: 音频流（用于ESP32播放）
- **返回**: audio/wav 格式流

### 7.2 WebSocket接口

#### 7.2.1 WS /ws/camera
- **描述**: ESP32 相机推流
- **方向**: ESP32 → Server
- **数据**: Binary (JPEG)

#### 7.2.2 WS /ws/viewer
- **描述**: 浏览器订阅视频
- **方向**: Server → Browser
- **数据**: Binary (JPEG)

#### 7.2.3 WS /ws_audio
- **描述**: ESP32 音频上传
- **方向**: ESP32 → Server
- **数据**: Binary (PCM16)
- **命令**:
  - `START`: 开始语音识别
  - `STOP`: 停止语音识别
  - `PROMPT:<text>`: 发起对话

#### 7.2.4 WS /ws_ui
- **描述**: UI 状态推送
- **方向**: Server → Browser
- **数据**: JSON
  - `INIT:<json>`: 初始状态
  - `PARTIAL:<text>`: 识别中
  - `FINAL:<text>`: 识别完成/AI回复

#### 7.2.5 WS /ws
- **描述**: IMU 数据推送
- **方向**: Server → Browser
- **数据**: JSON

### 7.3 UDP接口

#### 7.3.1 UDP 12345
- **描述**: ESP32 IMU 数据
- **格式**: JSON
```json
{
  "ts": 1234567890,
  "accel": {"x": 0.1, "y": 0.2, "z": 9.8},
  "gyro": {"x": 0.01, "y": 0.02, "z": 0.03}
}
```

---

## 8. 前端详解

### 8.1 整体架构

前端采用**模块化 JavaScript** 设计，主要分为三个功能模块：

| 模块 | 文件 | 功能 |
|------|------|------|
| 摄像头与ASR | main.js (第1-326行) | 视频流展示、语音识别UI |
| IMU 3D可视化 | main.js (第329-845行) | Three.js 姿态渲染 |
| 视觉流处理 | vision.js | 视觉数据解析（可选） |

### 8.2 页面布局

```
┌──────────────────────────────────────────────────────────────┐
│  .app (Grid Layout: 1fr 700px)                               │
│  ┌──────────────────────────┬──────────────────────────────┐ │
│  │  .stage (主视频区)        │  .chat (聊天区)              │ │
│  │  ┌──────────────────┐    │  ┌────────────────────────┐  │ │
│  │  │  #canvas (视频)   │    │  │ .chat-head (状态栏)    │  │ │
│  │  │                  │    │  │  - Camera/ASR/FPS      │  │ │
│  │  │  ┌──────────────┐ │    │  └────────────────────────┘  │ │
│  │  │  │.imu-float   │ │    │  ┌────────────────────────┐  │ │
│  │  │  │ IMU 3D面板   │ │    │  │ .chat-list            │  │ │
│  │  │  └──────────────┘ │    │  │  ┌──────────────────┐  │ │
│  │  │                  │    │  │  │ .live (实时识别)   │  │ │
│  │  └──────────────────┘    │  │  └──────────────────┘  │ │
│  │                          │  │  ┌──────────────────┐  │ │
│  │                          │  │  │ .finals (最终结果) │  │ │
│  │                          │  │  └──────────────────┘  │ │
│  └──────────────────────────┴──────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### 8.3 颜色系统 (CSS Variables)

```css
:root {
  --bg:       #0b0f14;    /* 背景色 */
  --card:     #121821;    /* 卡片背景 */
  --text:     #e6edf3;    /* 主文本色 */
  --muted:    #9fb0c3;    /* 次要文本色 */
  --ok:       #7ee787;    /* 成功色 */
  --err:      #ff8080;    /* 错误色 */
  --line:     #1f2937;    /* 边框色 */
}
```

### 8.4 摄像头与ASR模块

#### 8.4.1 DOM元素

| ID | 用途 |
|----|------|
| `#canvas` | 视频流渲染画布 |
| `#camStatus` | 相机连接状态徽章 |
| `#asrStatus` | ASR连接状态徽章 |
| `#fps` | 帧率显示 |
| `#partial` | 实时识别文本 |
| `#finalList` | 最终识别列表 |
| `#chatContainer` | 聊天消息容器（动态创建） |

#### 8.4.2 WebSocket连接

```javascript
// 相机视频流
wsCam = new WebSocket(`${proto}://${location.host}/ws/viewer`);
wsCam.binaryType = 'arraybuffer';
wsCam.onmessage = (ev) => drawBlob(ev.data);

// UI状态推送
wsUI = new WebSocket(`${proto}://${location.host}/ws_ui`);
wsUI.onmessage = (ev) => {
    if (s.startsWith('INIT:')) { /* 初始化 */ }
    if (s.startsWith('PARTIAL:')) { /* 实时识别 */ }
    if (s.startsWith('FINAL:')) { /* 最终结果 */ }
};
```

#### 8.4.3 消息类型处理

| 消息前缀 | 处理方式 |
|---------|----------|
| `INIT:` | 解析JSON，初始化聊天历史 |
| `PARTIAL:` | 更新 `#partial` 内容 |
| `FINAL:` | 创建聊天气泡（区分AI/用户/导航） |

#### 8.4.4 聊天气泡样式

```javascript
// 消息分类
if (text.startsWith('[AI]')) {
    addMessage(text.substring(4).trim(), false);  // AI消息（左侧）
} else if (text.startsWith('[导航]')) {
    const { label, text: show } = navLabelAndText(text);
    addMessage(show, false);  // 导航消息（左侧，带标签）
} else {
    addMessage(text, true);  // 用户消息（右侧）
}
```

### 8.5 IMU 3D可视化模块

#### 8.5.1 Three.js 场景组成

| 组件 | 描述 |
|------|------|
| `Scene` | 主场景 |
| `PerspectiveCamera` | 透视相机（FOV: 70°） |
| `WebGLRenderer` | WebGL渲染器（抗锯齿、透明背景） |
| `AxesHelper` | 坐标轴辅助线（X红/Y绿/Z蓝） |
| `GLTFLoader` | 加载 3D 眼镜模型（`aiglass.glb`） |

#### 8.5.2 灯光系统

```javascript
// 环境光
ambientLight = new THREE.AmbientLight(0x404080, 0.3)

// 主方向光（蓝色调）
mainLight = new THREE.DirectionalLight(0x00aaff, 1.2)

// 填充光（橙色调）
fillLight = new THREE.DirectionalLight(0xff6633, 0.8)

// 边缘光（青色，动态变化）
rimLight = new THREE.DirectionalLight(0x66ffff, 0.6)
```

#### 8.5.3 IMU数据融合算法

```javascript
// 1. 中值滤波（N=5默认）
const fx = mkMed(), fy = mkMed(), fz = mkMed();

// 2. 重力低通滤波（β=0.98）
gLP.x = GRAV_BETA*gLP.x + (1-GRAV_BETA)*ax;

// 3. 姿态解算
const roll  = rad2deg(Math.atan2(az, ay));
const pitch = rad2deg(Math.atan2(-ax, ay));

// 4. 偏航角积分（投影法）
let yawdot = (wx - gOff.x)*gHat.x + (wy - gOff.y)*gHat.y + (wz - gOff.z)*gHat.z;
yaw = wrap180(yaw + yawdot*dt);

// 5. 平滑滤波（EMA）
Rf = alpha*roll + (1-alpha)*Rf;
Pf = alpha*pitch + (1-alpha)*Pf;
Yf = alpha*yaw + (1-alpha)*Yf;

// 6. 零位校正
const R = wrap180(Rf - ref.roll);
const P = wrap180(Pf - ref.pitch);
const Y = wrap180(Yf - ref.yaw);
```

#### 8.5.4 姿态更新流程

```
UDP接收 → JSON解析 → 中值滤波 → 重力滤波 → 姿态解算
  → EMA平滑 → 零位校正 → 四元数转换 → 模型旋转
```

### 8.6 数据面板

实时显示以下IMU数据：

| 数据 | 单位 | 颜色 |
|------|------|------|
| Roll (翻滚角) | 度 | 红色 (#ff6b6b) |
| Pitch (俯仰角) | 度 | 青色 (#4ecdc4) |
| Yaw (偏航角) | 度 | 蓝色 (#45b7d1) |
| gX/gY/gZ | °/s | 红/绿/蓝 |
| aX/aY/aZ | m/s² | 红/绿/蓝 |

### 8.7 自定义参数

| 隐藏控件 | 默认值 | 说明 |
|----------|--------|------|
| `medn` | 5 | 中值滤波窗口大小 |
| `ang_ema` | 0.15 | 角度EMA系数 |
| `grav_beta` | 0.98 | 重力滤波系数 |
| `yaw_db` | 0.08 | 偏航死区 |
| `still_w` | 0.4 | 静止检测阈值 |
| `yaw_leak` | 0.2 | 偏航泄漏校正 |

---

## 9. 配置参数说明

### 9.1 环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `DASHSCOPE_API_KEY` | 必填 | 阿里云API密钥 |
| `BLIND_PATH_MODEL` | model/yolo-seg.pt | 盲道模型路径 |
| `OBSTACLE_MODEL` | model/yoloe-11l-seg.pt | 障碍物模型路径 |
| `AIGLASS_DEVICE` | cuda:0 | GPU设备 |
| `AIGLASS_AMP` | bf16 | 混合精度策略 |
| `AIGLASS_GPU_SLOTS` | 2 | GPU并发槽数 |

### 9.2 导航参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `AIGLASS_MASK_MIN_AREA` | 1500 | 最小掩码面积 |
| `AIGLASS_MASK_MORPH` | 3 | 形态学核大小 |
| `AIGLASS_OBS_INTERVAL` | 15 | 障碍物检测间隔（帧） |
| `AIGLASS_BLINDPATH_INTERVAL` | 8 | 盲道检测间隔（帧） |
| `AIGLASS_PANEL_SCALE` | 0.65 | 数据面板缩放 |

### 9.3 音频参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `TTS_INTERVAL_SEC` | 1.0 | 语音播报间隔 |
| `ENABLE_TTS` | true | 启用语音播报 |
| `VOICE_DIR` | voice/ | 语音文件目录 |

---

## 10. 开发指南

### 10.1 添加新的语音指令

在 `app_main.py` 的 `start_ai_with_text_custom()` 函数中添加：

```python
async def start_ai_with_text_custom(user_text: str):
    # 检查新指令
    if "新指令关键词" in user_text:
        print("[CUSTOM] 新指令被触发")
        await ui_broadcast_final("[系统] 新功能已启动")
        return
```

### 10.2 扩展导航功能

#### 10.2.1 添加新状��

在 `navigation_master.py` 添加状态常量：
```python
YOUR_NEW_MODE = "YOUR_NEW_MODE"
```

在 `NavigationMaster` 类添加状态处理：
```python
def start_your_new_mode(self):
    self.state = YOUR_NEW_MODE
    self.cooldown_until = time.time() + self.COOLDOWN_SEC
```

### 10.3 集成新模型

```python
# 1. 创建模型包装类
class YourModelWrapper:
    def __init__(self, model_path):
        self.model = load_your_model(model_path)

    def detect(self, image):
        return results

# 2. 在 app_main.py 中加载
your_model = YourModelWrapper("model/your_model.pt")

# 3. 在相应工作流中调用
results = your_model.detect(image)
```

### 10.4 调试技巧

```python
# 启用详细日志
import logging
logging.basicConfig(level=logging.DEBUG)

# 查看帧率瓶颈
PERF_DEBUG = True  # yolomedia.py

# 测试单个模块
python test_cross_street_blindpath.py
python test_traffic_light.py
```

---

## 11. 故障排除

### 11.1 常见问题

#### 问题1: 模型加载失败
```
[NAVIGATION] 错误：找不到模型文件
```
**解决方法**: 检查模型路径是否正确，确保文件存在。

#### 问题2: CUDA 不可用
```
[NAVIGATION] CUDA不可用，模型仍在CPU
```
**解决方法**:
1. 检查 NVIDIA 驱动是否安装
2. 检查 CUDA 版本是否匹配
3. 设置 `AIGLASS_DEVICE=cpu` 使用CPU模式

#### 问题3: WebSocket 连接断开
```
[WS] connection closed
```
**解决方法**:
1. 检查网络连接
2. 确认 ESP32 和服务器在同一网络
3. 检查防火墙设置

#### 问题4: 语音识别不工作
```
[AUDIO] 忽略重复START指令（冷却中）
```
**解决方法**:
1. 检查 API_KEY 是否正确
2. 确认网络可以访问阿里云服务
3. 检查麦克风是否正常工作

### 11.2 性能优化

#### 降低GPU内存使用
```python
# 减少并发槽数
AIGLASS_GPU_SLOTS = 1

# 使用FP16而非BF16
AIGLASS_AMP = "fp16"
```

#### 提高帧率
```python
# 增加检测间隔
AIGLASS_BLINDPATH_INTERVAL = 12  # 从8增加到12
AIGLASS_OBS_INTERVAL = 20        # 从15增加到20
```

---

## 附录A: 快速参考

### A.1 语音指令速查表

| 指令 | 功能 |
|------|------|
| "开始导航" | 启动盲道导航 |
| "停止导航" | 停止盲道导航 |
| "开始过马路" | 启动过马路模式 |
| "过马路结束" | 停止过马路模式 |
| "检测红绿灯" | 启动红绿灯检测 |
| "停止检测" | 停止红绿灯检测 |
| "帮我找一下 [物品]" | 启动物品搜索 |
| "找到了" | 确认找到物品 |
| "停下" / "别说了" | 热词中断 |

### A.2 状态速查表

| 状态 | 说明 | 退出条件 |
|------|------|----------|
| IDLE | 空闲 | 自动进入CHAT |
| CHAT | 对话模式 | 启动导航 |
| BLINDPATH_NAV | 盲道导航中 | 停止导航/发现斑马线 |
| SEEKING_CROSSWALK | 寻找斑马线 | 对准完成 |
| WAIT_TRAFFIC_LIGHT | 等待绿灯 | 绿灯稳定 |
| CROSSING | 过马路中 | 过马路完成 |
| TRAFFIC_LIGHT_DETECTION | 红绿灯检测 | 停止检测 |
| ITEM_SEARCH | 找物品模式 | 找到物品 |

### A.3 颜色代码速查表

| 元素 | 颜色 (BGR) | 用途 |
|------|------------|------|
| 盲道 | (0, 255, 0) | 绿色掩码 |
| 斑马线 | (0, 165, 255) | 橙色掩码 |
| 障碍物(近) | (0, 0, 255) | 红色边框 |
| 障碍物(远) | (0, 165, 255) | 黄色边框 |
| 中心线 | (0, 255, 255) | 青色引导线 |
| 目标点 | (255, 0, 255) | 粉色标记 |

---

## 附录B: 文件依赖关系

```
app_main.py
├── navigation_master.py
│   ├── workflow_blindpath.py
│   │   ├── yoloe_backend.py
│   │   ├── obstacle_detector_client.py
│   │   └── crosswalk_awareness.py
│   └── workflow_crossstreet.py
│       └── trafficlight_detection.py
├── yolomedia.py
│   └── yoloe_backend.py
├── asr_core.py
├── omni_client.py
├── audio_player.py
│   ├── audio_stream.py
│   └── audio_compressor.py
├── bridge_io.py
└── sync_recorder.py
```

---

**文档版本**: 1.0
**最后更新**: 2025年1月
**维护者**: 项目开发团队
