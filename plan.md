# 语音输出代码修改计划：移除大模型依赖 + 添加蓝牙音频输出

## 修改目标

1. **移除大模型依赖**：注释掉所有调用大模型的代码（omni_client, qwen_extractor等）
2. **保留结构化语音输出**：使用 semantic_output.py 的规则驱动语音生成
3. **添加蓝牙音频输出**：通过 Jetson Nano 的蓝牙模块传输到骨传导耳机
4. **集成 Piper-TTS**：使用轻量级神经 TTS 处理动态文本

**语音播放路径**：主板（传输信号） → Nano（通过蓝牙模块） → 联想骨传导耳机 S102

**设备配置**：
- 骨传导耳机：联想骨传导耳机 S102（通用 A2DP 协议）
- TTS 引擎：piper-tts（轻量神经 TTS）
- 音频系统：PulseAudio

---

## 关键文件列表

| 文件 | 操作 | 说明 |
|------|------|------|
| `omni_client.py` | 注释掉调用 | DashScope Omni-Turbo 大模型语音客户端 |
| `qwen_extractor.py` | 修改 | 保留本地映射，注释掉API调用 |
| `app_main.py` | 修改 | 注释掉 start_ai_with_text() 的AI语音部分 |
| `audio_player.py` | 修改 | 添加蓝牙输出支持 |
| `bluetooth_audio.py` | 新建 | 蓝牙设备管理和音频播放模块 |
| `piper_tts.py` | 新建 | Piper-TTS 轻量神经 TTS 封装 |
| `.env.example` | 修改 | 添加蓝牙和 TTS 相关配置 |

---

## Phase 1: 注释掉大模型调用

### 1.1 `omni_client.py`
- 整个文件功能暂时停用
- 在 app_main.py 中注释掉 `import omni_client`
- 注释掉 `start_ai_with_text()` 函数中的 AI 调用

### 1.2 `qwen_extractor.py`
- 保留本地映射字典 `LOCAL_LABEL_MAP`
- 注释掉 `_make_client()` 和 API 调用部分
- 只使用本地映射进行物品名转换

### 1.3 `app_main.py` 需要注释的位置
```python
# 第1218-1238行附近：AI音频处理
# 注释掉 base64 音频解码和播放部分

# 第2175-2195行附近：AI对话启动
# 将 await start_ai_with_text(user_text) 改为直接使用本地语音
```

---

## Phase 2: 添加蓝牙音频输出

### 2.1 新建 `bluetooth_audio.py`

功能设计：
```python
class BluetoothAudioManager:
    """蓝牙音频管理器"""

    def __init__(self):
        self.device_addr = None
        self.device_name = None
        self.connected = False
        self.pulse_client = None  # PulseAudio 客户端

    def scan_devices(self) -> List[Dict]:
        """扫描附近蓝牙设备"""

    def connect(self, device_addr: str) -> bool:
        """连接蓝牙设备"""

    def disconnect(self):
        """断开蓝牙连接"""

    def play_audio(self, audio_data: bytes):
        """通过蓝牙播放音频"""

    def is_connected(self) -> bool:
        """检查连接状态"""
```

实现方式：
- 使用 `pybluez` 库进行蓝牙连接管理
- 使用 PulseAudio 的 `pactl` 命令或 `pulsectl` 库进行音频路由
- 蓝牙配置文件使用 A2DP（音频传输）或 HFP（免提配置文件）

### 2.2 修改 `audio_player.py`

添加蓝牙输出模式：
```python
class AudioPlayer:
    def __init__(self):
        self.output_mode = os.getenv("AIGLASS_AUDIO_OUTPUT", "local")  # local/bluetooth
        self.bluetooth_mgr = None

    def play_audio_threadsafe(self, text_or_file):
        """统一音频播放接口，支持路由到蓝牙"""
        if self.output_mode == "bluetooth":
            self._play_via_bluetooth(text_or_file)
        else:
            # 原有的本地播放逻辑
            ...
```

### 2.3 配置文件更新

