# -*- coding: utf-8 -*-
"""
输出模式策略模块

根据多因素自动选择输出模式：关键词/短句/段落

设计模式：策略模式（Strategy Pattern）
- 将输出模式选择逻辑封装为可互换的算法
- 易于扩展新的输出模式
- 减少 if-elif 判断，提高代码可维护性

决策因素：
- 转头速度（yaw_rate）：转头快时需要简短播报
- 物体数量（object_count）：物体多时需要简短播报
- 播报间隔（last_announce_interval）：间隔短时需要简短播报
- 紧急度（has_high_urgency）：紧急情况需要清晰播报
- 用户偏好（user_preference）：用户可强制指定模式
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from enum import Enum
import os


class OutputMode(Enum):
    """输出模式枚举"""
    KEYWORD = "keyword"       # 关键词模式（最快、最简洁）
    PHRASE = "phrase"         # 短句模式（默认、平衡）
    PARAGRAPH = "paragraph"   # 段落模式（最详细）


@dataclass
class Context:
    """
    输出模式决策上下文

    Attributes:
        yaw_rate: 转头速度 (deg/s)，用于判断用户注意力状态
        scene_type: 场景类型（街道、超市等）
        object_count: 检测到的物体数量
        has_high_urgency: 是否有高紧急度物体（如快速接近的车辆）
        last_announce_interval: 距离上次播报的间隔（秒）
        user_preference: 用户偏好模式（keyword/phrase/paragraph/auto）
    """
    yaw_rate: float = 0.0
    scene_type: str = "unknown"
    object_count: int = 0
    has_high_urgency: bool = False
    last_announce_interval: float = 10.0
    user_preference: str = "auto"


class OutputModeStrategy(ABC):
    """输出模式策略基类"""

    @abstractmethod
    def decide(self, ctx: Context) -> float:
        """
        根据上下文决定该模式的匹配度得分

        Args:
            ctx: 决策上下文

        Returns:
            匹配度得分 (0.0 - 1.0)，越高表示越适合该模式
        """
        pass


class KeywordModeStrategy(OutputModeStrategy):
    """
    关键词模式策略

    适用场景：
    - 转头速度快（用户在快速移动，需要极简信息）
    - 物体数量多（信息过载，只保留关键物体名称）
    - 距离上次播报很近（避免信息轰炸）

    输出示例："人，车，柱子"
    """

    def decide(self, ctx: Context) -> float:
        score = 0.0

        # 转头快 → 需要简短播报（最高优先级）
        if abs(ctx.yaw_rate) > 30:
            score += 0.4
        elif abs(ctx.yaw_rate) > 20:
            score += 0.2

        # 场景复杂（物体多）→ 简短播报
        if ctx.object_count > 5:
            score += 0.3
        elif ctx.object_count > 3:
            score += 0.15

        # 距离上次播报很近 → 简短播报
        if ctx.last_announce_interval < 3.0:
            score += 0.3
        elif ctx.last_announce_interval < 5.0:
            score += 0.15

        return min(1.0, score)


class PhraseModeStrategy(OutputModeStrategy):
    """
    短句模式策略（默认模式）

    适用场景：
    - 正常转头速度
    - 适中数量的物体（2-5个）
    - 正常播报间隔（3-6秒）

    输出示例："5点方向约4步有床，从左侧绕开"
    """

    def decide(self, ctx: Context) -> float:
        score = 0.5  # 基础分（作为默认模式）

        # 正常转头速度
        if 10 < abs(ctx.yaw_rate) <= 30:
            score += 0.2
        elif abs(ctx.yaw_rate) <= 10:
            score += 0.1

        # 正常数量物体
        if 2 <= ctx.object_count <= 5:
            score += 0.2
        elif ctx.object_count == 1:
            score += 0.1

        # 正常播报间隔
        if 3.0 <= ctx.last_announce_interval < 6.0:
            score += 0.1
        elif 6.0 <= ctx.last_announce_interval < 10.0:
            score += 0.05

        return min(1.0, score)


class ParagraphModeStrategy(OutputModeStrategy):
    """
    段落模式策略（详细模式）

    适用场景：
    - 静止或很慢转头（用户在仔细观察）
    - 物体少（可以详细描述每个物体）
    - 距离上次播报较久（用户需要完整信息更新）

    不适用场景：
    - 有高紧急度物体（紧急情况需要快速响应，不适合长篇描述）

    输出示例："当前处于室内环境。第1个物体：5点方向前方的床，距离约2.4米，建议从左侧绕开。第2个物体：..."
    """

    def decide(self, ctx: Context) -> float:
        score = 0.0

        # 静止或很慢转头 → 可以详细播报
        if abs(ctx.yaw_rate) < 5:
            score += 0.4
        elif abs(ctx.yaw_rate) < 10:
            score += 0.2

        # 物体少 → 可以详细描述
        if ctx.object_count <= 2:
            score += 0.3
        elif ctx.object_count <= 3:
            score += 0.15

        # 距离上次播报较久 → 可以详细播报
        if ctx.last_announce_interval >= 10.0:
            score += 0.3
        elif ctx.last_announce_interval >= 6.0:
            score += 0.15

        # 有高紧急度物体 → 不适合段落模式（减分）
        if ctx.has_high_urgency:
            score -= 0.3

        return max(0.0, min(1.0, score))


class OutputModeSelector:
    """
    输出模式选择器

    使用策略模式管理多种输出模式，根据上下文自动选择最佳模式。

    使用方法：
        selector = OutputModeSelector()
        mode = selector.select(Context(
            yaw_rate=20.0,
            object_count=3,
            has_high_urgency=False,
            last_announce_interval=5.0,
            user_preference="auto"
        ))
        # mode 将是 OutputMode.PHRASE（最适合的模式）
    """

    def __init__(self):
        self.strategies = {
            OutputMode.KEYWORD: KeywordModeStrategy(),
            OutputMode.PHRASE: PhraseModeStrategy(),
            OutputMode.PARAGRAPH: ParagraphModeStrategy(),
        }

    def select(self, ctx: Context) -> OutputMode:
        """
        根据上下文选择最佳输出模式

        Args:
            ctx: 决策上下文

        Returns:
            最佳输出模式（OutputMode 枚举值）
        """
        # 如果用户有固定偏好，优先使用
        pref = ctx.user_preference.lower().strip()
        if pref in ["keyword", "phrase", "paragraph"]:
            return OutputMode(pref)

        # 从环境变量读取用户偏好（作为全局默认值）
        env_pref = os.getenv("AIGLASS_OUTPUT_MODE_PREF", "auto").lower().strip()
        if env_pref in ["keyword", "phrase", "paragraph"]:
            return OutputMode(env_pref)

        # 计算各策略得分
        scores = {
            mode: strategy.decide(ctx)
            for mode, strategy in self.strategies.items()
        }

        # 选择得分最高的模式
        best_mode = max(scores, key=scores.get)

        # 调试日志（可选）
        if os.getenv("AIGLASS_DEBUG_OUTPUT_MODE", "0") == "1":
            print(f"[OutputMode] Scores: {[(m.value, round(s, 2)) for m, s in scores.items()]}, "
                  f"Selected: {best_mode.value}")

        return best_mode

    def get_scores(self, ctx: Context) -> Dict[OutputMode, float]:
        """
        获取所有模式的得分（用于调试）

        Args:
            ctx: 决策上下文

        Returns:
            模式到得分的字典
        """
        return {
            mode: strategy.decide(ctx)
            for mode, strategy in self.strategies.items()
        }


# 全局单例（便于复用）
_default_selector: Optional[OutputModeSelector] = None


def get_output_mode_selector() -> OutputModeSelector:
    """获取默认的输出模式选择器（单例模式）"""
    global _default_selector
    if _default_selector is None:
        _default_selector = OutputModeSelector()
    return _default_selector


def decide_output_mode(
    yaw_rate: float = 0.0,
    scene_type: str = "unknown",
    object_count: int = 0,
    has_high_urgency: bool = False,
    last_announce_interval: float = 10.0,
    user_preference: str = "auto"
) -> OutputMode:
    """
    便捷函数：根据参数快速决定输出模式

    Args:
        yaw_rate: 转头速度 (deg/s)
        scene_type: 场景类型
        object_count: 物体数量
        has_high_urgency: 是否有高紧急度物体
        last_announce_interval: 距离上次播报间隔（秒）
        user_preference: 用户偏好（keyword/phrase/paragraph/auto）

    Returns:
        最佳输出模式
    """
    ctx = Context(
        yaw_rate=yaw_rate,
        scene_type=scene_type,
        object_count=object_count,
        has_high_urgency=has_high_urgency,
        last_announce_interval=last_announce_interval,
        user_preference=user_preference
    )
    return get_output_mode_selector().select(ctx)


# 便捷函数：判断当前应该使用什么模式
def should_use_keyword_mode(ctx: Context) -> bool:
    """判断是否应该使用关键词模式"""
    return decide_output_mode_from_context(ctx) == OutputMode.KEYWORD


def should_use_paragraph_mode(ctx: Context) -> bool:
    """判断是否应该使用段落模式"""
    return decide_output_mode_from_context(ctx) == OutputMode.PARAGRAPH


def decide_output_mode_from_context(ctx: Context) -> OutputMode:
    """根据上下文决定输出模式"""
    return get_output_mode_selector().select(ctx)


if __name__ == "__main__":
    # 测试代码
    print("测试输出模式策略模块")
    print("=" * 50)

    selector = OutputModeSelector()

    test_cases = [
        ("快速转头", Context(yaw_rate=40, object_count=2, last_announce_interval=2.0)),
        ("静止观察", Context(yaw_rate=5, object_count=2, last_announce_interval=8.0)),
        ("正常行走", Context(yaw_rate=15, object_count=3, last_announce_interval=5.0)),
        ("复杂场景", Context(yaw_rate=20, object_count=6, last_announce_interval=3.0)),
        ("紧急情况", Context(yaw_rate=10, object_count=1, has_high_urgency=True, last_announce_interval=4.0)),
    ]

    for name, ctx in test_cases:
        mode = selector.select(ctx)
        scores = selector.get_scores(ctx)
        print(f"\n{name}:")
        print(f"  上下文: yaw={ctx.yaw_rate}, objects={ctx.object_count}, "
              f"urgent={ctx.has_high_urgency}, interval={ctx.last_announce_interval}")
        print(f"  得分: {[(m.value, round(s, 2)) for m, s in scores.items()]}")
        print(f"  选择: {mode.value}")
