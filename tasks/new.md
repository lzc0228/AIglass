# 智能导航眼镜项目优化计划

## 背景与目标

### 问题概述
根据用户反馈和日志分析，当前系统存在三个主要问题：
1. **语音播报频率过高**导致传输数据过多，视频和语音播报卡顿
2. **TTS 语音合成系统不可用**，只能播报预录音频文件，无法输出任意语音
3. **代码中大量 if-else 判断**需要优化重构
4. **输出模式切换功能缺失**（任务清单要求但未实现）

### 目标
1. 降低语音播报频率，减少数据传输压力
2. 修复 TTS 系统，确保任意文本都能语音输出
3. 优化代码结构，减少 if-else 判断，使用策略模式/表驱动方式
4. 实现自适应输出模式切换（段落/短句/关键词）

---

## 问题1：语音播报频率优化

### 当前状态
| 播报类型 | 当前间隔 | 问题 |
|---------|---------|------|
| 实时物体播报 | 2.5秒 | 过于频繁 |
| 语义输出 | 3.0秒 | 过于频繁 |
| 盲道直行播报 | 4.0秒 | 适中 |
| 方向指令 | 3.0秒 | 适中 |

### 修复方案
**文件**: `.env`

```bash
# 降低频率50%以减少数据传输压力
AIGLASS_REALTIME_OBJECT_PERIOD_SEC=5.0
AIGLASS_SEM_PERIOD_SEC=6.0
```

---

## 问题2：TTS 系统修复

### 问题诊断
- Piper TTS 模型文件不存在：`model/piper/zh_CN-huayan-medium.onnx`
- Piper 可执行文件/包未安装

### 修复方案

#### 2.1 下载脚本 `scripts/download_piper_model.py`
```python
#!/usr/bin/env python3
"""下载 Piper TTS 中文模型"""
import os
import urllib.request
import sys

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "model", "piper")
MODEL_NAME = "zh_CN-huayan-medium"
MODEL_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/zh/zh_CN/huayan/medium/zh_CN-huayan-medium.onnx"
JSON_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/zh/zh_CN/huayan/medium/zh_CN-huayan-medium.onnx.json"

def download():
    os.makedirs(MODEL_DIR, exist_ok=True)
    model_path = os.path.join(MODEL_DIR, f"{MODEL_NAME}.onnx")
    json_path = os.path.join(MODEL_DIR, f"{MODEL_NAME}.onnx.json")

    if os.path.exists(model_path) and os.path.exists(json_path):
        print(f"[Piper] 模型已存在")
        return 0

    print(f"[Piper] 下载模型...")
    try:
        urllib.request.urlretrieve(MODEL_URL, model_path)
        urllib.request.urlretrieve(JSON_URL, json_path)
        print("[Piper] 模型下载完成")
        return 0
    except Exception as e:
        print(f"[Piper] 下载失败: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(download())
```

#### 2.2 依赖更新 `requirements.txt`
```
piper-tts>=1.2.0
onnxruntime>=1.16.0
```

---

## 问题3：代码优化 - 减少 if-else 判断

### 3.1 场景识别优化（`semantic_output.py`）

**当前问题**：大量使用 if-elif 判断场景

**优化方案**：使用表驱动 + 权重评分模式

```python
# 场景识别策略表（替代大量 if-elif）
SCENE_STRATEGIES = [
    SceneStrategy(
        name="traffic_light",
        keywords={"traffic light", "signal", "red light", "green light"},
        base_confidence=0.9,
        priority=5
    ),
    SceneStrategy(
        name="crosswalk",
        keywords={"crosswalk", "zebra crossing", "zebra"},
        base_confidence=0.85,
        priority=4
    ),
    SceneStrategy(
        name="supermarket",
        keywords={"shelf", "shopping cart", "aisle", "checkout", "counter"},
        base_confidence=0.8,
        priority=3
    ),
    # ... 其他场景
]

def infer_scene_scored(names: List[str], mean_luma: Optional[float] = None) -> Tuple[str, float]:
    """
    基于策略表的场影识别（替代原有大量 if-elif）
    返回: (scene_name, confidence)
    """
    name_set = set(n.lower() for n in names if n)
    scores = []

    for strategy in SCENE_STRATEGIES:
        matched = name_set & strategy.keywords
        if matched:
            # 基于匹配数量和优先级计算得分
            match_score = len(matched) / len(strategy.keywords)
            final_score = strategy.base_confidence * (0.5 + 0.5 * match_score)
            scores.append((strategy.name, final_score, strategy.priority))

    if not scores:
        return "unknown", 0.0

    # 按得分排序，相同得分时优先级高的胜出
    scores.sort(key=lambda x: (x[1], x[2]), reverse=True)
    return scores[0][0], scores[0][1]
```

### 3.2 输出模式策略模式（新增 `output_mode_strategy.py`）