在 `.env.example` 添加：
```bash
# 音频输出配置
AIGLASS_AUDIO_OUTPUT=bluetooth    # 输出模式: local/bluetooth/esp32
AIGLASS_BLUETOOTH_ENABLED=1       # 启用蓝牙音频
AIGLASS_BLUETOOTH_DEVICE_ADDR=    # 蓝牙设备MAC地址（自动扫描时可选）
AIGLASS_BLUETOOTH_DEVICE_NAME=联想S102  # 蓝牙设备名称（用于自动连接）
AIGLASS_BLUETOOTH_AUTO_CONNECT=1  # 启动时自动连接

# TTS 配置
AIGLASS_TTS_ENABLED=1             # 启用 TTS
AIGLASS_TTS_ENGINE=piper          # TTS 引擎: piper
AIGLASS_TTS_MODEL=model/piper/zh_CN-piper-medium.onnx
AIGLASS_TTS_VOICE=zh_CN-piper-medium
```

---

## Phase 4: Jetson Nano 蓝牙配置

### 3.1 系统依赖（需要在 Jetson Nano 上安装）

```bash
# 蓝牙支持
sudo apt-get install bluez bluez-tools

# PulseAudio 蓝牙模块
sudo apt-get install pulseaudio pulseaudio-module-bluetooth

# Python 蓝牙库
pip install pybluez pulsectl
```

### 3.2 蓝牙服务配置

```bash
# 启动蓝牙服务
sudo systemctl start bluetooth
sudo systemctl enable bluetooth

# PulseAudio 配置蓝牙自动切换
# 在 /etc/pulse/default.pa 中添加：
load-module module-bluetooth-discover
load-module module-bluetooth-policy
```

### 3.3 骨传导耳机配对（联想骨传导耳机 S102）

```bash
# 扫描设备
bluetoothctl scan on
# 输出中查找 "Lenovo S102" 或类似名称

# 配对设备（替换为实际 MAC 地址）
bluetoothctl pair XX:XX:XX:XX:XX:XX

# 连接设备
bluetoothctl connect XX:XX:XX:XX:XX:XX

# 设置为信任设备（自动连接）
bluetoothctl trust XX:XX:XX:XX:XX:XX

# 验证连接
bluetoothctl info XX:XX:XX:XX:XX:XX
```

**联想 S102 特殊说明**：
- 使用标准 A2DP 蓝牙配置文件
- 支持 SBC 编码（大部分 Linux 发行版默认支持）
- 如果连接不稳定，可以尝试关闭蓝牙节能：
```bash
sudo hciconfig hci0 nosmp
```

---

## Phase 2.5: 集成 Piper-TTS（轻量神经 TTS）

### 2.5.1 新建 `piper_tts.py`

功能设计：
```python
import torch
import numpy as np
import subprocess

class PiperTTS:
    """Piper-TTS 轻量神经 TTS 封装"""

    def __init__(self, model_path="model/piper/zh_CN-piper-medium.onnx"):
        self.model_path = model_path
        self.executable = "piper"  # piper 命令行工具

    def text_to_audio(self, text: str) -> bytes:
        """将文本转换为 PCM16 音频数据"""

    def text_to_file(self, text: str, output_path: str) -> str:
        """将文本转换为 WAV 文件"""
```

### 2.5.2 安装 Piper-TTS

```bash
# 方法1: 使用预编译二进制（推荐）
wget https://github.com/rhasspy/piper/releases/latest/download/piper_linux_aarch64.tar.gz
tar xvf piper_linux_aarch64.tar.gz
sudo mv piper/piper /usr/local/bin/

# 下载中��模型
wget https://huggingface.co/rhasspy/piper-voices/v1/0/zh_CN/medium/zh_CN-piper-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/v1/0/zh_CN/medium/zh_CN-piper-medium.onnx.json
mkdir -p model/piper
mv zh_CN-piper-medium.* model/piper/

# 方法2: Python 包安装
pip install piper-tts
```

### 2.5.3 修改 `audio_player.py` 集成 TTS

```python
from piper_tts import PiperTTS

class AudioPlayer:
    def __init__(self):
        self.tts = PiperTTS()
        self.output_mode = os.getenv("AIGLASS_AUDIO_OUTPUT", "local")
        self.bluetooth_mgr = None

    def play_voice_text(self, text: str):
        """播报语音文本，优先使用预录音频，否则使用 TTS"""
        # 检查是否有预录音频
        audio_file = self._find_pre_recorded(text)
        if audio_file:
            self.play_audio_threadsafe(audio_file)
        else:
            # 使用 TTS 生成音频
            wav_path = self.tts.text_to_file(text, f"/tmp/tts_{time.time()}.wav")
            self.play_audio_threadsafe(wav_path)
```

---

## Phase 3: 结构化语音输出（保留现有逻辑）

### 4.1 `semantic_output.py` 保持不变

该模块已经是规则驱动的结构化输出，不依赖大模型：
- 钟点方向：1-12点
- 距离估计：基于 bbox 面积的启发式估计
- 避让动作：预定义的动作模板
- 紧急程度：HIGH/MEDIUM/LOW

### 4.2 语音模板（各工作流）

| 工作流 | 语音模板示例 |
|--------|-------------|
| 盲道导航 | "前方有障碍物，注意避让"、"左转一点"、"保持直行" |
| 过马路 | "绿灯 1/5"、"正在等待绿灯"、"过马路结束" |
| 物品搜索 | "向上"、"向左"、"OK"、"请将物品移到画面中心" |
| 场景探索 | "X点方向大概Y米有物体，注意避让" |

---

## 实施步骤

### Step 1: 注释大模型调用
1. 在 `app_main.py` 中注释掉 `import omni_client`
2. 注释掉 `start_ai_with_text()` 中的 AI 音频处理
3. 修改 `qwen_extractor.py` 只使用本地映射

### Step 2: 创建蓝牙音频模块
1. 新建 `bluetooth_audio.py`
2. 实现蓝牙设备扫描和连接
3. 实现 PulseAudio 路由

### Step 3: 集成到音频播放器
1. 修改 `audio_player.py` 支持蓝牙输出
2. 修改 `voice_scheduler.py` 支持蓝牙模式
3. 更新 `.env.example` 配置

### Step 4: Jetson Nano 系统配置
1. 安装蓝牙和 PulseAudio 依赖
2. 配置蓝牙自动连接
3. 配置 PulseAudio 蓝牙模块

### Step 5: Piper-TTS 配置
1. 安装 Piper-TTS（推荐使用预编译二进制）
2. 下载中文语音模型到 `model/piper/`
3. 测试 TTS 生成音频是否正常

---

## 验证测试

### 测试 1: 大模型已禁用
- 启动系统后不调用任何 DashScope API
- 语音播报仍能正常工作（使用预录音频和结构化模板）

### 测试 2: 蓝牙音频输出
- 骨传导耳机能自动连接到 Jetson Nano
- 语音能通过蓝牙传输到耳机
- 音质和延迟满足要求

### 测试 3: 功能完整性
- 盲道导航语音播报正常
- 过马路语音播报正常
- 物品搜索语音播报正常
- 场景探索语音播报正常

### 测试 4: Piper-TTS 验证
- 动态文本能正确转换为语音
- TTS 生成的音频能通过蓝牙传输到耳机
- TTS 延迟满足实时性要求（<500ms）

---

## 依赖库更新

在 `requirements.txt` 添加：
```
pybluez>=0.23
pulsectl>=23.0.0
piper-tts>=1.2.0
```

---

## 风险与注意事项

1. **蓝牙连接稳定性**：蓝牙可能会断连，需要添加重连机制
2. **音频延迟**：蓝牙音频有额外延迟，可能需要优化
3. **设备兼容性**：不同骨传导耳机的蓝牙协议可能有差异
4. **PulseAudio 配置**：PulseAudio 在 Jetson 上可能需要额外调试

---

## 回滚方案

如果蓝牙方案不稳定，可以快速回滚：
1. 设置 `AIGLASS_AUDIO_OUTPUT=local` 使用本地 3.5mm 音频输出
2. 或者使用 `AIGLASS_AUDIO_OUTPUT=esp32` 通过 ESP32 传输到耳机