**设计模式**：策略模式（Strategy Pattern）替代 if-elif

```python
"""
输出模式策略模块
根据多因素自动选择输出模式：关键词/短句/段落
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from enum import Enum
import os

class OutputMode(Enum):
    KEYWORD = "keyword"     # 关键词模式（最快）
    PHRASE = "phrase"       # 短句模式（默认）
    PARAGRAPH = "paragraph" # 段落模式（最详细）

@dataclass
class Context:
    """决策上下文"""
    yaw_rate: float                    # 转头速度 (deg/s)
    scene_type: str                    # 场景类型
    object_count: int                  # 物体数量
    has_high_urgency: bool             # 是否有高紧急度物体
    last_announce_interval: float      # 距离上次播报间隔
    user_preference: str               # 用户偏好模式

class OutputModeStrategy(ABC):
    """输出模式策略基类"""
    @abstractmethod
    def decide(self, ctx: Context) -> float:
        """返回该模式的匹配度得分 (0-1)"""
        pass

class KeywordModeStrategy(OutputModeStrategy):
    """关键词模式策略"""
    def decide(self, ctx: Context) -> float:
        score = 0.0
        # 转头快 → 需要简短播报
        if abs(ctx.yaw_rate) > 30:
            score += 0.4
        # 场景复杂（物体多）→ 简短播报
        if ctx.object_count > 5:
            score += 0.3
        # 距离上次播报很近 → 简短播报
        if ctx.last_announce_interval < 3.0:
            score += 0.3
        return min(1.0, score)

class PhraseModeStrategy(OutputModeStrategy):
    """短句模式策略（默认）"""
    def decide(self, ctx: Context) -> float:
        score = 0.5  # 基础分
        # 正常转头速度
        if 10 < abs(ctx.yaw_rate) <= 30:
            score += 0.2
        # 正常数量物体
        if 2 <= ctx.object_count <= 5:
            score += 0.2
        # 正常播报间隔
        if 3.0 <= ctx.last_announce_interval < 6.0:
            score += 0.1
        return min(1.0, score)

class ParagraphModeStrategy(OutputModeStrategy):
    """段落模式策略（详细）"""
    def decide(self, ctx: Context) -> float:
        score = 0.0
        # 静止或很慢转头 → 可以详细播报
        if abs(ctx.yaw_rate) < 10:
            score += 0.4
        # 物体少 → 可以详细描述
        if ctx.object_count <= 2:
            score += 0.3
        # 距离上次播报较久 → 可以详细播报
        if ctx.last_announce_interval >= 6.0:
            score += 0.3
        # 有高紧急度物体需要详细说明
        if ctx.has_high_urgency:
            score -= 0.2  # 紧急情况不适合段落模式
        return min(1.0, score)

class OutputModeSelector:
    """输出模式选择器（策略模式）"""

    def __init__(self):
        self.strategies = {
            OutputMode.KEYWORD: KeywordModeStrategy(),
            OutputMode.PHRASE: PhraseModeStrategy(),
            OutputMode.PARAGRAPH: ParagraphModeStrategy(),
        }

    def select(self, ctx: Context) -> OutputMode:
        """根据上下文选择最佳输出模式"""
        # 如果用户有固定偏好，优先使用
        if ctx.user_preference in ["keyword", "phrase", "paragraph"]:
            return OutputMode(ctx.user_preference)

        # 计算各策略得分
        scores = {
            mode: strategy.decide(ctx)
            for mode, strategy in self.strategies.items()
        }

        # 选择得分最高的模式
        best_mode = max(scores, key=scores.get)
        return best_mode

# 使用示例
selector = OutputModeSelector()
mode = selector.select(Context(
    yaw_rate=latest_yaw_rate_dps,
    scene_type=current_scene,
    object_count=len(detected_objects),
    has_high_urgency=any(o.urgency == "HIGH" for o in objects),
    last_announce_interval=time.time() - last_announce_ts,
    user_preference=os.getenv("AIGLASS_OUTPUT_MODE_PREF", "auto")
))
```

### 3.3 播报文本生成器（策略模式）

```python
class TextGenerator(ABC):
    """文本生成器基类"""
    @abstractmethod
    def generate(self, objects: List[SemanticObject], scene: str) -> str:
        pass

class KeywordTextGenerator(TextGenerator):
    """关键词模式生成器"""
    def generate(self, objects: List[SemanticObject], scene: str) -> str:
        names = [_zh_name(o.name) for o in objects[:3]]
        return "，".join(names) if names else "前方安全"

class PhraseTextGenerator(TextGenerator):
    """短句模式生成器（使用现有逻辑）"""
    def generate(self, objects: List[SemanticObject], scene: str) -> str:
        # 使用现有的 _build_realtime_object_announce_text 逻辑
        return build_phrase_text(objects, scene)

class ParagraphTextGenerator(TextGenerator):
    """段落模式生成器"""
    def generate(self, objects: List[SemanticObject], scene: str) -> str:
        parts = []
        scene_zh = SCENE_ZH_MAP.get(scene, "")
        if scene_zh:
            parts.append(f"当前处于{scene_zh}。")

        for i, o in enumerate(objects[:3], 1):
            parts.append(f"第{i}个物体：{o.clock}点方向的{_zh_name(o.name)}，"
                        f"距离约{o.distance_m:.1f}米，建议{o.avoidance_action}")

        return " ".join(parts)

# 工厂函数
GENERATORS = {
    OutputMode.KEYWORD: KeywordTextGenerator(),
    OutputMode.PHRASE: PhraseTextGenerator(),
    OutputMode.PARAGRAPH: ParagraphTextGenerator(),
}

def generate_text(mode: OutputMode, objects: List[SemanticObject], scene: str) -> str:
    """根据模式生成对应文本"""
    generator = GENERATORS.get(mode, GENERATORS[OutputMode.PHRASE])
    return generator.generate(objects, scene)
```

---

## 问题4：自适应输出模式切换实现

### 集成到 `app_main.py`

```python
# 全局输出模式选择器
output_mode_selector = OutputModeSelector()
last_announce_ts = 0.0

def _decide_output_mode(
    yaw_rate: float,
    scene: str,
    objects: List[Dict],
    has_high_urgency: bool
) -> OutputMode:
    """根据当前状态决定输出模式"""
    ctx = Context(
        yaw_rate=yaw_rate,
        scene_type=scene,
        object_count=len(objects),
        has_high_urgency=has_high_urgency,
        last_announce_interval=time.time() - last_announce_ts,
        user_preference=os.getenv("AIGLASS_OUTPUT_MODE_PREF", "auto")
    )
    return output_mode_selector.select(ctx)

# 在实时播报循环中使用
if realtime_object_announce_enabled and bgr is not None:
    now_ts = time.time()
    if (now_ts - last_realtime_object_announce_ts) >= realtime_object_announce_interval:
        # 检测物体
        raw_objs = obstacle_detector.detect(bgr) if obstacle_detector else []

        # 决定输出模式
        has_high = any(o.get("urgency") == "HIGH" for o in raw_objs)
        mode = _decide_output_mode(
            yaw_rate=latest_yaw_rate_dps,
            scene=current_detected_scene,
            objects=raw_objs,
            has_high_urgency=has_high
        )

        # 生成对应模式的文本
        msg = generate_text(mode, raw_objs, current_detected_scene)

        if msg:
            play_voice_text(msg)
            await ui_broadcast_final(f"[导航] {msg}")
            last_realtime_object_announce_ts = now_ts
            last_announce_ts = now_ts
```

---

## 文件修改清单

| 文件 | 修改类型 | 修改内容 |
|------|---------|---------|
| `.env` | 修改 | 调整播报频率默认值（5.0s/6.0s） |
| `scripts/download_piper_model.py` | 新增 | Piper TTS 模型下载脚本 |
| `requirements.txt` | 修改 | 添加 piper-tts 依赖 |
| `semantic_output.py` | 修改 | 场景识别改用策略表（减少if-else） |
| `output_mode_strategy.py` | 新增 | 输出模式策略模式实现 |
| `text_generators.py` | 新增 | 三种模式的文本生成器 |
| `app_main.py` | 修改 | 集成自适应模式切换 |
| `audio_player.py` | 修改 | 改进TTS错误提示 |

---

## 数据结构参考（基于现有代码）

### ObstacleDetectorClient 返回格式
```python
{
    "name": str,           # 物体英文名称
    "conf": float,         # 置信度 0-1
    "bbox": [x1,y1,x2,y2], # 边界框
    "area": int,           # 像素面积
    "area_ratio": float,   # 相对于画面面积比例
    "center_x": float,     # 中心点x坐标
    "center_y": float,     # 中心点y坐标
    "mask": np.ndarray,    # 分割掩码
}
```

### SemanticObject 格式
```python
{
    "name": str,           # 物体名称
    "name_zh": str,        # 中文名称
    "clock": int,          # 钟点方向 (1-12)
    "clock_zh": str,       # 钟点方向中文
    "lr": str,             # 左中右 (left/center/right)
    "lr_zh": str,          # 左中右中文
    "distance_m": float,   # 距离（米）
    "urgency": str,        # 紧急度 (HIGH/MEDIUM/LOW)
    "avoidance_action": str,  # 避让建议
}
```

---

## 验证步骤

1. **频率优化**: 检查 `.env` 中频率参数是否为 5.0/6.0
2. **TTS修复**: 运行 `python scripts/download_piper_model.py` 下载模型
3. **模式切换**: 快速转头时播报应变为关键词模式，静止时变为段落模式
4. **代码结构**: 检查 `semantic_output.py` 中场景识别是否改用策略表
